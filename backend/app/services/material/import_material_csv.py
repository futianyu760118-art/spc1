"""物料齐套中心 — CSV导入服务（采购到料计划 / 问题物料 / 长交期物料 / 供应商付款排程）"""

import csv
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.material.purchase_order import PurchaseOrder
from app.models.material.material_issue import MaterialIssue
from app.models.material.long_lead_material import LongLeadMaterial


def _parse_date(val: str) -> Optional[date]:
    if not val or not val.strip():
        return None
    val = val.strip()
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%m/%d', '%m月%d日', '%Y.%m.%d', '%m-%d'):
        try:
            d = datetime.strptime(val, fmt)
            if d.year == 1900:
                d = d.replace(year=date.today().year)
            return d.date()
        except ValueError:
            continue
    return None


def _parse_float(val: str) -> Optional[float]:
    if not val or not val.strip():
        return None
    val = val.strip().replace(',', '')
    try:
        return float(val)
    except ValueError:
        return None


def _parse_int(val: str) -> Optional[int]:
    if not val or not val.strip():
        return None
    val = val.strip().replace(',', '').replace('天', '').replace('停产', '')
    if not val:
        return None
    try:
        return int(float(val))
    except ValueError:
        return None


def _gen_po_no(supplier: str, material_code: str) -> str:
    """为CSV记录生成唯一 po_no 占位符"""
    s = (supplier or '')[:4]
    m = (material_code or '')[-8:]
    uid = uuid.uuid4().hex[:6].upper()
    return f"CSV-{s}-{m}-{uid}"


async def import_purchase_plan_csv(filepath: str, db: AsyncSession) -> dict:
    """导入 3.采购计划.csv 到 purchase_order 表（data_source='csv_plan'）

    CSV结构：第1行为蓝色说明行，第2行为列头，第3行起为数据
    列序：供应商, 物料长代码, 物料名称, 规格型号, 单位, 数量, 收料数量,
          交货日期, 订单号, 到料时间, 到料按小时节点填写, 检验日期, 下单日期
    供应商列为空时沿用上一行的供应商（合并单元格规律）
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        rows = list(reader)

    created = 0
    updated = 0
    skipped = 0
    last_supplier = ''

    for row_idx, row in enumerate(rows):
        if row_idx < 2:
            continue
        if len(row) < 3:
            skipped += 1
            continue

        # 供应商列为空时沿用上一行（合并单元格）
        raw_supplier = (row[0] or '').strip()
        if raw_supplier:
            last_supplier = raw_supplier
        supplier_name = last_supplier

        material_code = (row[1] or '').strip()
        if not material_code:
            skipped += 1
            continue

        material_name = (row[2] or '').strip() if len(row) > 2 else None
        spec_model = (row[3] or '').strip() if len(row) > 3 else None
        unit = (row[4] or '').strip() if len(row) > 4 else None
        po_qty = _parse_float(row[5] if len(row) > 5 else '')
        received_qty = _parse_float(row[6] if len(row) > 6 else '')
        eta = _parse_date(row[7] if len(row) > 7 else '')
        order_no = (row[8] or '').strip() if len(row) > 8 else None
        actual_arrival_date = _parse_date(row[9] if len(row) > 9 else '')
        arrival_hour_note = (row[10] or '').strip() if len(row) > 10 else None
        inspection_date = _parse_date(row[11] if len(row) > 11 else '')
        po_date = _parse_date(row[12] if len(row) > 12 else '')

        # 计算状态
        today = date.today()
        if inspection_date:
            po_status = 'inspected'
        elif actual_arrival_date:
            po_status = 'arrived'
        elif eta and eta < today:
            po_status = 'overdue'
        else:
            po_status = 'pending'

        # 按 material_code + order_no + material_name 查找已有记录（csv_plan来源）
        # 增加material_name作为额外匹配条件以避免当order_no为空时误匹配
        match_filters = [
            PurchaseOrder.material_code == material_code,
            PurchaseOrder.data_source == 'csv_plan',
        ]
        if order_no:
            match_filters.append(PurchaseOrder.order_no == order_no)
        if material_name:
            match_filters.append(PurchaseOrder.material_name == material_name)

        result = await db.execute(select(PurchaseOrder).where(*match_filters))
        existing = result.scalars().first()

        if existing:
            existing.supplier_name = supplier_name
            existing.material_name = material_name or existing.material_name
            existing.spec_model = spec_model
            existing.unit = unit
            existing.po_qty = po_qty
            existing.received_qty = received_qty
            existing.eta = eta
            existing.order_no = order_no
            existing.actual_arrival_date = actual_arrival_date
            existing.arrival_hour_note = arrival_hour_note
            existing.inspection_date = inspection_date
            existing.po_date = po_date
            existing.po_status = po_status
            updated += 1
        else:
            po_no = _gen_po_no(supplier_name, material_code)
            # 自动计算 detail_id: 同一 po_no 下最大 detail_id + 1
            max_detail = await db.execute(
                select(func.coalesce(func.max(PurchaseOrder.detail_id), 0)).where(
                    PurchaseOrder.po_no == po_no
                )
            )
            detail_id = max_detail.scalar() + 1
            po = PurchaseOrder(
                po_no=po_no,
                detail_id=detail_id,
                material_code=material_code,
                supplier_name=supplier_name,
                material_name=material_name,
                spec_model=spec_model,
                unit=unit,
                po_qty=po_qty,
                received_qty=received_qty,
                eta=eta,
                order_no=order_no,
                actual_arrival_date=actual_arrival_date,
                arrival_hour_note=arrival_hour_note,
                inspection_date=inspection_date,
                po_date=po_date,
                po_status=po_status,
                data_source='csv_plan',
            )
            db.add(po)
            created += 1

    await db.flush()
    return {'created': created, 'updated': updated, 'skipped': skipped}


async def import_material_issue_csv(filepath: str, db: AsyncSession) -> dict:
    """导入 3.1问题物料.csv 到 material_issue 表

    CSV结构：第1行为列头，第2行起为数据
    列序：年份, 周序, 部门, 类别, 日期, 提出人, 问题描述, 节点, 部门(责任),
          责任人, 稽核, 评分, 立项, 月份, 周序, 稽核证据和跟进记录
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        rows = list(reader)

    created = 0
    updated = 0
    skipped = 0

    for row_idx, row in enumerate(rows):
        if row_idx < 1:
            continue
        if len(row) < 7:
            skipped += 1
            continue

        description = (row[6] or '').strip()
        if not description:
            skipped += 1
            continue

        year = _parse_int(row[0] if len(row) > 0 else '')
        week_no = _parse_int(row[1] if len(row) > 1 else '')
        department = (row[2] or '').strip() if len(row) > 2 else None
        category = (row[3] or '').strip() if len(row) > 3 else None
        issue_date = _parse_date(row[4] if len(row) > 4 else '')
        reporter = (row[5] or '').strip() if len(row) > 5 else None
        deadline = _parse_date(row[7] if len(row) > 7 else '')
        responsible_dept = (row[8] or '').strip() if len(row) > 8 else None
        responsible_person = (row[9] or '').strip() if len(row) > 9 else None
        audit_score_raw = (row[11] or '').strip() if len(row) > 11 else ''
        audit_score = _parse_int(audit_score_raw)
        is_project_raw = (row[12] or '').strip() if len(row) > 12 else ''
        is_project = bool(is_project_raw and is_project_raw not in ('0', '', 'None'))
        follow_up_record = (row[15] or '').strip() if len(row) > 15 else None

        # 按 year + week_no + description 查找
        match_filters = [MaterialIssue.description == description]
        if year:
            match_filters.append(MaterialIssue.year == year)
        if week_no:
            match_filters.append(MaterialIssue.week_no == week_no)

        result = await db.execute(select(MaterialIssue).where(*match_filters))
        existing = result.scalars().first()

        if existing:
            existing.department = department or existing.department
            existing.category = category or existing.category
            existing.issue_date = issue_date or existing.issue_date
            existing.reporter = reporter or existing.reporter
            existing.deadline = deadline or existing.deadline
            existing.responsible_dept = responsible_dept or existing.responsible_dept
            existing.responsible_person = responsible_person or existing.responsible_person
            existing.audit_score = audit_score
            existing.is_project = is_project
            existing.follow_up_record = follow_up_record or existing.follow_up_record
            updated += 1
        else:
            issue = MaterialIssue(
                year=year,
                week_no=week_no,
                department=department,
                category=category,
                issue_date=issue_date,
                reporter=reporter,
                description=description,
                deadline=deadline,
                responsible_dept=responsible_dept,
                responsible_person=responsible_person,
                audit_score=audit_score,
                is_project=is_project,
                follow_up_record=follow_up_record,
                status='open',
            )
            db.add(issue)
            created += 1

    await db.flush()
    return {'created': created, 'updated': updated, 'skipped': skipped}


