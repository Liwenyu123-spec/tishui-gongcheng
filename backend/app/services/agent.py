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
from .knowledge_search import KNOWLEDGE_RULES, KnowledgeHit, search_rules


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
    if any(word in message for word in ("检查", "核查", "原因", "怎么办", "建议", "下降", "告警", "规程")):
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


def _knowledge_hits(alarm: dict, message: str = "") -> list[KnowledgeHit]:
    """按告警测点与问句检索可引用规程，已过滤低置信命中。"""

    from .knowledge_generate import clean_query

    query = clean_query(f"{alarm.get('station_name', '')}{alarm['metric']}异常核查 {message}".strip())
    hits = [
        hit
        for hit in search_rules(
            query or f"{alarm['metric']} 异常核查",
            metric=alarm["metric"],
            limit=5,
            station_id=alarm["station_id"],
        )
        if hit.confidence != "low"
    ]
    if not hits:
        hits = [
            hit
            for hit in search_rules(
                f"{alarm['metric']} 异常核查",
                metric=alarm["metric"],
                limit=5,
                station_id=alarm["station_id"],
            )
            if hit.confidence != "low"
        ]
    if not hits:
        hits = [hit for hit in search_rules("泵站 异常", limit=3) if hit.confidence != "low"]
    return hits


def _knowledge_context(alarm: dict, message: str = "") -> AgentCitation:
    """根据告警测点检索一条版本化的只读规程引用。"""

    hits = _knowledge_hits(alarm, message)
    rule = hits[0] if hits else None
    if rule is None:
        builtin = KNOWLEDGE_RULES[0]
        rule = KnowledgeHit(
            source_id=builtin.source_id,
            title=f"{builtin.title} {builtin.version}",
            version=builtin.version,
            detail=builtin.detail,
            score=1,
        )
    return AgentCitation(
        source_type="knowledge",
        source_id=rule.source_id,
        title=rule.title,
        detail=rule.detail,
    )


def _protocol_explanation(alarm: dict, message: str) -> tuple[str | None, list[AgentCitation]]:
    """用强相关规程片段生成说明；无密钥时回退为原文摘要。测点数字不交给模型。"""

    from .knowledge_generate import (
        check_groundedness,
        compress_hits,
        generation_status,
        select_strong_hits,
        _complete,
    )

    hits = _knowledge_hits(alarm, message)
    strong, _gate = select_strong_hits(hits)
    if not strong:
        citation = _knowledge_context(alarm, message)
        return None, [citation]

    citations = [
        AgentCitation(source_type="knowledge", source_id=hit.source_id, title=hit.title, detail=hit.detail)
        for hit in strong[:3]
    ]
    status = generation_status()
    metric_name = metric_label(alarm["metric"])
    question = (
        f"{alarm['station_name']}出现{metric_name}告警，按现行规程应如何核查？"
        "只根据资料说明核查要点，不要写实时数字，不要给出开关泵或阀门指令。"
    )
    if status["generation_ready"]:
        compressed, _ = compress_hits(strong[:3], question)
        try:
            text = _complete(question, compressed)
            grounded = check_groundedness(text, compressed)
            if not grounded["grounded"]:
                text = f"{text}\n（忠实度提示：请以规程原文为准，勿作为操作依据。）"
            return text, citations
        except Exception:
            pass
    top = strong[0]
    return f"依据《{top.title}》：{top.detail}", citations


def _diagnosis_checks(alarm: dict) -> list[str]:
    """按告警指标给出确定性的现场核查顺序。"""

    checks = {
        "flow": ["核对入口压力和泵组运行电流", "核对下游压力与阀门状态", "确认测点质量和采样是否连续"],
        "pressure": ["确认上下游压力测点有效", "核查阀门状态和泵组运行记录", "确认是否存在关联片区压力变化"],
        "level": ["连续观察水位趋势", "核对来水量和进出水流量", "确认水位测点质量和现场液位"],
        "current": ["核查电机负荷和运行记录", "核对保护状态及泵组编号", "由现场负责人确认是否需要停机检查"],
    }
    return checks.get(alarm["metric"], ["核对关联测点、运行记录和现场状态"])


