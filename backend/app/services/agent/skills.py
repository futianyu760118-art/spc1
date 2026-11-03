"""智能体技能库：磁盘文件夹为事实来源，DB 仅做索引、启停与智能体绑定。"""

import asyncio
import hashlib
import io
import ipaddress
import json
import logging
import re
import shutil
import socket
import stat
import tempfile
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote, urljoin, urlparse

import httpx
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent.agent import Agent
from app.models.agent.skill import AgentSkill, AgentSkillBinding
from app.services.agent.errors import AgentError
from app.services.agent.skill_executors import get_skill_executor

logger = logging.getLogger(__name__)

SKILL_NAME_MAX = 64
SKILL_DESCRIPTION_MAX = 2000
SKILL_INSTRUCTIONS_MAX = 60000
SKILL_INDEX_DESCRIPTION_MAX = 300
MAX_SKILLS_PER_AGENT = 10
SKILL_STATUSES = ("active", "disabled")
SKILL_MD = "SKILL.md"
MAX_SKILL_MD_BYTES = 512 * 1024
MAX_SKILL_FILES = 500
MAX_SKILL_FILE_BYTES = 5 * 1024 * 1024
MAX_SKILL_TOTAL_BYTES = 20 * 1024 * 1024

SKILL_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_FRONTMATTER_RE = re.compile(r"^\ufeff?---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
_FRONTMATTER_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")

_BACKEND_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class TeamSkillInfo:
    """用户团队内一个可用技能的索引（不含正文，供提示词渐进披露）。"""

    skill_id: int
    name: str
    description: str
    agent_id: int
    agent_name: str
    has_executor: bool
    executor_name: Optional[str] = None
    has_scripts: bool = False


@dataclass(frozen=True)
class ParsedSkill:
    name: str
    description: str
    instructions: str
    executor_name: Optional[str] = None


@dataclass(frozen=True)
class SkillFile:
    path: str
    size: int
    kind: str


@dataclass(frozen=True)
class ParsedSkillFolder:
    skill_key: str
    name: str
    description: str
    instructions: str
    executor_name: Optional[str]
    content_hash: str
    files: List[SkillFile]
    folder: Path
    source: str = "builtin"


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1].strip()
    return value


def _read_frontmatter_value(lines: Sequence[str], start: int, inline: str) -> Tuple[str, int]:
    if inline[:1] in (">", "|"):
        block: List[str] = []
        index = start + 1
        while index < len(lines):
            line = lines[index]
            if line.strip() and not line.startswith((" ", "\t")):
                break
            block.append(line.strip())
            index += 1
        value = (" " if inline[0] == ">" else "\n").join(part for part in block if part)
        return value.strip(), index
    return _strip_quotes(inline), start + 1


def parse_skill_markdown(content: str) -> ParsedSkill:
    """解析标准 SKILL.md：YAML frontmatter + Markdown 正文。"""
    text = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise AgentError("SKILL.md 缺少 YAML frontmatter（需包含 name 与 description）")
    lines = match.group(1).split("\n")
    values: Dict[str, str] = {}
    index = 0
    while index < len(lines):
        key_match = _FRONTMATTER_KEY_RE.match(lines[index])
        if not key_match:
            index += 1
            continue
        key, inline = key_match.group(1), key_match.group(2)
        value, index = _read_frontmatter_value(lines, index, inline)
        values[key] = value

    name = (values.get("name") or "").strip()
    description = (values.get("description") or "").strip()
    instructions = text[match.end():].strip()
    executor_name = (values.get("executor") or values.get("executor_name") or "").strip() or None
    if not name:
        raise AgentError("SKILL.md frontmatter 缺少 name")
    if not description:
        raise AgentError("SKILL.md frontmatter 缺少 description")
    if not instructions:
        raise AgentError("SKILL.md 正文不能为空")
    if len(name) > SKILL_NAME_MAX:
        raise AgentError(f"技能名称超长：上限 {SKILL_NAME_MAX} 字符")
    if len(description) > SKILL_DESCRIPTION_MAX:
        raise AgentError(f"技能说明超长：上限 {SKILL_DESCRIPTION_MAX} 字符")
    if len(instructions) > SKILL_INSTRUCTIONS_MAX:
        raise AgentError(f"技能指令超长：上限 {SKILL_INSTRUCTIONS_MAX} 字符")
    return ParsedSkill(
        name=name, description=description, instructions=instructions,
        executor_name=executor_name,
    )


def builtin_skills_root() -> Path:
    value = (get_settings().SKILLS_DIR or "").strip()
    return Path(value).expanduser() if value else _BACKEND_ROOT / "skills"


def imported_skills_root() -> Path:
    value = (get_settings().SKILLS_IMPORT_DIR or "").strip()
    return Path(value).expanduser() if value else _BACKEND_ROOT / "skills-imported"


def skill_roots() -> List[Tuple[str, Path]]:
    return [("builtin", builtin_skills_root()), ("imported", imported_skills_root())]


def _root_for_source(source: str) -> Path:
    return imported_skills_root() if source == "imported" else builtin_skills_root()


def _folder_for_row(skill: AgentSkill) -> Path:
    if not skill.skill_key:
        raise AgentError("技能缺少文件夹标识，请重新同步技能目录")
    root = _root_for_source(skill.source or "builtin").resolve()
    folder = (root / skill.skill_key).resolve()
    if not folder.is_relative_to(root):
        raise AgentError("技能路径非法")
    return folder


