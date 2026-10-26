"""工程拓扑、站点、遥测和告警模型。"""

from datetime import datetime

from pydantic import BaseModel


class Station(BaseModel):
    """站点列表中的基础字段。"""

    # 站点唯一编号。
    id: str
    # 站点名称。
    name: str
    # 在线路拓扑中的顺序号。
    sequence: int
    # 站点类型，例如泵站或调蓄站。
    station_type: str
    # 当前站点运行状态。由最近一次测试水位决定：低于 3.20 m 为 warning。
    status: str
    # 本次刷新写入的测试水位。没有水位测点时为空。
    level: float | None = None
    # 数据来源标记。
    source: str = "mock"


class StationDetail(Station):
    """站点详情字段。"""

    # 站点所在位置的文字描述。
    location: str
    # 站点的补充说明。
    description: str
    # 该站点可查询的遥测指标名称。
    metrics: list[str]


class TopologyNode(BaseModel):
    """拓扑图节点。"""

    # 拓扑节点对应的站点编号。
    station_id: str
    # 拓扑图展示名称。
    name: str
    # 节点在线路中的顺序号。
    sequence: int


class TopologyEdge(BaseModel):
    """拓扑图有向连接边。"""

    # 上游节点站点编号。
    source: str
    # 下游节点站点编号。
    target: str
    # 水流或业务关系方向，默认表示下游方向。
    direction: str = "downstream"


class TopologyResponse(BaseModel):
    """拓扑接口整体响应。"""

    # 拓扑数据版本，用于前端判断是否需要刷新。
    version: str
    # 平台确认当前拓扑的时间。
    confirmed_at: datetime
    # 数据来源标记。
    source: str = "mock"
    # 拓扑中的全部站点节点。
    nodes: list[TopologyNode]
    # 拓扑中的站点连接关系。
    edges: list[TopologyEdge]


class DesignPoint(BaseModel):
    """资料中的设计参数，不是当前测试遥测。"""

    id: str
    object_id: str
    metric_code: str
    unit: str = ""
    source: str = ""
    note: str = ""


class TelemetryPoint(BaseModel):
    """单条遥测记录。"""

    # 指标采集或观测时间。
    observed_at: datetime
    # 指标名称，例如 pressure 或 flow。
    metric: str
    # 指标数值。
    value: float
    # 数值单位。
    unit: str
    # 数据来源标记。
    source: str = "mock"
    # 数据质量标记，good 表示当前样本可用。
    quality: str = "good"
    # 是否因长时间未更新而过期。
    is_stale: bool = False


class Alarm(BaseModel):
    """告警列表和确认接口响应。"""

    # 告警唯一编号。
    id: str
    # 告警所属站点编号。
    station_id: str
    # 告警所属站点名称。
    station_name: str
    # 告警等级。
    level: str
    # 触发告警的指标名称。
    metric: str
    # 触发时的指标值。
    value: float
    # 数值单位。
    unit: str
    # 触发告警的阈值描述。
    threshold: str
    # 告警当前确认或关闭状态。
    status: str
    # 告警发生时间。
    occurred_at: datetime
    # 与其他告警或事件的关联说明。
    relation: str | None = None
    # 数据来源标记。
    source: str = "mock"


class AlarmDetail(Alarm):
    """告警详情及建议动作。"""

    # 告警的详细文字说明。
    description: str
    # 给调度人员的建议处理动作。
    suggested_action: str
