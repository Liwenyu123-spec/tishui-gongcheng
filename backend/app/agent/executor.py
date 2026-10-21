"""多 Agent 计划的只读 Mock 工具执行层。

工具按账号可见站点和问题上下文直接读取进程内 Mock 数据，再生成可展示摘要与引用编号。
本层不访问外部系统，也不修改事件、通知或现场设备状态；控制边界工具只做检查。
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass

from ..data.repositories import get_data_source
from ..dependencies import user_has_station_access
from ..schemas.agent import AgentAnswer, AgentChatRequest
from ..services.analysis import compare_variation, metric_label
from ..services.knowledge_search import search_rules
from ..services.runtime_env import windows_env
from .tools import AgentPlan, ReadOnlyTool, ToolName


data_source = get_data_source()


# 与 Agent 服务保持一致的中文别名，避免工具层只能识别站点编号。
_STATION_ALIASES = {
    "集泉": "jq-01",
    "一泵站": "pump-01",
    "二泵站": "pump-02",
    "三泵站": "pump-03",
    "四泵站": "pump-04",
    "平定入口": "pingding-inlet",
}

# 这些引用不是站点实体，允许在任意授权账号的工具结果中出现。
_GLOBAL_SOURCE_IDS = {"mock-readonly-policy"}


@dataclass(frozen=True)
class ToolContext:
    """一次工具执行所需的账号、问题和共享协作状态。"""

    user: dict
    request: AgentChatRequest
    answer: AgentAnswer
    # 前序 Agent 已经写入共享状态的工具证据；只读快照，避免节点私自改写结果。
    shared_executions: tuple["ToolExecution", ...] = ()
    # 已经完成或跳过的前序 Agent，供当前节点形成可追踪的交接关系。
    shared_agents: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolExecution:
    """一次只读工具执行的可展示结果。"""

    tool: ReadOnlyTool
    status: str
    summary: str
    source_ids: tuple[str, ...] = ()
    read_only: bool = True
    # 实际执行该工具的专业 Agent；旧的直接执行调用默认归入工具执行器。
    agent: str = "tool_executor"
    # 工具级超时/失败重试次数，便于 SSE 和审计区分一次请求是否经历过重试。
    attempts: int = 1
    error: str | None = None


def _tool_timeout_seconds() -> float:
    """读取单个只读工具的超时上限，异常配置回退到安全默认值。"""

    try:
        value = float(windows_env("AGENT_TOOL_TIMEOUT") or "5")
    except ValueError:
        value = 5.0
    return min(max(value, 0.01), 60.0)


def _tool_retry_limit() -> int:
    """读取只读工具最大重试次数；默认只重试一次，避免放大请求。"""

    try:
        value = int(windows_env("AGENT_TOOL_RETRIES") or "1")
    except ValueError:
        value = 1
    return min(max(value, 0), 3)


def _invoke_with_timeout(handler, tool: ReadOnlyTool, context: ToolContext) -> ToolExecution:
    """在线程边界内执行工具，避免单个工具阻塞整个 Agent 请求。"""

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent-tool")
    future = executor.submit(handler, tool, context)
    try:
        return future.result(timeout=_tool_timeout_seconds())
    finally:
        # 超时后不等待后台线程结束；当前 Mock 工具只读，不会继续修改业务状态。
        executor.shutdown(wait=False, cancel_futures=True)


def _visible_station_ids(user: dict) -> set[str]:
    """返回当前账号有权访问的站点编号集合。"""

    return {station["id"] for station in data_source.stations.list() if user_has_station_access(user, station["id"])}


def _station_by_id(station_id: str, visible: set[str]) -> dict | None:
    """仅在可见范围内按站点编号取站点。"""

    if station_id not in visible:
        return None
    return data_source.stations.get(station_id)


def _station_from_message(message: str, visible: set[str]) -> dict | None:
    """从问题文本中的中文别名解析可见站点。"""

    for alias, station_id in _STATION_ALIASES.items():
        if alias in message:
            station = _station_by_id(station_id, visible)
            if station is not None:
                return station
    return None


def _station_from_context(context: ToolContext) -> dict | None:
    """按请求站点、问题别名、答案引用的优先级解析目标站点。

    告警引用的 source_id 是告警编号而不是站点编号，需要额外映射，否则会误落到
    第一个可见站点，并把其他站点告警带进工具摘要。
    """

    visible = _visible_station_ids(context.user)
    requested = context.request.station_id
    if requested:
        return _station_by_id(requested, visible)

    from_message = _station_from_message(context.request.message, visible)
    if from_message is not None:
        return from_message

    for citation in context.answer.citations:
        if citation.source_type == "telemetry" or citation.source_type == "supply":
            station = _station_by_id(citation.source_id, visible)
            if station is not None:
                return station
        if citation.source_type == "alarm":
            alarm = data_source.alarms.get(citation.source_id)
            if alarm is not None:
                station = _station_by_id(alarm["station_id"], visible)
                if station is not None:
                    return station
    return None


def _filter_source_ids(tool_name: ToolName, source_ids: tuple[str, ...], context: ToolContext) -> tuple[str, ...]:
    """二次过滤工具引用，阻止越权站点、告警或事件编号漏出。"""

    visible = _visible_station_ids(context.user)
    if tool_name in {"search_knowledge", "explain_protocol", "apply_control_boundary"}:
        # 规程目录、规程说明和控制策略是全局只读规则，不按站点裁剪。
        return source_ids
    if tool_name == "check_scope":
        return tuple(item for item in source_ids if item in visible)

    allowed: list[str] = []
    for item in source_ids:
        if item in _GLOBAL_SOURCE_IDS or item in visible:
            allowed.append(item)
            continue
        alarm = data_source.alarms.get(item)
        if alarm is not None and alarm["station_id"] in visible:
            allowed.append(item)
            continue
        incident = data_source.incidents.get(item)
        if incident is not None and incident.station_id in visible:
            allowed.append(item)
            continue
        notification = data_source.notifications.get(item)
        if notification is not None:
            related = data_source.incidents.get(notification.incident_id)
            if related is not None and related.station_id in visible:
                allowed.append(item)
    return tuple(allowed)


def _execute_check_scope(tool: ReadOnlyTool, context: ToolContext) -> ToolExecution:
    """读取当前账号可见站点范围，不依赖最终答案倒推。"""

    stations = [station for station in data_source.stations.list() if user_has_station_access(context.user, station["id"])]
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
    # 趋势问题需要读取全部可见站点，不能只读取答案引用中的第一个站点。
    is_cross_station_trend = (
        context.request.station_id is None
        and any(word in context.request.message for word in ("过去", "最近", "趋势", "波动", "变化"))
        and not any(alias in context.request.message for alias in ("集泉", "一泵站", "二泵站", "三泵站", "四泵站", "平定入口"))
    )
    if is_cross_station_trend:
        visible = [item for item in data_source.stations.list() if user_has_station_access(context.user, item["id"])]
        metric = "flow" if "流量" in context.request.message else "level" if "水位" in context.request.message else "energy" if "能耗" in context.request.message else "pressure"
        comparisons = compare_variation(visible, metric)
        if not comparisons:
            return ToolExecution(tool=tool, status="completed", summary="可见范围内没有可读取的趋势测点", source_ids=())
        top = comparisons[0]
        return ToolExecution(
            tool=tool,
            status="completed",
            summary=f"已读取 {len(comparisons)} 个站点的{metric_label(metric)}时间序列，最大波动为 {top['station_name']} {top['variation']} {top['unit']}",
            source_ids=tuple(item["station_id"] for item in comparisons),
        )
    if station is None:
        return ToolExecution(tool=tool, status="completed", summary="可见范围内没有可读取的遥测站点", source_ids=())
    metric = "flow" if "流量" in context.request.message else "level" if "水位" in context.request.message else "energy" if "能耗" in context.request.message else "pressure"
    comparisons = compare_variation([station], metric)
    latest = comparisons[0]["latest"] if comparisons else "无"
    unit = comparisons[0]["unit"] if comparisons else ""
    summary = f"已读取 {station['name']} Mock 遥测：{metric_label(metric)}约 {latest} {unit}，站点状态 {station['status']}"
    return ToolExecution(tool=tool, status="completed", summary=summary, source_ids=(station["id"],))


def _execute_read_alarms(tool: ReadOnlyTool, context: ToolContext) -> ToolExecution:
    """读取授权站点的告警 Mock，并返回编号摘要。"""

    visible = _visible_station_ids(context.user)
    alarms = [alarm for alarm in data_source.alarms.list() if alarm["station_id"] in visible]
    station = _station_from_context(context)
    # 已解析到目标站点时必须收窄，即使该站点暂无告警也不能回退成全量可见告警。
    if station is not None:
        alarms = [alarm for alarm in alarms if alarm["station_id"] == station["id"]]
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
    # 有明确站点时只读该站；没有时才退回全部可见站点，避免串站点上下文。
    station_ids = {station["id"]} if station is not None else visible
    incidents = [
        incident
        for incident in data_source.incidents.all().values()
        if incident.station_id in station_ids and incident.status not in {"resolved", "false_positive"}
    ]
    source_ids: list[str] = []
    notification_count = 0
    for incident in incidents:
        source_ids.append(incident.id)
        related = [item for item in data_source.notifications.all().values() if item.incident_id == incident.id]
        notification_count += len(related)
        source_ids.extend(item.id for item in related)
    if not incidents:
        return ToolExecution(tool=tool, status="completed", summary="可见范围内没有未关闭事件上下文", source_ids=())
    summary = f"已读取 {len(incidents)} 个未关闭事件和 {notification_count} 条平台通知"
    return ToolExecution(tool=tool, status="completed", summary=summary, source_ids=tuple(source_ids))


def _execute_search_knowledge(tool: ReadOnlyTool, context: ToolContext) -> ToolExecution:
    """调用本地规程检索服务，返回版本化引用编号。"""

    from ..services.knowledge_generate import clean_query

    metric = None
    for alarm in data_source.alarms.list():
        if any(citation.source_id == alarm["id"] for citation in context.answer.citations):
            metric = alarm["metric"]
            break
    query = clean_query(context.request.message.strip() or "泵站 异常核查")
    station = _station_from_context(context)
    visible = _visible_station_ids(context.user)
    hits = search_rules(
        query,
        metric=metric,
        limit=3,
        station_id=station["id"] if station else None,
        visible_station_ids=visible,
    )
    if not hits and metric:
        hits = search_rules(
            f"{metric} 异常核查",
            metric=metric,
            limit=3,
            station_id=station["id"] if station else None,
            visible_station_ids=visible,
        )
    usable = [hit for hit in hits if hit.confidence != "low"]
    source_ids = tuple(hit.source_id for hit in usable)
    if not usable:
        return ToolExecution(tool=tool, status="completed", summary="检索到的资料置信度不足，未写入诊断依据", source_ids=())
    top = usable[0]
    summary = f"已检索规程 {top.source_id}（{top.title}），共 {len(hits)} 条候选"
    return ToolExecution(tool=tool, status="completed", summary=summary, source_ids=source_ids)


def _execute_explain_protocol(tool: ReadOnlyTool, context: ToolContext) -> ToolExecution:
    """展示诊断中已整理的规程说明；说明正文由答案层生成，本工具只播报步骤。"""

    text = (context.answer.protocol_explanation or "").strip()
    source_ids = tuple(
        citation.source_id for citation in context.answer.citations if citation.source_type == "knowledge"
    )
    if not text:
        return ToolExecution(
            tool=tool,
            status="completed",
            summary="无强相关规程说明可整理，请补充问法或导入现行规程",
            source_ids=source_ids,
        )
    preview = text if len(text) <= 96 else f"{text[:96]}…"
    return ToolExecution(
        tool=tool,
        status="completed",
        summary=f"已整理规程说明：{preview}",
        source_ids=source_ids,
    )


def _execute_calculate_supply_balance(tool: ReadOnlyTool, context: ToolContext) -> ToolExecution:
    """按可见片区计算供需差额，选出缺口最大的片区。"""

    rows = [row for row in data_source.supply.list() if user_has_station_access(context.user, row["station_id"])]
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
    "explain_protocol": _execute_explain_protocol,
    "calculate_supply_balance": _execute_calculate_supply_balance,
    "apply_control_boundary": _execute_apply_control_boundary,
}


def execute_tool(tool: ReadOnlyTool, context: ToolContext) -> ToolExecution:
    """执行一个白名单工具，并提供超时、失败和有限重试保护。"""

    handler = _TOOL_HANDLERS.get(tool.name)
    if handler is None:
        return ToolExecution(tool=tool, status="completed", summary="已完成只读工具检查", source_ids=())
    retry_limit = _tool_retry_limit()
    last_status = "failed"
    last_error = "未知工具错误"

    for attempt in range(1, retry_limit + 2):
        try:
            execution = _invoke_with_timeout(handler, tool, context)
            # 工具返回失败状态时同样允许有限重试，便于后续替换真实数据适配器。
            if execution.status not in {"completed", "failed", "timeout"}:
                execution = ToolExecution(
                    tool=execution.tool,
                    status="failed",
                    summary="工具返回了无法识别的执行状态",
                    source_ids=execution.source_ids,
                    read_only=execution.read_only,
                    error=f"未知状态：{execution.status}",
                )
            if execution.status == "completed":
                suffix = f"；第 {attempt} 次尝试成功" if attempt > 1 else ""
                execution = ToolExecution(
                    tool=execution.tool,
                    status=execution.status,
                    summary=f"{execution.summary}{suffix}",
                    source_ids=execution.source_ids,
                    read_only=execution.read_only,
                    agent=execution.agent,
                    attempts=attempt,
                    error=execution.error,
                )
                # 统一做一次权限裁剪，防止单个工具实现遗漏时把越权编号发给前端。
                filtered_ids = _filter_source_ids(tool.name, execution.source_ids, context)
                return ToolExecution(
                    tool=execution.tool,
                    status=execution.status,
                    summary=execution.summary,
                    source_ids=filtered_ids,
                    read_only=execution.read_only,
                    agent=execution.agent,
                    attempts=execution.attempts,
                    error=execution.error,
                )
            last_status = execution.status
            last_error = execution.error or execution.summary
        except FutureTimeoutError:
            last_status = "timeout"
            last_error = f"工具执行超过 {_tool_timeout_seconds():g} 秒"
        except Exception as exc:  # noqa: BLE001
            # 单个专业工具失败不能拖垮整轮 Agent；保留错误摘要并交给上层降级。
            last_status = "failed"
            last_error = str(exc) or exc.__class__.__name__

    attempts = retry_limit + 1
    status_label = "超时" if last_status == "timeout" else "失败"
    return ToolExecution(
        tool=tool,
        status=last_status,
        summary=f"{tool.label}{status_label}，已尝试 {attempts} 次；{last_error}",
        source_ids=(),
        read_only=True,
        attempts=attempts,
        error=last_error,
    )


def execute_plan(plan: AgentPlan, context: ToolContext) -> tuple[ToolExecution, ...]:
    """按协调器给出的顺序执行计划中的只读工具。"""

    return tuple(execute_tool(tool, context) for tool in plan.tools)