def _skill_file_kind(relative_path: str) -> str:
    if relative_path == SKILL_MD:
        return "skill"
    if relative_path.startswith("scripts/"):
        return "script"
    if relative_path.startswith("references/"):
        return "reference"
    if relative_path.startswith("assets/"):
        return "asset"
    return "file"


def collect_skill_files(folder: Path) -> List[SkillFile]:
    files: List[SkillFile] = []
    total_bytes = 0
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise AgentError(f"技能文件夹不允许符号链接：{path.name}")
        if path.is_dir():
            continue
        relative = path.relative_to(folder).as_posix()
        size = path.stat().st_size
        if size > MAX_SKILL_FILE_BYTES:
            raise AgentError(f"技能文件过大：{relative}（上限 {MAX_SKILL_FILE_BYTES} 字节）")
        total_bytes += size
        if total_bytes > MAX_SKILL_TOTAL_BYTES:
            raise AgentError(f"技能文件夹过大：上限 {MAX_SKILL_TOTAL_BYTES} 字节")
        files.append(SkillFile(path=relative, size=size, kind=_skill_file_kind(relative)))
        if len(files) > MAX_SKILL_FILES:
            raise AgentError(f"技能文件过多：上限 {MAX_SKILL_FILES} 个")
    return files


def scan_skill_folder(folder: Path, *, skill_key: Optional[str] = None) -> ParsedSkillFolder:
    key = (skill_key or folder.name).strip()
    if not SKILL_KEY_RE.match(key):
        raise AgentError(
            "技能文件夹名必须是 slug（小写字母/数字开头，仅含小写字母、数字、._-，最长 128 字符）"
        )
    skill_md = folder / SKILL_MD
    if not skill_md.is_file():
        raise AgentError("技能文件夹缺少 SKILL.md")
    raw = skill_md.read_bytes()
    if len(raw) > MAX_SKILL_MD_BYTES:
        raise AgentError(f"SKILL.md 过大：上限 {MAX_SKILL_MD_BYTES} 字节")
    parsed = parse_skill_markdown(raw.decode("utf-8", errors="replace"))
    files = collect_skill_files(folder)
    return ParsedSkillFolder(
        skill_key=key,
        name=parsed.name,
        description=parsed.description,
        instructions=parsed.instructions,
        executor_name=parsed.executor_name,
        content_hash=hashlib.sha256(raw).hexdigest(),
        files=files,
        folder=folder,
    )


async def sync_skills_from_disk(
    db: AsyncSession, *, created_by_user_id: Optional[int] = None
) -> Dict[str, Any]:
    """扫描内置/导入根目录，upsert 索引并删除已消失技能；根目录不可用时保留该来源。"""
    discovered: Dict[str, ParsedSkillFolder] = {}
    available_sources = set()
    errors: List[str] = []

    for source, root in skill_roots():
        if not root.is_dir():
            # 目录不可用（未创建/挂载失败）时保留该来源的索引，避免误删。
            # 导入目录首次导入时才创建，缺失不算同步错误。
            logger.warning("[skills] 技能目录不存在，保留该来源索引：%s", root)
            if source == "builtin":
                errors.append(f"内置技能目录不存在：{root}")
            continue
        available_sources.add(source)
        for child in sorted(root.iterdir(), key=lambda item: item.name):
            if child.name.startswith(".") or not child.is_dir():
                continue
            if not (child / SKILL_MD).is_file():
                continue
            try:
                parsed = scan_skill_folder(child)
            except AgentError as exc:
                errors.append(f"{child.name}: {exc.message}")
                logger.warning("[skills] 跳过无效技能 %s: %s", child, exc.message)
                continue
            existing = discovered.get(parsed.skill_key)
            if existing is not None and existing.source == "imported" and source == "builtin":
                continue
            discovered[parsed.skill_key] = replace(parsed, source=source)

    filtered: Dict[str, ParsedSkillFolder] = {}
    seen_names: Dict[str, str] = {}
    for key, parsed in discovered.items():
        owner = seen_names.get(parsed.name)
        if owner is not None:
            errors.append(f"{key}: 与技能 {owner} 同名（{parsed.name}），已跳过")
            continue
        seen_names[parsed.name] = key
        filtered[key] = parsed
    discovered = filtered

    rows = (await db.execute(select(AgentSkill))).scalars().all()
    removed = 0

    # 先清理旧 DB-only 行与已消失技能，避免新增同技能时撞 name 唯一约束
    for row in rows:
        if not row.skill_key:
            await db.delete(row)
            removed += 1
            continue
        if row.source in available_sources and row.skill_key not in discovered:
            await db.delete(row)
            removed += 1
    rows = [row for row in rows if row.skill_key and row.skill_key in discovered]
    rows_by_key = {row.skill_key: row for row in rows}
    name_owner = {row.name: row.skill_key for row in rows}

    for key, parsed in discovered.items():
        owner = name_owner.get(parsed.name)
        if owner is not None and owner != key:
            errors.append(f"{key}: 与已索引技能 {owner} 同名（{parsed.name}），已跳过")
            continue
        row = rows_by_key.get(key)
        if row is None:
            db.add(AgentSkill(
                skill_key=key,
                name=parsed.name,
                description=parsed.description,
                instructions=parsed.instructions,
                executor_name=parsed.executor_name,
                source=parsed.source,
                content_hash=parsed.content_hash,
                file_count=len(parsed.files),
                has_scripts=any(item.kind == "script" for item in parsed.files),
                status="active",
                created_by_user_id=created_by_user_id,
            ))
        else:
            row.name = parsed.name
            row.description = parsed.description
            row.instructions = parsed.instructions
            row.executor_name = parsed.executor_name
            row.source = parsed.source
            row.content_hash = parsed.content_hash
            row.file_count = len(parsed.files)
            row.has_scripts = any(item.kind == "script" for item in parsed.files)
        name_owner[parsed.name] = key

    await db.flush()
    return {"synced": len(discovered), "removed": removed, "errors": errors}


