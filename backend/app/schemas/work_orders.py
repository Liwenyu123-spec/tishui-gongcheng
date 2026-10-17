"""工单草稿接口的请求和响应模型。"""

from datetime import datetime

from pydantic import BaseModel


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
    # 当前状态，接口创建时固定为草稿。
    status: str = "draft"
    # 草稿创建时间。
    created_at: datetime
    # 数据来源标记。
    source: str = "mock"
