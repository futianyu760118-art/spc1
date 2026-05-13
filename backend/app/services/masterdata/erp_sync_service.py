"""
ERP Sync Service — 直接通过 SQL 查询 ERP 数据库同步数据到 SPC
SQL 语句存储在 sync_sql_config 表中，可在后台管理界面配置
SQL 中使用 :since 作为增量时间参数
"""

import asyncio
import json
import logging
from datetime import datetime, date, timedelta
from typing import Optional

from sqlalchemy import create_engine, text, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.order.sale_order import SaleOrder, SaleOrderLine
from app.models.material.material_demand import MaterialDemand
from app.models.material.purchase_order import PurchaseOrder
from app.models.material.purchase_invoice import PurchaseInvoice
from app.models.masterdata.sync_sql_config import SyncSqlConfig
from app.models.masterdata.customer import Customer
from app.models.masterdata.supplier import Supplier
from app.models.masterdata.material import Material
from app.models.masterdata.sku import SKU
from app.models.masterdata.product import Product
from app.models.masterdata.warehouse import Warehouse
from app.models.masterdata.process import Process
from app.models.masterdata.organization import Organization
from app.models.masterdata.employee import Employee
from app.models.exception.quality_issue import QualityIssue

logger = logging.getLogger(__name__)
settings = get_settings()


class ERPConnectionError(Exception):
    """ERP 连接异常"""
    pass


