"""多 Agent 计划的只读 Mock 工具执行层。

工具按账号可见站点和问题上下文直接读取进程内 Mock 数据，再生成可展示摘要与引用编号。
本层不访问外部系统，也不修改事件、通知或现场设备状态；控制边界工具只做检查。
"""

from dataclasses import dataclass

from ..data.incidents import _INCIDENTS, _NOTIFICATIONS
from ..data.monitoring import _ALARMS, _STATIONS
from ..data.supply import _SUPPLY_AREAS
from ..dependencies import user_has_station_access
from ..schemas.agent import AgentAnswer, AgentChatRequest
from ..services.knowledge_search import search_rules
from .tools import AgentPlan, ReadOnlyTool


@dataclass(frozen=True)
class ToolContext:
    """一次工具执行所需的账号、问题和答案上下文。"""

    user: dict
    request: AgentChatRequest
    answer: AgentAnswer


@dataclass(frozen=True)
class ToolExecution:
    """一次只读工具执行的可展示结果。"""

    tool: ReadOnlyTool
    status: str
    summary: str
    source_ids: tuple[str, ...] = ()
    read_only: bool = True


def _visible_station_ids(user: dict) -> set[str]:
    """返回当前账号有权访问的站点编号集合。"""

    return {station["id"] for station in _STATIONS if user_has_station_access(user, station["id"])}


def _station_from_context(context: ToolContext) -> dict | None:
    """优先使用请求中的站点，其次从答案引用中回退到可见站点。"""

    visible = _visible_station_ids(context.user)
    requested = context.request.station_id
    if requested and requested in visible:
        return next((station for station in _STATIONS if station["id"] == requested), None)
    for citation in context.answer.citations:
        if citation.source_type in {"telemetry", "alarm", "supply"} and citation.source_id in visible:
            station = next((item for item in _STATIONS if item["id"] == citation.source_id), None)
            if station is not None:
                return station
            alarm = next((item for item in _ALARMS if item["id"] == citation.source_id), None)
            if alarm is not None and alarm["station_id"] in visible:
                return next((item for item in _STATIONS if item["id"] == alarm["station_id"]), None)
    return next((station for station in _STATIONS if station["id"] in visible), None)


def _execute_check_scope(tool: ReadOnlyTool, context: ToolContext) -> ToolExecution:
    """读取当前账号可见站点范围，不依赖最终答案倒推。"""

    stations = [station for station in _STATIONS if user_has_station_access(context.user, station["id"])]
    source_ids = tuple(station["id"] for station in stations)
    if not stations:
        summary = "当前账号没有可访问站点，后续只读工具将返回空结果"
    else:
        names = "、".join(station["name"] for station in stations[:3])
        suffix = " 等" if len(stations) > 3 else ""
        summary = f"已校验站点范围：可见 {len(stations)} 个站点（{names}{suffix}）"
    return ToolExecution(tool=tool, status="completed", summary=summary, source_ids=source_ids)


def _execute_read_telemetry(tool: ReadOnlyTool, context: ToolContext) -> ToolExecution:
    """按可见站点读取确定性 Mock 遥测摘要。"""

    station = _station_from_context(context)
    if station is None:
        return ToolExecution(tool=tool, status="completed", summary="可见范围内没有可读取的遥测站点", source_ids=())
    # 与监控 Mock 保持一致的基础值，只做展示摘要，不伪造实时采样。
    flow = round(1120.0 - (station["sequence"] - 1) * 18, 3)
    summary = f"已读取 {station['name']} Mock 遥测：流量约 {flow} m³/h，站点状态 {station['status']}"
    return ToolExecution(tool=tool, status="completed", summary=summary, source_ids=(station["id"],))


def _execute_read_alarms(tool: ReadOnlyTool, context: ToolContext) -> ToolExecution:
    """读取授权站点的告警 Mock，并返回编号摘要。"""

    visible = _visible_station_ids(context.user)
    alarms = [alarm for alarm in _ALARMS if alarm["station_id"] in visible]
    station = _station_from_context(context)
    if station is not None:
        scoped = [alarm for alarm in alarms if alarm["station_id"] == station["id"]]
        if scoped:
            alarms = scoped
    source_ids = tuple(alarm["id"] for alarm in alarms)
    if not alarms:
        return ToolExecution(tool=tool, status="completed", summary="可见范围内没有匹配的 Mock 告警", source_ids=())
    top = max(alarms, key=lambda item: {"high": 3, "medium": 2, "low": 1}.get(item["level"], 0))
    summary = f"已读取 {len(alarms)} 条告警，最高优先级为 {top['station_name']} {top['metric']}（{top['level']}）"
    return ToolExecution(tool=tool, status="completed", summary=summary, source_ids=source_ids)


