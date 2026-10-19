"""不依赖大模型的规则驱动 Agent 服务。

服务只读取现有内存 Mock 数据，负责意图判断、站点范围过滤、事实整理和依据引用。
后续接入模型时可以保留本服务作为安全边界和确定性回退路径。
"""

import re
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status

from ..data.incidents import _INCIDENTS, _NOTIFICATIONS
from ..data.monitoring import _ALARMS, _STATIONS
from ..data.supply import _SUPPLY_AREAS
from ..dependencies import user_has_station_access
from ..schemas.agent import AgentAnswer, AgentCitation, AgentChatRequest, AgentIntent, AgentWorkOrderSuggestion


_CONTROL_WORDS = ("启动", "停止", "开阀", "关阀", "切换阀", "修改压力", "下发", "控制指令")
_STATION_ALIASES = {
    "集泉": "jq-01",
    "一泵站": "pump-01",
    "二泵站": "pump-02",
    "三泵站": "pump-03",
    "四泵站": "pump-04",
    "平定入口": "pingding-inlet",
}

# 当前知识库接口只保存文档元数据，因此先用版本化规则表模拟可追溯的规程引用。
# 后续接入知识库正文或检索服务时，保留 source_id 和引用位置字段即可替换来源。
_DIAGNOSTIC_KNOWLEDGE = {
    "flow": {
        "source_id": "mock-knowledge-flow-v1.2",
        "title": "泵站流量异常核查规程 v1.2",
        "detail": "先核对入口压力、泵组运行电流和下游压力，再决定是否升级人工处置。",
    },
    "pressure": {
        "source_id": "mock-knowledge-pressure-v1.1",
        "title": "输水压力异常处置规程 v1.1",
        "detail": "先确认上下游压力测点有效，再核查阀门状态和泵组运行记录。",
    },
    "level": {
        "source_id": "mock-knowledge-level-v1.0",
        "title": "泵站水位巡检规程 v1.0",
        "detail": "连续观察水位趋势并核对来水情况，禁止仅凭单个 Mock 测点下结论。",
    },
    "current": {
        "source_id": "mock-knowledge-current-v1.0",
        "title": "泵组电流异常核查规程 v1.0",
        "detail": "核查电机负荷、运行记录和保护状态，必要时交由现场负责人确认。",
    },
}


def _now() -> datetime:
    """返回带时区的 UTC 时间，保证 SSE 返回时间格式统一。"""

    return datetime.now(timezone.utc)


def _time_range_label(message: str, default: str = "当前 Mock 样本") -> str:
    """从问题中提取可展示的时间范围，不伪造具体历史时间点。"""

    match = re.search(r"过去\s*(\d+)\s*(分钟|小时|天)", message)
    if match:
        return f"过去 {match.group(1)} {match.group(2)}"
    if "今天" in message:
        return "今天"
    if "最近" in message:
        return "最近一段 Mock 样本"
    return default


def _visible_stations(user: dict) -> list[dict]:
    """只返回当前账号有权查看的站点。"""

    return [station for station in _STATIONS if user_has_station_access(user, station["id"])]