def _answer_for_status(
    message: str,
    user: dict,
    request_id: str,
    now: datetime,
    requested_station_id: str | None,
    metric_override: str | None = None,
) -> AgentAnswer:
    station = _find_station(message, requested_station_id, user)
    if station is None:
        return AgentAnswer(
            request_id=request_id,
            intent="unknown",
            answer="当前账号没有可查询的站点范围。",
            pending_items=["请由管理员为当前账号配置可见站点"],
            generated_at=now,
        )
    metric = metric_override or (
        "pressure" if "压力" in message else "level" if "水位" in message else "energy" if "能耗" in message else "flow"
    )
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
        facts=[f"站点：{station['name']}（{station['id']}）", f"{metric_label(metric)}：{value} {unit}", f"数据来源：Mock 遥测"],
        recommendations=["当前结果仅用于联调，请在接入真实测点后复核。"],
        citations=[AgentCitation(source_type="telemetry", source_id=station["id"], title=title, detail=f"观测时间：{sample.observed_at.isoformat()}；质量：{sample.quality}")],
        confidence="medium",
        pending_items=["接入真实遥测后复核数据时间、测点质量和现场状态"],
        time_range=_time_range_label(message),
        observed_at=sample.observed_at,
        freshness=_freshness(sample.observed_at, now),
        generated_at=now,
    )


