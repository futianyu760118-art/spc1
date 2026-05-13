"""生产协同中心 — CSV导入服务（前道/贴片/精益/组装/包装）"""

import csv
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.production.process_progress import ProcessProgress


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
    val = val.strip().replace(',', '').replace('%', '')
    try:
        return float(val)
    except ValueError:
        return None


def _parse_int(val: str) -> Optional[int]:
    if not val or not val.strip():
        return None
    val = val.strip().replace(',', '')
    if not val:
        return None
    try:
        return int(float(val))
    except ValueError:
        return None


def _gen_record_no(process_type: str, order_no: str) -> str:
    s = process_type[:4].upper()
    o = (order_no or '')[:8]
    uid = uuid.uuid4().hex[:6].upper()
    return f"CSV-{s}-{o}-{uid}"


def _compute_status(row_data: dict) -> str:
    rate = row_data.get('completion_rate')
    if rate and '100' in str(rate):
        return 'completed'
    plan_date = row_data.get('plan_date')
    if plan_date and plan_date < date.today():
        return 'overdue'
    remark = row_data.get('remark') or ''
    if remark and any(kw in remark for kw in ['停线', '缺料', '异常', '报警']):
        return 'abnormal'
    return 'pending'


async def import_front_process_csv(filepath: str, db: AsyncSession) -> dict:
    """导入 4.1前道.csv

    CSV结构：第1行为列头，第2行起为数据
    列序：客户代码, 销售订单号, 下单日期, 型号, (空列), (空列), 颜色, 交期, 按款,
          壳体, 框, 手杆, 支架圆盘, 产品名称, 备注
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
        if len(row) < 8:
            skipped += 1
            continue

        customer_code = (row[0] or '').strip()
        sale_order_no = (row[1] or '').strip()
        order_date = (row[2] or '').strip()
        model_code = (row[3] or '').strip()
        # row[4], row[5] are empty/qty columns in some variants
        color_spec = (row[6] or '').strip() if len(row) > 6 else None
        delivery_date = _parse_date(row[7] if len(row) > 7 else '')
        by_style = _parse_int(row[8] if len(row) > 8 else '')
        shell_status = (row[9] or '').strip() if len(row) > 9 else None
        frame_status = (row[10] or '').strip() if len(row) > 10 else None
        handle_status = (row[11] or '').strip() if len(row) > 11 else None
        bracket_status = (row[12] or '').strip() if len(row) > 12 else None
        product_name = (row[13] or '').strip() if len(row) > 13 else None
        remark = (row[14] or '').strip() if len(row) > 14 else None
        # qty might be in col 4 or 5
        qty = _parse_float(row[4] if len(row) > 4 else '') or _parse_float(row[5] if len(row) > 5 else '')

        if not model_code and not sale_order_no:
            skipped += 1
            continue

        order_no = sale_order_no
        product_code = model_code  # 前道CSV中型号即产品编码
        row_data = {
            'plan_date': delivery_date,
            'order_no': order_no,
            'remark': remark,
            'completion_rate': None,
        }
        status = _compute_status(row_data)

        # upsert by sale_order_no + product_code + process_type
        match_filters = [
            ProcessProgress.process_type == 'front_process',
            ProcessProgress.sale_order_no == sale_order_no,
        ]
        if product_code:
            match_filters.append(ProcessProgress.product_code == product_code)
        elif model_code:
            match_filters.append(ProcessProgress.model_code == model_code)

        result = await db.execute(select(ProcessProgress).where(*match_filters))
        existing = result.scalars().first()

        if existing:
            existing.customer_code = customer_code or existing.customer_code
            existing.order_date = order_date or existing.order_date
            existing.color_spec = color_spec or existing.color_spec
            existing.delivery_date = delivery_date or existing.delivery_date
            existing.by_style = by_style
            existing.shell_status = shell_status or existing.shell_status
            existing.frame_status = frame_status or existing.frame_status
            existing.handle_status = handle_status or existing.handle_status
            existing.bracket_status = bracket_status or existing.bracket_status
            existing.product_name = product_name or existing.product_name
            existing.qty = qty or existing.qty
            existing.remark = remark or existing.remark
            existing.status = status
            updated += 1
        else:
            rec = ProcessProgress(
                process_type='front_process',
                customer_code=customer_code,
                sale_order_no=sale_order_no,
                order_date=order_date,
                product_code=product_code,
                model_code=model_code,
                color_spec=color_spec,
                delivery_date=delivery_date,
                by_style=by_style,
                shell_status=shell_status,
                frame_status=frame_status,
                handle_status=handle_status,
                bracket_status=bracket_status,
                product_name=product_name,
                qty=qty,
                order_no=order_no,
                remark=remark,
                status=status,
                data_source='csv_front',
            )
            db.add(rec)
            created += 1

    await db.flush()
    return {'created': created, 'updated': updated, 'skipped': skipped}


async def import_smt_csv(filepath: str, db: AsyncSession) -> dict:
    """导入 4.2贴片.csv

    CSV结构：前3行为说明+列头，第4行起为数据
    数据列：物料长代码, 物料名称, 订单号(销售订单号), 订单数量, 物料确认, 日期,
           当日排单, 当日完成, 单价, (空), 当日金额, 计划完成率, 工作时间, 备注,
           完成时间, 小时产能, 需求时间, 总计划完成数
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
        if row_idx < 3:
            continue
        if len(row) < 4:
            skipped += 1
            continue

        material_long_code = (row[0] or '').strip()
        material_name = (row[1] or '').strip()
        order_no = (row[2] or '').strip()
        qty = _parse_float(row[3] if len(row) > 3 else '')
        material_confirm = (row[4] or '').strip() if len(row) > 4 else None
        plan_date = _parse_date(row[5] if len(row) > 5 else '')
        daily_plan_qty = _parse_float(row[6] if len(row) > 6 else '')
        daily_complete_qty = _parse_float(row[7] if len(row) > 7 else '')
        unit_price = _parse_float(row[8] if len(row) > 8 else '')
        daily_amount = _parse_float(row[10] if len(row) > 10 else '')
        completion_rate = (row[11] or '').strip() if len(row) > 11 else None
        work_hours = _parse_float(row[12] if len(row) > 12 else '')
        remark = (row[13] or '').strip() if len(row) > 13 else None
        complete_time = (row[14] or '').strip() if len(row) > 14 else None
        hour_capacity = _parse_float(row[15] if len(row) > 15 else '')
        demand_time = (row[16] or '').strip() if len(row) > 16 else None
        total_plan_complete = _parse_float(row[17] if len(row) > 17 else '')

        if not material_long_code and not order_no:
            skipped += 1
            continue

        # 贴片CSV无直接产品编码，从物料长代码前缀推导
        product_code = (material_long_code[:8] if material_long_code else None)
        row_data = {
            'plan_date': plan_date,
            'order_no': order_no,
            'completion_rate': completion_rate,
            'remark': remark,
        }
        status = _compute_status(row_data)

        match_filters = [
            ProcessProgress.process_type == 'smt',
            ProcessProgress.material_long_code == material_long_code,
        ]
        if order_no:
            match_filters.append(ProcessProgress.order_no == order_no)

        result = await db.execute(select(ProcessProgress).where(*match_filters))
        existing = result.scalars().first()

        if existing:
            existing.material_name = material_name or existing.material_name
            existing.qty = qty or existing.qty
            existing.material_confirm = material_confirm or existing.material_confirm
            existing.plan_date = plan_date or existing.plan_date
            existing.daily_plan_qty = daily_plan_qty
            existing.daily_complete_qty = daily_complete_qty
            existing.unit_price = unit_price
            existing.daily_amount = daily_amount
            existing.completion_rate = completion_rate or existing.completion_rate
            existing.work_hours = work_hours
            existing.remark = remark or existing.remark
            existing.complete_time = complete_time or existing.complete_time
            existing.hour_capacity = hour_capacity
            existing.demand_time = demand_time or existing.demand_time
            existing.total_plan_complete = total_plan_complete
            existing.status = status
            updated += 1
        else:
            rec = ProcessProgress(
                process_type='smt',
                material_long_code=material_long_code,
                material_name=material_name,
                order_no=order_no,
                product_code=product_code,
                qty=qty,
                material_confirm=material_confirm,
                plan_date=plan_date,
                daily_plan_qty=daily_plan_qty,
                daily_complete_qty=daily_complete_qty,
                unit_price=unit_price,
                daily_amount=daily_amount,
                completion_rate=completion_rate,
                work_hours=work_hours,
                remark=remark,
                complete_time=complete_time,
                hour_capacity=hour_capacity,
                demand_time=demand_time,
                total_plan_complete=total_plan_complete,
                status=status,
                data_source='csv_smt',
            )
            db.add(rec)
            created += 1

    await db.flush()
    return {'created': created, 'updated': updated, 'skipped': skipped}