class ERPSyncService:
    """
    ERP 数据同步服务
    通过在 sync_sql_config 表中配置的 SQL 直接查询 ERP 数据库
    """

    def __init__(self, spc_db: AsyncSession):
        self.spc_db = spc_db
        self.erp_engine = None
        self.erp_session = None
        self.batch_size = settings.ERP_SYNC_BATCH_SIZE

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------
    async def _connect_erp(self):
        """建立到 ERP 数据库的只读连接（幂等：已连接则跳过），通过线程池避免阻塞事件循环"""
        if self.erp_session is not None:
            return
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._connect_erp_sync)

    def _connect_erp_sync(self):
        """同步建立 ERP 连接（在线程池中执行）"""
        if self.erp_session is not None:
            return
        if not settings.ERP_DB_URL:
            raise ERPConnectionError("ERP_DB_URL 未配置，请在 .env 中设置")
        if not settings.ERP_SYNC_ENABLED:
            raise ERPConnectionError("ERP 同步未启用，请设置 ERP_SYNC_ENABLED=true")

        try:
            url = settings.ERP_DB_URL
            for param in ["TrustServerCertificate=yes", "Encrypt=no"]:
                if param.split("=")[0] not in url:
                    url += f"&{param}" if "?" in url else f"?{param}"
            connect_args = {"login_timeout": 15, "timeout": 30}
            # 对于 SQL Server，添加编码参数
            if "mssql+pyodbc" in url:
                connect_args["charset"] = "utf-8"
            self.erp_engine = create_engine(
                url,
                echo=False,
                pool_size=5,
                max_overflow=2,
                pool_pre_ping=True,
                connect_args=connect_args,
            )
            Session = sessionmaker(bind=self.erp_engine)
            self.erp_session = Session()
            self.erp_session.execute(text("SELECT 1"))
            logger.info("ERP 数据库连接成功")
        except Exception as e:
            raise ERPConnectionError(f"ERP 数据库连接失败: {e}")

    def _close_erp(self, keep_alive: bool = False):
        """关闭 ERP 连接。keep_alive=True 时仅断开 session 但保留引擎供复用"""
        if self.erp_session:
            self.erp_session.close()
            if not keep_alive:
                self.erp_session = None
            else:
                # 重新创建 session 供下次使用
                Session = sessionmaker(bind=self.erp_engine)
                self.erp_session = Session()
        if not keep_alive and self.erp_engine:
            self.erp_engine.dispose()
            self.erp_engine = None
            self.erp_session = None

    # ------------------------------------------------------------------
    # SQL 配置加载
    # ------------------------------------------------------------------
    async def _load_sql_config(self, sync_type: str) -> tuple[str, dict]:
        """
        从 sync_sql_config 表加载 SQL 和字段映射
        返回 (sql_text, field_mapping_dict)
        """
        result = await self.spc_db.execute(
            select(SyncSqlConfig).where(
                SyncSqlConfig.sync_type == sync_type,
                SyncSqlConfig.sync_enabled == True,
            )
        )
        config = result.scalar_one_or_none()
        if not config:
            raise ERPConnectionError(
                f"未配置 sync_type='{sync_type}' 的同步 SQL，"
                f"请在 系统配置 → 同步SQL配置 中添加"
            )

        mapping = {}
        if config.field_mapping_json:
            try:
                mapping = json.loads(config.field_mapping_json)
            except json.JSONDecodeError:
                logger.warning(f"sync_type={sync_type} 的字段映射 JSON 解析失败，使用原始字段名")

        return config.sql_text, mapping

    # ------------------------------------------------------------------
    # 通用：执行 SQL 并映射字段
    # ------------------------------------------------------------------
    async def _execute_erp_sql(self, sql_text: str, params: dict) -> list[dict]:
        """在 ERP 数据库上执行 SQL，返回字典列表（通过线程池避免阻塞事件循环）"""
        loop = asyncio.get_event_loop()
        rows = await loop.run_in_executor(
            None,
            lambda: self.erp_session.execute(text(sql_text), params).mappings().all()
        )

        def clean_value(v):
            """清理值，处理编码问题"""
            if v is None:
                return v
            if isinstance(v, bytes):
                try:
                    return v.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        return v.decode('gbk')
                    except UnicodeDecodeError:
                        return v.decode('latin-1', errors='replace')
            if isinstance(v, str):
                try:
                    v.encode('utf-8')
                    return v
                except UnicodeEncodeError:
                    try:
                        return v.encode('latin-1').decode('gbk')
                    except (UnicodeDecodeError, UnicodeEncodeError):
                        return v.encode('latin-1', errors='replace').decode('utf-8', errors='replace')
            return v

        cleaned_rows = []
        for row in rows:
            row_dict = {}
            for k, v in dict(row).items():
                row_dict[k] = clean_value(v)
            cleaned_rows.append(row_dict)
        return cleaned_rows

    @staticmethod
    def _get_model_columns(model_class) -> set:
        """获取 ORM 模型的所有列名（排除自动字段）"""
        auto = {"id", "created_at", "updated_at"}
        return {col.name for col in model_class.__table__.columns if col.name not in auto}

    @staticmethod
    def _ensure_utf8_string(value: str) -> str:
        """确保字符串是有效的 UTF-8 编码，如果不是则尝试从 GBK/GB2312 转换"""
        if not isinstance(value, str):
            return value
        try:
            # 尝试编码为 UTF-8 来验证
            value.encode('utf-8')
            return value
        except UnicodeEncodeError:
            try:
                # 尝试从 GBK/GB2312 解码并重新编码为 UTF-8
                return value.encode('latin-1').decode('gbk')
            except (UnicodeDecodeError, UnicodeEncodeError):
                # 如果都失败，替换无效字符
                return value.encode('latin-1', errors='replace').decode('utf-8', errors='replace')

    @staticmethod
    def _map_row(row: dict, mapping: dict) -> dict:
        """根据字段映射转换一行数据"""
        mapped = {}
        for key, value in row.items():
            target_key = mapping.get(key, key)
            if value is not None:
                if isinstance(value, datetime):
                    value = value.date()
                elif isinstance(value, str):
                    value = ERPSyncService._ensure_utf8_string(value)
                mapped[target_key] = value
        return mapped

    @staticmethod
    def _filter_model_fields(row_dict: dict, valid_columns: set) -> dict:
        """过滤掉不属于目标模型的字段，防止 ORM 构造报错"""
        return {k: v for k, v in row_dict.items() if k in valid_columns}

    @staticmethod
    def _coerce_row_types(row_dict: dict, model_class) -> dict:
        """
        根据 ORM 模型列类型强制转换值类型
        防止 asyncpg 严格类型检查报错（如 int 传给 VARCHAR 列）
        """
        from sqlalchemy import String, Numeric, Date, Integer, Float, Boolean
        col_map = {col.name: col for col in model_class.__table__.columns}
        coerced = {}
        for k, v in row_dict.items():
            if v is None:
                coerced[k] = v
                continue
            col = col_map.get(k)
            if col is None:
                coerced[k] = v
                continue
            col_type = type(col.type)
            try:
                if col_type is String and not isinstance(v, str):
                    coerced[k] = str(v)
                elif col_type in (Numeric, Float) and not isinstance(v, (int, float)):
                    coerced[k] = float(v)
                elif col_type is Integer and not isinstance(v, int):
                    coerced[k] = int(v)
                elif col_type is Date and isinstance(v, str):
                    coerced[k] = datetime.strptime(v, "%Y-%m-%d").date() if v else None
                elif col_type is Boolean and not isinstance(v, bool):
                    coerced[k] = bool(v)
                else:
                    coerced[k] = v
            except (ValueError, TypeError):
                coerced[k] = v
        return coerced

    # ------------------------------------------------------------------
    # 订单数据同步
    # ------------------------------------------------------------------
    async def sync_orders(
        self,
        since: Optional[datetime] = None,
        order_numbers: Optional[list[str]] = None,
        custom_params: Optional[dict] = None
    ) -> dict:
        """
        同步订单行数据

        Args:
            since: 同步指定时间之后的数据
            order_numbers: 只同步指定订单（如果提供，忽略since参数）
            custom_params: 自定义条件参数（用于SQL中的条件筛选）
        """
        stats = {"synced": 0, "created": 0, "updated": 0, "skipped": 0, "errors": []}

        try:
            await self._connect_erp()
            sql_text, mapping = await self._load_sql_config("orders")

            # 构建查询参数 — 始终提供 :since 以防 SQL 中引用了该占位符
            if since is None:
                since = datetime.now() - timedelta(hours=24)
            params: dict = {"since": since}

            if order_numbers:
                # 转义单引号防止 SQL 注入
                safe_nos = [no.replace("'", "''") for no in order_numbers if no.strip()]
                order_list_str = ",".join([f"'{no}'" for no in safe_nos])
                
                # 查找真正的 ORDER BY 子句位置（不在括号内的）
                order_by_pos = -1
                paren_depth = 0
                for i in range(len(sql_text) - 8):
                    if sql_text[i] == '(':
                        paren_depth += 1
                    elif sql_text[i] == ')':
                        paren_depth -= 1
                    elif paren_depth == 0 and sql_text[i:i+9].upper() == "ORDER BY ":
                        order_by_pos = i
                        break
                
                condition = f"FContractNo IN ({order_list_str})"
                if order_by_pos > 0:
                    # 在 ORDER BY 之前插入条件
                    if "WHERE" in sql_text[:order_by_pos].upper() or "where" in sql_text[:order_by_pos]:
                        # 已有 WHERE 子句
                        sql_text = sql_text[:order_by_pos] + f" AND {condition} " + sql_text[order_by_pos:]
                    else:
                        # 无 WHERE 子句
                        sql_text = sql_text[:order_by_pos] + f" WHERE {condition} " + sql_text[order_by_pos:]
                else:
                    # 没有 ORDER BY 子句，直接追加
                    if "WHERE" in sql_text.upper() or "where" in sql_text:
                        sql_text += f" AND {condition}"
                    else:
                        sql_text += f" WHERE {condition}"
                logger.info(f"按订单筛选同步: {order_numbers}，SQL 添加条件: {condition}")

            # 添加自定义参数
            if custom_params:
                params.update(custom_params)
                logger.info(f"使用自定义参数: {custom_params}")

            rows = await self._execute_erp_sql(sql_text, params)
            print(f"ERP数据：{rows}")
            logger.info(f"从 ERP 获取到 {len(rows)} 条订单记录")
            valid_cols = self._get_model_columns(SaleOrder)

            for row in rows:
                try:
                    row_dict = self._map_row(row, mapping)
                    order_no = str(row_dict.get("order_no", "")).strip()
                    line_no = str(row_dict.get("line_no", "")).strip()

                    if not order_no:
                        stats["skipped"] += 1
                        continue

                    # 如果 line_no 为空，设置默认值
                    if not line_no:
                        line_no = "10"
                        row_dict["line_no"] = line_no

                    # 只保留模型字段 + 类型强转
                    row_dict = self._filter_model_fields(row_dict, valid_cols)
                    row_dict = self._coerce_row_types(row_dict, SaleOrder)

                    result = await self.spc_db.execute(
                        select(SaleOrder).where(
                            SaleOrder.order_no == order_no,
                        )
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        if getattr(existing, "data_source", None) in ("erp", None, ""):
                            for k, v in row_dict.items():
                                if k == "order_no":
                                    continue
                                if getattr(existing, k, None) != v and v is not None:
                                    setattr(existing, k, v)
                            if hasattr(existing, "data_source"):
                                existing.data_source = "erp"
                            stats["updated"] += 1
                        else:
                            stats["skipped"] += 1
                    else:
                        order = SaleOrder(**row_dict)
                        if hasattr(order, "data_source"):
                            order.data_source = "erp"
                        self.spc_db.add(order)
                        stats["created"] += 1

                    stats["synced"] += 1
                except Exception as e:
                    await self.spc_db.rollback()
                    stats["errors"].append(f"订单 {row_dict.get('order_no')}-{row_dict.get('line_no')}: {e}")

            await self.spc_db.flush()
            logger.info(f"订单同步完成: {stats}")

        except Exception as e:
            stats["errors"].append(str(e))
            logger.exception(f"订单同步异常: {e}")
        finally:
            self._close_erp(keep_alive=True)

        return stats

    # ------------------------------------------------------------------
    # 订单明细同步
    # ------------------------------------------------------------------
    async def sync_order_details(
        self,
        since: Optional[datetime] = None,
        custom_params: Optional[dict] = None
    ) -> dict:
        """同步订单明细行数据到 SaleOrderLine"""
        stats = {"synced": 0, "created": 0, "updated": 0, "skipped": 0, "errors": []}

        try:
            await self._connect_erp()
            sql_text, mapping = await self._load_sql_config("order_details")

            if since is None:
                since = datetime.now() - timedelta(hours=24)
            params: dict = {"since": since}

            if custom_params:
                params.update(custom_params)

            rows = await self._execute_erp_sql(sql_text, params)
            logger.info(f"从 ERP 获取到 {len(rows)} 条订单明细记录")
            valid_cols = self._get_model_columns(SaleOrderLine)

            for row in rows:
                try:
                    row_dict = self._map_row(row, mapping)
                    order_no = str(row_dict.get("order_no", "")).strip()
                    line_no = str(row_dict.get("line_no", "")).strip()
                    erp_line_id = str(row_dict.get("erp_line_id", "")).strip()

                    if not order_no:
                        stats["skipped"] += 1
                        continue
                    if not erp_line_id:
                        stats["skipped"] += 1
                        logger.warning(f"订单明细缺少 erp_line_id，跳过: {order_no}")
                        continue
                    if not line_no:
                        line_no = "10"
                        row_dict["line_no"] = line_no

                    # 查找关联的 SaleOrder 以获取 sale_order_id
                    sale_order_result = await self.spc_db.execute(
                        select(SaleOrder).where(SaleOrder.order_no == order_no).limit(1)
                    )
                    sale_order = sale_order_result.scalar_one_or_none()
                    if not sale_order:
                        stats["skipped"] += 1
                        continue
                    row_dict["sale_order_id"] = sale_order.id

                    row_dict = self._filter_model_fields(row_dict, valid_cols)
                    row_dict = self._coerce_row_types(row_dict, SaleOrderLine)

                    # 使用正确的唯一约束字段 erp_line_id 查询
                    result = await self.spc_db.execute(
                        select(SaleOrderLine).where(
                            SaleOrderLine.order_no == order_no,
                            SaleOrderLine.erp_line_id == erp_line_id,
                        )
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        for k, v in row_dict.items():
                            if k in ("order_no", "erp_line_id"):
                                continue
                            if getattr(existing, k, None) != v and v is not None:
                                setattr(existing, k, v)
                        stats["updated"] += 1
                    else:
                        line = SaleOrderLine(**row_dict)
                        self.spc_db.add(line)
                        stats["created"] += 1

                    stats["synced"] += 1
                except Exception as e:
                    await self.spc_db.rollback()
                    stats["errors"].append(f"订单明细 {row_dict.get('order_no')}-{row_dict.get('erp_line_id')}: {e}")

            await self.spc_db.flush()
            logger.info(f"订单明细同步完成: {stats}")

        except Exception as e:
            stats["errors"].append(str(e))
            logger.exception(f"订单明细同步异常: {e}")
        finally:
            self._close_erp(keep_alive=True)

        return stats

    # ------------------------------------------------------------------
    # 物料需求同步
    # ------------------------------------------------------------------
    async def sync_materials(
        self,
        since: Optional[datetime] = None,
        order_numbers: Optional[list[str]] = None,
        custom_params: Optional[dict] = None
    ) -> dict:
        """
        同步物料需求数据

        Args:
            since: 同步指定时间之后的数据
            order_numbers: 只同步指定订单的物料需求（如果提供，忽略since参数）
            custom_params: 自定义条件参数（用于SQL中的条件筛选）
        """
        stats = {"synced": 0, "created": 0, "updated": 0, "skipped": 0, "errors": []}

        try:
            await self._connect_erp()
            sql_text, mapping = await self._load_sql_config("materials")

            # 构建查询参数 — 始终提供 :since 以防 SQL 中引用了该占位符
            if since is None:
                since = datetime.now() - timedelta(hours=24)
            params: dict = {"since": since}

            if order_numbers:
                # 转义单引号防止 SQL 注入
                safe_nos = [no.replace("'", "''") for no in order_numbers if no.strip()]
                order_list_str = ",".join([f"'{no}'" for no in safe_nos])
                
                # 查找真正的 ORDER BY 子句位置（不在括号内的）
                order_by_pos = -1
                paren_depth = 0
                for i in range(len(sql_text) - 8):
                    if sql_text[i] == '(':
                        paren_depth += 1
                    elif sql_text[i] == ')':
                        paren_depth -= 1
                    elif paren_depth == 0 and sql_text[i:i+9].upper() == "ORDER BY ":
                        order_by_pos = i
                        break
                
                condition = f"FContractNo IN ({order_list_str})"
                if order_by_pos > 0:
                    # 在 ORDER BY 之前插入条件
                    if "WHERE" in sql_text[:order_by_pos].upper() or "where" in sql_text[:order_by_pos]:
                        # 已有 WHERE 子句
                        sql_text = sql_text[:order_by_pos] + f" AND {condition} " + sql_text[order_by_pos:]
                    else:
                        # 无 WHERE 子句
                        sql_text = sql_text[:order_by_pos] + f" WHERE {condition} " + sql_text[order_by_pos:]
                else:
                    # 没有 ORDER BY 子句，直接追加
                    if "WHERE" in sql_text.upper() or "where" in sql_text:
                        sql_text += f" AND {condition}"
                    else:
                        sql_text += f" WHERE {condition}"
                logger.info(f"按订单筛选同步: {order_numbers}，SQL 添加条件: {condition}")

            # 添加自定义参数
            if custom_params:
                params.update(custom_params)
                logger.info(f"使用自定义参数: {custom_params}")

            rows = await self._execute_erp_sql(sql_text, params)
            logger.info(f"从 ERP 获取到 {len(rows)} 条物料需求记录")
            valid_cols = self._get_model_columns(MaterialDemand)

            for row in rows:
                try:
                    row_dict = self._map_row(row, mapping)
                    order_no = str(row_dict.get("order_no", "")).strip()
                    line_no = str(row_dict.get("line_no", "")).strip()
                    material_code = str(row_dict.get("material_code", "")).strip()

                    if not order_no or not line_no or not material_code:
                        stats["skipped"] += 1
                        continue

                    # 计算欠料
                    req_qty = float(row_dict.get("req_qty") or 0)
                    allocated_qty = float(row_dict.get("allocated_qty") or 0)
                    shortage_qty = max(0, req_qty - allocated_qty)
                    row_dict["shortage_qty"] = shortage_qty
                    row_dict["shortage_flag"] = shortage_qty > 0

                    # 只保留模型字段 + 类型强转
                    row_dict = self._filter_model_fields(row_dict, valid_cols)
                    row_dict = self._coerce_row_types(row_dict, MaterialDemand)

                    result = await self.spc_db.execute(
                        select(MaterialDemand).where(
                            MaterialDemand.order_no == order_no,
                            MaterialDemand.line_no == line_no,
                            MaterialDemand.material_code == material_code,
                        )
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        if getattr(existing, "data_source", None) in ("erp", None, ""):
                            for k, v in row_dict.items():
                                if k in ("order_no", "line_no", "material_code"):
                                    continue
                                if v is not None:
                                    setattr(existing, k, v)
                            if hasattr(existing, "data_source"):
                                existing.data_source = "erp"
                            stats["updated"] += 1
                        else:
                            stats["skipped"] += 1
                    else:
                        # 检查关联订单是否存在
                        order_exists = await self.spc_db.execute(
                            select(SaleOrder).where(
                                SaleOrder.order_no == order_no,
                                SaleOrder.line_no == line_no,
                            )
                        )
                        if not order_exists.scalar_one_or_none():
                            stats["skipped"] += 1
                            continue
                        demand = MaterialDemand(**row_dict)
                        if hasattr(demand, "data_source"):
                            demand.data_source = "erp"
                        self.spc_db.add(demand)
                        stats["created"] += 1

                    stats["synced"] += 1
                except Exception as e:
                    await self.spc_db.rollback()
                    stats["errors"].append(f"物料 {row_dict.get('material_code')}: {e}")

            await self.spc_db.flush()
            logger.info(f"物料需求同步完成: {stats}")

        except Exception as e:
            stats["errors"].append(str(e))
            logger.exception(f"物料需求同步异常: {e}")
        finally:
            self._close_erp(keep_alive=True)

        return stats

    # ------------------------------------------------------------------
    # 采购订单同步
    # ------------------------------------------------------------------
    async def sync_purchase_orders(self, since: Optional[datetime] = None, custom_params: Optional[dict] = None) -> dict:
        """同步采购订单数据"""
        stats = {"synced": 0, "created": 0, "updated": 0, "skipped": 0, "errors": []}

        try:
            await self._connect_erp()
            sql_text, mapping = await self._load_sql_config("purchase_orders")

            if since is None:
                since = datetime.now() - timedelta(hours=24)

            params = {"since": since}
            if custom_params:
                params.update(custom_params)
                logger.info(f"使用自定义参数: {custom_params}")

            rows = await self._execute_erp_sql(sql_text, params)
            logger.info(f"从 ERP 获取到 {len(rows)} 条采购订单记录")
            valid_cols = self._get_model_columns(PurchaseOrder)

            for row in rows:
                try:
                    row_dict = self._map_row(row, mapping)
                    po_no = str(row_dict.get("po_no", "")).strip()
                    if not po_no:
                        stats["skipped"] += 1
                        continue

                    # 只保留模型字段 + 类型强转
                    row_dict = self._filter_model_fields(row_dict, valid_cols)
                    row_dict = self._coerce_row_types(row_dict, PurchaseOrder)

                    # 设置必填字段的默认值
                    if not row_dict.get("po_status"):
                        row_dict["po_status"] = "placed"
                    if not row_dict.get("detail_id"):
                        row_dict["detail_id"] = 1
                    detail_id = row_dict.get("detail_id", 1)

                    result = await self.spc_db.execute(
                        select(PurchaseOrder).where(
                            PurchaseOrder.po_no == po_no,
                            PurchaseOrder.detail_id == detail_id,
                        )
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        if getattr(existing, "data_source", None) in ("erp", None, ""):
                            old_eta = existing.eta
                            for k, v in row_dict.items():
                                if k == "po_no":
                                    continue
                                if getattr(existing, k, None) != v and v is not None:
                                    setattr(existing, k, v)
                            if hasattr(existing, "data_source"):
                                existing.data_source = "erp"
                            # ETA 变更记录
                            new_eta = existing.eta
                            if old_eta and new_eta and old_eta != new_eta:
                                from app.models.order.eta_update import ETAUpdate
                                self.spc_db.add(ETAUpdate(
                                    po_no=po_no, old_eta=old_eta, new_eta=new_eta,
                                    updater="erp_sync", update_reason="ERP 数据同步更新",
                                ))
                            stats["updated"] += 1
                        else:
                            stats["skipped"] += 1
                    else:
                        po = PurchaseOrder(**row_dict)
                        if not po.original_eta and po.eta:
                            po.original_eta = po.eta
                        if hasattr(po, "data_source"):
                            po.data_source = "erp"
                        self.spc_db.add(po)
                        stats["created"] += 1

                    stats["synced"] += 1
                except Exception as e:
                    await self.spc_db.rollback()
                    stats["errors"].append(f"PO {row_dict.get('po_no')}: {e}")

            await self.spc_db.flush()
            logger.info(f"采购订单同步完成: {stats}")

        except Exception as e:
            stats["errors"].append(str(e))
            logger.exception(f"采购订单同步异常: {e}")
        finally:
            self._close_erp(keep_alive=True)

        return stats

    # ------------------------------------------------------------------
    # 客户主数据同步
    # ------------------------------------------------------------------
    async def sync_customers(self, since: Optional[datetime] = None, custom_params: Optional[dict] = None) -> dict:
        """同步客户主数据"""
        stats = {"synced": 0, "created": 0, "updated": 0, "skipped": 0, "errors": []}

        try:
            await self._connect_erp()
            sql_text, mapping = await self._load_sql_config("customers")

            if since is None:
                since = datetime.now() - timedelta(hours=24)

            params = {"since": since}
            if custom_params:
                params.update(custom_params)
                logger.info(f"使用自定义参数: {custom_params}")

            rows = await self._execute_erp_sql(sql_text, params)
            logger.info(f"从 ERP 获取到 {len(rows)} 条客户记录")
            valid_cols = self._get_model_columns(Customer)

            for row in rows:
                try:
                    row_dict = self._map_row(row, mapping)
                    customer_code = str(row_dict.get("customer_code", "")).strip()
                    if not customer_code:
                        stats["skipped"] += 1
                        continue

                    # 只保留模型字段 + 类型强转
                    row_dict = self._filter_model_fields(row_dict, valid_cols)
                    row_dict = self._coerce_row_types(row_dict, Customer)

                    result = await self.spc_db.execute(
                        select(Customer).where(Customer.customer_code == customer_code)
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        if getattr(existing, "data_source", None) in ("erp", None, ""):
                            for k, v in row_dict.items():
                                if k == "customer_code":
                                    continue
                                if getattr(existing, k, None) != v and v is not None:
                                    setattr(existing, k, v)
                            if hasattr(existing, "data_source"):
                                existing.data_source = "erp"
                            stats["updated"] += 1
                        else:
                            stats["skipped"] += 1
                    else:
                        customer = Customer(**row_dict)
                        if hasattr(customer, "data_source"):
                            customer.data_source = "erp"
                        self.spc_db.add(customer)
                        stats["created"] += 1

                    stats["synced"] += 1
                except Exception as e:
                    await self.spc_db.rollback()
                    stats["errors"].append(f"客户 {row_dict.get('customer_code')}: {e}")

            await self.spc_db.flush()
            logger.info(f"客户主数据同步完成: {stats}")

        except Exception as e:
            stats["errors"].append(str(e))
            logger.exception(f"客户主数据同步异常: {e}")
        finally:
            self._close_erp(keep_alive=True)

        return stats

    # ------------------------------------------------------------------
    # 供应商主数据同步
    # ------------------------------------------------------------------
    async def sync_suppliers(self, since: Optional[datetime] = None, custom_params: Optional[dict] = None) -> dict:
        """同步供应商主数据"""
        stats = {"synced": 0, "created": 0, "updated": 0, "skipped": 0, "errors": []}

        try:
            await self._connect_erp()
            sql_text, mapping = await self._load_sql_config("suppliers")

            if since is None:
                since = datetime.now() - timedelta(hours=24)

            params = {"since": since}
            if custom_params:
                params.update(custom_params)
                logger.info(f"使用自定义参数: {custom_params}")

            rows = await self._execute_erp_sql(sql_text, params)
            logger.info(f"从 ERP 获取到 {len(rows)} 条供应商记录")
            valid_cols = self._get_model_columns(Supplier)

            for row in rows:
                try:
                    row_dict = self._map_row(row, mapping)
                    supplier_code = str(row_dict.get("supplier_code", "")).strip()
                    if not supplier_code:
                        stats["skipped"] += 1
                        continue

                    row_dict = self._filter_model_fields(row_dict, valid_cols)
                    row_dict = self._coerce_row_types(row_dict, Supplier)

                    result = await self.spc_db.execute(
                        select(Supplier).where(Supplier.supplier_code == supplier_code)
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        if getattr(existing, "data_source", None) in ("erp", None, ""):
                            for k, v in row_dict.items():
                                if k == "supplier_code":
                                    continue
                                if getattr(existing, k, None) != v and v is not None:
                                    setattr(existing, k, v)
                            if hasattr(existing, "data_source"):
                                existing.data_source = "erp"
                            stats["updated"] += 1
                        else:
                            stats["skipped"] += 1
                    else:
                        supplier = Supplier(**row_dict)
                        if hasattr(supplier, "data_source"):
                            supplier.data_source = "erp"
                        self.spc_db.add(supplier)
                        stats["created"] += 1

                    stats["synced"] += 1
                except Exception as e:
                    await self.spc_db.rollback()
                    stats["errors"].append(f"供应商 {row_dict.get('supplier_code')}: {e}")

            await self.spc_db.flush()
            logger.info(f"供应商主数据同步完成: {stats}")

        except Exception as e:
            stats["errors"].append(str(e))
            logger.exception(f"供应商主数据同步异常: {e}")
        finally:
            self._close_erp(keep_alive=True)

        return stats

    # ------------------------------------------------------------------
    # 物料主数据同步
    # ------------------------------------------------------------------
    async def sync_materials_masterdata(self, since: Optional[datetime] = None, custom_params: Optional[dict] = None) -> dict:
        """同步物料主数据"""
        stats = {"synced": 0, "created": 0, "updated": 0, "skipped": 0, "errors": []}

        try:
            await self._connect_erp()
            sql_text, mapping = await self._load_sql_config("materials_masterdata")

            if since is None:
                since = datetime.now() - timedelta(hours=24)

            params = {"since": since}
            if custom_params:
                params.update(custom_params)
                logger.info(f"使用自定义参数: {custom_params}")

            rows = await self._execute_erp_sql(sql_text, params)
            logger.info(f"从 ERP 获取到 {len(rows)} 条物料主数据记录")
            valid_cols = self._get_model_columns(Material)

            for row in rows:
                try:
                    row_dict = self._map_row(row, mapping)
                    material_code = str(row_dict.get("material_code", "")).strip()
                    if not material_code:
                        stats["skipped"] += 1
                        continue

                    row_dict = self._filter_model_fields(row_dict, valid_cols)
                    row_dict = self._coerce_row_types(row_dict, Material)

                    # ERP 数据可能缺少 NOT NULL 字段，填充默认值
                    row_dict.setdefault("material_type", row_dict.get("material_type") or "未分类")
                    row_dict.setdefault("unit_of_measure", row_dict.get("unit_of_measure") or "个")

                    result = await self.spc_db.execute(
                        select(Material).where(Material.material_code == material_code)
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        if getattr(existing, "data_source", None) in ("erp", None, ""):
                            for k, v in row_dict.items():
                                if k == "material_code":
                                    continue
                                if getattr(existing, k, None) != v and v is not None:
                                    setattr(existing, k, v)
                            if hasattr(existing, "data_source"):
                                existing.data_source = "erp"
                            stats["updated"] += 1
                        else:
                            stats["skipped"] += 1
                    else:
                        material = Material(**row_dict)
                        if hasattr(material, "data_source"):
                            material.data_source = "erp"
                        self.spc_db.add(material)
                        stats["created"] += 1

                    stats["synced"] += 1
                except Exception as e:
                    await self.spc_db.rollback()
                    stats["errors"].append(f"物料 {row_dict.get('material_code')}: {e}")

            await self.spc_db.flush()
            logger.info(f"物料主数据同步完成: {stats}")

        except Exception as e:
            stats["errors"].append(str(e))
            logger.exception(f"物料主数据同步异常: {e}")
        finally:
            self._close_erp(keep_alive=True)

        return stats

    # ------------------------------------------------------------------
    # SKU主数据同步
    # ------------------------------------------------------------------
    async def sync_skus(self, since: Optional[datetime] = None, custom_params: Optional[dict] = None) -> dict:
        """同步SKU主数据"""
        stats = {"synced": 0, "created": 0, "updated": 0, "skipped": 0, "errors": []}

        try:
            await self._connect_erp()
            sql_text, mapping = await self._load_sql_config("skus")

            if since is None:
                since = datetime.now() - timedelta(hours=24)

            params = {"since": since}
            if custom_params:
                params.update(custom_params)
                logger.info(f"使用自定义参数: {custom_params}")

            rows = await self._execute_erp_sql(sql_text, params)
            logger.info(f"从 ERP 获取到 {len(rows)} 条SKU记录")
            valid_cols = self._get_model_columns(SKU)

            for row in rows:
                try:
                    row_dict = self._map_row(row, mapping)
                    sku_code = str(row_dict.get("sku_code", "")).strip()
                    if not sku_code:
                        stats["skipped"] += 1
                        continue

                    row_dict = self._filter_model_fields(row_dict, valid_cols)
                    row_dict = self._coerce_row_types(row_dict, SKU)

                    result = await self.spc_db.execute(
                        select(SKU).where(SKU.sku_code == sku_code)
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        if getattr(existing, "data_source", None) in ("erp", None, ""):
                            for k, v in row_dict.items():
                                if k == "sku_code":
                                    continue
                                if getattr(existing, k, None) != v and v is not None:
                                    setattr(existing, k, v)
                            if hasattr(existing, "data_source"):
                                existing.data_source = "erp"
                            stats["updated"] += 1
                        else:
                            stats["skipped"] += 1
                    else:
                        sku = SKU(**row_dict)
                        if hasattr(sku, "data_source"):
                            sku.data_source = "erp"
                        self.spc_db.add(sku)
                        stats["created"] += 1

                    stats["synced"] += 1
                except Exception as e:
                    await self.spc_db.rollback()
                    stats["errors"].append(f"SKU {row_dict.get('sku_code')}: {e}")

            await self.spc_db.flush()
            logger.info(f"SKU主数据同步完成: {stats}")

        except Exception as e:
            stats["errors"].append(str(e))
            logger.exception(f"SKU主数据同步异常: {e}")
        finally:
            self._close_erp(keep_alive=True)

        return stats

    # ------------------------------------------------------------------
    # 产品主数据同步
    # ------------------------------------------------------------------
    async def sync_products(self, since: Optional[datetime] = None, custom_params: Optional[dict] = None) -> dict:
        """同步产品主数据"""
        stats = {"synced": 0, "created": 0, "updated": 0, "skipped": 0, "errors": []}

        try:
            await self._connect_erp()
            sql_text, mapping = await self._load_sql_config("products")

            if since is None:
                since = datetime.now() - timedelta(hours=24)

            params = {"since": since}
            if custom_params:
                params.update(custom_params)
                logger.info(f"使用自定义参数: {custom_params}")

            rows = await self._execute_erp_sql(sql_text, params)
            logger.info(f"从 ERP 获取到 {len(rows)} 条产品记录")
            valid_cols = self._get_model_columns(Product)

            for row in rows:
                try:
                    row_dict = self._map_row(row, mapping)
                    product_code = str(row_dict.get("product_code", "")).strip()
                    if not product_code:
                        stats["skipped"] += 1
                        continue

                    row_dict = self._filter_model_fields(row_dict, valid_cols)
                    row_dict = self._coerce_row_types(row_dict, Product)

                    result = await self.spc_db.execute(
                        select(Product).where(Product.product_code == product_code)
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        if getattr(existing, "data_source", None) in ("erp", None, ""):
                            for k, v in row_dict.items():
                                if k == "product_code":
                                    continue
                                if getattr(existing, k, None) != v and v is not None:
                                    setattr(existing, k, v)
                            if hasattr(existing, "data_source"):
                                existing.data_source = "erp"
                            stats["updated"] += 1
                        else:
                            stats["skipped"] += 1
                    else:
                        product = Product(**row_dict)
                        if hasattr(product, "data_source"):
                            product.data_source = "erp"
                        self.spc_db.add(product)
                        stats["created"] += 1

                    stats["synced"] += 1
                except Exception as e:
                    await self.spc_db.rollback()
                    stats["errors"].append(f"产品 {row_dict.get('product_code')}: {e}")

            await self.spc_db.flush()
            logger.info(f"产品主数据同步完成: {stats}")

        except Exception as e:
            stats["errors"].append(str(e))
            logger.exception(f"产品主数据同步异常: {e}")
        finally:
            self._close_erp(keep_alive=True)

        return stats

    # ------------------------------------------------------------------
    # 仓库主数据同步
    # ------------------------------------------------------------------
    async def sync_warehouses(self, since: Optional[datetime] = None, custom_params: Optional[dict] = None) -> dict:
        """同步仓库主数据"""
        stats = {"synced": 0, "created": 0, "updated": 0, "skipped": 0, "errors": []}

        try:
            await self._connect_erp()
            sql_text, mapping = await self._load_sql_config("warehouses")

            if since is None:
                since = datetime.now() - timedelta(hours=24)

            params = {"since": since}
            if custom_params:
                params.update(custom_params)
                logger.info(f"使用自定义参数: {custom_params}")

            rows = await self._execute_erp_sql(sql_text, params)
            logger.info(f"从 ERP 获取到 {len(rows)} 条仓库记录")
            valid_cols = self._get_model_columns(Warehouse)

            for row in rows:
                try:
                    row_dict = self._map_row(row, mapping)
                    wh_code = str(row_dict.get("wh_code", "")).strip()
                    if not wh_code:
                        stats["skipped"] += 1
                        continue

                    row_dict = self._filter_model_fields(row_dict, valid_cols)
                    row_dict = self._coerce_row_types(row_dict, Warehouse)

                    result = await self.spc_db.execute(
                        select(Warehouse).where(Warehouse.wh_code == wh_code)
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        if getattr(existing, "data_source", None) in ("erp", None, ""):
                            for k, v in row_dict.items():
                                if k == "wh_code":
                                    continue
                                if getattr(existing, k, None) != v and v is not None:
                                    setattr(existing, k, v)
                            if hasattr(existing, "data_source"):
                                existing.data_source = "erp"
                            stats["updated"] += 1
                        else:
                            stats["skipped"] += 1
                    else:
                        warehouse = Warehouse(**row_dict)
                        if hasattr(warehouse, "data_source"):
                            warehouse.data_source = "erp"
                        self.spc_db.add(warehouse)
                        stats["created"] += 1

                    stats["synced"] += 1
                except Exception as e:
                    await self.spc_db.rollback()
                    stats["errors"].append(f"仓库 {row_dict.get('wh_code')}: {e}")

            await self.spc_db.flush()
            logger.info(f"仓库主数据同步完成: {stats}")

        except Exception as e:
            stats["errors"].append(str(e))
            logger.exception(f"仓库主数据同步异常: {e}")
        finally:
            self._close_erp(keep_alive=True)

        return stats

    # ------------------------------------------------------------------
    # 工序主数据同步
    # ------------------------------------------------------------------
    async def sync_processes(self, since: Optional[datetime] = None, custom_params: Optional[dict] = None) -> dict:
        """同步工序主数据"""
        stats = {"synced": 0, "created": 0, "updated": 0, "skipped": 0, "errors": []}

        try:
            await self._connect_erp()
            sql_text, mapping = await self._load_sql_config("processes")

            if since is None:
                since = datetime.now() - timedelta(hours=24)

            params = {"since": since}
            if custom_params:
                params.update(custom_params)
                logger.info(f"使用自定义参数: {custom_params}")

            rows = await self._execute_erp_sql(sql_text, params)
            logger.info(f"从 ERP 获取到 {len(rows)} 条工序记录")
            valid_cols = self._get_model_columns(Process)

            for row in rows:
                try:
                    row_dict = self._map_row(row, mapping)
                    process_code = str(row_dict.get("process_code", "")).strip()
                    if not process_code:
                        stats["skipped"] += 1
                        continue

                    row_dict = self._filter_model_fields(row_dict, valid_cols)
                    row_dict = self._coerce_row_types(row_dict, Process)

                    result = await self.spc_db.execute(
                        select(Process).where(Process.process_code == process_code)
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        if getattr(existing, "data_source", None) in ("erp", None, ""):
                            for k, v in row_dict.items():
                                if k == "process_code":
                                    continue
                                if getattr(existing, k, None) != v and v is not None:
                                    setattr(existing, k, v)
                            if hasattr(existing, "data_source"):
                                existing.data_source = "erp"
                            stats["updated"] += 1
                        else:
                            stats["skipped"] += 1
                    else:
                        process = Process(**row_dict)
                        if hasattr(process, "data_source"):
                            process.data_source = "erp"
                        self.spc_db.add(process)
                        stats["created"] += 1

                    stats["synced"] += 1
                except Exception as e:
                    await self.spc_db.rollback()
                    stats["errors"].append(f"工序 {row_dict.get('process_code')}: {e}")

            await self.spc_db.flush()
            logger.info(f"工序主数据同步完成: {stats}")

        except Exception as e:
            stats["errors"].append(str(e))
            logger.exception(f"工序主数据同步异常: {e}")
        finally:
            self._close_erp(keep_alive=True)

        return stats

    # ------------------------------------------------------------------
    # 组织主数据同步
    # ------------------------------------------------------------------
    async def sync_organizations(self, since: Optional[datetime] = None, custom_params: Optional[dict] = None) -> dict:
        """同步组织主数据"""
        stats = {"synced": 0, "created": 0, "updated": 0, "skipped": 0, "errors": []}

        try:
            await self._connect_erp()
            sql_text, mapping = await self._load_sql_config("organizations")

            if since is None:
                since = datetime.now() - timedelta(hours=24)

            params = {"since": since}
            if custom_params:
                params.update(custom_params)
                logger.info(f"使用自定义参数: {custom_params}")

            rows = await self._execute_erp_sql(sql_text, params)
            logger.info(f"从 ERP 获取到 {len(rows)} 条组织记录")
            valid_cols = self._get_model_columns(Organization)

            for row in rows:
                try:
                    row_dict = self._map_row(row, mapping)
                    org_code = str(row_dict.get("org_code", "")).strip()
                    if not org_code:
                        stats["skipped"] += 1
                        continue

                    row_dict = self._filter_model_fields(row_dict, valid_cols)
                    row_dict = self._coerce_row_types(row_dict, Organization)

                    result = await self.spc_db.execute(
                        select(Organization).where(Organization.org_code == org_code)
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        if getattr(existing, "data_source", None) in ("erp", None, ""):
                            for k, v in row_dict.items():
                                if k == "org_code":
                                    continue
                                if getattr(existing, k, None) != v and v is not None:
                                    setattr(existing, k, v)
                            if hasattr(existing, "data_source"):
                                existing.data_source = "erp"
                            stats["updated"] += 1
                        else:
                            stats["skipped"] += 1
                    else:
                        organization = Organization(**row_dict)
                        if hasattr(organization, "data_source"):
                            organization.data_source = "erp"
                        self.spc_db.add(organization)
                        stats["created"] += 1

                    stats["synced"] += 1
                except Exception as e:
                    await self.spc_db.rollback()
                    stats["errors"].append(f"组织 {row_dict.get('org_code')}: {e}")

            await self.spc_db.flush()
            logger.info(f"组织主数据同步完成: {stats}")

        except Exception as e:
            stats["errors"].append(str(e))
            logger.exception(f"组织主数据同步异常: {e}")
        finally:
            self._close_erp(keep_alive=True)

        return stats

    # ------------------------------------------------------------------
    # 人员主数据同步
    # ------------------------------------------------------------------
    async def sync_employees(self, since: Optional[datetime] = None, custom_params: Optional[dict] = None) -> dict:
        """同步人员主数据"""
        stats = {"synced": 0, "created": 0, "updated": 0, "skipped": 0, "errors": []}

        try:
            await self._connect_erp()
            sql_text, mapping = await self._load_sql_config("employees")

            if since is None:
                since = datetime.now() - timedelta(hours=24)

            params = {"since": since}
            if custom_params:
                params.update(custom_params)
                logger.info(f"使用自定义参数: {custom_params}")

            rows = await self._execute_erp_sql(sql_text, params)
            logger.info(f"从 ERP 获取到 {len(rows)} 条人员记录")
            valid_cols = self._get_model_columns(Employee)

            for row in rows:
                try:
                    row_dict = self._map_row(row, mapping)
                    emp_code = str(row_dict.get("emp_code", "")).strip()
                    if not emp_code:
                        stats["skipped"] += 1
                        continue

                    row_dict = self._filter_model_fields(row_dict, valid_cols)
                    row_dict = self._coerce_row_types(row_dict, Employee)

                    result = await self.spc_db.execute(
                        select(Employee).where(Employee.emp_code == emp_code)
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        if getattr(existing, "data_source", None) in ("erp", None, ""):
                            for k, v in row_dict.items():
                                if k == "emp_code":
                                    continue
                                if getattr(existing, k, None) != v and v is not None:
                                    setattr(existing, k, v)
                            if hasattr(existing, "data_source"):
                                existing.data_source = "erp"
                            stats["updated"] += 1
                        else:
                            stats["skipped"] += 1
                    else:
                        employee = Employee(**row_dict)
                        if hasattr(employee, "data_source"):
                            employee.data_source = "erp"
                        self.spc_db.add(employee)
                        stats["created"] += 1

                    stats["synced"] += 1
                except Exception as e:
                    await self.spc_db.rollback()
                    stats["errors"].append(f"人员 {row_dict.get('emp_code')}: {e}")

            await self.spc_db.flush()
            logger.info(f"人员主数据同步完成: {stats}")

        except Exception as e:
            stats["errors"].append(str(e))
            logger.exception(f"人员主数据同步异常: {e}")
        finally:
            self._close_erp(keep_alive=True)

        return stats

    # ------------------------------------------------------------------
    # 采购开票同步
    # ------------------------------------------------------------------
    async def sync_purchase_invoices(
        self, since: Optional[datetime] = None, custom_params: Optional[dict] = None
    ) -> dict:
        """同步采购开票数据。幂等依据: (invoice_no, line_no) 复合唯一键。"""
        stats = {"synced": 0, "created": 0, "updated": 0, "skipped": 0, "errors": []}

        try:
            await self._connect_erp()
            sql_text, mapping = await self._load_sql_config("purchase_invoices")

            if since is None:
                since = datetime.now() - timedelta(hours=24)

            params = {"since": since}
            if custom_params:
                params.update(custom_params)
                logger.info(f"使用自定义参数: {custom_params}")

            rows = await self._execute_erp_sql(sql_text, params)
            logger.info(f"从 ERP 获取到 {len(rows)} 条采购开票记录")
            valid_cols = self._get_model_columns(PurchaseInvoice)

            for row in rows:
                row_dict: dict = {}
                try:
                    row_dict = self._map_row(row, mapping)
                    invoice_no = str(row_dict.get("invoice_no", "")).strip()
                    line_no = str(row_dict.get("line_no", "")).strip()
                    if not invoice_no or not line_no:
                        stats["skipped"] += 1
                        continue

                    # 统一类型
                    row_dict["invoice_no"] = invoice_no
                    row_dict["line_no"] = line_no
                    row_dict = self._filter_model_fields(row_dict, valid_cols)
                    row_dict = self._coerce_row_types(row_dict, PurchaseInvoice)

                    result = await self.spc_db.execute(
                        select(PurchaseInvoice).where(
                            PurchaseInvoice.invoice_no == invoice_no,
                            PurchaseInvoice.line_no == line_no,
                        )
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        for k, v in row_dict.items():
                            if k in ("invoice_no", "line_no"):
                                continue
                            if v is not None:
                                setattr(existing, k, v)
                        stats["updated"] += 1
                    else:
                        invoice = PurchaseInvoice(**row_dict)
                        self.spc_db.add(invoice)
                        stats["created"] += 1

                    stats["synced"] += 1
                except Exception as e:
                    await self.spc_db.rollback()
                    stats["errors"].append(
                        f"采购开票 {row_dict.get('invoice_no')}-{row_dict.get('line_no')}: {e}"
                    )

            await self.spc_db.flush()
            logger.info(f"采购开票同步完成: {stats}")

        except Exception as e:
            stats["errors"].append(str(e))
            logger.exception(f"采购开票同步异常: {e}")
        finally:
            self._close_erp(keep_alive=True)

        return stats

    # ------------------------------------------------------------------
    # 品质异常同步
    # ------------------------------------------------------------------
    async def sync_quality_issues(
        self, since: Optional[datetime] = None, custom_params: Optional[dict] = None
    ) -> dict:
        """同步品质异常数据。幂等依据: issue_no 唯一键。"""
        stats = {"synced": 0, "created": 0, "updated": 0, "skipped": 0, "errors": []}

        try:
            await self._connect_erp()
            sql_text, mapping = await self._load_sql_config("quality_issues")

            if since is None:
                since = datetime.now() - timedelta(hours=24)

            params = {"since": since}
            if custom_params:
                params.update(custom_params)
                logger.info(f"使用自定义参数: {custom_params}")

            rows = await self._execute_erp_sql(sql_text, params)
            logger.info(f"从 ERP 获取到 {len(rows)} 条品质异常记录")
            valid_cols = self._get_model_columns(QualityIssue)

            # 用于生成 issue_no 的计数器
            issue_counter = 0
            date_str = datetime.now().strftime("%Y%m%d")

            for row in rows:
                row_dict: dict = {}
                try:
                    row_dict = self._map_row(row, mapping)
                    logger.info(f"映射后数据: {row_dict}")
                    issue_no = str(row_dict.get("issue_no", "")).strip()
                    
                    # 如果 ERP 数据中没有 issue_no，自动生成
                    if not issue_no:
                        submit_date = row_dict.get("submit_date")
                        if submit_date:
                            date_str = str(submit_date).replace("-", "")
                        issue_counter += 1
                        issue_no = f"QI-{date_str}-{issue_counter:04d}"
                        logger.info(f"自动生成 issue_no: {issue_no}")
                    
                    row_dict["issue_no"] = issue_no
                    row_dict = self._filter_model_fields(row_dict, valid_cols)
                    logger.info(f"过滤后数据: {row_dict}")
                    if not row_dict:
                        logger.warning(f"跳过: 过滤后无有效字段, issue_no: {issue_no}")
                        stats["skipped"] += 1
                        continue
                    row_dict = self._coerce_row_types(row_dict, QualityIssue)
                    logger.info(f"类型强转后数据: {row_dict}")

                    result = await self.spc_db.execute(
                        select(QualityIssue).where(QualityIssue.issue_no == issue_no)
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        for k, v in row_dict.items():
                            if k == "issue_no":
                                continue
                            if v is not None:
                                setattr(existing, k, v)
                        stats["updated"] += 1
                    else:
                        qi = QualityIssue(**row_dict)
                        self.spc_db.add(qi)
                        stats["created"] += 1

                    stats["synced"] += 1
                except Exception as e:
                    await self.spc_db.rollback()
                    stats["errors"].append(
                        f"品质异常 {row_dict.get('issue_no')}: {e}"
                    )
                    logger.exception(f"处理品质异常失败: {row_dict}")

            await self.spc_db.flush()
            logger.info(f"品质异常同步完成: {stats}")

        except Exception as e:
            stats["errors"].append(str(e))
            logger.exception(f"品质异常同步异常: {e}")
        finally:
            self._close_erp(keep_alive=True)

        return stats

    # ------------------------------------------------------------------
    # 全量同步
    # ------------------------------------------------------------------
    async def sync_all(self, since: Optional[datetime] = None, custom_params: Optional[dict] = None) -> dict:
        """同步所有已配置的数据类型，复用单个 ERP 连接"""
        try:
            await self._connect_erp()
            results = {}
            results["orders"] = await self.sync_orders(since, None, custom_params)
            results["materials"] = await self.sync_materials(since, None, custom_params)
            results["purchase_orders"] = await self.sync_purchase_orders(since, custom_params)
            results["customers"] = await self.sync_customers(since, custom_params)
            results["suppliers"] = await self.sync_suppliers(since, custom_params)
            results["materials_masterdata"] = await self.sync_materials_masterdata(since, custom_params)
            results["skus"] = await self.sync_skus(since, custom_params)
            results["products"] = await self.sync_products(since, custom_params)
            results["warehouses"] = await self.sync_warehouses(since, custom_params)
            results["processes"] = await self.sync_processes(since, custom_params)
            results["organizations"] = await self.sync_organizations(since, custom_params)
            results["employees"] = await self.sync_employees(since, custom_params)
            results["purchase_invoices"] = await self.sync_purchase_invoices(since, custom_params)
            results["quality_issues"] = await self.sync_quality_issues(since, custom_params)
            return results
        finally:
            self._close_erp()