async def list_team_skill_briefs(
    db: AsyncSession, agent_ids: Iterable[int]
) -> List[TeamSkillInfo]:
    ids = sorted({int(agent_id) for agent_id in agent_ids})
    if not ids:
        return []
    rows = (await db.execute(
        select(AgentSkillBinding.agent_id, Agent.display_name, AgentSkill)
        .join(Agent, Agent.id == AgentSkillBinding.agent_id)
        .join(AgentSkill, AgentSkill.id == AgentSkillBinding.skill_id)
        .where(
            AgentSkillBinding.agent_id.in_(ids),
            AgentSkill.status == "active",
        )
        .order_by(AgentSkill.id.asc())
    )).all()
    return [
        TeamSkillInfo(
            skill_id=int(skill.id),
            name=skill.name,
            description=skill.description,
            agent_id=int(agent_id),
            agent_name=agent_name,
            has_executor=bool(skill.executor_name),
            executor_name=skill.executor_name,
            has_scripts=bool(skill.has_scripts),
        )
        for agent_id, agent_name, skill in rows
    ]


async def load_agent_skills(
    db: AsyncSession, agent_ids: Iterable[int], *, include_disabled: bool = False
) -> Dict[int, List[dict]]:
    ids = sorted({int(agent_id) for agent_id in agent_ids})
    result: Dict[int, List[dict]] = {agent_id: [] for agent_id in ids}
    if not ids:
        return result
    conditions = [AgentSkillBinding.agent_id.in_(ids)]
    if not include_disabled:
        conditions.append(AgentSkill.status == "active")
    rows = (await db.execute(
        select(AgentSkillBinding.agent_id, AgentSkill)
        .join(AgentSkill, AgentSkill.id == AgentSkillBinding.skill_id)
        .where(*conditions)
        .order_by(AgentSkill.id.asc())
    )).all()
    for agent_id, skill in rows:
        result[int(agent_id)].append({
            "id": int(skill.id),
            "skill_key": skill.skill_key,
            "name": skill.name,
            "description": skill.description,
            "executor_name": skill.executor_name,
            "source": skill.source,
            "status": skill.status,
            "has_scripts": bool(skill.has_scripts),
        })
    return result


async def get_skill_for_user(
    db: AsyncSession, skill_id: Any, user_context: Any
) -> AgentSkill:
    try:
        normalized = int(skill_id)
    except (TypeError, ValueError):
        raise AgentError("skill_id 必须是数字")
    brief = user_context.skill_by_id(normalized) if user_context is not None else None
    if brief is None:
        raise AgentError("技能不在当前团队的技能清单内")
    skill = await db.get(AgentSkill, normalized)
    if skill is None or skill.status != "active":
        raise AgentError("技能不可用（已停用或不存在）")
    return skill


def load_skill_content(skill: AgentSkill) -> ParsedSkillFolder:
    """从磁盘读取 SKILL.md 与文件清单；运行时不使用 DB 正文缓存。"""
    folder = _folder_for_row(skill)
    if not folder.is_dir():
        raise AgentError("技能文件夹不存在，请同步技能目录或删除索引", 404)
    return scan_skill_folder(folder, skill_key=skill.skill_key)


def read_skill_text_file(
    skill: AgentSkill, relative_path: str, *, max_bytes: Optional[int] = None
) -> Dict[str, Any]:
    """读取技能文件夹内文本文件；拒绝路径穿越、符号链接、二进制与超限文件。"""
    content = load_skill_content(skill)
    raw_path = (relative_path or "").strip().replace("\\", "/")
    if not raw_path:
        raise AgentError("文件路径不能为空")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or ".." in path.parts or ":" in raw_path or "\x00" in raw_path:
        raise AgentError("文件路径非法")
    folder = content.folder.resolve()
    candidate = (folder / Path(*path.parts)).resolve()
    if not candidate.is_relative_to(folder):
        raise AgentError("文件路径非法")
    if candidate.is_symlink() or not candidate.is_file():
        raise AgentError("文件不存在")
    limit = max_bytes if max_bytes is not None else int(get_settings().SKILL_FILE_PREVIEW_MAX_BYTES or 0)
    size = candidate.stat().st_size
    if limit and size > limit:
        raise AgentError(f"文件过大，无法读取：上限 {limit} 字节")
    data = candidate.read_bytes()
    if b"\x00" in data:
        raise AgentError("二进制文件不可读取")
    return {
        "path": path.as_posix(),
        "size": size,
        "content": data.decode("utf-8", errors="replace"),
    }


def package_skill_folder(skill: AgentSkill) -> bytes:
    """把技能文件夹打包成 zip（沙箱按请求接收，不共享技能目录）。"""
    content = load_skill_content(skill)
    folder = content.folder.resolve()
    buffer = io.BytesIO()
    total = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in content.files:
            path = (folder / item.path).resolve()
            if path.is_symlink() or not path.is_file() or not path.is_relative_to(folder):
                raise AgentError(f"技能文件非法：{item.path}")
            total += path.stat().st_size
            if total > MAX_SKILL_TOTAL_BYTES:
                raise AgentError(f"技能文件夹过大：上限 {MAX_SKILL_TOTAL_BYTES} 字节")
            archive.write(path, item.path)
    return buffer.getvalue()


