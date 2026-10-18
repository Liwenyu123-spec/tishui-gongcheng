"""工单草稿接口的请求和响应模型。"""

from datetime import datetime

from typing import Literal

from pydantic import BaseModel


# 工单状态按“草稿—已分派—处理中—已完成”顺序推进，也允许未开始的工单取消。
WorkOrderStatus = Literal["draft", "assigned", "in_progress", "completed", "cancelled"]


class WorkOrderDraftRequest(BaseModel):
    """工单草稿请求；只描述建议，不触发设备操作。"""

    # 工单草稿标题。
    title: str
    # 关联站点编号；跨站点问题可以不填写。
    station_id: str | None = None
    # 需要处理的问题描述。
    issue: str
    # 建议现场人员采取的处理动作。
    suggested_action: str
    # 工单优先级，未填写时按中等级别处理。
    priority: str = "medium"
    # 处理负责人账号或班组标识，可在生成后补充。
    owner: str | None = None
    # 计划完成时间；Mock 阶段只保存时间，不触发提醒任务。
    due_at: datetime | None = None


class WorkOrderDraft(BaseModel):
    """工单草稿响应结构。"""

    # 工单草稿唯一编号。
    id: str
    # 工单标题。
    title: str
    # 工单关联站点；可能为空。
    station_id: str | None
    # 工单需要处理的问题。
    issue: str
    # 工单中的建议动作。
    suggested_action: str
    # 工单优先级。
    priority: str
    # 当前处理负责人或班组。
    owner: str | None = None
    # 计划完成时间。
    due_at: datetime | None = None
    # 当前状态，接口创建时固定为草稿，后续由状态接口推进。
    status: WorkOrderStatus = "draft"
    # 草稿创建时间。
    created_at: datetime
    # 数据来源标记。
    source: str = "mock"


class WorkOrderStatusUpdateRequest(BaseModel):
    """工单状态更新请求。"""

    # 目标状态由模型限制，路由还会检查当前状态是否允许流转。
    status: WorkOrderStatus


class WorkOrderAssignmentUpdateRequest(BaseModel):
    """工单负责人和截止时间更新请求。"""

    # 负责人为空时保留现有负责人；当前阶段不自动分配账号。
    owner: str | None = None
    # 截止时间为空时保留现有时间；时间格式由 Pydantic 解析校验。
    due_at: datetime | None = None
