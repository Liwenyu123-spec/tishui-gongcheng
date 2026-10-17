"""工程拓扑、站点、遥测和告警模型。"""

from datetime import datetime

from pydantic import BaseModel


class Station(BaseModel):
    """站点列表中的基础字段。"""

    id: str
    name: str
    sequence: int
    station_type: str
    status: str
    source: str = "mock"


class StationDetail(Station):
    """站点详情字段。"""

    location: str
    description: str
    metrics: list[str]


class TopologyNode(BaseModel):
    """拓扑图节点。"""

    station_id: str
    name: str
    sequence: int


class TopologyEdge(BaseModel):
    """拓扑图有向连接边。"""

    source: str
    target: str
    direction: str = "downstream"


class TopologyResponse(BaseModel):
    """拓扑接口整体响应。"""

    version: str
    confirmed_at: datetime
    source: str = "mock"
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]


class TelemetryPoint(BaseModel):
    """单条遥测记录。"""

    observed_at: datetime
    metric: str
    value: float
    unit: str
    source: str = "mock"
    quality: str = "good"
    is_stale: bool = False


class Alarm(BaseModel):
    """告警列表和确认接口响应。"""

    id: str
    station_id: str
    station_name: str
    level: str
    metric: str
    value: float
    unit: str
    threshold: str
    status: str
    occurred_at: datetime
    relation: str | None = None
    source: str = "mock"


class AlarmDetail(Alarm):
    """告警详情及建议动作。"""

    description: str
    suggested_action: str
