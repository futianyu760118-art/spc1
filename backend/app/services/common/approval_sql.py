"""审批中心 - SQL 接入业务的只读 SQL 校验 / 执行 / 行归一化。

管理员配置的取数 SQL 只允许单条只读查询：校验时剥离注释并把字符串字面量清空
（避免把数据值误判成关键字），执行时用子查询包一层强制 LIMIT 并设置 5s 语句超时。
字段映射把来源列映射到统一字段；`id` 必须是数字主键（全链路沿用整数 ID）。
"""

import re
from typing import Optional
from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

FETCH_LIMIT = 200
PREVIEW_LIMIT = 5
STATEMENT_TIMEOUT_MS = 5000

REQUIRED_MAPPINGS = ("id", "no", "title", "applicant", "submitted_at", "current_node")
OPTIONAL_MAPPINGS = ("summary", "amount")

IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

FIELD_LABELS = {
    "no": "单号", "title": "标题", "summary": "摘要", "applicant": "申请人",
    "submitted_at": "提交时间", "current_node": "当前节点", "amount": "金额",
}

_LEADING_OK = ("select", "with")
_FORBIDDEN = {
    "insert", "update", "delete", "drop", "alter", "create", "truncate", "grant", "revoke",
    "comment", "copy", "call", "merge", "vacuum", "analyze", "refresh", "reindex", "cluster",
    "set", "reset", "begin", "commit", "rollback", "savepoint", "lock", "notify", "listen",
    "unlisten", "prepare", "execute", "declare", "fetch", "move", "close", "discard", "into",
}
_WORD_RE = re.compile(r"[a-zA-Z_]+")


def _scan_sql(sql: str, *, blank_literals: bool) -> str:
    """剥离注释；blank_literals=True 时同时清空字符串字面量内容（供关键字校验）。"""
    out: list[str] = []
    i, n = 0, len(sql or "")
    in_single = False
    while i < n:
        ch = sql[i]
        if in_single:
            if blank_literals:
                if ch == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        i += 2
                        continue
                    in_single = False
                i += 1
                continue
            out.append(ch)
            if ch == "'":
                if i + 1 < n and sql[i + 1] == "'":
                    out.append("'")
                    i += 2
                    continue
                in_single = False
            i += 1
            continue
        if ch == "'":
            in_single = True
            if not blank_literals:
                out.append(ch)
            i += 1
            continue
        if sql.startswith("--", i):
            while i < n and sql[i] != "\n":
                i += 1
            continue
        if sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def strip_sql_comments(sql: str) -> str:
    """去掉行注释与块注释，保留字符串字面量（执行用）。"""
    return _scan_sql(sql, blank_literals=False)


def _check_text(sql: str) -> str:
    """校验用文本：去注释 + 字符串字面量内容清空（`'update'` 不该被当成关键字）。"""
    return _scan_sql(sql, blank_literals=True)


def validate_readonly_sql(sql_text: Optional[str]) -> Optional[str]:
    """返回错误信息；None 表示通过。"""
    code = _check_text(sql_text or "").strip()
    if not code:
        return "取数 SQL 不能为空"
    if ";" in code:
        return "只允许单条查询语句（不能包含分号）"
    first = _WORD_RE.match(code)
    if not first or first.group(0).lower() not in _LEADING_OK:
        return "只允许 SELECT / WITH 开头的只读查询"
    for word in set(_WORD_RE.findall(code.lower())):
        if word in _FORBIDDEN:
            return f"取数 SQL 不允许包含写操作或会话控制关键字：{word}"
    return None


def wrap_readonly_sql(sql_text: str, limit: int) -> str:
    """用子查询包一层强制 LIMIT（配置里已有 LIMIT/OFFSET 时也能限制返回行数）。"""
    inner = strip_sql_comments(sql_text).strip().rstrip(";")
    return f"SELECT * FROM (\n{inner}\n) AS approval_src LIMIT {int(limit)}"


async def _execute(db: AsyncSession, sql_text: str, limit: int):
    await db.execute(text(f"SET LOCAL statement_timeout = {int(STATEMENT_TIMEOUT_MS)}"))
    return await db.execute(text(wrap_readonly_sql(sql_text, limit)))


async def execute_readonly_sql(db: AsyncSession, sql_text: str, *, limit: int = FETCH_LIMIT) -> list[dict]:
    result = await _execute(db, sql_text, limit)
    return [dict(r._mapping) for r in result]


async def preview_readonly_sql(db: AsyncSession, sql_text: str, *, limit: int = PREVIEW_LIMIT) -> dict:
    result = await _execute(db, sql_text, limit)
    return {"columns": list(result.keys()), "rows": [dict(r._mapping) for r in result]}


