"""common 模块：跨域通用接口（健康检查、对外联调 ping 等）。"""

from app.api.v1.common import health
from app.api.v1.common.files import router as files_router