def _execute_read_event_context(tool: ReadOnlyTool, context: ToolContext) -> ToolExecution:
    """读取授权站点未关闭事件和平台通知。"""

    visible = _visible_station_ids(context.user)
    station = _station_from_context(context)
    station_ids = {station["id"]} if station is not None else visible
    incidents = [
        incident
        for incident in _INCIDENTS.values()
        if incident.station_id in station_ids and incident.status not in {"resolved", "false_positive"}
    ]
    source_ids: list[str] = []
    notification_count = 0
    for incident in incidents:
        source_ids.append(incident.id)
        related = [item for item in _NOTIFICATIONS.values() if item.incident_id == incident.id]
        notification_count += len(related)
        source_ids.extend(item.id for item in related)
    if not incidents:
        return ToolExecution(tool=tool, status="completed", summary="可见范围内没有未关闭事件上下文", source_ids=())
    summary = f"已读取 {len(incidents)} 个未关闭事件和 {notification_count} 条平台通知"
    return ToolExecution(tool=tool, status="completed", summary=summary, source_ids=tuple(source_ids))


def _execute_search_knowledge(tool: ReadOnlyTool, context: ToolContext) -> ToolExecution:
    """调用本地规程检索服务，返回版本化引用编号。"""

    metric = None
    for alarm in _ALARMS:
        if any(citation.source_id == alarm["id"] for citation in context.answer.citations):
            metric = alarm["metric"]
            break
    query = context.request.message.strip() or "泵站 异常核查"
    hits = search_rules(query, metric=metric, limit=3)
    if not hits and metric:
        hits = search_rules(f"{metric} 异常核查", metric=metric, limit=3)
    source_ids = tuple(hit.source_id for hit in hits)
    if not hits:
        return ToolExecution(tool=tool, status="completed", summary="本地规程目录未匹配到适用规则", source_ids=())
    top = hits[0]
    summary = f"已检索规程 {top.source_id}（{top.title}），共 {len(hits)} 条候选"
    return ToolExecution(tool=tool, status="completed", summary=summary, source_ids=source_ids)


def _execute_calculate_supply_balance(tool: ReadOnlyTool, context: ToolContext) -> ToolExecution:
    """按可见片区计算供需差额，选出缺口最大的片区。"""

    rows = [row for row in _SUPPLY_AREAS if user_has_station_access(context.user, row["station_id"])]
    if not rows:
        return ToolExecution(tool=tool, status="completed", summary="可见范围内没有可计算的供需片区", source_ids=())
    bottleneck = min(rows, key=lambda row: row["supply"] - row["demand"])
    balance = bottleneck["supply"] - bottleneck["demand"]
    summary = f"已计算供需差额：{bottleneck['area']} 结余 {balance:.0f} m³/d"
    return ToolExecution(tool=tool, status="completed", summary=summary, source_ids=(bottleneck["station_id"],))


def _execute_apply_control_boundary(tool: ReadOnlyTool, context: ToolContext) -> ToolExecution:
    """检查控制边界：只记录拒绝结论，不执行任何现场写操作。"""

    summary = "已检查控制边界：当前请求被判定为只读分析，未生成泵组/阀门/PLC 写指令"
    return ToolExecution(
        tool=tool,
        status="completed",
        summary=summary,
        source_ids=("mock-readonly-policy",),
    )


_TOOL_HANDLERS = {
    "check_scope": _execute_check_scope,
    "read_telemetry": _execute_read_telemetry,
    "read_alarms": _execute_read_alarms,
    "read_event_context": _execute_read_event_context,
    "search_knowledge": _execute_search_knowledge,
    "calculate_supply_balance": _execute_calculate_supply_balance,
    "apply_control_boundary": _execute_apply_control_boundary,
}


def execute_tool(tool: ReadOnlyTool, context: ToolContext) -> ToolExecution:
    """执行一个白名单工具的确定性 Mock 读取，并返回摘要和引用编号。"""

    handler = _TOOL_HANDLERS.get(tool.name)
    if handler is None:
        return ToolExecution(tool=tool, status="completed", summary="已完成只读工具检查", source_ids=())
    return handler(tool, context)


def execute_plan(plan: AgentPlan, context: ToolContext) -> tuple[ToolExecution, ...]:
    """按协调器给出的顺序执行计划中的只读工具。"""

    return tuple(execute_tool(tool, context) for tool in plan.tools)
