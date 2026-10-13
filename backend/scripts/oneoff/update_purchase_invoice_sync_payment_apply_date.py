"""一次性：purchase_invoices 同步 SQL 加选付款申请日期并写字段映射。最后验证: 2026-10-13"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import asyncio
import json

from sqlalchemy import text

from app.core.database import engine


NEW_COL = "aa.FDate AS 付款申请日期"
NEW_MAP_ENTRY = {"target": "payment_apply_date", "remark": "付款申请主表的单据日期字段"}
ANCHOR = "aa.FPayBillID_CN AS 付款单Id,"


async def main():
    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT sql_text, field_mapping_json FROM sync_sql_config WHERE sync_type='purchase_invoices'")
        )).mappings().first()
        if row is None:
            print("purchase_invoices config not found, skip")
            return
        sql_text = row["sql_text"] or ""
        if "付款申请日期" in sql_text:
            print("SQL already contains 付款申请日期, skip sql update")
        elif ANCHOR in sql_text:
            new_sql = sql_text.replace(ANCHOR, ANCHOR + "\n  " + NEW_COL + ",", 1)
            await conn.execute(text(
                "UPDATE sync_sql_config SET sql_text=:s, updated_at=NOW() WHERE sync_type='purchase_invoices'"
            ), {"s": new_sql})
            print("SQL updated: added 付款申请日期")
        else:
            print("ANCHOR not found, skip sql update (manual needed)")
        mapping = json.loads(row["field_mapping_json"] or "{}")
        if "付款申请日期" not in mapping:
            mapping["付款申请日期"] = NEW_MAP_ENTRY
            await conn.execute(text(
                "UPDATE sync_sql_config SET field_mapping_json=:m, updated_at=NOW() WHERE sync_type='purchase_invoices'"
            ), {"m": json.dumps(mapping, ensure_ascii=False)})
            print("mapping updated")
        else:
            print("mapping already has 付款申请日期, skip")
        await conn.commit()


if __name__ == "__main__":
    asyncio.run(main())
