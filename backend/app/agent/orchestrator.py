"""协调 Agent 的规则编排入口。

这里先保留确定性的编排边界：答案仍由现有规则服务生成，协调器只决定专业 Agent
和只读工具白名单。后续接入模型或 LangGraph 时，可以在此处替换计划生成逻辑。
"""

from .tools import AgentPlan, READ_ONLY_TOOLS, plan_for_question
from ..schemas.agent import AgentAnswer


def coordinate(answer: AgentAnswer, message: str = "") -> AgentPlan:
    """根据意图和问题用词生成一次最小专业协作计划。"""

    rule_plan = plan_for_question(answer.intent, message)
    requested_names = [
        name
        for name in answer.planned_tools
        if name in READ_ONLY_TOOLS and name != "apply_control_boundary"
    ]
    if not requested_names or answer.intent == "control_rejected":
        return rule_plan

    # 模型可以调整顺序并选择可选工具，但不能删掉后端认为必需的工具。
    required_by_intent = {
        "status": ["read_telemetry"],
        "trend": ["read_telemetry"],
        "diagnosis": ["read_alarms", "search_knowledge", "explain_protocol"],
        "supply": ["calculate_supply_balance"],
    }
    required = required_by_intent.get(answer.intent, [])
    ordered_names: list[str] = ["check_scope"]
    for name in [*requested_names, *required]:
        if name not in ordered_names:
            ordered_names.append(name)

    return AgentPlan(
        primary_agent=rule_plan.primary_agent,
        collaborating_agents=rule_plan.collaborating_agents,
        tools=tuple(READ_ONLY_TOOLS[name] for name in ordered_names),
    )


def run_plan(answer: AgentAnswer, request, user: dict) -> tuple[AgentPlan, tuple[object, ...], AgentAnswer]:
    """执行一次 Plan & Execute 流程，再把工具结果交给答案校正阶段。

    这是当前 Mock 阶段的确定性版本：计划由规则生成，工具仍然是只读工具；
    结构上对应参考项目中的「制定计划 → 分步执行 → 结果汇总」，后续接入模型
    时可以替换计划生成器，而不改变权限和安全边界。
    """

    from .executor import ToolContext, execute_plan
    from ..services.agent import reconcile_answer_with_tools

    plan = coordinate(answer, request.message)
    executions = execute_plan(plan, ToolContext(user=user, request=request, answer=answer))
    final_answer = reconcile_answer_with_tools(answer, executions)
    return plan, executions, final_answer

