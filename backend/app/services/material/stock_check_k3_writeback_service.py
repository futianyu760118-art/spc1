"""盘点完结 K3 回写服务 — 按 (盘点单, 类型, 仓库) 分组生成 K3 未审核单据。

设计文档: docs/superpowers/specs/2026-09-01-stockcheck-k3-writeback-design.md

- 盘盈: ICStockBill FTranType=40 (YADJ), 入库仓=盘点行仓库; FQty=盘差, FQtyMust=账面, FQtyActual=实盘
- 盘亏: ICStockBill FTranType=41 (CHG) 仓库调拨, 调出仓=盘点行仓库, 调入仓=库存检查不良仓(92852); FQty=|盘差|
- 全部写未审核单(FCheckerID=0), 由仓管员在 K3 审核生效; 本系统 scm_inventory 不动, 等 ERP 同步回流
- 幂等: (check_id, bill_type, wh_id) 唯一约束; execute 只处理 pending/failed
"""

import asyncio
import logging
import re
import threading
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material.inventory_check import StockCheck, StockCheckItem
from app.models.material.stock_check_writeback import StockCheckK3Writeback
from app.services.material.stock_check_k3_service import (
    BAD_STOCK_WH_ID,
    K3_DB,
    TRAN_TYPE_GAIN,
    TRAN_TYPE_TRANSFER_LOSS,
    _get_k3_engine,
)

logger = logging.getLogger(__name__)

WRITEBACK_TIMEOUT = 15  # 单张单据写入超时(秒);超时即记 failed,不拖垮完结请求

# 默认值来源: Task 0 K3 核实结论(2026-09-01, 见计划文件末尾)
K3_DEFAULT_BILLER_ID = 16546   # 制单人;盘盈/调拨最新单据常用值
K3_DEFAULT_MANAGER_ID = 34899  # 保管人(FFManagerID/FSManagerID);跨两种单型出现
K3_FENTRYID_STEP = 1           # FEntryID 步长: 生产库实证 1 递增
# 单据模板列(K3 客户端序时簿按模板过滤,缺失则客户端查不到单据;生产库实证 2026-09-01):
# 盘盈单(40) 恒 FInventoryType=36700/FRefType=0; 调拨单(41) 恒 FRefType=12561/FInventoryType=0
K3_GAIN_INVENTORY_TYPE = 36700
K3_TRANSFER_REF_TYPE = 12561


async def plan_writebacks(db: AsyncSession, head: StockCheck) -> List[StockCheckK3Writeback]:
    """完结事务内调用:按盘差行分组生成 pending 回写记录。幂等(已有记录则跳过)。

    - source='k3' 的单不回写(K3 单据已存在)
    - diff_qty=0 或 wh_id 为空的行不参与;后者由 overview 返回 skipped 清单
    """
    if (head.source or "manual") == "k3":
        return []
    existing = (await db.execute(
        select(StockCheckK3Writeback.id).where(StockCheckK3Writeback.check_id == head.id)
    )).scalars().first()
    if existing:
        return []

    items: List[StockCheckItem] = list(getattr(head, "items", None) or [])
    groups: Dict[Tuple[str, int], dict] = {}
    for it in items:
        diff = Decimal(str(it.diff_qty or 0))
        if diff == 0 or it.wh_id is None:
            continue
        bill_type = "gain" if diff > 0 else "loss_transfer"
        key = (bill_type, int(it.wh_id))
        g = groups.setdefault(key, {
            "bill_type": bill_type, "wh_id": int(it.wh_id),
            "wh_code": it.wh_code, "wh_name": it.wh_name,
            "item_count": 0, "total_qty": Decimal("0"),
        })
        g["item_count"] += 1
        g["total_qty"] += abs(diff)

    creator = head.checked_by or head.created_by or "系统"
    records: List[StockCheckK3Writeback] = []
    for g in groups.values():
        records.append(StockCheckK3Writeback(
            check_id=head.id, bill_type=g["bill_type"],
            wh_id=g["wh_id"], wh_code=g["wh_code"], wh_name=g["wh_name"],
            status="pending", item_count=g["item_count"], total_qty=g["total_qty"],
            created_by=creator,
        ))
    db.add_all(records)
    return records