async def validate_skill_ids(db: AsyncSession, skill_ids: Sequence[int]) -> List[int]:
    ids = list(dict.fromkeys(int(skill_id) for skill_id in (skill_ids or [])))
    if len(ids) > MAX_SKILLS_PER_AGENT:
        raise AgentError(f"每个智能体最多绑定 {MAX_SKILLS_PER_AGENT} 个技能")
    if ids:
        existing = (await db.execute(
            select(AgentSkill.id).where(AgentSkill.id.in_(ids))
        )).scalars().all()
        missing = sorted(set(ids) - {int(skill_id) for skill_id in existing})
        if missing:
            raise AgentError(f"技能不存在：{'、'.join(str(i) for i in missing)}")
    return ids


async def sync_agent_skill_bindings(
    db: AsyncSession, agent_id: int, skill_ids: Sequence[int]
) -> None:
    ids = await validate_skill_ids(db, skill_ids)
    await db.execute(delete(AgentSkillBinding).where(AgentSkillBinding.agent_id == int(agent_id)))
    for skill_id in ids:
        db.add(AgentSkillBinding(agent_id=int(agent_id), skill_id=int(skill_id)))
    await db.flush()


def _skill_brief(skill: AgentSkill, bound_count: int = 0) -> dict:
    try:
        folder_exists = _folder_for_row(skill).is_dir()
    except AgentError:
        folder_exists = False
    return {
        "id": int(skill.id),
        "skill_key": skill.skill_key,
        "name": skill.name,
        "description": skill.description,
        "executor_name": skill.executor_name,
        "executor_available": bool(
            skill.executor_name and get_skill_executor(skill.executor_name) is not None
        ),
        "source": skill.source,
        "status": skill.status,
        "file_count": int(skill.file_count or 0),
        "has_scripts": bool(skill.has_scripts),
        "folder_exists": folder_exists,
        "bound_agents_count": int(bound_count or 0),
        "created_at": skill.created_at.isoformat() if skill.created_at else None,
        "updated_at": skill.updated_at.isoformat() if skill.updated_at else None,
    }


