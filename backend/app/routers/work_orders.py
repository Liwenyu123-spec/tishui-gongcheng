"""工单草稿路由。"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from ..data.monitoring import _STATIONS
from ..dependencies import require_roles, user_has_station_access
from ..schemas.work_orders import WorkOrderDraft, WorkOrderDraftRequest

# 工单接口只生成建议草稿，明确禁止现场设备控制。
router = APIRouter(prefix="/api/v1", tags=["工单"])


@router.post("/work-orders/draft", response_model=WorkOrderDraft)
def create_work_order_draft(
    payload: WorkOrderDraftRequest,
    user: dict = Depends(require_roles("admin", "operator")),
) -> WorkOrderDraft:
    """根据建议生成工单草稿，不执行现场控制。"""

    # 如果请求指定站点，先确认站点编号存在。
    if payload.station_id and not any(station["id"] == payload.station_id for station in _STATIONS):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="站点不存在")
    # 站点存在不代表当前账号有权访问，还要执行站点范围检查。
    if payload.station_id and not user_has_station_access(user, payload.station_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权访问该站点")
    # 通过校验后生成草稿编号和创建时间；返回状态固定为 draft。
    return WorkOrderDraft(
        id=f"work-order-{uuid4().hex[:10]}",
        **payload.model_dump(),
        created_at=datetime.now(timezone.utc),
    )
