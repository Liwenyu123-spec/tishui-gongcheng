"""不依赖大模型的规则驱动 Agent 服务。

服务只读取现有内存 Mock 数据，负责意图判断、站点范围过滤、事实整理和依据引用。
后续接入模型时可以保留本服务作为安全边界和确定性回退路径。
"""

import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException, status

from ..data.incidents import _INCIDENTS, _NOTIFICATIONS
from ..data.monitoring import _ALARMS, _STATIONS
from ..data.supply import _SUPPLY_AREAS
from ..dependencies import user_has_station_access
from ..schemas.agent import AgentAnswer, AgentCitation, AgentChatRequest, AgentIntent, AgentWorkOrderSuggestion
from .analysis import compare_variation, latest_telemetry, metric_label
from .knowledge_search import search_rules


_CONTROL_WORDS = ("启动", "停止", "开阀", "关阀", "切换阀", "修改压力", "下发", "控制指令")
_STATION_ALIASES = {
    "集泉": "jq-01",
    "一泵站": "pump-01",
    "二泵站": "pump-02",
    "三泵站": "pump-03",
    "四泵站": "pump-04",
    "平定入口": "pingding-inlet",
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


def _freshness(observed_at: datetime | None, now: datetime) -> str:
    """按一小时阈值标记观测数据新鲜度，避免 Mock 旧样本伪装成实时数据。"""

    if observed_at is None:
        return "unknown"
    return "stale" if now - observed_at > timedelta(hours=1) else "fresh"


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
    """从统一的只读分析服务取得最新 Mock 测点值。"""

    sample = latest_telemetry(station, metric)
    if sample is None:
        raise ValueError(f"站点不支持测点: {metric}")
    return sample.value, sample.unit


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
    """根据告警测点检索一条版本化的只读规程引用。"""

    hits = search_rules(f"{alarm['metric']} 异常核查", metric=alarm["metric"], limit=1)
    rule = hits[0] if hits else search_rules("泵站 异常", limit=1)[0]
    return AgentCitation(
        source_type="knowledge",
        source_id=rule.source_id,
        title=rule.title,
        detail=rule.detail,
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
    sample = latest_telemetry(station, metric)
    if sample is None:
        return AgentAnswer(
            request_id=request_id,
            intent="status",
            answer=f"{station['name']}没有可用的{metric_label(metric)}测点，暂时不能给出数值。",
            facts=[f"站点：{station['name']}（{station['id']}）", f"请求指标：{metric_label(metric)}"],
            recommendations=["请确认该站点的测点配置或改查其他指标。"],
            confidence="low",
            pending_items=[f"补充{station['name']}的{metric_label(metric)}测点配置"],
            time_range=_time_range_label(message),
            generated_at=now,
        )
    value, unit = sample.value, sample.unit
    title = f"{station['name']} {metric_label(metric)} Mock 测点"
    return AgentAnswer(
        request_id=request_id,
        intent="status",
        answer=f"{station['name']}当前{metric_label(metric)}为 {value} {unit}，站点状态为 {station['status']}。",
        facts=[f"站点：{station['name']}（{station['id']}）", f"{metric}：{value} {unit}", f"数据来源：Mock 遥测"],
        recommendations=["当前结果仅用于联调，请在接入真实测点后复核。"],
        citations=[AgentCitation(source_type="telemetry", source_id=station["id"], title=title, detail=f"观测时间：{sample.observed_at.isoformat()}；质量：{sample.quality}")],
        confidence="medium",
        pending_items=["接入真实遥测后复核数据时间、测点质量和现场状态"],
        time_range=_time_range_label(message),
        observed_at=sample.observed_at,
        freshness=_freshness(sample.observed_at, now),
        generated_at=now,
    )


def _answer_for_trend(message: str, user: dict, request_id: str, now: datetime, requested_station_id: str | None) -> AgentAnswer:
    # 选择站点时只分析该站点；未选择时比较当前账号可见的全部站点。
    if requested_station_id is not None:
        selected_station = _find_station(message, requested_station_id, user)
        stations = [selected_station] if selected_station else []
    else:
        stations = _visible_stations(user)
    metric = "flow" if "流量" in message else "level" if "水位" in message else "energy" if "能耗" in message else "pressure"
    comparisons = compare_variation(stations, metric)
    if not comparisons:
        return AgentAnswer(
            request_id=request_id,
            intent="trend",
            answer=f"当前可见范围没有可分析的{metric_label(metric)}趋势样本。",
            pending_items=[f"补充有效时间范围或等待新的{metric_label(metric)}遥测样本"],
            generated_at=now,
        )
    top = comparisons[0]
    station = next(item for item in stations if item["id"] == top["station_id"])
    context_facts, context_recommendations, context_citations = _event_context(top["station_id"], user)
    telemetry_citations = [
        AgentCitation(
            source_type="telemetry",
            source_id=item["station_id"],
            title=f"{item['station_name']} {metric_label(metric)}趋势",
            detail=f"最大值 {item['maximum']} {item['unit']}，最小值 {item['minimum']} {item['unit']}，波动范围 {item['variation']} {item['unit']}",
        )
        for item in comparisons
    ]
    comparison_facts = [
        f"{item['station_name']}：波动范围 {item['variation']} {item['unit']}，最新值 {item['latest']} {item['unit']}"
        for item in comparisons[:3]
    ]
    return AgentAnswer(
        request_id=request_id,
        intent="trend",
        answer=f"按当前 Mock 时间序列的最大值减最小值计算，{top['station_name']}的{metric_label(metric)}波动最大，范围为 {top['variation']} {top['unit']}。",
        facts=[f"分析指标：{metric_label(metric)}", f"分析站点数：{len(comparisons)}", *comparison_facts] + context_facts,
        recommendations=[f"建议优先核对{station['name']}的原始测点、采样完整性和泵组运行记录。"] + context_recommendations,
        citations=telemetry_citations + context_citations,
        confidence="medium",
        pending_items=["确认趋势时间窗内的原始测点、单位和采样完整性", "当前结果仍是 Mock 样本，不能替代现场趋势判断"],
        time_range=_time_range_label(message),
        observed_at=top["observed_at"],
        freshness=_freshness(top["observed_at"], now),
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
        observed_at=alarm["occurred_at"],
        freshness=_freshness(alarm["occurred_at"], now),
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

