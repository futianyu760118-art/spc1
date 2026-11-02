"""智能体中心 — 技能库管理端点（磁盘文件夹为准，支持 zip 导入/预览/启停/绑定）。"""

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.agent.routes import _capture, _err, _load_user, _ok
from app.core.audit import log_audit
from app.core.database import get_db
from app.core.security import PermissionChecker
from app.models.agent.skill import AgentSkill
from app.services.agent.errors import AgentError
from app.services.agent.skill_executors import executor_catalog
from app.services.agent.skills import (
    delete_imported_skill,
    get_skill_detail,
    import_skill_zip,
    list_skills,
    parse_skill_markdown,
    read_skill_text_file,
    sync_skills_from_disk,
    update_skill_status,
)

router = APIRouter()


class SkillParseIn(BaseModel):
    content: str = Field(min_length=1)


class SkillStatusIn(BaseModel):
    status: str = Field(min_length=1, max_length=16)


@router.get("/admin/skills")
async def admin_skills(
    keyword: str = "",
    status: str = "",
    source: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "read")),
):
    try:
        return _ok(await list_skills(
            db, keyword=keyword, status=status, source=source, page=page, page_size=page_size,
        ))
    except Exception as exc:
        return _capture(exc)


@router.get("/admin/skills/{skill_id}")
async def admin_skill_detail(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "read")),
):
    try:
        return _ok(await get_skill_detail(db, skill_id))
    except AgentError as exc:
        return _err(exc.message, exc.status_code)
    except Exception as exc:
        return _capture(exc)


@router.get("/admin/skills/{skill_id}/file")
async def admin_skill_file(
    skill_id: int,
    path: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "read")),
):
    try:
        skill = await db.get(AgentSkill, skill_id)
        if skill is None:
            return _err("技能不存在", 404)
        return _ok(read_skill_text_file(skill, path))
    except AgentError as exc:
        return _err(exc.message, exc.status_code)
    except Exception as exc:
        return _capture(exc)


@router.post("/admin/skills/parse")
async def parse_skill(
    body: SkillParseIn,
    current_user=Depends(PermissionChecker("ai.agent.admin", "update")),
):
    try:
        parsed = parse_skill_markdown(body.content)
        return _ok({
            "name": parsed.name,
            "description": parsed.description,
            "instructions": parsed.instructions,
            "executor_name": parsed.executor_name,
        })
    except AgentError as exc:
        return _err(exc.message, exc.status_code)


@router.post("/admin/skills/sync")
async def sync_skills(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "update")),
):
    try:
        operator = await _load_user(db, current_user)
        summary = await sync_skills_from_disk(db)
        await log_audit(
            db, "agent_skill", 0, "sync", field_name="磁盘扫描",
            new_value=f"同步 {summary.get('synced', 0)} 个，移除 {summary.get('removed', 0)} 个",
            operator=operator.username,
        )
        return _ok(summary, "已同步")
    except Exception as exc:
        return _capture(exc)


@router.post("/admin/skills/import")
async def import_skill(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "update")),
):
    try:
        operator = await _load_user(db, current_user)
        data = await file.read()
        result = await import_skill_zip(
            db, data, created_by_user_id=int(operator.id),
        )
        await log_audit(
            db, "agent_skill", result["id"], "import", field_name="skill_key",
            new_value=str(result["skill_key"])[:500], operator=operator.username,
        )
        return _ok(await get_skill_detail(db, result["id"]), "已导入")
    except AgentError as exc:
        return _err(exc.message, exc.status_code)
    except Exception as exc:
        return _capture(exc)


@router.put("/admin/skills/{skill_id}/status")
async def update_status(
    skill_id: int,
    body: SkillStatusIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "update")),
):
    try:
        operator = await _load_user(db, current_user)
        skill = await update_skill_status(db, skill_id, body.status)
        await log_audit(
            db, "agent_skill", skill_id, "update", field_name="status",
            new_value=body.status, operator=operator.username,
        )
        return _ok(skill, "已保存")
    except AgentError as exc:
        return _err(exc.message, exc.status_code)
    except Exception as exc:
        return _capture(exc)


@router.delete("/admin/skills/{skill_id}")
async def delete_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(PermissionChecker("ai.agent.admin", "update")),
):
    try:
        operator = await _load_user(db, current_user)
        result = await delete_imported_skill(db, skill_id)
        await log_audit(
            db, "agent_skill", result["id"], "delete", field_name="skill_key",
            new_value=str(result["skill_key"])[:500], operator=operator.username,
        )
        return _ok(result, "已删除")
    except AgentError as exc:
        return _err(exc.message, exc.status_code)
    except Exception as exc:
        return _capture(exc)


@router.get("/admin/skill-executors")
async def admin_skill_executors(
    current_user=Depends(PermissionChecker("ai.agent.admin", "read")),
):
    return _ok({"items": executor_catalog()})