def validate_field_mapping(mapping) -> Optional[str]:
    """返回错误信息；None 表示通过。必需字段缺一不可，空列名视为未映射。"""
    if not isinstance(mapping, dict):
        return "字段映射格式不正确"
    for key in REQUIRED_MAPPINGS:
        value = mapping.get(key)
        if not (isinstance(value, str) and value.strip()):
            return f"字段映射缺少必需字段：{key}"
    allowed = set(REQUIRED_MAPPINGS) | set(OPTIONAL_MAPPINGS)
    unknown = sorted(k for k in mapping if k not in allowed)
    if unknown:
        return f"字段映射包含未知字段：{', '.join(unknown)}"
    for key, value in mapping.items():
        if value is not None and not isinstance(value, str):
            return f"字段映射 {key} 的列名必须是字符串"
    return None


def pick_mapped_value(row: dict, mapping: dict, key: str):
    """按映射取来源列的值；未映射或缺列返回 None。"""
    column = mapping.get(key)
    if not column:
        return None
    return row.get(column.strip())


def normalize_sql_row(cfg: dict, row: dict) -> dict:
    """把一行来源数据归一化成待办条目（缺列返回 None，不抛错）。"""
    mapping = cfg.get("field_mapping") or {}
    amount = pick_mapped_value(row, mapping, "amount")
    try:
        amount = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        amount = None
    return {
        "biz_type": cfg.get("biz_type"),
        "biz_name": cfg.get("biz_name"),
        "id": pick_mapped_value(row, mapping, "id"),
        "no": pick_mapped_value(row, mapping, "no"),
        "title": pick_mapped_value(row, mapping, "title"),
        "summary": pick_mapped_value(row, mapping, "summary"),
        "applicant": pick_mapped_value(row, mapping, "applicant"),
        "submitted_at": pick_mapped_value(row, mapping, "submitted_at"),
        "current_node": pick_mapped_value(row, mapping, "current_node"),
        "amount": amount,
        "status": "pending",
        "can_act": False,
        "can_recall": False,
    }


async def validate_sql_and_mapping(db: AsyncSession, sql_text: str, mapping) -> Optional[str]:
    """保存前实跑一次取数：SQL 能执行、映射列存在、id 行值可取整数，否则拒绝保存。

    这是「坏 SQL 不该进库」与「id 必须是数字主键」两道闸门的唯一落点。
    """
    err = validate_readonly_sql(sql_text)
    if err:
        return err
    err = validate_field_mapping(mapping)
    if err:
        return err
    try:
        preview = await preview_readonly_sql(db, sql_text)
    except Exception as exc:
        return f"SQL 执行失败：{exc}"
    columns = set(preview["columns"])
    for key, column in (mapping or {}).items():
        if column and column.strip() not in columns:
            return f"字段映射 {key} 的列 {column} 不在取数结果中（可用列：{', '.join(sorted(columns)) or '无'}）"
    for row in preview["rows"]:
        try:
            int(pick_mapped_value(row, mapping, "id"))
        except (TypeError, ValueError):
            return "id 映射必须是数字主键（取数结果中的 id 列取不到整数）"
    return None


def render_deep_link(template: Optional[str], item: dict) -> str:
    """按 {no} / {id} / {title} 等占位符渲染业务详情链接；未配置模板返回空串。

    占位值做 URL 编码，避免来源数据里的 `/`、`?` 等字符把深链拆坏。
    """
    if not template:
        return ""
    return re.sub(r"\{(\w+)\}", lambda m: quote(str(item.get(m.group(1)) or ""), safe=""), template)


WRITEBACK_STATUSES = ("pending", "approved", "rejected", "recalled")


async def validate_writeback_config(db: AsyncSession, writeback) -> Optional[str]:
    """校验声明式回写配置；空配置（不同步业务表）合法。返回错误信息，None 表示通过。"""
    if not writeback:
        return None
    if not isinstance(writeback, dict):
        return "回写配置格式不正确"
    table = writeback.get("table")
    id_col = writeback.get("id_column")
    st_col = writeback.get("status_column")
    for name, v in (("table", table), ("id_column", id_col), ("status_column", st_col)):
        if not isinstance(v, str) or not IDENTIFIER_RE.match(v):
            return f"回写配置 {name} 必须是合法的数据库标识符"
    status_map = writeback.get("status_map")
    if not isinstance(status_map, dict):
        return "回写状态映射格式不正确"
    for status in WRITEBACK_STATUSES:
        v = status_map.get(status)
        if v is None or str(v) == "":
            return f"回写状态映射缺少终态/状态值：{status}"
    rows = await db.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = :t"), {"t": table})
    columns = {r[0] for r in rows}
    if not columns:
        return f"回写表 {table} 不存在"
    for name, v in (("id_column", id_col), ("status_column", st_col)):
        if v not in columns:
            return f"回写表 {table} 不存在列 {v}"
    return None