async def import_long_lead_csv(filepath: str, db: AsyncSession) -> dict:
    """导入 3.2长交期物料台账.csv 到 long_lead_material 注解表

    CSV结构：第1行为列头，第2行起为数据
    列序：序号, 物料代码, 物料名称, 交货周期大于20天, 供应商, 改善对策
    注：material_name 和 lead_time_days 已从注解表移除，仅导入 improvement_plan
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        rows = list(reader)

    created = 0
    updated = 0
    skipped = 0

    for row_idx, row in enumerate(rows):
        if row_idx < 1:
            continue
        if len(row) < 3:
            skipped += 1
            continue

        material_name = (row[2] or '').strip()
        if not material_name:
            skipped += 1
            continue

        material_code = (row[1] or '').strip() if len(row) > 1 else None
        if not material_code:
            skipped += 1
            continue

        supplier_name = (row[4] or '').strip() if len(row) > 4 else None
        improvement_plan = (row[5] or '').strip() if len(row) > 5 else None

        # 按 material_code + supplier_name upsert
        match_filters = [LongLeadMaterial.material_code == material_code]
        if supplier_name:
            match_filters.append(LongLeadMaterial.supplier_name == supplier_name)

        result = await db.execute(select(LongLeadMaterial).where(*match_filters))
        existing = result.scalars().first()

        if existing:
            existing.improvement_plan = improvement_plan or existing.improvement_plan
            updated += 1
        else:
            item = LongLeadMaterial(
                material_code=material_code,
                supplier_name=supplier_name,
                improvement_plan=improvement_plan,
                status='active',
            )
            db.add(item)
            created += 1

    await db.flush()
    return {'created': created, 'updated': updated, 'skipped': skipped}