async def get_writeback_overview(db: AsyncSession, check_id: int) -> Dict:
    """回写记录列表 + 无仓库被跳过的盘差行清单。"""
    records = (await db.execute(
        select(StockCheckK3Writeback)
        .where(StockCheckK3Writeback.check_id == check_id)
        .order_by(StockCheckK3Writeback.bill_type, StockCheckK3Writeback.wh_id)
    )).scalars().all()
    skipped = (await db.execute(
        select(StockCheckItem)
        .where(
            StockCheckItem.check_id == check_id,
            StockCheckItem.wh_id.is_(None),
            StockCheckItem.diff_qty != 0,
        )
    )).scalars().all()
    return {
        "writebacks": list(records),
        "skipped_items": [
            {
                "material_code": it.material_code,
                "material_name": it.material_name,
                "unit": it.unit,
                "diff_qty": Decimal(str(it.diff_qty or 0)),
            }
            for it in skipped
        ],
    }


# ---------------------------------------------------------------- K3 写入 --

def _next_k3_bill_no_sync(conn, prefix: str) -> str:
    """按 K3 现有单号规则生成下一号: prefix + 数字后缀零填充(位数对齐现有最大号)。"""
    mx = conn.execute(text(
        f"SELECT MAX(FBillNo) FROM {K3_DB}.dbo.ICStockBill WHERE FBillNo LIKE :p"
    ), {"p": prefix + "%"}).scalar()
    width, next_seq = 10, 1
    if mx:
        m = re.search(r"(\d+)$", str(mx))
        if m:
            width = len(m.group(1))
            next_seq = int(m.group(1)) + 1
    return f"{prefix}{str(next_seq).zfill(width)}"


INSERT_HEAD_SQL = f"""
INSERT INTO {K3_DB}.dbo.ICStockBill
    (FInterID, FBrNo, FBrID, FBillNo, FDate, FTranType, FNote, FExplanation,
     FBillerID, FCheckerID, FCancellation, FFManagerID, FSManagerID,
     FInventoryType, FRefType)
VALUES
    (:FInterID, '0', :FBrID, :FBillNo, :FDate, :FTranType, :FNote, :FExplanation,
     :FBillerID, 0, 0, :FManagerID, :FManagerID,
     :FInventoryType, :FRefType)
"""

INSERT_ENTRY_SQL = f"""
INSERT INTO {K3_DB}.dbo.ICStockBillEntry
    (FInterID, FEntryID, FBrNo, FItemID, FUnitID, FQty, FQtyMust, FQtyActual,
     FPrice, FAmount, FDCStockID, FSCStockID, FBatchNo)
VALUES
    (:FInterID, :FEntryID, '0', :FItemID, :FUnitID, :FQty, :FQtyMust, :FQtyActual,
     0, 0, :FDCStockID, :FSCStockID, '')
"""

GAIN_PREFIX, TRANSFER_PREFIX = "YADJ", "CHG"

# K3 取号(MAX+1)无原子性: 进程内锁把「取号→插入→补偿」整体串行化(单 worker 部署下足够)
_K3_WRITE_LOCK = threading.Lock()


