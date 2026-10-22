"""协调 Agent 的专业节点编排入口。

协调器先生成最小计划，再交给共享状态式的专业 Agent 工作流执行。模型只影响
受限路由和答案表达；站点权限、工具白名单、事实和安全复核仍由后端确定。
"""

from .tools import AgentPlan, READ_ONLY_TOOLS, plan_for_question
from .workflow import CollaborationTrace, DispatchWorkflow
from ..schemas.agent import AgentAnswer
from uuid import uuid4
from ..services.agent_limits import agent_slot


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
        "knowledge": ["search_knowledge", "explain_protocol"],
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


def run_plan(
    answer: AgentAnswer,
    request,
    user: dict,
) -> tuple[AgentPlan, tuple[object, ...], AgentAnswer, CollaborationTrace]:
    """执行协调 → 专业 Agent → 安全复核 → 答案整理流程。"""

    from .executor import ToolContext
    from ..services.agent import reconcile_answer_with_tools

    run_id = answer.run_id or f"run-{uuid4().hex[:16]}"
    answer = answer.model_copy(update={"run_id": run_id, "thread_id": request.session_id})
    plan = coordinate(answer, request.message)
    context = ToolContext(user=user, request=request, answer=answer, run_id=run_id)
    with agent_slot() as acquired:
        if not acquired:
            from ..agent.executor import ToolExecution

            executions = tuple(
                ToolExecution(
                    tool=tool,
                    status="failed",
                    summary="当前 Agent 并发数已达到上限，请稍后重试",
                    error="进程内并发槽位不足",
                    error_code="AGENT_CAPACITY_EXCEEDED",
                )
                for tool in plan.tools
            )
            trace = CollaborationTrace(runs=())
        else:
            executions, trace = DispatchWorkflow(plan).run(context)
    final_answer = reconcile_answer_with_tools(answer, executions)
    from ..services.agent_llm import generate_answer_from_evidence

    generated_text = generate_answer_from_evidence(request.message, final_answer, executions)
    if generated_text:
        source = "llm-router+answer+mock" if "llm-router" in final_answer.source else "llm-answer+mock"
        final_answer = final_answer.model_copy(
            update={
                "answer": generated_text,
                "source": source,
                "limitations": [
                    *final_answer.limitations,
                    "最终措辞由可选大模型整理，事实、引用和工具证据仍由后端确定性工具提供",
                ],
            }
        )
    return plan, executions, final_answer, trace

