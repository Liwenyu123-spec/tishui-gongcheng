"""Agent 协作使用的只读工具目录、计划和白名单。

工具目录只描述允许读取的能力，实际执行由专业 Agent 工作流交给确定性的
Mock Service。模型可以建议计划，但不能绕过本目录、权限校验或安全边界。
"""

from dataclasses import dataclass
from typing import Literal

from ..schemas.agent import AgentIntent


ToolName = Literal[
    "check_scope",
    "read_telemetry",
    "read_alarms",
    "read_event_context",
    "search_knowledge",
    "explain_protocol",
    "calculate_supply_balance",
    "apply_control_boundary",
]


@dataclass(frozen=True)
class ReadOnlyTool:
    """一个只读工具的展示元数据。"""

    name: ToolName
    label: str
    description: str


@dataclass(frozen=True)
class AgentPlan:
    """协调 Agent 为一次问题生成的最小执行计划。"""

    primary_agent: str
    collaborating_agents: tuple[str, ...]
    tools: tuple[ReadOnlyTool, ...]


# 所有工具均为读取、计算或安全边界检查，不包含泵组、阀门或 PLC 写操作。
READ_ONLY_TOOLS: dict[ToolName, ReadOnlyTool] = {
    "check_scope": ReadOnlyTool("check_scope", "校验当前账号的站点范围", "确认问题涉及的站点是否在当前账号范围内"),
    "read_telemetry": ReadOnlyTool("read_telemetry", "读取站点遥测 Mock 数据", "读取固定 Mock 测点和数据质量元信息"),
    "read_alarms": ReadOnlyTool("read_alarms", "读取关联告警", "读取授权站点的告警和趋势样本"),
    "read_event_context": ReadOnlyTool("read_event_context", "读取未关闭事件和平台通知", "读取授权站点的事件、通知和处理状态"),
    "search_knowledge": ReadOnlyTool("search_knowledge", "检索版本化规程引用", "从当前规则知识目录返回适用规程引用"),
    "explain_protocol": ReadOnlyTool(
        "explain_protocol",
        "整理规程说明",
        "基于已检索片段整理核查说明；不编造实时数字，不生成控制指令",
    ),
    "calculate_supply_balance": ReadOnlyTool("calculate_supply_balance", "计算供需差额和缺口片区", "使用确定性代码计算供水量减需求量"),
    "apply_control_boundary": ReadOnlyTool("apply_control_boundary", "检查只读控制边界并拒绝控制指令", "识别控制请求并阻止任何现场写操作"),
}


def plan_for_question(intent: AgentIntent, message: str = "") -> AgentPlan:
    """按意图返回协调 Agent 的专业协作和工具白名单。"""

    common = (READ_ONLY_TOOLS["check_scope"],)
    if intent == "status":
        return AgentPlan("station_monitor_agent", ("station_monitor_agent",), common + (READ_ONLY_TOOLS["read_telemetry"],))
    if intent == "trend":
        return AgentPlan(
            "trend_analysis_agent",
            ("trend_analysis_agent", "event_context_agent"),
            common + (READ_ONLY_TOOLS["read_telemetry"], READ_ONLY_TOOLS["read_event_context"]),
        )
    if intent == "diagnosis":
        procedure_first = any(word in message for word in ("规程", "预案", "手册", "依据")) and not any(
            word in message for word in ("告警", "下降", "压力", "流量", "水位", "电流")
        )
        diagnosis_tools = (
            ("search_knowledge", "explain_protocol", "read_alarms", "read_event_context")
            if procedure_first
            else ("read_alarms", "search_knowledge", "explain_protocol", "read_event_context")
        )
        return AgentPlan(
            "diagnosis_agent",
            ("diagnosis_agent", "safety_review_agent", "event_context_agent"),
            common + tuple(READ_ONLY_TOOLS[name] for name in diagnosis_tools),
        )
    if intent == "knowledge":
        return AgentPlan(
            "diagnosis_agent",
            ("diagnosis_agent", "safety_review_agent"),
            common + (READ_ONLY_TOOLS["search_knowledge"], READ_ONLY_TOOLS["explain_protocol"]),
        )
    if intent == "supply":
        return AgentPlan("supply_balance_agent", ("supply_balance_agent",), common + (READ_ONLY_TOOLS["calculate_supply_balance"],))
    if intent == "control_rejected":
        return AgentPlan("safety_review_agent", ("safety_review_agent",), common + (READ_ONLY_TOOLS["apply_control_boundary"],))
    return AgentPlan("clarification_agent", ("clarification_agent",), common)


def plan_for_intent(intent: AgentIntent) -> AgentPlan:
    """兼容只按意图编排的调用。诊断类问题请改用 plan_for_question。"""

    return plan_for_question(intent)

