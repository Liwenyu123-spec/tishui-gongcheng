"""工单草稿路由。"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from ..data.repositories import get_data_source, save_row
from ..dependencies import require_roles, user_has_station_access
from ..schemas.work_orders import WorkOrderAssignmentUpdateRequest, WorkOrderDraft, WorkOrderDraftRequest, WorkOrderStatusUpdateRequest
from ..services.audit import record_audit

# 工单接口只生成建议草稿，明确禁止现场设备控制。
router = APIRouter(prefix="/api/v1", tags=["工单"])
data_source = get_data_source()

# 状态变更只允许沿着业务流程推进，重复提交当前状态保持幂等。
_WORK_ORDER_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"draft", "assigned", "cancelled"},
    "assigned": {"assigned", "in_progress", "cancelled"},
    "in_progress": {"in_progress", "completed", "cancelled"},
    "completed": {"completed"},
    "cancelled": {"cancelled"},
}


def _can_view_order(order: WorkOrderDraft, user: dict) -> bool:
    """按关联站点过滤工单；未关联站点的通用工单对所有调度账号可见。"""

    return order.station_id is None or user_has_station_access(user, order.station_id)


@router.post("/work-orders/draft", response_model=WorkOrderDraft)
def create_work_order_draft(
    payload: WorkOrderDraftRequest,
    user: dict = Depends(require_roles("admin", "operator", required_permissions=("submit_scheme",))),
) -> WorkOrderDraft:
    """根据建议生成工单草稿，不执行现场控制。"""

    # 如果请求指定站点，先确认站点编号存在。
    if payload.station_id and data_source.stations.get(payload.station_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="站点不存在")
    # 站点存在不代表当前账号有权访问，还要执行站点范围检查。
    if payload.station_id and not user_has_station_access(user, payload.station_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权访问该站点")
    # 通过校验后生成草稿编号和创建时间；返回状态固定为 draft。
    order = WorkOrderDraft(
        id=f"work-order-{uuid4().hex[:10]}",
        **payload.model_dump(),
        created_at=datetime.now(timezone.utc),
    )
    # 草稿先保存到 Mock 存储，后续列表和状态接口才能继续处理同一条工单。
    data_source.work_orders.all()[order.id] = order
    save_row("commit_order", order)
    record_audit("create", "work_order", order.id, f"创建工单草稿：{order.title}")
    return order


@router.get("/work-orders", response_model=list[WorkOrderDraft])
def list_work_orders(user: dict = Depends(require_roles("admin", "operator"))) -> list[WorkOrderDraft]:
    """返回当前账号有权查看的工单列表。"""

    # 工单站点范围与站点监控、事件查询保持一致，避免跨站点泄露处理任务。
    return [order for order in reversed(list(data_source.work_orders.all().values())) if _can_view_order(order, user)]


@router.get("/work-orders/{work_order_id}", response_model=WorkOrderDraft)
def get_work_order(
    work_order_id: str,
    user: dict = Depends(require_roles("admin", "operator")),
) -> WorkOrderDraft:
    """查询单条工单详情。"""

    order = data_source.work_orders.get(work_order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工单不存在")
    if not _can_view_order(order, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权查看该工单")
    return order


@router.patch("/work-orders/{work_order_id}/status", response_model=WorkOrderDraft)
def update_work_order_status(
    work_order_id: str,
    payload: WorkOrderStatusUpdateRequest,
    user: dict = Depends(require_roles("admin", "operator", required_permissions=("submit_scheme",))),
) -> WorkOrderDraft:
    """推进工单状态，不执行现场设备控制。"""

    order = data_source.work_orders.get(work_order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工单不存在")
    if not _can_view_order(order, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权处理该工单")
    # 当前状态和目标状态必须符合预设流转表，防止跳过分派或处理中阶段。
    allowed_statuses = _WORK_ORDER_TRANSITIONS.get(order.status, {order.status})
    if payload.status not in allowed_statuses:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"工单不能从 {order.status} 直接变更为 {payload.status}")
    if order.status == payload.status:
        return order
    previous_status = order.status
    order.status = payload.status
    save_row("commit_order", order)
    record_audit("status_update", "work_order", order.id, f"工单状态由 {previous_status} 更新为 {payload.status}")
    return order


@router.patch("/work-orders/{work_order_id}", response_model=WorkOrderDraft)
def update_work_order_assignment(
    work_order_id: str,
    payload: WorkOrderAssignmentUpdateRequest,
    user: dict = Depends(require_roles("admin", "operator", required_permissions=("submit_scheme",))),
) -> WorkOrderDraft:
    """补充工单负责人和截止时间，不执行自动派单或现场控制。"""

    order = data_source.work_orders.get(work_order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工单不存在")
    if not _can_view_order(order, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权处理该工单")
    # 已完成或已取消的工单进入只读状态，保留历史处理结果。
    if order.status in {"completed", "cancelled"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已完成或已取消的工单不能修改处理信息")
    if payload.owner is None and payload.due_at is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="至少填写负责人或截止时间")
    if payload.owner is not None:
        owner = payload.owner.strip()
        if not owner:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="负责人不能为空")
        order.owner = owner
    if payload.due_at is not None:
        order.due_at = payload.due_at
    save_row("commit_order", order)
    record_audit("assignment_update", "work_order", order.id, f"工单 {order.title} 处理信息已更新")
    return order
