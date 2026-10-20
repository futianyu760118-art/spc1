"""Router factory for shared business document ledgers."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.common.business_document import (
    BusinessDocument,
    BusinessDocumentFieldConfig,
    BusinessDocumentVersion,
)
from app.schemas.business_document import (
    BusinessDocumentCreate,
    BusinessDocumentFieldConfigCreate,
    BusinessDocumentFieldConfigOut,
    BusinessDocumentFieldConfigUpdate,
    BusinessDocumentOut,
    BusinessDocumentUpdate,
    BusinessDocumentVersionCreate,
    BusinessDocumentVersionOut,
)
from app.schemas.common import PageResult, ResponseModel
from app.services.common.business_document_fields import (
    WIDGETS,
    generate_field_key,
    normalize_options,
    validate_custom_fields,
)
from app.services.common.file_service import FileService


def _attachment_keys(attachments) -> list[str]:
    return [a.get("key") for a in (attachments or []) if isinstance(a, dict) and a.get("key")]


def create_business_document_router(doc_type: str, permission: str) -> APIRouter:
    router = APIRouter()

    async def _field_configs(db: AsyncSession) -> list[BusinessDocumentFieldConfig]:
        result = await db.execute(
            select(BusinessDocumentFieldConfig)
            .where(BusinessDocumentFieldConfig.doc_type == doc_type)
            .order_by(
                BusinessDocumentFieldConfig.sort_order.asc(),
                BusinessDocumentFieldConfig.id.asc(),
            )
        )
        return list(result.scalars().all())

    async def _get_field_config(
        db: AsyncSession, config_id: int
    ) -> BusinessDocumentFieldConfig | None:
        return (await db.execute(
            select(BusinessDocumentFieldConfig).where(
                BusinessDocumentFieldConfig.id == config_id,
                BusinessDocumentFieldConfig.doc_type == doc_type,
            )
        )).scalar_one_or_none()

    async def _ensure_label_unique(
        db: AsyncSession, label: str, exclude_id: int | None = None
    ) -> None:
        conditions = [
            BusinessDocumentFieldConfig.doc_type == doc_type,
            BusinessDocumentFieldConfig.label == label,
        ]
        if exclude_id is not None:
            conditions.append(BusinessDocumentFieldConfig.id != exclude_id)
        duplicate = await db.execute(
            select(BusinessDocumentFieldConfig.id).where(*conditions)
        )
        if duplicate.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="字段名称已存在")

    @router.get("/field-configs", response_model=ResponseModel[list[BusinessDocumentFieldConfigOut]])
    async def list_field_configs(
        current_user: dict = Depends(PermissionChecker(permission, "read")),
        db: AsyncSession = Depends(get_db),
    ):
        configs = await _field_configs(db)
        return ResponseModel(
            data=[BusinessDocumentFieldConfigOut.model_validate(config) for config in configs]
        )

    @router.post("/field-configs", response_model=ResponseModel[BusinessDocumentFieldConfigOut])
    async def create_field_config(
        data: BusinessDocumentFieldConfigCreate,
        current_user: dict = Depends(PermissionChecker(permission, "update")),
        db: AsyncSession = Depends(get_db),
    ):
        if data.widget not in WIDGETS:
            raise HTTPException(status_code=400, detail="不支持的字段类型")
        label = data.label.strip()
        if not label:
            raise HTTPException(status_code=400, detail="字段名称不能为空")

        await _ensure_label_unique(db, label)

        field_key = ""
        for _ in range(5):
            candidate = generate_field_key()
            exists = await db.execute(
                select(BusinessDocumentFieldConfig.id).where(
                    BusinessDocumentFieldConfig.doc_type == doc_type,
                    BusinessDocumentFieldConfig.field_key == candidate,
                )
            )
            if not exists.scalar_one_or_none():
                field_key = candidate
                break
        if not field_key:
            raise HTTPException(status_code=500, detail="字段标识生成失败，请重试")

        config = BusinessDocumentFieldConfig(
            doc_type=doc_type,
            field_key=field_key,
            label=label,
            widget=data.widget,
            required=data.required,
            show_in_list=data.show_in_list,
            options=normalize_options(data.widget, data.options),
            sort_order=data.sort_order,
        )
        try:
            db.add(config)
            await db.flush()
            await log_audit(
                db,
                "business_document_field_config",
                config.id,
                "create",
                field_name=doc_type,
                operator=current_user["username"],
            )
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status_code=400, detail="字段名称或标识已存在") from None
        await db.refresh(config)
        return ResponseModel(data=BusinessDocumentFieldConfigOut.model_validate(config))

    @router.put("/field-configs/{config_id}", response_model=ResponseModel[BusinessDocumentFieldConfigOut])
    async def update_field_config(
        config_id: int,
        data: BusinessDocumentFieldConfigUpdate,
        current_user: dict = Depends(PermissionChecker(permission, "update")),
        db: AsyncSession = Depends(get_db),
    ):
        config = await _get_field_config(db, config_id)
        if not config:
            raise HTTPException(status_code=404, detail="字段配置不存在")

        update_data = data.model_dump(exclude_unset=True)
        null_error_labels = {"required": "必填", "show_in_list": "列表显示"}
        for field, field_label in null_error_labels.items():
            if field in update_data and update_data[field] is None:
                raise HTTPException(status_code=400, detail=f"「{field_label}」不能为空")
        if update_data.get("sort_order") is None and "sort_order" in update_data:
            update_data["sort_order"] = 0
        if "label" in update_data:
            label = (update_data["label"] or "").strip()
            if not label:
                raise HTTPException(status_code=400, detail="字段名称不能为空")
            await _ensure_label_unique(db, label, config_id)
            update_data["label"] = label
        if "options" in update_data:
            update_data["options"] = normalize_options(config.widget, update_data["options"])

        try:
            if update_data:
                await log_audit(
                    db,
                    "business_document_field_config",
                    config.id,
                    "update",
                    old_obj=config,
                    update_data=update_data,
                    operator=current_user["username"],
                )
                for field, value in update_data.items():
                    setattr(config, field, value)
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status_code=400, detail="字段名称或标识已存在") from None
        await db.refresh(config)
        return ResponseModel(data=BusinessDocumentFieldConfigOut.model_validate(config))

    @router.delete("/field-configs/{config_id}", response_model=ResponseModel[dict])
    async def delete_field_config(
        config_id: int,
        current_user: dict = Depends(PermissionChecker(permission, "update")),
        db: AsyncSession = Depends(get_db),
    ):
        config = await _get_field_config(db, config_id)
        if not config:
            raise HTTPException(status_code=404, detail="字段配置不存在")

        field_key = config.field_key
        await db.delete(config)
        await db.execute(
            text(
                "UPDATE business_document "
                "SET custom_fields = custom_fields - :field_key "
                "WHERE doc_type = :doc_type AND custom_fields IS NOT NULL "
                "AND jsonb_exists(custom_fields, :field_key)"
            ),
            {"field_key": field_key, "doc_type": doc_type},
        )
        await log_audit(
            db,
            "business_document_field_config",
            config_id,
            "delete",
            field_name=doc_type,
            operator=current_user["username"],
        )
        await db.commit()
        return ResponseModel(data={"deleted": config_id})

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

        configs = await _field_configs(db)
        custom_fields = validate_custom_fields(configs, data.custom_fields)

        document = BusinessDocument(
            doc_type=doc_type,
            code=data.code,
            title=data.title,
            applicable_product=data.applicable_product,
            applicable_order=data.applicable_order,
            applicable_process=data.applicable_process,
            custom_fields=custom_fields,
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
        if "custom_fields" in update_data:
            configs = await _field_configs(db)
            update_data["custom_fields"] = validate_custom_fields(
                configs,
                update_data["custom_fields"],
                document.custom_fields or {},
            )
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
