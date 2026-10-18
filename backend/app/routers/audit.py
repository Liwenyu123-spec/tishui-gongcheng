"""审计事件查询路由。"""

from fastapi import APIRouter, Depends

from ..data.audit import _AUDIT_EVENTS
from ..dependencies import require_roles
from ..schemas.audit import AuditEvent

# 审计事件包含账号操作记录，只允许管理员查询。
router = APIRouter(prefix="/api/v1", tags=["管理"])


@router.get("/audit-events", response_model=list[AuditEvent])
def audit_events(_: dict = Depends(require_roles("admin"))) -> list[AuditEvent]:
    """返回管理员可见的审计事件，并将最新事件放在前面。"""

    # 审计记录由共享服务追加，查询时反转内存列表保证最新事件优先。
    return list(reversed(_AUDIT_EVENTS))
