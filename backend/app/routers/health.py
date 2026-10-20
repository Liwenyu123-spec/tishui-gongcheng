"""健康检查路由。"""

from datetime import datetime, timezone

from fastapi import APIRouter

from ..schemas.auth import HealthResponse
from ..services.startup_state import startup_status

# 健康检查保持公开，前端登录前也可以用它判断后端是否启动。
router = APIRouter(prefix="/api/v1", tags=["基础"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """确认服务进程可用，不依赖数据库或登录。"""

    # 返回当前 UTC 时间，帮助前端区分服务在线和页面缓存。
    # status、service 和 environment 使用响应模型默认值，保持健康检查结构稳定。
    return HealthResponse(timestamp=datetime.now(timezone.utc), startup=startup_status())