def _find_station(message: str, requested_station_id: str | None, user: dict) -> dict | None:
    """按显式站点编号、中文别名或可见站点默认值定位站点。"""

    station_id = requested_station_id
    if station_id is None:
        for alias, candidate in _STATION_ALIASES.items():
            if alias in message:
                station_id = candidate
                break
    if station_id is not None:
        if not user_has_station_access(user, station_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权访问该站点")
        return next((station for station in _STATIONS if station["id"] == station_id), None)
    return next(iter(_visible_stations(user)), None)


def _intent(message: str) -> AgentIntent:
    """根据问题关键词选择确定性的分析分支。"""

    if any(word in message for word in _CONTROL_WORDS):
        return "control_rejected"
    if any(word in message for word in ("供需", "缺口", "片区")):
        return "supply"
    if any(word in message for word in ("过去", "最近", "趋势", "波动", "变化")):
        return "trend"
    if any(word in message for word in ("检查", "原因", "怎么办", "建议", "下降", "告警")):
        return "diagnosis"
    if any(word in message for word in ("当前", "现在", "多少", "状态", "流量", "压力", "水位", "能耗")):
        return "status"
    return "unknown"


def _telemetry_value(station: dict, metric: str) -> tuple[float, str]:
    """生成与监控接口一致的确定性 Mock 测点值。"""

    base_values = {"flow": (1120.0, "m³/h"), "pressure": (0.72, "MPa"), "level": (3.7, "m"), "energy": (184.0, "kWh")}
    value, unit = base_values[metric]
    # 不同站点使用稳定偏移，便于 Agent 回答具有区分度。
    offset = (station["sequence"] - 1) * 18 if metric == "flow" else (station["sequence"] - 1) * 0.02
    return round(value - offset, 3), unit


def _event_context(station_id: str, user: dict) -> tuple[list[str], list[str], list[AgentCitation]]:
    """读取站点未关闭事件及其平台通知，作为 Agent 的只读上下文。"""

    if not user_has_station_access(user, station_id):
        return [], [], []
    active_incidents = [
        incident
        for incident in _INCIDENTS.values()
        if incident.station_id == station_id and incident.status not in {"resolved", "false_positive"}
    ]
    facts: list[str] = []
    recommendations: list[str] = []
    citations: list[AgentCitation] = []
    for incident in active_incidents:
        facts.append(f"平台事件：{incident.id}，状态为 {incident.status}，上报次数 {incident.report_count}")
        citations.append(
            AgentCitation(
                source_type="incident",
                source_id=incident.id,
                title=f"站点事件 {incident.id}",
                detail=incident.description,
            )
        )
        related_notifications = [item for item in _NOTIFICATIONS.values() if item.incident_id == incident.id]
        for notification in related_notifications:
            facts.append(f"平台通知：{notification.id}，接收人 {notification.recipient}，状态为 {notification.status}")
            citations.append(
                AgentCitation(
                    source_type="notification",
                    source_id=notification.id,
                    title=f"事件通知 {notification.id}",
                    detail=f"接收人：{notification.recipient}；状态：{notification.status}；升级等级：{notification.escalation_level}",
                )
            )
            if notification.status == "sent":
                recommendations.append(f"通知 {notification.id} 尚未确认，建议在通知中心确认或按流程升级。")
    return facts, recommendations, citations


def _knowledge_context(alarm: dict) -> AgentCitation:
    """根据告警测点返回一条版本化的只读规程引用。"""

    rule = _DIAGNOSTIC_KNOWLEDGE.get(alarm["metric"], _DIAGNOSTIC_KNOWLEDGE["flow"])
    return AgentCitation(
        source_type="knowledge",
        source_id=rule["source_id"],
        title=rule["title"],
        detail=rule["detail"],
    )


def _answer_for_status(message: str, user: dict, request_id: str, now: datetime, requested_station_id: str | None) -> AgentAnswer:
    station = _find_station(message, requested_station_id, user)
    if station is None:
        return AgentAnswer(
            request_id=request_id,
            intent="unknown",
            answer="当前账号没有可查询的站点范围。",
            pending_items=["请由管理员为当前账号配置可见站点"],
            generated_at=now,
        )
    metric = "pressure" if "压力" in message else "level" if "水位" in message else "energy" if "能耗" in message else "flow"
    value, unit = _telemetry_value(station, metric)
    title = f"{station['name']} {metric} Mock 测点"
    return AgentAnswer(
        request_id=request_id,
        intent="status",
        answer=f"{station['name']}当前{metric}为 {value} {unit}，站点状态为 {station['status']}。",
        facts=[f"站点：{station['name']}（{station['id']}）", f"{metric}：{value} {unit}", f"数据来源：Mock 遥测"],
        recommendations=["当前结果仅用于联调，请在接入真实测点后复核。"],
        citations=[AgentCitation(source_type="telemetry", source_id=station["id"], title=title, detail="由现有监控 Mock 数据按固定规则生成")],
        confidence="medium",
        pending_items=["接入真实遥测后复核数据时间、测点质量和现场状态"],
        time_range=_time_range_label(message),
        generated_at=now,
    )


def _answer_for_trend(message: str, user: dict, request_id: str, now: datetime, requested_station_id: str | None) -> AgentAnswer:
    # 选择站点时只分析该站点；未选择时保留跨站点趋势排序行为。
    if requested_station_id is not None:
        selected_station = _find_station(message, requested_station_id, user)
        visible_ids = {selected_station["id"]} if selected_station else set()
    else:
        visible_ids = {station["id"] for station in _visible_stations(user)}
    alarms = [alarm for alarm in _ALARMS if alarm["station_id"] in visible_ids]
    alarm = max(alarms, key=lambda item: {"high": 3, "medium": 2, "low": 1}.get(item["level"], 0), default=None)
    if alarm is None:
        return AgentAnswer(
            request_id=request_id,
            intent="trend",
            answer="当前可见范围没有可分析的告警或趋势样本。",
            pending_items=["补充有效时间范围或等待新的遥测、告警样本"],
            generated_at=now,
        )
    context_facts, context_recommendations, context_citations = _event_context(alarm["station_id"], user)
    return AgentAnswer(
        request_id=request_id,
        intent="trend",
        answer=f"当前 Mock 样本中，{alarm['station_name']} 的 {alarm['metric']} 波动风险最高，告警等级为 {alarm['level']}。",
        facts=[f"告警值：{alarm['value']} {alarm['unit']}", f"阈值：{alarm['threshold']}", f"告警状态：{alarm['status']}"] + context_facts,
        recommendations=["建议查看该站点最近遥测，并核对泵组运行记录。"] + context_recommendations,
        citations=[AgentCitation(source_type="alarm", source_id=alarm["id"], title=f"{alarm['station_name']} {alarm['metric']} 告警", detail=alarm["description"])] + context_citations,
        confidence="medium",
        pending_items=["确认趋势时间窗内的原始测点和采样完整性"],
        time_range=_time_range_label(message),
        generated_at=now,
    )


def _answer_for_diagnosis(message: str, user: dict, request_id: str, now: datetime, requested_station_id: str | None) -> AgentAnswer:
    station = _find_station(message, requested_station_id, user)
    alarm = next((item for item in _ALARMS if station and item["station_id"] == station["id"]), None)
    if alarm is None:
        return AgentAnswer(
            request_id=request_id,
            intent="diagnosis",
            answer="当前站点没有匹配的 Mock 告警，暂时无法形成诊断建议。",
            confidence="low",
            pending_items=["补充有效告警或现场现象后再进行诊断"],
            generated_at=now,
        )
    context_facts, context_recommendations, context_citations = _event_context(alarm["station_id"], user)
    knowledge_citation = _knowledge_context(alarm)
    # 将诊断中的站点、问题和建议动作结构化返回，前端可据此生成工单草稿。
    work_order_suggestion = AgentWorkOrderSuggestion(
        station_id=alarm["station_id"],
        title=f"{alarm['station_name']}{alarm['metric']}异常核查",
        issue=alarm["description"],
        suggested_action=alarm["suggested_action"],
        priority=alarm["level"] if alarm["level"] in {"low", "medium", "high"} else "medium",
    )
    return AgentAnswer(
        request_id=request_id,
        intent="diagnosis",
        answer=f"根据 {alarm['station_name']} 的 Mock 告警，建议先核查泵组运行状态和下游压力数据。",
        facts=[alarm["description"], f"关联关系：{alarm['relation'] or '暂无关联片区'}"] + context_facts,
        recommendations=[alarm["suggested_action"], "核查完成前不要生成现场控制指令。"] + context_recommendations,
        citations=[
            AgentCitation(source_type="alarm", source_id=alarm["id"], title="关联告警", detail=alarm["description"]),
            AgentCitation(source_type="policy", source_id="mock-readonly-policy", title="只读分析边界", detail="Agent 只能提供分析和建议，不能操作泵组或阀门"),
            knowledge_citation,
        ] + context_citations,
        work_order_suggestion=work_order_suggestion,
        confidence="low",
        pending_items=["现场确认泵组运行状态和下游压力", "接入真实测点和维修历史后复核诊断"],
        time_range=_time_range_label(message),
        generated_at=now,
    )


def _answer_for_supply(user: dict, request_id: str, now: datetime) -> AgentAnswer:
    rows = [row for row in _SUPPLY_AREAS if user_has_station_access(user, row["station_id"])]
    if not rows:
        return AgentAnswer(
            request_id=request_id,
            intent="supply",
            answer="当前账号没有可查询的供需片区。",
            pending_items=["请由管理员为当前账号配置供需片区访问范围"],
            generated_at=now,
        )
    bottleneck = min(rows, key=lambda row: row["supply"] - row["demand"])
    balance = bottleneck["supply"] - bottleneck["demand"]
    return AgentAnswer(
        request_id=request_id,
        intent="supply",
        answer=f"当前 Mock 数据中，{bottleneck['area']} 的供需缺口最大，结余为 {balance:.0f} m³/d。",
        facts=[f"供水量：{bottleneck['supply']:.0f} m³/d", f"需求量：{bottleneck['demand']:.0f} m³/d", f"压力：{bottleneck['pressure']:.2f} MPa"],
        recommendations=["建议优先核查关联泵站流量和片区需求数据。"],
        citations=[AgentCitation(source_type="supply", source_id=bottleneck["station_id"], title=bottleneck["area"], detail="由供需 Mock 数据计算供水量减需求量")],
        confidence="medium",
        pending_items=["确认片区需求数据的统计时间窗、来源和完整性"],
        time_range="当前供需 Mock 统计周期",
        generated_at=now,
    )


def build_answer(payload: AgentChatRequest, user: dict) -> AgentAnswer:
    """构建一次确定性 Agent 答案，不调用模型或外部服务。"""

    request_id = f"agent-{uuid4().hex[:12]}"
    now = _now()
    intent = _intent(payload.message)
    if intent == "control_rejected":
        return AgentAnswer(
            request_id=request_id,
            intent=intent,
            answer="该请求涉及现场控制操作，当前 Agent 只允许只读分析，已拒绝生成控制指令。",
            facts=["控制接口当前未开放", "需要由授权人员在既有控制系统中执行操作"],
            recommendations=["如需处理异常，请先查看遥测、告警和规程核查建议。"],
            citations=[AgentCitation(source_type="policy", source_id="mock-readonly-policy", title="只读分析边界", detail="禁止向泵组、阀门、PLC、DCS 或 SCADA 下发命令")],
            confidence="high",
            pending_items=["由授权人员按现有控制系统和审批流程处理"],
            time_range="未执行控制查询",
            generated_at=now,
        )
    if intent == "status":
        return _answer_for_status(payload.message, user, request_id, now, payload.station_id)
    if intent == "trend":
        return _answer_for_trend(payload.message, user, request_id, now, payload.station_id)
    if intent == "diagnosis":
        return _answer_for_diagnosis(payload.message, user, request_id, now, payload.station_id)
    if intent == "supply":
        return _answer_for_supply(user, request_id, now)
    return AgentAnswer(
        request_id=request_id,
        intent="unknown",
        answer="我目前支持运行状态、趋势异常、供需缺口和规程核查问题。请补充站点或时间范围。",
        recommendations=["例如：现在二泵站的压力是多少？", "例如：过去两小时哪个泵站波动最大？"],
        confidence="low",
        pending_items=["补充站点、指标或时间范围"],
        time_range="未指定",
        generated_at=now,
    )