def _write_bill_sync(rec: StockCheckK3Writeback, entries: List[dict]) -> Tuple[str, int]:
    """同步写一张 K3 未审核单(头+体)。entries 由调用方按明细行构造。

    连接经链接服务器(k3sv)访问 K3: 显式事务内跨链接服务器 INSERT 会报
    7395(OLE DB 提供程序不支持嵌套事务), 故写路径用 AUTOCOMMIT 逐句提交,
    失败时以补偿删除清理残留(未审核单无下游影响, 删除安全)。
    取号(MAX+1)无原子性, 以进程内锁把「取号→插入→补偿」整体串行化,
    避免并发完结/重试撞号与补偿误删(单 worker 部署下已足够)。
    """
    inter_id: Optional[int] = None
    bill_no: Optional[str] = None
    with _K3_WRITE_LOCK, _get_k3_engine().connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        try:
            inter_id = int(conn.execute(text(
                f"SELECT ISNULL(MAX(FInterID), 0) + 1 FROM {K3_DB}.dbo.ICStockBill"
            )).scalar())
            # FDetailID 是 IDENTITY 自增列(链接服务器下显式插入报 7344 无列权限), 交给 SQL Server 生成
            is_gain = rec.bill_type == "gain"
            prefix = GAIN_PREFIX if is_gain else TRANSFER_PREFIX
            bill_no = _next_k3_bill_no_sync(conn, prefix)
            conn.execute(text(INSERT_HEAD_SQL), {
                "FInterID": inter_id, "FBrID": 0, "FBillNo": bill_no,
                "FDate": entries[0]["fdate"], "FTranType": TRAN_TYPE_GAIN if is_gain else TRAN_TYPE_TRANSFER_LOSS,
                "FNote": entries[0]["fnote"], "FExplanation": "",
                "FBillerID": K3_DEFAULT_BILLER_ID, "FManagerID": K3_DEFAULT_MANAGER_ID,
                "FInventoryType": K3_GAIN_INVENTORY_TYPE if is_gain else 0,
                "FRefType": 0 if is_gain else K3_TRANSFER_REF_TYPE,
            })
            for idx, e in enumerate(entries, start=1):
                conn.execute(text(INSERT_ENTRY_SQL), {
                    "FInterID": inter_id,
                    "FEntryID": idx * K3_FENTRYID_STEP,
                    "FItemID": e["item_id"], "FUnitID": e["unit_id"],
                    "FQty": e["qty"], "FQtyMust": e["qty_must"], "FQtyActual": e["qty_actual"],
                    "FDCStockID": e["dc_stock"], "FSCStockID": e["sc_stock"],
                })
            return bill_no, inter_id
        except Exception as e:
            # 补偿清理: 删掉可能已插入的头/体残留(未审核单无下游影响)。
            # 头表删除限定 FBillNo, 防止极端并发下误删他人已提交的同 FInterID 单据。
            if inter_id is not None:
                try:
                    conn.execute(text(
                        f"DELETE FROM {K3_DB}.dbo.ICStockBillEntry WHERE FInterID = :i"
                    ), {"i": inter_id})
                    conn.execute(text(
                        f"DELETE FROM {K3_DB}.dbo.ICStockBill WHERE FInterID = :i AND FBillNo = :b"
                    ), {"i": inter_id, "b": bill_no})
                except Exception:
                    raise RuntimeError(
                        f"K3 写入失败且补偿删除失败(残留未审核单 FInterID={inter_id} {bill_no}),"
                        f"请人工在 K3 删除后重试; 原错误: {str(e)[:200]}"
                    ) from e
            raise


def _load_unit_ids_sync(item_ids: List[int]) -> Dict[int, int]:
    """物料默认单位: t_ICItem.FUnitID(批量查,缺失回退 0)。"""
    if not item_ids:
        return {}
    ids = ",".join(str(int(i)) for i in item_ids)
    with _get_k3_engine().connect() as conn:
        rows = conn.execute(text(
            f"SELECT FItemID, FUnitID FROM {K3_DB}.dbo.t_ICItem WHERE FItemID IN ({ids})"
        )).mappings().all()
    return {int(r["FItemID"]): int(r["FUnitID"] or 0) for r in rows}