async def list_skills(
    db: AsyncSession,
    *,
    keyword: str = "",
    status: str = "",
    source: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    conditions = []
    if keyword.strip():
        like = f"%{keyword.strip()}%"
        conditions.append(or_(
            AgentSkill.name.ilike(like),
            AgentSkill.description.ilike(like),
            AgentSkill.skill_key.ilike(like),
        ))
    if status:
        conditions.append(AgentSkill.status == status)
    if source:
        conditions.append(AgentSkill.source == source)
    total = int((await db.execute(
        select(func.count(AgentSkill.id)).where(*conditions)
    )).scalar() or 0)
    bound_count = (
        select(func.count(AgentSkillBinding.id))
        .where(AgentSkillBinding.skill_id == AgentSkill.id)
        .correlate(AgentSkill)
        .scalar_subquery()
    )
    rows = (await db.execute(
        select(AgentSkill, bound_count.label("bound_count"))
        .where(*conditions)
        .order_by(AgentSkill.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).all()
    return {
        "items": [_skill_brief(skill, count) for skill, count in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_skill_detail(db: AsyncSession, skill_id: int) -> dict:
    skill = await db.get(AgentSkill, int(skill_id))
    if skill is None:
        raise AgentError("技能不存在", 404)
    content = load_skill_content(skill)
    bound_count = int((await db.execute(
        select(func.count(AgentSkillBinding.id)).where(AgentSkillBinding.skill_id == skill.id)
    )).scalar() or 0)
    from app.services.agent.skill_sandbox import is_sandbox_enabled

    return {
        **_skill_brief(skill, bound_count),
        "instructions": content.instructions,
        "files": [
            {"path": item.path, "size": item.size, "kind": item.kind}
            for item in content.files
        ],
        "script_execution_available": is_sandbox_enabled(),
    }


async def update_skill_status(db: AsyncSession, skill_id: int, status: str) -> dict:
    if status not in SKILL_STATUSES:
        raise AgentError("status 只能为 active 或 disabled")
    skill = await db.get(AgentSkill, int(skill_id))
    if skill is None:
        raise AgentError("技能不存在", 404)
    skill.status = status
    await db.flush()
    await db.refresh(skill)
    return _skill_brief(skill)


async def delete_imported_skill(db: AsyncSession, skill_id: int) -> dict:
    skill = await db.get(AgentSkill, int(skill_id))
    if skill is None:
        raise AgentError("技能不存在", 404)
    if (skill.source or "builtin") != "imported":
        raise AgentError("内置技能不能删除；可在智能体中解绑或停用")
    folder = _folder_for_row(skill)
    import_root = imported_skills_root().resolve()
    if not folder.is_relative_to(import_root) or folder == import_root:
        raise AgentError("技能路径非法")
    try:
        if folder.exists():
            shutil.rmtree(folder)
    except OSError as exc:
        raise AgentError(f"删除技能文件夹失败：{exc}") from exc
    result = {"id": int(skill.id), "skill_key": skill.skill_key, "name": skill.name}
    await db.delete(skill)
    await db.flush()
    await sync_skills_from_disk(db)
    return result


def _normalize_skill_relative(name: str) -> str:
    raw = (name or "").replace("\\", "/")
    if not raw or "\x00" in raw:
        raise AgentError("文件路径不能为空")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or ":" in raw:
        raise AgentError(f"文件路径非法：{name}")
    return path.as_posix()


def _ensure_skill_frontmatter(data: bytes, name: str, description: str) -> bytes:
    """SkillHub 部分子技能没有 YAML frontmatter；补一个标准头后重新打包。"""
    try:
        source = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise AgentError("技能包不是有效 zip") from exc
    names = source.namelist()
    skill_md = "SKILL.md" if "SKILL.md" in names else next(
        (item for item in names if item.endswith("/SKILL.md") and item.count("/") == 1),
        None,
    )
    if not skill_md:
        raise AgentError("技能包缺少 SKILL.md")
    content = source.read(skill_md).decode("utf-8", errors="replace")
    if content.lstrip().startswith("---"):
        return data
    safe_description = (description or name).replace("\n", " ").strip()[:SKILL_DESCRIPTION_MAX]
    front = f"---\nname: {name}\ndescription: {safe_description}\n---\n\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            if info.is_dir():
                continue
            payload = front + content if info.filename == skill_md else source.read(info.filename)
            target.writestr(info.filename, payload)
    return buffer.getvalue()


def _normalize_zip_name(name: str) -> Optional[str]:
    raw = (name or "").replace("\\", "/")
    if not raw or "\x00" in raw:
        raise AgentError("压缩包包含非法文件名")
    while raw.startswith("./"):
        raw = raw[2:]
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or ":" in raw:
        raise AgentError(f"压缩包包含非法路径：{name}")
    if raw.startswith("__MACOSX/") or raw.endswith("/.DS_Store") or raw == ".DS_Store":
        return None
    return path.as_posix()


def _extract_skill_zip(data: bytes, target_dir: Path) -> Tuple[Path, str]:
    """解压一个技能包到 target_dir；返回 (技能文件夹, skill_key)。"""
    max_bytes = int(get_settings().SKILL_IMPORT_MAX_BYTES or MAX_SKILL_TOTAL_BYTES)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise AgentError("不是有效的 zip 文件") from exc

    infos = archive.infolist()
    if not infos:
        raise AgentError("zip 文件为空")
    if len(infos) > MAX_SKILL_FILES:
        raise AgentError(f"zip 文件过多：上限 {MAX_SKILL_FILES} 个")
    total_uncompressed = 0
    for info in infos:
        if info.flag_bits & 0x1:
            raise AgentError("不支持加密 zip")
        mode = info.external_attr >> 16
        if mode and stat.S_ISLNK(mode):
            raise AgentError("zip 内不允许符号链接")
        total_uncompressed += int(info.file_size)
        if total_uncompressed > max_bytes:
            raise AgentError(f"zip 解压后超过上限 {max_bytes} 字节")
        if int(info.file_size) > MAX_SKILL_FILE_BYTES:
            raise AgentError(f"zip 内单文件过大：{info.filename}")

    normalized: List[Tuple[zipfile.ZipInfo, str]] = []
    for info in infos:
        if info.is_dir():
            continue
        name = _normalize_zip_name(info.filename)
        if name is None:
            continue
        normalized.append((info, name))

    names = [name for _, name in normalized]
    if SKILL_MD in names:
        prefix = ""
    else:
        top_dirs = {name.split("/", 1)[0] for name in names if "/" in name}
        if len(top_dirs) != 1:
            raise AgentError("zip 内必须只包含一个技能文件夹")
        prefix = top_dirs.pop()
        if f"{prefix}/{SKILL_MD}" not in names:
            raise AgentError("技能文件夹缺少 SKILL.md")
        if not SKILL_KEY_RE.match(prefix):
            raise AgentError(
                "技能文件夹名必须是 slug（小写字母/数字开头，仅含小写字母、数字、._-）"
            )

    work = (target_dir / "package").resolve()
    work.mkdir(parents=True, exist_ok=True)
    for info, name in normalized:
        target = (work / name).resolve()
        if not target.is_relative_to(work):
            raise AgentError(f"压缩包包含非法路径：{name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, open(target, "wb") as destination:
            shutil.copyfileobj(source, destination, length=1024 * 1024)

    folder = (work / prefix).resolve() if prefix else work
    if not prefix:
        parsed = parse_skill_markdown(
            (folder / SKILL_MD).read_text(encoding="utf-8", errors="replace")
        )
        if not SKILL_KEY_RE.match(parsed.name):
            raise AgentError(
                "zip 根目录的 SKILL.md 需要把 name 写成 slug，或把文件放进同名文件夹后再打包"
            )
        skill_key = parsed.name
    else:
        skill_key = prefix
    return folder, skill_key


async def import_skill_zip(
    db: AsyncSession, data: bytes, *, created_by_user_id: Optional[int] = None
) -> dict:
    max_bytes = int(get_settings().SKILL_IMPORT_MAX_BYTES or MAX_SKILL_TOTAL_BYTES)
    if not data:
        raise AgentError("上传文件为空")
    if len(data) > max_bytes:
        raise AgentError(f"zip 文件过大：上限 {max_bytes} 字节")

    import_root = imported_skills_root().resolve()
    builtin_root = builtin_skills_root().resolve()
    import_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="spc-skill-import-") as tmp:
        folder, skill_key = _extract_skill_zip(data, Path(tmp))
        parsed = scan_skill_folder(folder, skill_key=skill_key)
        if parsed.executor_name and get_skill_executor(parsed.executor_name) is None:
            raise AgentError(f"未知执行器：{parsed.executor_name}")
        target = import_root / skill_key
        if target.exists() or (builtin_root / skill_key).exists():
            raise AgentError(f"技能文件夹已存在：{skill_key}")
        existing_name = (await db.execute(
            select(AgentSkill.id).where(AgentSkill.name == parsed.name)
        )).scalars().first()
        if existing_name:
            raise AgentError(f"已存在同名技能：{parsed.name}")
        shutil.move(str(folder), str(target))

    summary = await sync_skills_from_disk(db, created_by_user_id=created_by_user_id)
    row = (await db.execute(
        select(AgentSkill).where(AgentSkill.skill_key == skill_key)
    )).scalars().first()
    if row is None:
        raise AgentError("技能导入后同步失败：" + "；".join(summary.get("errors") or []))
    return {"id": int(row.id), "skill_key": skill_key, "sync": summary}


async def create_skill_from_content(
    db: AsyncSession,
    *,
    content: str,
    skill_key: str,
    files: Optional[Dict[str, str]] = None,
    allow_scripts: bool = False,
    created_by_user_id: Optional[int] = None,
) -> AgentSkill:
    """用助手生成的 SKILL.md 内容创建导入技能文件夹。"""
    key = (skill_key or "").strip()
    if not SKILL_KEY_RE.match(key):
        raise AgentError("skill_key 必须是 slug（小写字母/数字开头，仅含小写字母、数字、._-）")
    raw = (content or "").encode("utf-8")
    if not raw or len(raw) > MAX_SKILL_MD_BYTES:
        raise AgentError(f"SKILL.md 为空或过大（上限 {MAX_SKILL_MD_BYTES} 字节）")
    parsed = parse_skill_markdown(raw.decode("utf-8", errors="replace"))
    if parsed.executor_name and get_skill_executor(parsed.executor_name) is None:
        raise AgentError(f"未知执行器：{parsed.executor_name}")

    normalized_files: Dict[str, str] = {}
    total = 0
    for name, text in (files or {}).items():
        if not isinstance(text, str):
            raise AgentError("files 的值必须是文本")
        relative = _normalize_skill_relative(name)
        if relative == SKILL_MD:
            raise AgentError("files 不能包含 SKILL.md")
        if not allow_scripts and relative.startswith("scripts/"):
            raise AgentError("创建脚本文件需要显式 allow_scripts=true")
        data = text.encode("utf-8")
        total += len(data)
        if len(normalized_files) >= MAX_SKILL_FILES or total > MAX_SKILL_TOTAL_BYTES:
            raise AgentError("技能文件过多或过大")
        normalized_files[relative] = text

    import_root = imported_skills_root().resolve()
    builtin_root = builtin_skills_root().resolve()
    import_root.mkdir(parents=True, exist_ok=True)
    if (import_root / key).exists() or (builtin_root / key).exists():
        raise AgentError(f"技能文件夹已存在：{key}")
    existing_name = (await db.execute(
        select(AgentSkill.id).where(AgentSkill.name == parsed.name)
    )).scalars().first()
    if existing_name:
        raise AgentError(f"已存在同名技能：{parsed.name}")

    with tempfile.TemporaryDirectory(prefix="spc-skill-create-") as tmp:
        folder = Path(tmp) / key
        folder.mkdir(parents=True)
        (folder / SKILL_MD).write_text(content, encoding="utf-8")
        for relative, text in normalized_files.items():
            target = (folder / relative).resolve()
            if not target.is_relative_to(folder.resolve()):
                raise AgentError(f"文件路径非法：{relative}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        scan_skill_folder(folder, skill_key=key)
        target = import_root / key
        shutil.move(str(folder), str(target))

    await sync_skills_from_disk(db, created_by_user_id=created_by_user_id)
    row = (await db.execute(
        select(AgentSkill).where(AgentSkill.skill_key == key)
    )).scalars().first()
    if row is None:
        raise AgentError("技能创建后同步失败")
    return row


async def resolve_skill_for_manage(
    db: AsyncSession, *, skill_id: Optional[int] = None, skill_key: str = ""
) -> AgentSkill:
    key = (skill_key or "").strip()
    row = None
    if key:
        row = (await db.execute(
            select(AgentSkill).where(or_(
                AgentSkill.skill_key == key,
                AgentSkill.name == key,
            ))
        )).scalars().first()
    if row is None and skill_id is not None:
        row = await db.get(AgentSkill, int(skill_id))
    if row is None:
        raise AgentError("技能不存在", 404)
    return row


async def _pack_children_for_skill(skill: AgentSkill) -> List[str]:
    """优先读安装时写入的 _pack.json；旧安装回退到 SkillHub manifest。"""
    try:
        content = load_skill_content(skill)
        if any(item.path == "_pack.json" for item in content.files):
            payload = json.loads(read_skill_text_file(skill, "_pack.json")["content"])
            children = payload.get("children") or []
            return [str(item).strip() for item in children if str(item).strip()]
    except (AgentError, ValueError, TypeError):
        pass
    if not skill.skill_key:
        return []
    try:
        data = await _download_skill_zip(
            SKILLHUB_PACK_API.format(slug=quote(skill.skill_key, safe=""))
        )
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        children = manifest.get("skillSlugs") or []
        return [str(item).strip() for item in children if str(item).strip()]
    except Exception:
        return []


async def uninstall_skill_with_pack(db: AsyncSession, skill_id: int) -> dict:
    """卸载技能；若它是 SkillHub 专家包主技能，则连同已安装子技能一起卸载。"""
    skill = await db.get(AgentSkill, int(skill_id))
    if skill is None:
        raise AgentError("技能不存在", 404)
    if (skill.source or "builtin") != "imported":
        raise AgentError("内置技能不能卸载；可在智能体中解绑或停用")
    children = await _pack_children_for_skill(skill)
    removed: List[dict] = []
    skipped: List[dict] = []
    errors: List[str] = []
    for child_key in list(dict.fromkeys(children)):
        if child_key == skill.skill_key:
            continue
        child = (await db.execute(
            select(AgentSkill).where(AgentSkill.skill_key == child_key)
        )).scalars().first()
        if child is None or (child.source or "builtin") != "imported":
            skipped.append({"skill_key": child_key, "reason": "未找到导入技能"})
            continue
        try:
            result = await delete_imported_skill(db, int(child.id))
            removed.append(result)
        except AgentError as exc:
            errors.append(f"{child_key}: {exc.message}")
    try:
        result = await delete_imported_skill(db, int(skill.id))
        removed.append(result)
    except AgentError as exc:
        errors.append(f"{skill.skill_key}: {exc.message}")
    if not removed:
        raise AgentError("卸载失败：" + "；".join(errors or ["没有可卸载的技能"]))
    return {
        "removed": removed,
        "skipped": skipped,
        "errors": errors,
        "is_pack": bool(children),
    }


async def uninstall_skillhub_pack(db: AsyncSession, pack: str) -> dict:
    """按 SkillHub 专家包标识卸载：manifest.skillSlugs + 主技能，允许主技能已缺失。"""
    slug = (pack or "").strip()
    if not SKILL_KEY_RE.match(slug):
        raise AgentError("SkillHub 专家包标识必须是 slug")
    try:
        data = await _download_skill_zip(
            SKILLHUB_PACK_API.format(slug=quote(slug, safe=""))
        )
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    except (AgentError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        raise AgentError(f"无法获取专家包信息：{exc}") from exc
    child_slugs = manifest.get("skillSlugs") or []
    if not isinstance(child_slugs, list):
        child_slugs = []
    keys = [slug] + [str(item).strip() for item in child_slugs if str(item).strip()]
    removed: List[dict] = []
    skipped: List[dict] = []
    errors: List[str] = []
    for key in dict.fromkeys(keys):
        row = (await db.execute(
            select(AgentSkill).where(or_(
                AgentSkill.skill_key == key,
                AgentSkill.name == key,
            ))
        )).scalars().first()
        if row is None:
            skipped.append({"skill_key": key, "reason": "未安装"})
            continue
        if (row.source or "builtin") != "imported":
            skipped.append({"skill_key": key, "reason": "内置技能不可卸载"})
            continue
        try:
            result = await delete_imported_skill(db, int(row.id))
            removed.append(result)
        except AgentError as exc:
            errors.append(f"{key}: {exc.message}")
    if not removed:
        raise AgentError("专家包未安装或不存在：" + "；".join(errors or ["未找到相关技能"]))
    return {
        "pack": slug,
        "removed": removed,
        "skipped": skipped,
        "errors": errors,
        "is_pack": True,
    }


async def _validate_install_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise AgentError("技能安装 URL 必须是 HTTPS 公网地址")
    if parsed.username or parsed.password:
        raise AgentError("技能安装 URL 不能包含用户名/密码")
    if parsed.port not in (None, 443):
        raise AgentError("技能安装 URL 仅允许 443 端口")
    host = parsed.hostname.strip().lower()
    settings = get_settings()
    allowed = [
        item.strip().lower()
        for item in (settings.SKILL_INSTALL_ALLOWED_HOSTS or "").split(",")
        if item.strip()
    ]
    if allowed and not any(host == item or host.endswith("." + item) for item in allowed):
        raise AgentError(f"技能安装域名不在白名单：{host}")
    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise AgentError(f"技能安装域名解析失败：{host}") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved \
                or ip.is_multicast or ip.is_unspecified:
            raise AgentError("技能安装 URL 不能指向内网/回环地址")
    return url.strip()


async def _download_skill_zip(url: str) -> bytes:
    """安全下载 HTTPS zip：逐跳校验域名/IP、限制大小、拒绝非法重定向。"""
    settings = get_settings()
    max_bytes = int(settings.SKILL_IMPORT_MAX_BYTES or MAX_SKILL_TOTAL_BYTES)
    timeout_s = int(settings.SKILL_INSTALL_TIMEOUT_S or 30)
    chunks: List[bytes] = []
    total = 0
    current_url = (url or "").strip()
    try:
        async with httpx.AsyncClient(
            timeout=timeout_s, follow_redirects=False,
            headers={"User-Agent": "SPC-Skill-Installer/1.0"},
        ) as client:
            for _ in range(4):
                current_url = await _validate_install_url(current_url)
                async with client.stream("GET", current_url) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise AgentError("技能包下载重定向缺少 Location")
                        current_url = urljoin(current_url, location)
                        continue
                    if response.status_code != 200:
                        raise AgentError(f"技能包下载失败：HTTP {response.status_code}")
                    length = response.headers.get("content-length")
                    if length and int(length) > max_bytes:
                        raise AgentError(f"技能包过大：上限 {max_bytes} 字节")
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            raise AgentError(f"技能包过大：上限 {max_bytes} 字节")
                        chunks.append(chunk)
                    break
            else:
                raise AgentError("技能包下载重定向次数过多")
    except httpx.HTTPError as exc:
        raise AgentError(f"技能包下载失败：{str(exc)[:200]}") from exc
    if not chunks:
        raise AgentError("技能包为空")
    return b"".join(chunks)


async def install_skill_from_url(
    db: AsyncSession, url: str, *, created_by_user_id: Optional[int] = None
) -> dict:
    """从 HTTPS 公网 zip URL 安装单个技能。"""
    data = await _download_skill_zip(url)
    return await import_skill_zip(db, data, created_by_user_id=created_by_user_id)


SKILLHUB_PACK_API = "https://api.skillhub.cn/api/v1/skillsets/{slug}/download"
SKILLHUB_SKILL_API = "https://api.skillhub.cn/api/v1/download?slug={slug}"


async def install_skillhub_skill(
    db: AsyncSession, skill_key: str, *, created_by_user_id: Optional[int] = None
) -> dict:
    """安装 SkillHub 单个技能（支持 @scope/name 形式）。"""
    key = (skill_key or "").strip()
    if not key:
        raise AgentError("SkillHub 技能标识不能为空")
    data = await _download_skill_zip(
        SKILLHUB_SKILL_API.format(slug=quote(key, safe=""))
    )
    return await import_skill_zip(db, data, created_by_user_id=created_by_user_id)


async def _import_pack_child(
    db: AsyncSession, data: bytes, slug: str, meta: Dict[str, Any],
    created_by_user_id: Optional[int],
) -> dict:
    try:
        return await import_skill_zip(db, data, created_by_user_id=created_by_user_id)
    except AgentError as exc:
        if "缺少 YAML frontmatter" not in exc.message:
            raise
        description = str(meta.get("summary") or meta.get("displayName") or slug)
        fixed = _ensure_skill_frontmatter(data, slug, description)
        return await import_skill_zip(db, fixed, created_by_user_id=created_by_user_id)


async def install_skillhub_pack(
    db: AsyncSession, pack: str, *, created_by_user_id: Optional[int] = None
) -> dict:
    """按 SkillHub 专家包协议安装：主技能 identify.md + manifest.skillSlugs 子技能。"""
    slug = (pack or "").strip()
    if not SKILL_KEY_RE.match(slug):
        raise AgentError("SkillHub 专家包标识必须是 slug")
    pack_zip = await _download_skill_zip(SKILLHUB_PACK_API.format(slug=quote(slug, safe="")))
    try:
        archive = zipfile.ZipFile(io.BytesIO(pack_zip))
    except zipfile.BadZipFile as exc:
        raise AgentError("SkillHub 专家包不是有效 zip") from exc
    try:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    except (KeyError, ValueError) as exc:
        raise AgentError("SkillHub 专家包缺少 manifest.json") from exc

    installed: List[dict] = []
    skipped: List[dict] = []
    errors: List[str] = []

    child_slugs = manifest.get("skillSlugs") or []
    if not isinstance(child_slugs, list):
        child_slugs = []
    child_slugs = [str(item).strip() for item in child_slugs if str(item).strip()]
    sidecar = json.dumps(
        {"pack": slug, "children": child_slugs}, ensure_ascii=False,
    )

    contents: List[tuple] = []
    if "identify.md" in archive.namelist():
        contents.append((slug, archive.read("identify.md").decode("utf-8", errors="replace")))
    for name in archive.namelist():
        if name.startswith("skillsets/") and name.endswith(".md"):
            child_slug = name[len("skillsets/"):-len(".md")]
            if child_slug:
                contents.append((child_slug, archive.read(name).decode("utf-8", errors="replace")))

    for skill_key, content in contents:
        try:
            row = await create_skill_from_content(
                db, content=content, skill_key=skill_key,
                files={"_pack.json": sidecar} if skill_key == slug else None,
                created_by_user_id=created_by_user_id,
            )
            installed.append({"skill_id": int(row.id), "skill_key": row.skill_key, "name": row.name})
        except AgentError as exc:
            if "已存在" in exc.message:
                skipped.append({"skill_key": skill_key, "reason": exc.message})
            else:
                errors.append(f"{skill_key}: {exc.message}")
    skill_meta = {
        str(item.get("slug")): item
        for item in (manifest.get("skills") or [])
        if isinstance(item, dict) and item.get("slug")
    }
    for child_slug in child_slugs:
        child_slug = str(child_slug).strip()
        if not child_slug:
            continue
        try:
            data = await _download_skill_zip(
                SKILLHUB_SKILL_API.format(slug=quote(child_slug, safe=""))
            )
            result = await _import_pack_child(
                db, data, child_slug, skill_meta.get(child_slug) or {},
                created_by_user_id,
            )
            installed.append({
                "skill_id": result["id"], "skill_key": result["skill_key"],
                "name": child_slug, "source": "child",
            })
        except AgentError as exc:
            if "已存在" in exc.message:
                skipped.append({"skill_key": child_slug, "reason": exc.message})
            else:
                errors.append(f"{child_slug}: {exc.message}")
        except Exception as exc:
            errors.append(f"{child_slug}: {exc}")

    if not installed and not skipped:
        raise AgentError("SkillHub 专家包未安装任何技能：" + "；".join(errors or ["无子技能"]))
    return {
        "pack": slug,
        "installed": installed,
        "skipped": skipped,
        "errors": errors,
    }
