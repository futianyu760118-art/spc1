"""调价单审批通过后回写 K3 供应商报价表 (t_Supply / t_SupplyEntry)。

复刻原 OA 表单内嵌"手动同步"JS 的行为:
- t_Supply:      不存在 (FSupID, FItemID, FPType) 则插入供应商-物料报价关系
- t_SupplyEntry: 不存在 (供应商+物料+报价时间+价格+类型) 则插入新报价, FEntryID = max+1

字段映射(中台 -> K3):
  supplier_code -> t_Supplier.FNumber -> FSupID
  material_code -> t_ICItem.FNumber   -> FItemID (FUnitID 取采购单位 FOrderUnitID, 缺省回退基本单位 FUnitID)
  change_date   -> FQuoteTime / FLastModifiedDate
  new_price     -> FPrice
  order_qty / delivery_qty -> FStartQty / FEndQty
  remark        -> FRemark
固定值: FPType=1(采购报价), FUsed=1, FDisableDate=2100-01-01, 经手人=16547(与OA脚本一致)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_erp_write_engine

logger = logging.getLogger(__name__)

K3_QUOTE_FPTYPE = 1
K3_SYNC_USER_ID = 16547


async def _fetch_change(db: AsyncSession, change_id: int) -> dict | None:
    row = (await db.execute(text(
        "SELECT id, change_no, supplier_code, supplier_name, change_date, approval_status "
        "FROM purchase_price_change WHERE id = :c"
    ), {"c": change_id})).mappings().first()
    if not row:
        return None
    items = (await db.execute(text(
        "SELECT material_code, material_name, new_price, order_qty, delivery_qty, remark "
        "FROM purchase_price_change_item WHERE change_id = :c ORDER BY seq"
    ), {"c": change_id})).mappings().all()
    return {**row, "items": [dict(i) for i in items]}


def _sync_quotes_sync(change: dict) -> dict:
    """同步执行 K3 回写(在 executor 线程中调用)。"""
    engine = get_erp_write_engine()
    stats = {
        "change_no": change["change_no"],
        "entries_inserted": 0,
        "already_exists": 0,
        "supply_inserted": 0,
        "missing_lookup": [],
        "errors": [],
    }
    quote_time = change.get("change_date") or date.today()
    if isinstance(quote_time, str):
        quote_time = datetime.fromisoformat(quote_time[:10]).date()
    supplier_code, supplier_name = change.get("supplier_code"), change.get("supplier_name")

    with engine.connect() as conn:
        fsup = None
        if supplier_code:
            fsup = conn.execute(text(
                "SELECT FItemID FROM k3sv.[AIS20161019115614].dbo.t_Supplier WHERE FNumber = :c"
            ), {"c": supplier_code}).scalar()
        if fsup is None and supplier_name:
            fsup = conn.execute(text(
                "SELECT FItemID FROM k3sv.[AIS20161019115614].dbo.t_Supplier WHERE FName = :n"
            ), {"n": supplier_name}).scalar()
        if fsup is None:
            stats["errors"].append(f"K3未找到供应商: {supplier_code or supplier_name}")
            return stats
        fsup = int(fsup)

        for item in change["items"]:
            mc = item.get("material_code")
            if not mc:
                continue
            k3item = conn.execute(text(
                "SELECT FItemID, FUnitID, FOrderUnitID FROM k3sv.[AIS20161019115614].dbo.t_ICItem "
                "WHERE FNumber = :mc AND FDeleted = 0"
            ), {"mc": mc}).first()
            if not k3item:
                stats["missing_lookup"].append(mc)
                continue
            # 报价单位取「采购单位」FOrderUnitID（与历史报价一致）；缺省回退「基本单位」FUnitID
            fitem = int(k3item[0])
            funit = int(k3item[2] or k3item[1] or 0)

            # 1) 供应商-物料关系(链接服务器远程表 INSERT 要求 XACT_ABORT ON)
            conn.execute(text(
                "SET XACT_ABORT ON; "
                "IF NOT EXISTS (SELECT 1 FROM k3sv.[AIS20161019115614].dbo.t_Supply "
                "WHERE FSupID = :s AND FItemID = :i AND FPType = :t) "
                "INSERT INTO k3sv.[AIS20161019115614].dbo.t_Supply (FBrNo, FSupID, FItemID, FPType) "
                "VALUES ('0', :s, :i, :t)"
            ), {"s": fsup, "i": fitem, "t": K3_QUOTE_FPTYPE})

            # 2) 报价明细(存在相同报价则跳过, 幂等)
            exists = conn.execute(text(
                "SELECT 1 FROM k3sv.[AIS20161019115614].dbo.t_SupplyEntry "
                "WHERE FSupID = :s AND FItemID = :i AND FQuoteTime = :q AND FPrice = :p AND FPType = :t"
            ), {"s": fsup, "i": fitem, "q": quote_time, "p": item.get("new_price"), "t": K3_QUOTE_FPTYPE}).first()
            if exists:
                stats["already_exists"] += 1
                continue
            conn.execute(text(
                "SET XACT_ABORT ON; "
                "DECLARE @m int; SELECT @m = MAX(FEntryID) + 1 FROM k3sv.[AIS20161019115614].dbo.t_SupplyEntry; "
                "INSERT INTO k3sv.[AIS20161019115614].dbo.t_SupplyEntry "
                "(FBrNo, FSupID, FItemID, FEntryID, FUnitID, FStartQty, FEndQty, FPrice, FCyID, FDiscount, "
                "FLeadTime, FQuoteTime, FUsed, FDisableDate, FRemark, FPType, FLastModifiedDate, FLastModifiedBy, "
                "FCheckerID, FCheckDate) "
                "VALUES ('0', :s, :i, @m, :u, :sq, :eq, :p, 1, 0, 0, :q, 1, '2100-01-01', :rm, :t, :q, :op, :op, GETDATE())"
            ), {
                "s": fsup, "i": fitem, "u": funit,
                "sq": item.get("order_qty") or 0, "eq": item.get("delivery_qty") or 0,
                "p": item.get("new_price"), "q": quote_time,
                "rm": (item.get("remark") or "")[:255],
                "t": K3_QUOTE_FPTYPE, "op": K3_SYNC_USER_ID,
            })
            stats["entries_inserted"] += 1
        conn.commit()
    return stats


async def sync_price_change_quotes_to_k3(change_id: int, db: AsyncSession | None = None) -> dict:
    """调价单 K3 报价回写入口。仅 approved 状态执行; 失败不抛出, 返回错误信息。"""
    own_session = db is None
    if own_session:
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            return await sync_price_change_quotes_to_k3(change_id, db)

    change = await _fetch_change(db, change_id)  # type: ignore[arg-type]
    if not change:
        return {"success": False, "message": "调价单不存在"}
    if change.get("approval_status") != "approved":
        return {"success": False, "message": "仅审批通过的调价单可回写K3报价"}

    try:
        loop = asyncio.get_running_loop()
        stats = await loop.run_in_executor(None, lambda: _sync_quotes_sync(dict(change)))
    except Exception as exc:
        logger.exception(f"[调价K3回写] change_id={change_id} 失败: {exc}")
        return {"success": False, "message": f"K3回写失败: {exc}", "change_no": change["change_no"]}
    logger.info(f"[调价K3回写] {change['change_no']}: {stats}")
    return {"success": True, **stats}
