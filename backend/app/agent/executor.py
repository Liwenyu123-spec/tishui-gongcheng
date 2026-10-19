"""多 Agent 计划的只读 Mock 工具执行层。

当前执行器不访问外部系统，也不修改任何业务状态；它把规则服务已经整理出的
答案引用映射为可追踪的工具执行结果。后续接入真实数据源时，可以在这里替换
单个工具的读取实现，而不改变协调器和 SSE 事件格式。
"""

from dataclasses import dataclass

from ..schemas.agent import AgentAnswer
from .tools import AgentPlan, ReadOnlyTool


@dataclass(frozen=True)
class ToolExecution:
    """一次只读工具执行的可展示结果。"""

    tool: ReadOnlyTool
    status: str
    summary: str
    source_ids: tuple[str, ...] = ()
    read_only: bool = True


def _source_ids(answer: AgentAnswer, source_types: set[str]) -> tuple[str, ...]:
    """从结构化答案中提取指定类型的引用编号，保持工具结果可追溯。"""

    return tuple(citation.source_id for citation in answer.citations if citation.source_type in source_types)


def execute_tool(tool: ReadOnlyTool, answer: AgentAnswer) -> ToolExecution:
    """执行一个白名单工具的确定性 Mock 读取，并返回摘要和引用编号。"""

    source_ids: tuple[str, ...] = ()
    summaries = {
        "check_scope": "已校验当前账号的站点访问范围",
        "read_telemetry": "已读取答案关联的 Mock 遥测引用",
        "read_alarms": "已读取答案关联的 Mock 告警引用",
        "read_event_context": "已读取未关闭事件和平台通知上下文",
        "search_knowledge": "已检索版本化规程引用",
        "calculate_supply_balance": "已计算可见片区的供需差额",
        "apply_control_boundary": "已检查控制边界，未执行现场写操作",
    }
    source_type_map = {
        "read_telemetry": {"telemetry"},
        "read_alarms": {"alarm"},
        "read_event_context": {"incident", "notification"},
        "search_knowledge": {"knowledge", "policy"},
        "calculate_supply_balance": {"supply"},
        "apply_control_boundary": {"policy"},
    }
    if tool.name in source_type_map:
        source_ids = _source_ids(answer, source_type_map[tool.name])
    summary = summaries.get(tool.name, "已完成只读工具检查")
    if source_ids:
        summary = f"{summary}（{len(source_ids)} 条引用）"
    return ToolExecution(tool=tool, status="completed", summary=summary, source_ids=source_ids)


def execute_plan(plan: AgentPlan, answer: AgentAnswer) -> tuple[ToolExecution, ...]:
    """按协调器给出的顺序执行计划中的只读工具。"""

    return tuple(execute_tool(tool, answer) for tool in plan.tools)
