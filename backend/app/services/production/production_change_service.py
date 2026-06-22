from datetime import date
from typing import List, Tuple

from sqlalchemy import select, and_, Numeric
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.production.schedule_plan import ProductionSchedulePlan
from app.models.order.sale_order import SaleOrderLine
from app.models.production.sale_order_line_change_log import SaleOrderLineChangeLog


class ProductionChangeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def detect_and_log_sale_order_line_changes(self) -> List[SaleOrderLineChangeLog]:
        """检测销售订单行变更并记录日志，同时标记相关排产计划需要重排"""
        changed_logs = []

        # 1. 查询所有活跃的排产计划
        active_plans_result = await self.db.execute(
            select(ProductionSchedulePlan).where(ProductionSchedulePlan.is_active == True)
        )
        active_plans: List[ProductionSchedulePlan] = active_plans_result.scalars().all()

        for plan in active_plans:
            # 2. 获取当前销售订单行数据 (去重，只取最新的一条)
            sale_order_line_result = await self.db.execute(
                select(SaleOrderLine).where(
                    and_(
                        SaleOrderLine.order_no == plan.order_no,
                        SaleOrderLine.line_no == plan.line_no,
                    )
                ).order_by(SaleOrderLine.id.desc()).limit(1)
            )
            current_sale_order_line: SaleOrderLine = sale_order_line_result.scalar_one_or_none()

            if not current_sale_order_line:
                # 如果订单行不存在，可能已被删除，需要标记计划为无效或取消
                if plan.is_active:
                    plan.is_active = False
                    plan.needs_reschedule = True
                    plan.reschedule_reason = "订单行已删除"
                    self.db.add(plan)
                    changed_logs.append(SaleOrderLineChangeLog(
                        order_no=plan.order_no,
                        line_no=plan.line_no,
                        change_type="deleted",
                        old_value=f"订单行 {plan.order_no}-{plan.line_no}",
                        new_value="-",
                        is_processed=0
                    ))
                continue

            changes = []

            # 3. 比较交期变化
            if plan.source_promised_date != current_sale_order_line.promised_date:
                changes.append(
                    f"交期从 {plan.source_promised_date} 变为 {current_sale_order_line.promised_date}"
                )
            
            # 4. 比较数量变化
            # 注意 Numeric 类型的比较，需要转换为 float 或 decimal
            if plan.source_order_qty is not None and current_sale_order_line.order_qty is not None:
                if float(plan.source_order_qty) != float(current_sale_order_line.order_qty):
                    changes.append(
                        f"数量从 {plan.source_order_qty} 变为 {current_sale_order_line.order_qty}"
                    )
            elif plan.source_order_qty is None and current_sale_order_line.order_qty is not None:
                 changes.append(
                    f"数量从 无 变为 {current_sale_order_line.order_qty}"
                )
            elif plan.source_order_qty is not None and current_sale_order_line.order_qty is None:
                changes.append(
                    f"数量从 {plan.source_order_qty} 变为 无"
                )

            # 5. 比较产品编码变化 (如果需要)
            # if plan.source_product_code != current_sale_order_line.product_code:
            #     changes.append(
            #         f"产品编码从 {plan.source_product_code} 变为 {current_sale_order_line.product_code}"
            #     )

            if changes:
                # 记录变更日志
                change_log = SaleOrderLineChangeLog(
                    order_no=plan.order_no,
                    line_no=plan.line_no,
                    change_type="order_line_changed",
                    old_value=str({ # Store snapshot of old values
                        "promised_date": str(plan.source_promised_date),
                        "order_qty": float(plan.source_order_qty) if plan.source_order_qty else None,
                        "product_code": plan.source_product_code,
                        "product_model": plan.source_product_model,
                    }),
                    new_value=str({ # Store snapshot of new values
                        "promised_date": str(current_sale_order_line.promised_date),
                        "order_qty": float(current_sale_order_line.order_qty) if current_sale_order_line.order_qty else None,
                        "product_code": current_sale_order_line.product_code,
                        "product_model": current_sale_order_line.product_model,
                    }),
                    is_processed=0
                )
                self.db.add(change_log)
                changed_logs.append(change_log)

                # 标记排产计划需要重排
                if not plan.needs_reschedule:
                    plan.needs_reschedule = True
                    plan.reschedule_reason = ", ".join(changes)
                    self.db.add(plan)
        
        await self.db.commit()
        return changed_logs