async def import_lean_csv(filepath: str, db: AsyncSession) -> dict:
    """导入 4.3精益.csv

    CSV结构：前2行为说明+列头，第3行起为数据
    数据列：序号, 时间, 订单号(短编号), 型号, 颜色, 下一工序, 数量, 齐套数量,
           上线时间, 当日排单量, 完成数量, 完成率, (空), 工作时间, 备注
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
        if row_idx < 2:
            continue
        if len(row) < 5:
            skipped += 1
            continue

        seq_no = _parse_int(row[0] if len(row) > 0 else '')
        plan_date = _parse_date(row[1] if len(row) > 1 else '')
        order_no = (row[2] or '').strip()
        model_code = (row[3] or '').strip()
        color_spec = (row[4] or '').strip() if len(row) > 4 else None
        next_process = (row[5] or '').strip() if len(row) > 5 else None
        qty = _parse_float(row[6] if len(row) > 6 else '')
        kit_qty = _parse_float(row[7] if len(row) > 7 else '')
        online_date = _parse_date(row[8] if len(row) > 8 else '')
        daily_plan_qty = _parse_float(row[9] if len(row) > 9 else '')
        daily_complete_qty = _parse_float(row[10] if len(row) > 10 else '')
        completion_rate = (row[11] or '').strip() if len(row) > 11 else None
        work_hours = _parse_float(row[13] if len(row) > 13 else '')
        remark = (row[14] or '').strip() if len(row) > 14 else None

        if not model_code and not order_no:
            skipped += 1
            continue

        product_code = model_code  # 精益CSV中型号即产品编码
        row_data = {
            'plan_date': plan_date,
            'order_no': order_no,
            'completion_rate': completion_rate,
            'remark': remark,
        }
        status = _compute_status(row_data)

        match_filters = [
            ProcessProgress.process_type == 'lean',
        ]
        if order_no:
            match_filters.append(ProcessProgress.order_no == order_no)
        if product_code:
            match_filters.append(ProcessProgress.product_code == product_code)
        elif model_code:
            match_filters.append(ProcessProgress.model_code == model_code)
        if plan_date:
            match_filters.append(ProcessProgress.plan_date == plan_date)

        result = await db.execute(select(ProcessProgress).where(*match_filters))
        existing = result.scalars().first()

        if existing:
            existing.seq_no = seq_no or existing.seq_no
            existing.color_spec = color_spec or existing.color_spec
            existing.next_process = next_process or existing.next_process
            existing.qty = qty or existing.qty
            existing.kit_qty = kit_qty
            existing.online_date = online_date or existing.online_date
            existing.daily_plan_qty = daily_plan_qty
            existing.daily_complete_qty = daily_complete_qty
            existing.completion_rate = completion_rate or existing.completion_rate
            existing.work_hours = work_hours
            existing.remark = remark or existing.remark
            existing.status = status
            updated += 1
        else:
            rec = ProcessProgress(
                process_type='lean',
                seq_no=seq_no,
                plan_date=plan_date,
                order_no=order_no,
                product_code=product_code,
                model_code=model_code,
                color_spec=color_spec,
                next_process=next_process,
                qty=qty,
                kit_qty=kit_qty,
                online_date=online_date,
                daily_plan_qty=daily_plan_qty,
                daily_complete_qty=daily_complete_qty,
                completion_rate=completion_rate,
                work_hours=work_hours,
                remark=remark,
                status=status,
                data_source='csv_lean',
            )
            db.add(rec)
            created += 1

    await db.flush()
    return {'created': created, 'updated': updated, 'skipped': skipped}


async def import_assembly_csv(filepath: str, db: AsyncSession) -> dict:
    """导入 4.4组装.csv

    CSV结构：前4行为说明+列头，第5行起为数据
    数据列：总装, 序号, 时间, 订单号, 型号, 颜色, 数量, 计划数量, 上线时间,
           当日排单量, 当日完成量, 完成率, 工作时间, 备注, 组装, 包装
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
        if row_idx < 4:
            continue
        if len(row) < 6:
            skipped += 1
            continue

        assembly_group = (row[0] or '').strip()
        seq_no = _parse_int(row[1] if len(row) > 1 else '')
        plan_date = _parse_date(row[2] if len(row) > 2 else '')
        order_no = (row[3] or '').strip()
        model_code = (row[4] or '').strip()
        color_spec = (row[5] or '').strip() if len(row) > 5 else None
        qty = _parse_float(row[6] if len(row) > 6 else '')
        planned_qty = _parse_float(row[7] if len(row) > 7 else '')
        online_date = _parse_date(row[8] if len(row) > 8 else '')
        daily_plan_qty = _parse_float(row[9] if len(row) > 9 else '')
        daily_complete_qty = _parse_float(row[10] if len(row) > 10 else '')
        completion_rate = (row[11] or '').strip() if len(row) > 11 else None
        work_hours = _parse_float(row[12] if len(row) > 12 else '')
        remark = (row[13] or '').strip() if len(row) > 13 else None

        if not model_code and not order_no:
            skipped += 1
            continue

        product_code = model_code  # 组装CSV中型号即产品编码
        row_data = {
            'plan_date': plan_date,
            'order_no': order_no,
            'completion_rate': completion_rate,
            'remark': remark,
        }
        status = _compute_status(row_data)

        match_filters = [
            ProcessProgress.process_type == 'assembly',
        ]
        if order_no:
            match_filters.append(ProcessProgress.order_no == order_no)
        if product_code:
            match_filters.append(ProcessProgress.product_code == product_code)
        elif model_code:
            match_filters.append(ProcessProgress.model_code == model_code)
        if plan_date:
            match_filters.append(ProcessProgress.plan_date == plan_date)

        result = await db.execute(select(ProcessProgress).where(*match_filters))
        existing = result.scalars().first()

        if existing:
            existing.assembly_group = assembly_group or existing.assembly_group
            existing.seq_no = seq_no or existing.seq_no
            existing.color_spec = color_spec or existing.color_spec
            existing.qty = qty or existing.qty
            existing.planned_qty = planned_qty
            existing.online_date = online_date or existing.online_date
            existing.daily_plan_qty = daily_plan_qty
            existing.daily_complete_qty = daily_complete_qty
            existing.completion_rate = completion_rate or existing.completion_rate
            existing.work_hours = work_hours
            existing.remark = remark or existing.remark
            existing.status = status
            updated += 1
        else:
            rec = ProcessProgress(
                process_type='assembly',
                assembly_group=assembly_group,
                seq_no=seq_no,
                plan_date=plan_date,
                order_no=order_no,
                product_code=product_code,
                model_code=model_code,
                color_spec=color_spec,
                qty=qty,
                planned_qty=planned_qty,
                online_date=online_date,
                daily_plan_qty=daily_plan_qty,
                daily_complete_qty=daily_complete_qty,
                completion_rate=completion_rate,
                work_hours=work_hours,
                remark=remark,
                status=status,
                data_source='csv_assembly',
            )
            db.add(rec)
            created += 1

    await db.flush()
    return {'created': created, 'updated': updated, 'skipped': skipped}


