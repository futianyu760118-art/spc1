"""存量审批数据迁移：builtin 业务的在途/历史单据导入审批中心三表。

幂等：实例按 (biz_type, biz_id) 唯一约束冲突跳过；流水按 (instance_id, action, operator, created_at)
去重；在途任务已存在则跳过。生产部署后手工执行一次：
    cd backend && python migrate_approval_center.py
回滚：中心表数据可整体 TRUNCATE（业务表旧审批列在过渡期由 on_transition 维护，始终完整）。
"""

import asyncio
import json

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.services.common.approval_adapters import adapter_instance
from app.services.common.approval_center_service import ApprovalCenterService

# builtin 存量来源（与 Adapter 同步维护）
SOURCES = [
    {"biz_type": "supplier_claim", "table": "supplier_claim",
     "log_table": "supplier_claim_approval_log", "ref_col": "claim_id"},
    {"biz_type": "purchase_requisition", "table": "purchase_requisition",
     "log_table": "purchase_requisition_approval_log", "ref_col": "req_id"},
]


def _loads(raw, default):
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw or "")
    except (TypeError, ValueError):
        return default


async def _migrate_source(db, src) -> dict:
    svc = ApprovalCenterService(db)
    adapter = adapter_instance(db, src["biz_type"])
    if adapter is None:
        raise ValueError(f"未注册的 builtin 业务: {src['biz_type']}")
    stats = {"instances": 0, "records": 0, "tasks": 0}
    rows = await db.execute(text(
        f"SELECT * FROM {src['table']} WHERE submitted_at IS NOT NULL ORDER BY id"))
    for r in rows:
        rec = dict(r._mapping)
        biz_id = rec["id"]
        payload = await adapter.submit_payload(db, biz_id)
        snap = _loads(rec.get("approval_snapshot"), [])
        level = rec.get("approval_level") or 1
        node = next((n for n in snap if n.get("seq") == level), None) if snap else None
        exists = (await db.execute(text(
            "SELECT id FROM approval_instance WHERE biz_type = :bt AND biz_id = :bid"),
            {"bt": src["biz_type"], "bid": biz_id})).fetchone()
        if exists:
            iid = exists[0]
        else:
            amount = payload.get("amount")
            try:
                amount = float(amount) if amount is not None else None
            except (TypeError, ValueError):
                amount = None
            iid = (await db.execute(text("""
                INSERT INTO approval_instance
                    (biz_type, biz_id, biz_no, title, summary, applicant, amount, extra_json,
                     status, current_level, snapshot_json, timeout_hours, version,
                     submitted_at, finished_at, created_at)
                VALUES (:bt, :bid, :no, :t, :s, :ap, :amt, :extra, :st, :lv, :snap, :to, :v, :sa, :fa, :ca)
                RETURNING id
            """), {"bt": src["biz_type"], "bid": biz_id, "no": payload.get("no"),
                   "t": payload.get("title"), "s": payload.get("summary"),
                   "ap": rec.get("applicant") or payload.get("applicant"), "amt": amount,
                   "extra": json.dumps(payload.get("extra") or {}, ensure_ascii=False, default=str),
                   "st": rec.get("approval_status") or "pending", "lv": level,
                   "snap": json.dumps(snap, ensure_ascii=False),
                   "to": (node or {}).get("timeout_hours"), "v": rec.get("version") or 1,
                   "sa": rec.get("submitted_at"), "fa": rec.get("approved_at"),
                   "ca": rec.get("submitted_at")})).scalar_one()
            stats["instances"] += 1
        log_rows = await db.execute(text(
            f"SELECT action, approval_level, approver, comment, operated_at FROM {src['log_table']}"
            f" WHERE {src['ref_col']} = :eid ORDER BY id"), {"eid": biz_id})
        for lg in log_rows:
            dup = (await db.execute(text("""
                SELECT 1 FROM approval_record WHERE instance_id = :iid AND action = :ac
                  AND operator = :op AND created_at = :ca LIMIT 1
            """), {"iid": iid, "ac": lg[0], "op": lg[2], "ca": lg[4]})).fetchone()
            if dup:
                continue
            await db.execute(text(
                "INSERT INTO approval_record (instance_id, action, node_seq, operator, comment, created_at)"
                " VALUES (:iid, :ac, :lv, :op, :cm, :ca)"),
                {"iid": iid, "ac": lg[0], "lv": lg[1], "op": lg[2], "cm": lg[3], "ca": lg[4]})
            stats["records"] += 1
        # 在途单据：当前节点展开任务（幂等：已有任务则跳过；notify=False 不打扰审批人）
        if rec.get("approval_status") == "pending" and node:
            has_task = (await db.execute(text(
                "SELECT 1 FROM approval_task WHERE instance_id = :iid AND node_seq = :lv LIMIT 1"),
                {"iid": iid, "lv": level})).fetchone()
            if not has_task:
                await svc._activate_level(iid, level, node, notify=False)
                stats["tasks"] += 1
    return stats


async def main():
    from app.services.quality import supplier_claim_adapter  # noqa: F401
    from app.services.material import purchase_requisition_adapter  # noqa: F401
    async with AsyncSessionLocal() as db:
        total = {"instances": 0, "records": 0, "tasks": 0}
        for src in SOURCES:
            stats = await _migrate_source(db, src)
            print(f"{src['biz_type']}: {stats}")
            for k in total:
                total[k] += stats[k]
        await db.commit()
        print(f"done: {total}")


if __name__ == "__main__":
    asyncio.run(main())
