from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache

# config.py 位于 backend/app/core/，项目根目录为其上三级
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILES = (
    _PROJECT_ROOT / ".env.local",
    _PROJECT_ROOT / ".env",
    Path(".env.local"),
    Path(".env"),
)


class Settings(BaseSettings):
    PROJECT_NAME: str = "供应链与生产协同中台"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api/v1"

    # Database（默认值仅为占位符；真实连接串必须由 .env / 环境变量注入）
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/spc_db"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/spc_db"
    # 远程 DB 空闲连接会被防火墙/NAT 静默掐断(无 RST),必须 recycle+pre_ping 双保险
    DB_POOL_RECYCLE: int = 180

    # 后端服务实例标识（同步日志溯源）；空则回退 hostname
    SERVER_ID: str = ""

    # ERP 中间库连接（只读）
    ERP_DB_URL: str = ""  # e.g. "mssql+pyodbc://user:pass@host/erp_db?driver=ODBC+Driver+17+for+SQL+Server"
    ERP_DB_SCHEMA: str = "dbo"  # ERP 中间表所在 schema
    ERP_SYNC_BATCH_SIZE: int = 500  # 每批次同步条数
    ERP_SYNC_QUERY_TIMEOUT: int = 600  # 单次 ERP 查询超时(秒)，防止无限挂起
    ERP_SYNC_ENABLED: bool = False  # 是否启用 ERP 同步
    ERP_SYNC_DEFAULT_PASSWORD: str = "admin123"  # 自动创建用户的默认密码
    # K3 账套(链接服务器四段名前缀)。同步/读取(盘点单导入预览、物料单位等)用 K3_DB,
    # 默认生产账套; 回写用 K3_WRITE_DB, 留空(或空串)回落 K3_DB。
    # 测试验证期可保持同步读生产、只把回写指到测试账套:
    #   K3_DB=k3sv.AIS20161019115614
    #   K3_WRITE_DB=k3sv.AIS20240905142145
    K3_DB: str = "k3sv.AIS20161019115614"
    K3_WRITE_DB: Optional[str] = None
    UPPH_MATCH_MODE: str="bom_code"

    erp_db_url_write: Optional[str] = None
    writeback_enabled: bool = True
    writeback_poll_interval: int = 5
    writeback_batch_size: int = 20
    writeback_claim_timeout: int = 120

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Cache
    DASHBOARD_CACHE_TTL: int = 300  # 5 minutes

    # File storage
    STORAGE_BACKEND: str = "local"  # local / s3
    STORAGE_LOCAL_ROOT: str = "/app/uploads"
    BACKUP_DIR: str = "/app/backups"
    STORAGE_LOCAL_URL_PREFIX: str = "/uploads"
    STORAGE_MAX_FILE_SIZE: int = 100 * 1024 * 1024  # 100MB
    STORAGE_ALLOWED_MIMES: list[str] = [
        "image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp", "image/bmp",
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/zip",
        "application/x-zip-compressed",
        "application/x-rar-compressed",
        "text/plain",
        "text/csv",
    ]
    # S3 / MinIO（STORAGE_BACKEND=s3 时生效）
    STORAGE_S3_ENDPOINT: str = ""          # 不含协议头，例: minio:9000（compose 内）或 192.168.1.10:19000（跨机）
    STORAGE_S3_BUCKET: str = "spc-files"
    STORAGE_S3_ACCESS_KEY: str = ""
    STORAGE_S3_SECRET_KEY: str = ""
    STORAGE_S3_REGION: str = ""
    STORAGE_S3_SECURE: bool = False        # MinIO 内网 http 保持 False

    # AI Service
    AI_DEFAULT_PROVIDER: str = "rule_based"  # rule_based | openai | dashscope
    AI_OPENAI_API_KEY: str = ""
    AI_OPENAI_MODEL: str = "gpt-4o-mini"
    AI_OPENAI_BASE_URL: str = ""
    AI_DASHSCOPE_API_KEY: str = ""
    AI_DASHSCOPE_MODEL: str = "qwen-plus"
    AI_REQUEST_TIMEOUT: int = 30

    # Agent 稳固性
    AI_SUMMARY_ENABLED: bool = True
    AI_SUMMARY_TOKEN_LIMIT: int = 80000
    AI_RUN_LOG_DIR: str = ""
    AI_LOG_RETENTION_DAYS: int = 30
    AI_MAX_AGENT_DURATION_S: int = 120

    # 智能体技能（磁盘文件夹为事实来源；DB 仅索引/绑定）
    SKILLS_DIR: str = ""                 # 内置技能根目录；空=backend/skills
    SKILLS_IMPORT_DIR: str = ""          # 导入技能根目录；空=backend/skills-imported
    SKILL_IMPORT_MAX_BYTES: int = 20 * 1024 * 1024
    SKILL_FILE_PREVIEW_MAX_BYTES: int = 1024 * 1024
    SKILL_INSTALL_ALLOWED_HOSTS: str = ""   # 逗号分隔；空=允许任意公网 HTTPS（私网/回环始终拒绝）
    SKILL_INSTALL_TIMEOUT_S: int = 30
    # 第二阶段：技能脚本沙箱（UDS 优先；URL 仅本地调试）
    SKILL_SANDBOX_UDS: str = ""
    SKILL_SANDBOX_URL: str = ""
    SKILL_SANDBOX_ORCHESTRATOR_URL: str = ""
    SKILL_SANDBOX_TOKEN: str = ""
    SKILL_SCRIPT_TIMEOUT_S: int = 30
    SKILL_SCRIPT_MAX_OUTPUT_BYTES: int = 8000

    # 执行面推理（AEOS reason_control_platform 只读分析接入）
    REASONING_TIMEOUT_S: int = 170          # 单次推理任务总超时（含证据采集与 LLM；执行面 agent HTTP 超时 180s，留 10s 余量）
    REASONING_MODEL: str = ""               # 推理专用模型名；留空沿用 AI_OPENAI_MODEL（建议 flash 档以压时延）
    REASONING_MAX_CONCURRENT: int = 5       # 单实例并发推理上限，超出返回 429
    REASONING_MAX_EVIDENCE_ITEMS: int = 25  # 单次任务证据条数上限（控制 prompt 体积与推理耗时）
    REASONING_MAX_CONCLUSIONS: int = 20     # 单次任务结论条数上限

    # 智能体管理台（backend 代理访问执行面 agent 的 admin 面；两者留空则 status/restart 返回下线态）
    EXECUTION_AGENT_BASE_URL: str = ""   # legacy 单 Agent 管理代理（已停用，仅旧端点兼容）
    EXECUTION_QUERY_AGENT_BASE_URL: str = ""
    EXECUTION_REASONING_AGENT_BASE_URL: str = ""
    EXECUTION_WRITE_AGENT_BASE_URL: str = ""
    AGENT_ADMIN_TOKEN: str = ""          # 与 agent .env 的 AGENT_ADMIN_TOKEN 一致

    # SPC 单一网关（Hub 执行面/出站统一出口）
    GATEWAY_BASE_URL: str = ""
    GATEWAY_INTERNAL_TOKEN: str = ""
    GATEWAY_CALLER_USER_ID_FIELD: str = "emp_code"
    GATEWAY_HUB_TIMEOUT_S: float = 20.0

    # SPC 系统 ID：backend 仅用于构造 caller.systemId；Hub 鉴权/CA 由网关容器直接读同名 env
    AEOS_SYSTEM_ID: str = ""

    # 物料盘点
    STOCK_CHECK_RECENT_SKIP_DAYS: int = 7  # 订单盘点建单/刷新BOM时，近 N 天内已盘过的(物料×仓库)行仅标记"近期已盘"免盘(不预填盘点数据)

    # WeCom (企业微信)
    wecom_corp_id: Optional[str] = None
    wecom_agent_id: Optional[str] = None
    wecom_corp_secret: Optional[str] = None
    wecom_contact_secret: Optional[str] = None
    frontend_base_url: Optional[str] = None
    data_supply_alert_wecom_uids: str = ""  # 逗号分隔的企微 userid，空则告警只记日志

    # 订单工价缺口每日提醒
    wage_reminder_enabled: bool = True
    wage_reminder_usernames: str = "chenqiaoxia"  # 收件人系统用户名, 逗号分隔(需绑定 wecom_user_id)
    wage_reminder_hour: int = 8
    wage_reminder_minute: int = 30

    # 待排快照定时刷新(每天刷新当前及未来若干月的待排快照, 避免新订单不进排产池)
    snapshot_refresh_enabled: bool = True
    snapshot_refresh_hour: int = 3
    snapshot_refresh_minute: int = 30
    snapshot_refresh_months_ahead: int = 2  # 未来月数(含当月共 N+1 个月)
    snapshot_refresh_limit: int = 500       # 单月最多刷新订单数(后端上限500)

    # 已排产订单变更检测(出货计划/数量/UPPH 变更 -> 标记待重排)
    change_detect_enabled: bool = True
    change_detect_interval_hours: int = 1

    # 智能体中心（上下文缓存 TTL）
    AGENT_SCOPE_CACHE_TTL_SECONDS: int = 300

    model_config = {"env_file": _ENV_FILES, "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_server_identity() -> str:
    """后端服务实例标识：SERVER_ID 优先，未配置回退 hostname（Docker 内为容器ID）"""
    import socket
    return get_settings().SERVER_ID or socket.gethostname()
