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

    def with_custom(plan: AgentPlan) -> AgentPlan:
        """让工具集合与本轮计划相交的自定义 Agent 进入条件分支。"""
        from ..services.agent_registry import list_registered_agents

        tool_names = {tool.name for tool in plan.tools}
        custom_agents = [
            str(item["name"])
            for item in list_registered_agents()
            if item.get("custom") and tool_names.intersection(item.get("tool_names") or [])
        ]
        from ..services.agent_skills import select_skill

        skill = select_skill(message, answer.intent)
        base = plan if not custom_agents else AgentPlan(
            primary_agent=plan.primary_agent,
            collaborating_agents=tuple(dict.fromkeys((*plan.collaborating_agents, *custom_agents))),
            tools=plan.tools,
        )
        if not skill:
            return base
        return AgentPlan(
            primary_agent=base.primary_agent,
            collaborating_agents=base.collaborating_agents,
            tools=base.tools,
            skill_id=skill["id"],
            skill_summary=skill["summary"],
        )

    requested_names = [
        name
        for name in answer.planned_tools
        if name in READ_ONLY_TOOLS and name != "apply_control_boundary"
    ]
    if not requested_names or answer.intent == "control_rejected":
        return with_custom(rule_plan)

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

    return with_custom(AgentPlan(
        primary_agent=rule_plan.primary_agent,
        collaborating_agents=rule_plan.collaborating_agents,
        tools=tuple(READ_ONLY_TOOLS[name] for name in ordered_names),
    ))


def run_plan(
    answer: AgentAnswer,
    request,
    user: dict,
) -> tuple[AgentPlan, tuple[object, ...], AgentAnswer, CollaborationTrace]:
    """执行协调 → 专业 Agent → 安全复核 → 答案整理流程。"""

    from .executor import ToolContext
    from ..services.agent import reconcile_answer_with_tools

    from ..services.agent_runs import save_task_snapshot

    def save_capacity_snapshot(run_id: str, request) -> None:
        """并发槽位不足时留下可重放的问题快照，供稍后恢复同一轮分析。"""
        save_task_snapshot(run_id, {
            "user_id": user.get("id") or user.get("username"),
            "message": request.message,
            "station_id": getattr(request, "station_id", None),
            "session_id": getattr(request, "session_id", None),
            "reason": "capacity",
        })

    run_id = answer.run_id or f"run-{uuid4().hex[:16]}"
    from ..services.agent_runs import set_run_status
    set_run_status(run_id, "running")
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
            trace = CollaborationTrace(runs=(), status="degraded")
            save_capacity_snapshot(run_id, request)
        else:
            executions, trace = DispatchWorkflow(plan).run(context)
    final_answer = reconcile_answer_with_tools(answer, executions)
    set_run_status(run_id, trace.status)
    from ..services.agent_llm import generate_answer_from_evidence
    from ..services.agent_limits import max_model_calls

    # 第 2 次模型预算用于答案润色；预算不足时保留确定性规则答案。
    generated_text = (
        generate_answer_from_evidence(request.message, final_answer, executions)
        if max_model_calls() >= 2
        else None
    )
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

