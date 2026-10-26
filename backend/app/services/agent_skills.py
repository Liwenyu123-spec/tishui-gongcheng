"""调度技能目录。

技能说明适用场景、权限、允许的只读工具，以及是否必须人工确认。
协调器按问句或意图选中一项，不因此放行控制指令。
"""

_FORBIDDEN = ("start_pump", "stop_pump", "open_valve", "close_valve", "set_pressure")

_SKILLS = (
    {
        "id": "flow-drop-check",
        "title": "流量下降先核查",
        "version": "1",
        "keywords": ("流量下降", "出水下降", "流量低"),
        "intent": "diagnosis",
        "scenarios": ("流量下降", "出水偏低"),
        "permission": "ask",
        "allowed_tools": ("check_scope", "read_telemetry", "read_alarms", "search_knowledge", "explain_protocol"),
        "requires_confirmation": False,
        "summary": "先核对流量测点、关联告警和现行规程，不生成启停泵指令。",
    },
    {
        "id": "pressure-fluctuation-check",
        "title": "压力波动先核查",
        "version": "1",
        "keywords": ("压力波动", "压力下降", "压力异常"),
        "intent": "diagnosis",
        "scenarios": ("压力波动", "压力异常"),
        "permission": "ask",
        "allowed_tools": ("check_scope", "read_telemetry", "read_alarms", "search_knowledge", "explain_protocol"),
        "requires_confirmation": True,
        "summary": "先看压力趋势、告警和规程阈值。现场开关操作需人工确认。",
    },
    {
        "id": "control-boundary",
        "title": "控制请求拒绝",
        "version": "1",
        "keywords": ("启动", "停止", "开阀", "关阀"),
        "intent": "control_rejected",
        "scenarios": ("启停泵", "开关阀", "改设定"),
        "permission": "ask",
        "allowed_tools": ("check_scope", "apply_control_boundary"),
        "requires_confirmation": True,
        "summary": "拒绝控制请求，只说明只读边界。",
    },
    {
        "id": "station-status",
        "title": "运行状态核对",
        "version": "1",
        "keywords": (),
        "intent": "status",
        "scenarios": ("当前流量", "当前压力", "站点状态"),
        "permission": "ask",
        "allowed_tools": ("check_scope", "read_telemetry"),
        "requires_confirmation": False,
        "summary": "只读当前站点遥测，不改运行方式。",
    },
    {
        "id": "station-trend",
        "title": "趋势核对",
        "version": "1",
        "keywords": (),
        "intent": "trend",
        "scenarios": ("趋势", "波动", "近期变化"),
        "permission": "ask",
        "allowed_tools": ("check_scope", "read_telemetry", "read_event_context"),
        "requires_confirmation": False,
        "summary": "对照近期遥测和事件，不生成调度指令。",
    },
    {
        "id": "alarm-diagnosis",
        "title": "告警诊断",
        "version": "1",
        "keywords": (),
        "intent": "diagnosis",
        "scenarios": ("告警原因", "异常排查"),
        "permission": "ask",
        "allowed_tools": ("check_scope", "read_telemetry", "read_alarms", "read_event_context", "search_knowledge", "explain_protocol"),
        "requires_confirmation": False,
        "summary": "用告警、遥测和现行规程做只读排查。",
    },
    {
        "id": "knowledge-lookup",
        "title": "规程检索",
        "version": "1",
        "keywords": (),
        "intent": "knowledge",
        "scenarios": ("规程", "手册", "怎么核查"),
        "permission": "knowledge",
        "allowed_tools": ("check_scope", "search_knowledge", "explain_protocol"),
        "requires_confirmation": False,
        "summary": "只引用现行知识，不把规程改写成控制步骤。",
    },
    {
        "id": "supply-balance",
        "title": "供需核对",
        "version": "1",
        "keywords": (),
        "intent": "supply",
        "scenarios": ("供需", "供水量", "片区平衡"),
        "permission": "ask",
        "allowed_tools": ("check_scope", "calculate_supply_balance"),
        "requires_confirmation": False,
        "summary": "按可见片区计算供需差额，不直接改计划。",
    },
)


def _public(skill: dict) -> dict:
    return {
        "id": skill["id"],
        "title": skill["title"],
        "version": skill["version"],
        "scenarios": list(skill["scenarios"]),
        "permission": skill["permission"],
        "allowed_tools": list(skill["allowed_tools"]),
        "forbidden_tools": list(_FORBIDDEN),
        "requires_confirmation": skill["requires_confirmation"],
        "summary": skill["summary"],
    }


def list_skills() -> list[dict]:
    """返回可登记的只读技能，供页面和测试查看。"""
    return [_public(skill) for skill in _SKILLS]


def select_skill(message: str, intent: str = "") -> dict | None:
    """问句命中核查主题时优先用专项技能，否则按意图选用职责技能。"""
    text = message or ""
    for skill in _SKILLS:
        if skill["keywords"] and any(word in text for word in skill["keywords"]):
            return _public(skill)
    for skill in _SKILLS:
        if intent and skill["intent"] == intent and not skill["keywords"]:
            return _public(skill)
    return None
