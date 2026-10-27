"""从表自带序列预分配主键，用于生成 AG-/AT- 编号。"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def next_serial_id(db: AsyncSession, table: str) -> int:
    if table not in ("agent", "agent_task"):
        raise ValueError(f"unsupported serial table: {table}")
    value = (await db.execute(
        text(f"SELECT nextval(pg_get_serial_sequence('{table}', 'id'))")
    )).scalar_one()
    return int(value)
