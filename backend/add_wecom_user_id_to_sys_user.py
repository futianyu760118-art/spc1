"""一次性迁移脚本：为 sys_user 增加 wecom_user_id 列与部分唯一索引。

用途：在运行中的数据库上立即应用「企业微信账号绑定」所需的 schema 变更，
无需重启容器（init_database.py 仅在容器启动时执行）。

幂等：所有 DDL 均带 IF NOT EXISTS，可重复执行。

用法（在 backend/ 目录下运行）：
    python add_wecom_user_id_to_sys_user.py

DB 连接串来自 app.core.config.Settings.DATABASE_URL_SYNC，不在脚本中硬编码凭据。
"""
from __future__ import annotations

from sqlalchemy import create_engine, text

from app.core.config import get_settings


COLUMN_DDL = "ALTER TABLE sys_user ADD COLUMN IF NOT EXISTS wecom_user_id VARCHAR(64)"
INDEX_DDL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_sys_user_wecom_user_id "
    "ON sys_user (wecom_user_id) WHERE wecom_user_id IS NOT NULL"
)
NEW_REVISION = "add_wecom_user_id_to_sys_user"
PARENT_REVISION = "add_is_default_password"


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL_SYNC)

    with engine.begin() as conn:
        conn.execute(text(COLUMN_DDL))
        print("[1/2] OK  sys_user.wecom_user_id column ensured")
        conn.execute(text(INDEX_DDL))
        print("[2/2] OK  ux_sys_user_wecom_user_id unique index ensured")

    # 可选：推进 Alembic 版本号。仅当当前 alembic_version 正好处于直接父修订时才推进，
    # 避免在多 head 图中破坏既有版本状态。
    with engine.connect() as conn:
        try:
            current = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
        except Exception as e:
            current = []
            print(f"      --  跳过 alembic 版本推进（alembic_version 读取失败: {e}）")

    if current:
        versions = [row[0] for row in current]
        if PARENT_REVISION in versions:
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM alembic_version"))
                conn.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                    {"v": NEW_REVISION},
                )
            print(f"      OK  alembic_version: {PARENT_REVISION} -> {NEW_REVISION}")
        else:
            print(
                f"      --  跳过 alembic 版本推进（当前 {versions} 非直接父修订 {PARENT_REVISION}）。"
                f"DDL 已生效；如需可手动执行: alembic stamp {NEW_REVISION}"
            )

    engine.dispose()
    print("Done.")


if __name__ == "__main__":
    main()
