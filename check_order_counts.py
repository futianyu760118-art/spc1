import sys
import os
from sqlalchemy import create_engine, select, func

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))

from app.models.order.sale_order import SaleOrder, SaleOrderLine

DATABASE_URL_SYNC = "postgresql+psycopg2://root:123456@183.134.254.14:15432/spc_db"
engine = create_engine(DATABASE_URL_SYNC)

def main():
    with engine.connect() as conn:
        sale_order_count = conn.execute(select(func.count(SaleOrder.id))).scalar()
        sale_order_line_count = conn.execute(select(func.count(SaleOrderLine.id))).scalar()
        print(f"SaleOrder count: {sale_order_count}")
        print(f"SaleOrderLine count: {sale_order_line_count}")

if __name__ == "__main__":
    main()