async def import_packaging_csv(filepath: str, db: AsyncSession) -> dict:
    """导入 4.5包装.csv

    CSV结构：前4行为说明+列头，第5行起为数据
    数据列：总装, 序号, 时间, 订单号, 型号, 颜色, 计划数量, 上线时间,
           当日排单量, 当日完成量, 完成率, 工作时间, 备注, 入库
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
        if row_idx < 4:
            continue
        if len(row) < 6:
            skipped += 1
            continue

        assembly_group = (row[0] or '').strip()
        seq_no = _parse_int(row[1] if len(row) > 1 else '')
        plan_date = _parse_date(row[2] if len(row) > 2 else '')
        order_no = (row[3] or '').strip()
        model_code = (row[4] or '').strip()
        color_spec = (row[5] or '').strip() if len(row) > 5 else None
        planned_qty = _parse_float(row[6] if len(row) > 6 else '')
        online_date = _parse_date(row[7] if len(row) > 7 else '')
        daily_plan_qty = _parse_float(row[8] if len(row) > 8 else '')
        daily_complete_qty = _parse_float(row[9] if len(row) > 9 else '')
        completion_rate = (row[10] or '').strip() if len(row) > 10 else None
        work_hours = _parse_float(row[11] if len(row) > 11 else '')
        remark = (row[12] or '').strip() if len(row) > 12 else None
        warehouse_in_qty = _parse_float(row[13] if len(row) > 13 else '')

        if not model_code and not order_no:
            skipped += 1
            continue

        product_code = model_code  # 包装CSV中型号即产品编码
        row_data = {
            'plan_date': plan_date,
            'order_no': order_no,
            'completion_rate': completion_rate,
            'remark': remark,
        }
        status = _compute_status(row_data)

        match_filters = [
            ProcessProgress.process_type == 'packaging',
        ]
        if order_no:
            match_filters.append(ProcessProgress.order_no == order_no)
        if product_code:
            match_filters.append(ProcessProgress.product_code == product_code)
        elif model_code:
            match_filters.append(ProcessProgress.model_code == model_code)
        if plan_date:
            match_filters.append(ProcessProgress.plan_date == plan_date)

        result = await db.execute(select(ProcessProgress).where(*match_filters))
        existing = result.scalars().first()

        if existing:
            existing.assembly_group = assembly_group or existing.assembly_group
            existing.seq_no = seq_no or existing.seq_no
            existing.color_spec = color_spec or existing.color_spec
            existing.planned_qty = planned_qty
            existing.online_date = online_date or existing.online_date
            existing.daily_plan_qty = daily_plan_qty
            existing.daily_complete_qty = daily_complete_qty
            existing.completion_rate = completion_rate or existing.completion_rate
            existing.work_hours = work_hours
            existing.remark = remark or existing.remark
            existing.warehouse_in_qty = warehouse_in_qty
            existing.status = status
            updated += 1
        else:
            rec = ProcessProgress(
                process_type='packaging',
                assembly_group=assembly_group,
                seq_no=seq_no,
                plan_date=plan_date,
                order_no=order_no,
                product_code=product_code,
                model_code=model_code,
                color_spec=color_spec,
                planned_qty=planned_qty,
                online_date=online_date,
                daily_plan_qty=daily_plan_qty,
                daily_complete_qty=daily_complete_qty,
                completion_rate=completion_rate,
                work_hours=work_hours,
                remark=remark,
                warehouse_in_qty=warehouse_in_qty,
                status=status,
                data_source='csv_packaging',
            )
            db.add(rec)
            created += 1

    await db.flush()
    return {'created': created, 'updated': updated, 'skipped': skipped}