async def _execute_one(db: AsyncSession, rec: StockCheckK3Writeback, head: StockCheck) -> None:
    """生成一张 K3 单并更新记录状态(单张独立成败,异常记 failed 不抛出)。

    全部 K3 访问(单位装载/单据写入)都在 try 内:K3 不可达只置本记录 failed,
    不中断同批其余记录,也不让 retry 端点 500。
    """
    try:
        items = (await db.execute(
            select(StockCheckItem).where(
                StockCheckItem.check_id == rec.check_id,
                StockCheckItem.wh_id == rec.wh_id,
                StockCheckItem.diff_qty != 0,
            ).order_by(StockCheckItem.id)
        )).scalars().all()
        diff_rows = [it for it in items if (Decimal(str(it.diff_qty or 0)) > 0) == (rec.bill_type == "gain")]
        diff_rows = [it for it in diff_rows if it.material_id is not None]  # K3 FItemID 必需
        if not diff_rows:
            rec.status = "failed"
            rec.error_msg = "未找到对应的盘差明细行(或行均无物料ID)"
            return
        unit_ids = await asyncio.to_thread(
            _load_unit_ids_sync, [int(it.material_id) for it in diff_rows])
        fdate = head.check_date
        fnote = f"盘点单 {head.check_no} 完结自动生成"
        entries = []
        for it in diff_rows:
            diff = Decimal(str(it.diff_qty or 0))
            qty = abs(diff)
            if rec.bill_type == "gain":
                entries.append({
                    "item_id": int(it.material_id), "unit_id": unit_ids.get(int(it.material_id), 0),
                    "qty": qty, "qty_must": Decimal(str(it.system_qty or 0)),
                    "qty_actual": Decimal(str(it.actual_qty or 0)),
                    "dc_stock": rec.wh_id, "sc_stock": 0,
                    "fdate": fdate, "fnote": fnote,
                })
            else:
                entries.append({
                    "item_id": int(it.material_id), "unit_id": unit_ids.get(int(it.material_id), 0),
                    "qty": qty, "qty_must": qty, "qty_actual": 0,
                    "dc_stock": BAD_STOCK_WH_ID, "sc_stock": rec.wh_id,
                    "fdate": fdate, "fnote": fnote,
                })
        bill_no, inter_id = await asyncio.wait_for(
            asyncio.to_thread(_write_bill_sync, rec, entries), timeout=WRITEBACK_TIMEOUT)
        rec.status = "success"
        rec.erp_bill_no = bill_no
        rec.k3_inter_id = inter_id
        rec.written_at = datetime.now()
        rec.error_msg = None
    except asyncio.TimeoutError:
        rec.status = "failed"
        rec.error_msg = (
            f"K3 写入超时({WRITEBACK_TIMEOUT}s);写入可能仍在后台完成,重试前请先在 K3 核实是否已生成单据"
        )
        rec.retry_count = int(rec.retry_count or 0) + 1
        logger.warning(f"K3 回写超时 check={rec.check_id} type={rec.bill_type} wh={rec.wh_id}")
    except Exception as e:  # 单张失败不中断其余
        rec.status = "failed"
        rec.error_msg = str(e)[:500]
        rec.retry_count = int(rec.retry_count or 0) + 1
        logger.warning(f"K3 回写失败 check={rec.check_id} type={rec.bill_type} wh={rec.wh_id}: {e}")


async def execute_pending_writebacks(
    db: AsyncSession, check_id: int, current_user: Optional[dict] = None,
) -> Dict:
    """执行(或重试)该盘点单所有 pending/failed 回写记录;success 不动。返回统计。"""
    head = (await db.execute(select(StockCheck).where(StockCheck.id == check_id))).scalar_one_or_none()
    if not head:
        raise ValueError(f"盘点单 {check_id} 不存在")
    if head.status != "completed":
        raise ValueError("仅已完结的盘点单可执行 K3 回写")
    recs = (await db.execute(
        select(StockCheckK3Writeback).where(
            StockCheckK3Writeback.check_id == check_id,
            StockCheckK3Writeback.status.in_(("pending", "failed")),
        ).order_by(StockCheckK3Writeback.id)
    )).scalars().all()
    for rec in recs:
        await _execute_one(db, rec, head)
    await db.commit()  # 状态更新立即落库(自管事务;get_db 结束时再 commit 幂等)
    all_recs = (await db.execute(
        select(StockCheckK3Writeback).where(StockCheckK3Writeback.check_id == check_id)
    )).scalars().all()
    return {
        "total": len(all_recs),
        "success": sum(1 for r in all_recs if r.status == "success"),
        "failed": sum(1 for r in all_recs if r.status == "failed"),
        "pending": sum(1 for r in all_recs if r.status == "pending"),
    }
