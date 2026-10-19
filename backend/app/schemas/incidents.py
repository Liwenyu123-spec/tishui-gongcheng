"""站点事件和平台内通知接口的模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


# 事件等级从一般到严重依次升高，接口只接受这四个值。
IncidentLevel = Literal["low", "medium", "high", "critical"]
# 事件处置状态，表示从发现到关闭的生命周期。
IncidentStatus = Literal["open", "acknowledged", "in_progress", "resolved", "false_positive"]
# 平台内通知的送达或处理状态。
NotificationStatus = Literal["sent", "acknowledged", "failed"]


class IncidentCreateRequest(BaseModel):
    """站点人工或只读适配器提交的事件。"""

    # 事件分类，例如漏损、压力异常或设备告警。
    category: str
    # 事件严重程度，未填写时按中等级别处理。
    level: IncidentLevel = "medium"
    # 站点人员提交的故障描述。
    description: str
    # 事件来源，默认表示站点人工上报。
    source: str = "station_manual"
    # 事件实际发生时间；未提供时由服务端使用当前时间。
    occurred_at: datetime | None = None
    # 上报人标识，默认使用站点操作员账号。
    reported_by: str = "station-operator"
    # 用于识别重复上报的业务键；为空时不做显式去重。
    deduplication_key: str | None = None
    # 仅用于 Mock 验收：让新通知进入失败状态，演示失败原因和重试流程。
    simulate_delivery_failure: bool = False


class Incident(BaseModel):
    """平台保存的站点事件。"""

    # 平台生成的事件唯一编号。
    id: str
    # 事件所属站点编号。
    station_id: str
    # 事件分类。
    category: str
    # 事件严重程度。
    level: IncidentLevel
    # 事件来源渠道。
    source: str
    # 事件发生时间。
    occurred_at: datetime
    # 当前处置状态，新增事件默认为 open。
    status: IncidentStatus = "open"
    # 发起上报的用户或系统标识。
    reported_by: str
    # 事件的文字描述。
    description: str
    # 用于合并相同事件的去重键。
    deduplication_key: str | None = None
    # 该事件累计被上报的次数，去重合并时递增。
    report_count: int = 1
    # 是否发生过重复事件合并。
    deduplicated: bool = False
    # 平台创建事件的时间。
    created_at: datetime
    # 事件最近一次被修改的时间。
    updated_at: datetime
    # 数据来源标记，当前为内存 Mock。
    data_source: str = "mock"
    # Mock 验收标记；真实通知网关接入后不应由业务人员传入此字段。
    simulate_delivery_failure: bool = False


class Notification(BaseModel):
    """平台内通知及其送达状态。"""

    # 通知唯一编号。
    id: str
    # 通知关联的事件编号。
    incident_id: str
    # 通知接收人账号或联系人标识。
    recipient: str
    # 通知渠道，当前默认是平台内通知。
    channel: str = "in_app"
    # 通知初始状态，创建成功后默认为 sent。
    status: NotificationStatus = "sent"
    # 通知生成或发送的时间。
    sent_at: datetime
    # 接收人确认通知的时间，未确认时为空。
    acknowledged_at: datetime | None = None
    # 通知失败后的重试次数。
    retry_count: int = 0
    # 最后一次发送失败的原因。
    failure_reason: str | None = None
    # 冗余保存关联事件状态，便于通知中心直接展示处置进度。
    incident_status: IncidentStatus = "open"
    # 记录该通知是否已经向备用联系人升级，避免重复生成升级通知。
    escalation_level: int = 0
    # 通知升级到备用联系人或更高等级的时间。
    escalated_at: datetime | None = None
    # 数据来源标记，当前为内存 Mock。
    data_source: str = "mock"


class HeartbeatResponse(BaseModel):
    """预留给站点在线心跳的响应模型。"""

    # 上报心跳的站点编号。
    station_id: str
    # 本次心跳被平台接收的时间。
    received_at: datetime
    # 平台记录的站点最近在线时间。
    last_seen_at: datetime
    # 根据最近心跳计算出的在线状态。
    status: str = "online"
    # 是否超过允许的心跳间隔。
    is_stale: bool = False
    # 数据来源标记。
    data_source: str = "mock"


class StationContact(BaseModel):
    """站点当前生效的调度联系人配置。"""

    # 联系人所属站点编号。
    station_id: str
    # primary 为主联系人，backup 为备用联系人。
    contact_type: Literal["primary", "backup"]
    # 接收通知的账号或联系方式。
    recipient: str
    # 联系渠道，当前默认记录为平台内通知。
    channel: str = "in_app"
    # 联系优先级，数值越小通常越先通知。
    priority: int
    # 是否启用该联系人配置。
    enabled: bool = True
    # 数据来源标记。
    data_source: str = "mock"
