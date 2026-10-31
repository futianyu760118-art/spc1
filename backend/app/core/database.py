from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()


def _connect_args() -> dict:
    # 空闲池连接可能被防火墙/NAT 静默丢弃：pre_ping；服务端兜底超时防止锁冲突/泄漏事务拖垮整库。
    return {
        "timeout": 10,
        "command_timeout": 600,
        "server_settings": {
            "lock_timeout": "15000",
            "idle_in_transaction_session_timeout": "300000",
            "statement_timeout": "600000",
        },
    }


# 主池服务读请求与一般请求；写路径独立池，避免读流量/慢查询把关键写请求饿死。
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=40,
    max_overflow=40,
    pool_timeout=30,
    pool_pre_ping=True,
    pool_recycle=settings.DB_POOL_RECYCLE,
    connect_args=_connect_args(),
)

write_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=5,
    pool_timeout=15,
    pool_pre_ping=True,
    pool_recycle=settings.DB_POOL_RECYCLE,
    connect_args=_connect_args(),
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

AsyncWriteSessionLocal = async_sessionmaker(
    write_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_write_db() -> AsyncSession:
    """关键写路径专用 session：独立连接池，避免被读流量/慢查询挤占。"""
    async with AsyncWriteSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_read_only_db() -> AsyncSession:
    """只读请求用的 db session：不 commit。

    - 远程 DB 单次 commit 网络往返 ~2 秒，只读请求白白浪费。
    - 这个依赖让"明确不写数据"的端点跳过 commit，把 2 秒缩到 ~0.1 秒。
    - 注意：使用这个依赖的端点必须保证不会修改任何 ORM 对象、不依赖事务兜底提交。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


import threading

_erp_write_lock = threading.Lock()
_erp_write_engine = None


def get_erp_write_engine():
    """ERP 写权限的同步 SQLAlchemy engine (pyodbc/psycopg2).

    Returns None if erp_db_url_write is not configured.
    """
    global _erp_write_engine
    if _erp_write_engine is not None:
        return _erp_write_engine
    with _erp_write_lock:
        if _erp_write_engine is not None:
            return _erp_write_engine
        from app.core.config import get_settings
        url = get_settings().erp_db_url_write
        if not url:
            return None
        from sqlalchemy import create_engine
        _erp_write_engine = create_engine(url, pool_pre_ping=True, pool_recycle=3600)
        return _erp_write_engine
