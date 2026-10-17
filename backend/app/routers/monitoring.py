"""拓扑、站点、遥测和告警查询路由。"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, status

from ..data.monitoring import _ALARMS, _STATIONS
from ..schemas.monitoring import Alarm, AlarmDetail, Station, StationDetail, TelemetryPoint, TopologyEdge, TopologyNode, TopologyResponse

router = APIRouter(prefix="/api/v1", tags=["监控"])


@router.get("/topology", response_model=TopologyResponse, tags=["拓扑"])
def topology() -> TopologyResponse:
    """把站点列表转换为拓扑节点和相邻连接边。"""

    nodes = [TopologyNode(station_id=station["id"], name=station["name"], sequence=station["sequence"]) for station in _STATIONS]
    edges = [TopologyEdge(source=_STATIONS[index]["id"], target=_STATIONS[index + 1]["id"]) for index in range(len(_STATIONS) - 1)]
    return TopologyResponse(version="mock-topology-v1", confirmed_at=datetime(2026, 10, 15, tzinfo=timezone.utc), nodes=nodes, edges=edges)


@router.get("/stations", response_model=list[Station], tags=["站点"])
def stations() -> list[Station]:
    """返回全部站点的基础字段。"""

    return [Station(**station) for station in _STATIONS]


@router.get("/stations/{station_id}", response_model=StationDetail, tags=["站点"])
def station_detail(station_id: str) -> StationDetail:
    """查询单个站点详细资料。"""

    station = next((item for item in _STATIONS if item["id"] == station_id), None)
    if station is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="站点不存在")
    return StationDetail(**station)


@router.get("/stations/{station_id}/telemetry", response_model=list[TelemetryPoint], tags=["监控"])
def telemetry(station_id: str, metric: str | None = Query(default=None, max_length=32), from_time: str | None = Query(default=None, alias="from", max_length=64), to_time: str | None = Query(default=None, alias="to", max_length=64)) -> list[TelemetryPoint]:
    """生成指定站点的模拟遥测时间序列。"""

    if not any(station["id"] == station_id for station in _STATIONS):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="站点不存在")
    values = {"flow": (1120.0, "m³/h"), "pressure": (0.72, "MPa"), "level": (3.7, "m"), "energy": (184.0, "kWh")}
    metrics = [metric] if metric else list(values)
    points: list[TelemetryPoint] = []
    base_time = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)
    for offset in range(6):
        for metric_name in metrics:
            value_unit = values.get(metric_name)
            if value_unit is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"不支持的测点: {metric_name}")
            value, unit = value_unit
            points.append(TelemetryPoint(observed_at=base_time - timedelta(minutes=offset * 10), metric=metric_name, value=round(value + offset * 2, 3), unit=unit))
    return points


@router.get("/alarms", response_model=list[Alarm], tags=["告警"])
def alarms(status_filter: str | None = Query(default=None, alias="status", max_length=32), station_id: str | None = Query(default=None, max_length=64)) -> list[Alarm]:
    """返回告警列表，可按状态和站点筛选。"""

    rows = _ALARMS
    if status_filter:
        rows = [alarm for alarm in rows if alarm["status"] == status_filter]
    if station_id:
        rows = [alarm for alarm in rows if alarm["station_id"] == station_id]
    return [Alarm(**{key: value for key, value in alarm.items() if key not in {"description", "suggested_action"}}) for alarm in rows]


@router.get("/alarms/{alarm_id}", response_model=AlarmDetail, tags=["告警"])
def alarm_detail(alarm_id: str) -> AlarmDetail:
    """返回单条告警及处理建议。"""

    alarm = next((item for item in _ALARMS if item["id"] == alarm_id), None)
    if alarm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="告警不存在")
    return AlarmDetail(**alarm)