def _answer_for_trend(
    message: str,
    user: dict,
    request_id: str,
    now: datetime,
    requested_station_id: str | None,
    metric_override: str | None = None,
) -> AgentAnswer:
    # 选择站点时只分析该站点；未选择时比较当前账号可见的全部站点。
    if requested_station_id is not None:
        selected_station = _find_station(message, requested_station_id, user)
        stations = [selected_station] if selected_station is not None else []
    else:
        stations = _visible_stations(user)
    metric = metric_override or (
        "flow" if "流量" in message else "level" if "水位" in message else "energy" if "能耗" in message else "pressure"
    )
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
    station_named = requested_station_id is not None or any(alias in message for alias in _STATION_ALIASES)
    if not station_named:
        return AgentAnswer(
            request_id=request_id,
            intent="diagnosis",
            answer="诊断需要先确定泵站。请补充站点，例如二泵站，或在页面选择站点后再提问。",
            confidence="low",
            pending_items=["补充要核查的泵站"],
            generated_at=now,
        )
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
    protocol_text, knowledge_citations = _protocol_explanation(alarm, message)
    checks = _diagnosis_checks(alarm)
    station = next((item for item in _STATIONS if item["id"] == alarm["station_id"]), None)
    telemetry = latest_telemetry(station, alarm["metric"]) if station else None
    telemetry_citations = [
        AgentCitation(
            source_type="telemetry",
            source_id=alarm["station_id"],
            title=f"{alarm['station_name']} {metric_label(alarm['metric'])}测点",
            detail=f"当前 Mock 值 {telemetry.value} {telemetry.unit}；观测时间：{telemetry.observed_at.isoformat()}",
        )
    ] if telemetry else []
    # 将诊断中的站点、问题和建议动作结构化返回，前端可据此生成工单草稿。
    work_order_suggestion = AgentWorkOrderSuggestion(
        station_id=alarm["station_id"],
        title=f"{alarm['station_name']}{alarm['metric']}异常核查",
        issue=alarm["description"],
        suggested_action=alarm["suggested_action"],
        priority=alarm["level"] if alarm["level"] in {"low", "medium", "high"} else "medium",
    )
    answer_lines = [
        f"根据 {alarm['station_name']} 的 Mock 告警，建议先执行：{checks[0]}。",
        "当前只能形成核查建议，不能认定设备已经故障。",
    ]
    if protocol_text:
        answer_lines.append(f"规程说明：{protocol_text}")
    return AgentAnswer(
        request_id=request_id,
        intent="diagnosis",
        answer="\n".join(answer_lines),
        facts=[alarm["description"], f"告警值：{alarm['value']} {alarm['unit']}；阈值：{alarm['threshold']}", f"关联关系：{alarm['relation'] or '暂无关联片区'}", f"核查顺序：{'；'.join(checks)}"] + context_facts,
        recommendations=[*checks, "核查完成前不要生成现场控制指令。"] + context_recommendations,
        citations=[
            AgentCitation(source_type="alarm", source_id=alarm["id"], title="关联告警", detail=alarm["description"]),
            AgentCitation(source_type="policy", source_id="mock-readonly-policy", title="只读分析边界", detail="Agent 只能提供分析和建议，不能操作泵组或阀门"),
        ] + knowledge_citations + telemetry_citations + context_citations,
        work_order_suggestion=work_order_suggestion,
        protocol_explanation=protocol_text,
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
    """构建 Agent 答案；可选使用大模型路由，数据仍由确定性工具提供。"""

    request_id = f"agent-{uuid4().hex[:12]}"
    now = _now()
    intent = _intent(payload.message)
    model_route = None
    if intent != "control_rejected":
        from .agent_llm import route_question

        model_route = route_question(
            payload.message,
            visible_stations=_visible_stations(user),
            requested_station_id=payload.station_id,
        )
        if model_route is not None:
            intent = model_route.intent
            if model_route.station_id is not None:
                payload = payload.model_copy(update={"station_id": model_route.station_id})
    metric_override = None if model_route is None or model_route.metric == "unknown" else model_route.metric
    if intent == "control_rejected":
        answer = AgentAnswer(
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
    elif intent == "status":
        answer = _answer_for_status(payload.message, user, request_id, now, payload.station_id, metric_override)
    elif intent == "trend":
        answer = _answer_for_trend(payload.message, user, request_id, now, payload.station_id, metric_override)
    elif intent == "diagnosis":
        answer = _answer_for_diagnosis(payload.message, user, request_id, now, payload.station_id)
    elif intent == "supply":
        answer = _answer_for_supply(user, request_id, now)
    else:
        answer = AgentAnswer(
            request_id=request_id,
            intent="unknown",
            answer="我目前支持运行状态、趋势异常、供需缺口和规程核查问题。请补充站点或时间范围。",
            recommendations=["例如：现在二泵站的压力是多少？", "例如：过去两小时哪个泵站波动最大？"],
            confidence="low",
            pending_items=["补充站点、指标或时间范围"],
            time_range="未指定",
            generated_at=now,
        )

    if model_route is not None:
        answer = answer.model_copy(
            update={
                "source": "llm-router+mock",
                "time_range": model_route.time_range or answer.time_range,
                "facts": [
                    *answer.facts,
                    f"大模型路由：意图={model_route.intent}；指标={model_route.metric}；时间范围={model_route.time_range}",
                ],
                "limitations": [
                    *answer.limitations,
                    "大模型仅用于问题路由，数值和引用仍由后端只读工具计算",
                ],
            }
        )
    return answer


def reconcile_answer_with_tools(answer: AgentAnswer, executions: tuple[object, ...]) -> AgentAnswer:
    """用实际执行过的只读工具结果校正答案和引用。

    当前规则分支仍负责生成业务答案，但工具执行不再只是前端展示轨迹：
    这里会根据工具实际返回的来源编号过滤答案引用，并在知识工具没有有效
    命中时撤掉规程说明，避免把未检索到的默认规则误当成检索依据。

    ``object`` 是为了避免服务层和 agent 执行层形成循环导入；执行对象只需
    提供 ``tool.name``、``source_ids`` 和 ``summary`` 属性。
    """

    executed_source_ids = {
        source_id
        for execution in executions
        for source_id in getattr(execution, "source_ids", ())
    }
    executed_tool_names = {
        getattr(getattr(execution, "tool", None), "name", "")
        for execution in executions
    }

    # 只保留本轮工具真正返回或明确允许的引用。策略引用不属于数据检索，
    # 必须始终保留，用来说明只读边界。
    filtered_citations = [
        citation
        for citation in answer.citations
        if citation.source_type == "policy" or citation.source_id in executed_source_ids
    ]

    updates: dict[str, object] = {
        "citations": filtered_citations,
        "facts": [
            *answer.facts,
            *[
                f"工具证据：{getattr(execution, 'summary', '')}"
                for execution in executions
                if getattr(execution, "summary", "")
            ],
        ],
    }

    # 诊断必须经过知识检索；没有有效知识来源时不能继续保留规程说明。
    knowledge_tools_used = {"search_knowledge", "explain_protocol"}.intersection(executed_tool_names)
    has_knowledge_evidence = any(
        citation.source_type == "knowledge" and citation.source_id in executed_source_ids
        for citation in filtered_citations
    )
    if answer.intent == "diagnosis" and knowledge_tools_used and not has_knowledge_evidence:
        updates["protocol_explanation"] = None
        updates["confidence"] = "low"
        updates["pending_items"] = [
            *answer.pending_items,
            "当前工具链没有返回足够的现行规程依据，请补充资料或由人工复核",
        ]
        updates["limitations"] = [
            *answer.limitations,
            "本次诊断未使用有效知识库命中，不能将通用建议视为规程结论",
        ]

    return answer.model_copy(update=updates)

