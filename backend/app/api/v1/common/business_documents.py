"""Router factory for shared business document ledgers."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.common.business_document import BusinessDocument, BusinessDocumentVersion
from app.schemas.business_document import (
    BusinessDocumentCreate,
    BusinessDocumentOut,
    BusinessDocumentUpdate,
    BusinessDocumentVersionCreate,
    BusinessDocumentVersionOut,
)
from app.schemas.common import PageResult, ResponseModel
from app.services.common.file_service import FileService


def _attachment_keys(attachments) -> list[str]:
    return [a.get("key") for a in (attachments or []) if isinstance(a, dict) and a.get("key")]


def create_business_document_router(doc_type: str, permission: str) -> APIRouter:
    router = APIRouter()

    @router.get("", response_model=ResponseModel[PageResult[BusinessDocumentOut]])
    async def list_documents(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=200),
        status: Optional[str] = Query(None),
        keyword: Optional[str] = Query(None),
        current_user: dict = Depends(PermissionChecker(permission, "read")),
        db: AsyncSession = Depends(get_db),
    ):
        conditions = [BusinessDocument.doc_type == doc_type, BusinessDocument.is_deleted == 0]
        if status:
            statuses = [s.strip() for s in status.split(",") if s.strip()]
            if statuses:
                conditions.append(BusinessDocument.status.in_(statuses))
        if keyword:
            like = f"%{keyword}%"
            conditions.append(
                or_(
                    BusinessDocument.code.ilike(like),
                    BusinessDocument.title.ilike(like),
                    BusinessDocument.applicable_product.ilike(like),
                    BusinessDocument.applicable_order.ilike(like),
                    BusinessDocument.applicable_process.ilike(like),
                )
            )

        total = (await db.execute(select(func.count(BusinessDocument.id)).where(*conditions))).scalar() or 0
        result = await db.execute(
            select(BusinessDocument)
            .where(*conditions)
            .order_by(BusinessDocument.updated_at.desc(), BusinessDocument.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = [BusinessDocumentOut.model_validate(row) for row in result.scalars().all()]
        return ResponseModel(data=PageResult(total=total, page=page, page_size=page_size, items=items))

    @router.post("", response_model=ResponseModel[BusinessDocumentOut])
    async def create_document(
        data: BusinessDocumentCreate,
        current_user: dict = Depends(PermissionChecker(permission, "create")),
        db: AsyncSession = Depends(get_db),
    ):
        exists = await db.execute(
            select(BusinessDocument.id).where(
                BusinessDocument.doc_type == doc_type,
                BusinessDocument.code == data.code,
                BusinessDocument.is_deleted == 0,
            )
        )
        if exists.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="资料编码已存在")

        document = BusinessDocument(
            doc_type=doc_type,
            code=data.code,
            title=data.title,
            applicable_product=data.applicable_product,
            applicable_order=data.applicable_order,
            applicable_process=data.applicable_process,
            current_version=data.version_no,
            status="draft",
            created_by=current_user["username"],
        )
        db.add(document)
        await db.flush()

        version = BusinessDocumentVersion(
            document_id=document.id,
            version_no=data.version_no,
            content=data.content,
            attachments=data.attachments or [],
            status="draft",
            effective_date=data.effective_date,
            created_by=current_user["username"],
        )
        db.add(version)
        await db.flush()
        await FileService(db).attach(
            _attachment_keys(data.attachments),
            doc_type,
            f"business_document_version:{version.id}",
        )
        await log_audit(db, "business_document", document.id, "create", field_name=doc_type, operator=current_user["username"])
        await db.commit()
        await db.refresh(document)
        return ResponseModel(data=BusinessDocumentOut.model_validate(document))

    @router.put("/{document_id}", response_model=ResponseModel[BusinessDocumentOut])
    async def update_document(
        document_id: int,
        data: BusinessDocumentUpdate,
        current_user: dict = Depends(PermissionChecker(permission, "update")),
        db: AsyncSession = Depends(get_db),
    ):
        document = (await db.execute(
            select(BusinessDocument).where(
                BusinessDocument.id == document_id,
                BusinessDocument.doc_type == doc_type,
                BusinessDocument.is_deleted == 0,
            )
        )).scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=404, detail="资料不存在")

        update_data = data.model_dump(exclude_unset=True)
        await log_audit(db, "business_document", document.id, "update", old_obj=document, update_data=update_data, operator=current_user["username"])
        for field, value in update_data.items():
            setattr(document, field, value)
        await db.commit()
        await db.refresh(document)
        return ResponseModel(data=BusinessDocumentOut.model_validate(document))

    @router.delete("/{document_id}", response_model=ResponseModel[dict])
    async def delete_document(
        document_id: int,
        current_user: dict = Depends(PermissionChecker(permission, "delete")),
        db: AsyncSession = Depends(get_db),
    ):
        document = (await db.execute(
            select(BusinessDocument).where(
                BusinessDocument.id == document_id,
                BusinessDocument.doc_type == doc_type,
                BusinessDocument.is_deleted == 0,
            )
        )).scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=404, detail="资料不存在")

        document.is_deleted = 1
        await log_audit(
            db,
            "business_document",
            document.id,
            "delete",
            field_name="is_deleted",
            old_value="0",
            new_value="1",
            operator=current_user["username"],
        )
        await db.commit()
        return ResponseModel(data={"deleted": document_id})

    @router.post("/{document_id}/publish", response_model=ResponseModel[BusinessDocumentOut])
    async def publish_document(
        document_id: int,
        current_user: dict = Depends(PermissionChecker(permission, "update")),
        db: AsyncSession = Depends(get_db),
    ):
        document = (await db.execute(
            select(BusinessDocument).where(
                BusinessDocument.id == document_id,
                BusinessDocument.doc_type == doc_type,
                BusinessDocument.is_deleted == 0,
            )
        )).scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=404, detail="资料不存在")
        if document.status != "draft":
            raise HTTPException(status_code=400, detail="仅草稿状态的资料可以发布")

        document.status = "published"
        current_ver = (await db.execute(
            select(BusinessDocumentVersion).where(
                BusinessDocumentVersion.document_id == document_id,
                BusinessDocumentVersion.version_no == document.current_version,
            )
        )).scalar_one_or_none()
        if current_ver and current_ver.status != "published":
            current_ver.status = "published"
            current_ver.published_at = datetime.utcnow()
            current_ver.published_by = current_user["username"]

        await log_audit(
            db,
            "business_document",
            document.id,
            "update",
            field_name="status",
            old_value="draft",
            new_value="published",
            operator=current_user["username"],
        )
        await db.commit()
        await db.refresh(document)
        return ResponseModel(data=BusinessDocumentOut.model_validate(document))

    @router.post("/{document_id}/archive", response_model=ResponseModel[BusinessDocumentOut])
    async def archive_document(
        document_id: int,
        current_user: dict = Depends(PermissionChecker(permission, "update")),
        db: AsyncSession = Depends(get_db),
    ):
        document = (await db.execute(
            select(BusinessDocument).where(
                BusinessDocument.id == document_id,
                BusinessDocument.doc_type == doc_type,
                BusinessDocument.is_deleted == 0,
            )
        )).scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=404, detail="资料不存在")
        if document.status != "published":
            raise HTTPException(status_code=400, detail="仅已发布的资料可以归档")

        old_status = document.status
        document.status = "archived"
        await log_audit(
            db,
            "business_document",
            document.id,
            "update",
            field_name="status",
            old_value=old_status,
            new_value="archived",
            operator=current_user["username"],
        )
        await db.commit()
        await db.refresh(document)
        return ResponseModel(data=BusinessDocumentOut.model_validate(document))

    @router.get("/{document_id}/versions", response_model=ResponseModel[list[BusinessDocumentVersionOut]])
    async def list_versions(
        document_id: int,
        current_user: dict = Depends(PermissionChecker(permission, "read")),
        db: AsyncSession = Depends(get_db),
    ):
        document = (await db.execute(
            select(BusinessDocument.id).where(
                BusinessDocument.id == document_id,
                BusinessDocument.doc_type == doc_type,
                BusinessDocument.is_deleted == 0,
            )
        )).scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=404, detail="资料不存在")

        result = await db.execute(
            select(BusinessDocumentVersion)
            .where(BusinessDocumentVersion.document_id == document_id)
            .order_by(BusinessDocumentVersion.created_at.desc(), BusinessDocumentVersion.id.desc())
        )
        return ResponseModel(data=[BusinessDocumentVersionOut.model_validate(row) for row in result.scalars().all()])

    @router.post("/{document_id}/versions", response_model=ResponseModel[BusinessDocumentVersionOut])
    async def publish_version(
        document_id: int,
        data: BusinessDocumentVersionCreate,
        current_user: dict = Depends(PermissionChecker(permission, "update")),
        db: AsyncSession = Depends(get_db),
    ):
        document = (await db.execute(
            select(BusinessDocument).where(
                BusinessDocument.id == document_id,
                BusinessDocument.doc_type == doc_type,
                BusinessDocument.is_deleted == 0,
            )
        )).scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=404, detail="资料不存在")
        if document.status != "published":
            raise HTTPException(status_code=400, detail="仅已发布的资料可以发新版本")

        exists = await db.execute(
            select(BusinessDocumentVersion.id).where(
                BusinessDocumentVersion.document_id == document_id,
                BusinessDocumentVersion.version_no == data.version_no,
            )
        )
        if exists.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="版本号已存在")

        version = BusinessDocumentVersion(
            document_id=document_id,
            version_no=data.version_no,
            content=data.content,
            attachments=data.attachments or [],
            status="published",
            effective_date=data.effective_date,
            published_at=datetime.utcnow(),
            published_by=current_user["username"],
            created_by=current_user["username"],
        )
        db.add(version)
        document.current_version = data.version_no
        await db.flush()
        await FileService(db).attach(
            _attachment_keys(data.attachments),
            doc_type,
            f"business_document_version:{version.id}",
        )
        await log_audit(db, "business_document_version", version.id, "create", field_name=doc_type, operator=current_user["username"])
        await db.commit()
        await db.refresh(version)
        return ResponseModel(data=BusinessDocumentVersionOut.model_validate(version))

    return router
