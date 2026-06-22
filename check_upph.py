#!/usr/bin/env python3
"""检查产品UPPH和订单数据"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

from sqlalchemy import select, func
from app.core.database import AsyncSessionLocal
from app.models.basicdata.product import Product
from app.models.order.sale_order import SaleOrder


async def check_data():
    async with AsyncSessionLocal() as db:
        print("=" * 60)
        print("检查产品UPPH数据")
        print("=" * 60)
        
        # 统计产品总数
        total_products = (await db.execute(select(func.count(Product.id)))).scalar() or 0
        print(f"\n产品总数: {total_products}")
        
        # 查看前10个产品
        print("\n前10个产品:")
        products = (await db.execute(select(Product).limit(10))).scalars().all()
        products_with_upph = 0
        for p in products:
            has_upph = (p.upph or 0) > 0
            if has_upph:
                products_with_upph += 1
            print(f"  - {p.product_code}: UPPH={p.upph}")
        
        print("\n" + "=" * 60)
        print("检查销售订单数据")
        print("=" * 60)
        
        # 统计订单总数
        total_orders = (await db.execute(select(func.count(SaleOrder.id)))).scalar() or 0
        print(f"\n销售订单总数: {total_orders}")
        
        # 查看前10个订单
        print("\n前10个订单:")
        orders = (await db.execute(select(SaleOrder).limit(10))).scalars().all()
        for o in orders:
            print(f"  - {o.order_no}: 数量={o.order_qty}, 交期={o.promised_date}, 产品={o.product_code}")


if __name__ == "__main__":
    asyncio.run(check_data())