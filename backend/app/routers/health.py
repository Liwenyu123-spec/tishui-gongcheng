"""健康检查路由。"""

from datetime import datetime, timezone

from fastapi import APIRouter

from ..schemas.auth import HealthResponse

router = APIRouter(prefix="/api/v1", tags=["基础"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """确认服务进程可用，不依赖数据库或登录。"""

    return HealthResponse(timestamp=datetime.now(timezone.utc))
