"""拓扑、站点、遥测和告警查询路由。"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..data.monitoring import _ALARMS, _STATIONS
from ..dependencies import require_roles, require_station_access, user_has_station_access
from ..schemas.monitoring import Alarm, AlarmDetail, Station, StationDetail, TelemetryPoint, TopologyEdge, TopologyNode, TopologyResponse

# 监控路由统一提供拓扑、站点、遥测和告警查询。
router = APIRouter(prefix="/api/v1", tags=["监控"])


@router.get("/topology", response_model=TopologyResponse, tags=["拓扑"])
def topology(user: dict = Depends(require_roles("admin", "operator"))) -> TopologyResponse:
    """把站点列表转换为拓扑节点和相邻连接边。"""

    # 先按用户范围筛选节点，避免拓扑暴露未授权站点。
    visible_stations = [station for station in _STATIONS if user_has_station_access(user, station["id"])]
    # 用集合保存可见站点编号，后续构造相邻边时可以快速判断两端是否可见。
    visible_ids = {station["id"] for station in visible_stations}
    # 将内部字典转换为拓扑节点响应模型。
    nodes = [TopologyNode(station_id=station["id"], name=station["name"], sequence=station["sequence"]) for station in visible_stations]
    # 只连接原始输水顺序中相邻且同时可见的站点。
    edges = [
        TopologyEdge(source=_STATIONS[index]["id"], target=_STATIONS[index + 1]["id"])
        for index in range(len(_STATIONS) - 1)
        if _STATIONS[index]["id"] in visible_ids and _STATIONS[index + 1]["id"] in visible_ids
    ]
    # 返回固定 Mock 版本和确认时间，明确拓扑尚未接入真实 GIS 或 SCADA。
    return TopologyResponse(version="mock-topology-v1", confirmed_at=datetime(2026, 10, 15, tzinfo=timezone.utc), nodes=nodes, edges=edges)


@router.get("/stations", response_model=list[Station], tags=["站点"])
def stations(user: dict = Depends(require_roles("admin", "operator"))) -> list[Station]:
    """返回全部站点的基础字段。"""

    # 站点列表与拓扑使用相同的站点范围规则。
    return [Station(**station) for station in _STATIONS if user_has_station_access(user, station["id"])]


@router.get("/stations/{station_id}", response_model=StationDetail, tags=["站点"])
def station_detail(station_id: str, _: dict = Depends(require_station_access("admin", "operator"))) -> StationDetail:
    """查询单个站点详细资料。"""

    # 依赖项已校验权限，这里继续检查站点是否真实存在并返回详细字段。
    station = next((item for item in _STATIONS if item["id"] == station_id), None)
    if station is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="站点不存在")
    return StationDetail(**station)


@router.get("/stations/{station_id}/telemetry", response_model=list[TelemetryPoint], tags=["监控"])
def telemetry(station_id: str, metric: str | None = Query(default=None, max_length=32), from_time: str | None = Query(default=None, alias="from", max_length=64), to_time: str | None = Query(default=None, alias="to", max_length=64), _: dict = Depends(require_station_access("admin", "operator"))) -> list[TelemetryPoint]:
    """生成指定站点的模拟遥测时间序列。"""

    # 依赖项完成权限校验后，路由仍要确认站点存在，避免为未知站点生成数据。
    if not any(station["id"] == station_id for station in _STATIONS):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="站点不存在")
    # 每种测点定义一个基准值和单位，供 Mock 时间序列生成使用。
    values = {"flow": (1120.0, "m³/h"), "pressure": (0.72, "MPa"), "level": (3.7, "m"), "energy": (184.0, "kWh")}
    # 指定 metric 时只返回单个测点，否则返回全部支持的测点。
    metrics = [metric] if metric else list(values)
    points: list[TelemetryPoint] = []
    # Mock 时间序列固定起点，from/to 参数当前仅保留接口兼容性，不参与计算。
    base_time = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)
    # 生成六个时间点，每个点相隔十分钟，用于前端趋势图展示。
    for offset in range(6):
        for metric_name in metrics:
            # 未知测点属于请求参数错误，不返回伪造数据。
            value_unit = values.get(metric_name)
            if value_unit is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"不支持的测点: {metric_name}")
            value, unit = value_unit
            # offset 越大表示更早的观测点，同时让数值产生可视化趋势变化。
            points.append(TelemetryPoint(observed_at=base_time - timedelta(minutes=offset * 10), metric=metric_name, value=round(value + offset * 2, 3), unit=unit))
    # 生成顺序为当前时间到较早时间，前端可直接用于趋势图展示。
    return points


@router.get("/alarms", response_model=list[Alarm], tags=["告警"])
def alarms(status_filter: str | None = Query(default=None, alias="status", max_length=32), station_id: str | None = Query(default=None, max_length=64), user: dict = Depends(require_roles("admin", "operator"))) -> list[Alarm]:
    """返回告警列表，可按状态和站点筛选。"""

    # 查询参数指定站点时，先单独校验该站点，避免通过过滤条件越权探测。
    if station_id and not user_has_station_access(user, station_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权访问该站点告警")
    # 先过滤授权站点，再应用状态和站点筛选条件。
    rows = [alarm for alarm in _ALARMS if user_has_station_access(user, alarm["station_id"])]
    if status_filter:
        # status 参数按告警当前状态精确筛选，未传时保留所有状态。
        rows = [alarm for alarm in rows if alarm["status"] == status_filter]
    if station_id:
        # station_id 参数只影响已经通过权限检查的站点数据。
        rows = [alarm for alarm in rows if alarm["station_id"] == station_id]
    # 列表响应隐藏详情字段，详情接口再返回处理建议。
    return [Alarm(**{key: value for key, value in alarm.items() if key not in {"description", "suggested_action"}}) for alarm in rows]


@router.get("/alarms/{alarm_id}", response_model=AlarmDetail, tags=["告警"])
def alarm_detail(alarm_id: str, user: dict = Depends(require_roles("admin", "operator"))) -> AlarmDetail:
    """返回单条告警及处理建议。"""

    # 先按告警编号定位记录，再校验其所属站点权限。
    alarm = next((item for item in _ALARMS if item["id"] == alarm_id), None)
    if alarm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="告警不存在")
    if not user_has_station_access(user, alarm["station_id"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权访问该站点告警")
    return AlarmDetail(**alarm)
