"""提水工程 Agent 的专业节点协作工作流。

参考 ``H:\\Python工程\\agent`` 中的共享状态、流水线节点和审稿回路，
这里把当前项目的只读工具拆给可执行的专业 Agent。每个 Agent 只负责自己的
工具集合，所有结果回到共享协作状态，最后由安全复核 Agent 检查结果。

本阶段不让多个模型自由编造事实：专业 Agent 直接读取经过权限过滤的后端工具，
DeepSeek 仍只负责受限路由和答案整理。这样先得到可测试、可追踪的多 Agent
协作结构，后续再按 Agent 增加独立模型提示词不会改变安全边界。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..schemas.agent import AgentAnswer
from .executor import ToolContext, ToolExecution, execute_tool
from ..services.agent_limits import max_tool_calls
from .tools import AgentPlan, ReadOnlyTool


@dataclass(frozen=True)
class SpecialistRun:
    """一个专业 Agent 节点的结构化执行记录。"""

    agent: str
    role: str
    status: str
    summary: str
    tool_names: tuple[str, ...] = ()
    iterations: int = 1
    # 当前节点读取过的前序 Agent，明确共享状态的交接关系。
    depends_on: tuple[str, ...] = ()
    # 当前节点启动时看到的共享只读工具证据数量。
    shared_evidence_count: int = 0

    def as_event(self) -> dict[str, object]:
        """转换成 SSE 可直接返回的结构。"""

        return {
            "agent": self.agent,
            "role": self.role,
            "status": self.status,
            "summary": self.summary,
            "tool_names": list(self.tool_names),
            "iterations": self.iterations,
            "depends_on": list(self.depends_on),
            "shared_evidence_count": self.shared_evidence_count,
        }


@dataclass(frozen=True)
class CollaborationTrace:
    """一次协作工作流的共享状态摘要。"""

    runs: tuple[SpecialistRun, ...]
    execution_mode: str = "specialist-pipeline"
    shared_state: bool = True
    # 工作流级状态，供 SSE 和前端统一展示；当前运行在进程内同步完成。
    status: str = "completed"

    def as_events(self) -> list[dict[str, object]]:
        return [run.as_event() for run in self.runs]


_AGENT_ROLES = {
    "dispatch_coordinator": "调度协调与权限范围校验",
    "station_monitor_agent": "站点状态与遥测分析",
    "trend_analysis_agent": "跨站点趋势和波动分析",
    "diagnosis_agent": "告警、规程和异常诊断",
    "event_context_agent": "事件和平台通知上下文整理",
    "supply_balance_agent": "片区供需平衡计算",
    "safety_review_agent": "安全边界与结果复核",
    "clarification_agent": "问题澄清和缺失信息提示",
}


_AGENT_TOOL_NAMES: dict[str, tuple[str, ...]] = {
    "dispatch_coordinator": ("check_scope",),
    "station_monitor_agent": ("read_telemetry",),
    "trend_analysis_agent": ("read_telemetry",),
    "diagnosis_agent": ("read_alarms", "search_knowledge", "explain_protocol"),
    "event_context_agent": ("read_event_context",),
    "supply_balance_agent": ("calculate_supply_balance",),
    "safety_review_agent": ("apply_control_boundary",),
    "clarification_agent": (),
}


class SpecialistAgent:
    """拥有独立职责和工具白名单的专业 Agent 节点。"""

    def __init__(self, name: str) -> None:
        self.name = name
        from ..services.agent_registry import get_registered_agent
        registered = get_registered_agent(name) or {}
        self.role = str(registered.get("role") or _AGENT_ROLES.get(name, name))
        self.tool_names = tuple(registered.get("tool_names") or _AGENT_TOOL_NAMES.get(name, ()))

    def _tools_for_plan(self, plan: AgentPlan) -> tuple[ReadOnlyTool, ...]:
        allowed = set(self.tool_names)
        return tuple(tool for tool in plan.tools if tool.name in allowed)

    def run(self, plan: AgentPlan, context: ToolContext) -> tuple[SpecialistRun, tuple[ToolExecution, ...]]:
        """执行当前 Agent 的工具，并读取前序节点交接的共享状态快照。"""

        tools = self._tools_for_plan(plan)
        if not tools:
            return (
                SpecialistRun(
                    agent=self.name,
                    role=self.role,
                    status="skipped",
                    summary="本轮计划没有分配该 Agent 的工具",
                    tool_names=(),
                    depends_on=context.shared_agents,
                    shared_evidence_count=len(context.shared_executions),
                ),
                (),
            )

        executions: list[ToolExecution] = []
        for tool in tools:
            execution = execute_tool(tool, context)
            # 工具仍由统一执行层完成权限裁剪，但执行归属明确记录到专业 Agent。
            executions.append(replace(execution, agent=self.name))
        completed = sum(1 for execution in executions if execution.status == "completed")
        handoff = (
            f"；已接收 {len(context.shared_executions)} 条共享证据"
            if context.shared_executions
            else ""
        )
        summary = f"完成 {completed}/{len(executions)} 个只读步骤{handoff}"
        return (
            SpecialistRun(
                agent=self.name,
                role=self.role,
                status="completed" if completed == len(executions) else "partial",
                summary=summary,
                tool_names=tuple(tool.name for tool in tools),
                depends_on=context.shared_agents,
                shared_evidence_count=len(context.shared_executions),
            ),
            tuple(executions),
        )


class SafetyReviewAgent(SpecialistAgent):
    """对所有专业 Agent 的共享结果做最终安全复核。"""

    def review(
        self,
        answer: AgentAnswer,
        executions: tuple[ToolExecution, ...],
        tool_run: SpecialistRun | None,
        shared_agents: tuple[str, ...] = (),
    ) -> SpecialistRun:
        """复核共享状态中的全部工具证据和前序 Agent 交接关系。"""

        unsafe = [execution for execution in executions if not execution.read_only]
        evidence_note = f"；已复核 {len(shared_agents)} 个 Agent 的共享证据"
        if unsafe:
            return SpecialistRun(
                agent=self.name,
                role=self.role,
                status="blocked",
                summary="复核拒绝：发现非只读执行结果，未允许进入最终答案",
                tool_names=tool_run.tool_names if tool_run else (),
                iterations=1,
                depends_on=shared_agents,
                shared_evidence_count=len(executions),
            )

        if answer.intent == "control_rejected":
            summary = f"复核通过：控制请求已被边界工具拦截，未生成现场写指令{evidence_note}"
        else:
            summary = f"复核通过：{len(executions)} 个工具结果均为只读证据{evidence_note}"
        return SpecialistRun(
            agent=self.name,
            role=self.role,
            status="approved",
            summary=summary,
            tool_names=tool_run.tool_names if tool_run else (),
            iterations=1,
            depends_on=shared_agents,
            shared_evidence_count=len(executions),
        )


class DispatchWorkflow:
    """共享状态式的协调 → 专业节点 → 安全复核流水线。"""

    def __init__(self, plan: AgentPlan) -> None:
        self.plan = plan

    def _agent_order(self) -> tuple[str, ...]:
        names = ["dispatch_coordinator", *self.plan.collaborating_agents]
        if self.plan.primary_agent not in names:
            names.append(self.plan.primary_agent)
        # 安全复核必须最后执行，确保它看到所有专业 Agent 的结果。
        names = [name for name in names if name != "safety_review_agent"] + [
            name for name in names if name == "safety_review_agent"
        ]
        return tuple(dict.fromkeys(names))

    def run(self, context: ToolContext) -> tuple[tuple[ToolExecution, ...], CollaborationTrace]:
        executions: list[ToolExecution] = []
        runs: list[SpecialistRun] = []
        safety_run: SpecialistRun | None = None
        tool_budget = max_tool_calls()
        # 预算按整轮工作流累计，而不是每个专业 Agent 单独重新计数。

        for name in self._agent_order():
            from ..services.agent_runs import is_cancelled, is_paused
            if is_cancelled(context.run_id):
                runs.append(SpecialistRun(agent=name, role=_AGENT_ROLES.get(name, name), status="cancelled", summary="运行已被用户取消"))
                break
            if is_paused(context.run_id):
                runs.append(SpecialistRun(agent=name, role=_AGENT_ROLES.get(name, name), status="paused", summary="等待人工审批后继续执行"))
                break
            # 每个节点只拿到前序结果的不可变快照；本节点新结果完成后再写回共享列表。
            node_context = replace(
                context,
                shared_executions=tuple(executions),
                shared_agents=tuple(run.agent for run in runs),
            )
            if name == "safety_review_agent":
                # 先执行控制边界工具（如果计划包含），再复核前面所有共享结果。
                agent = SpecialistAgent(name)
                tool_run, tool_executions = agent.run(self.plan, node_context)
                tool_executions = tuple(
                    self._budget_execution(item, len(executions) + index, tool_budget)
                    for index, item in enumerate(tool_executions)
                )
                executions.extend(tool_executions)
                safety_run = SafetyReviewAgent(name).review(
                    node_context.answer,
                    tuple(executions),
                    tool_run,
                    shared_agents=node_context.shared_agents,
                )
                # 工具事件会单独展示；Agent 事件只保留合并后的最终复核状态，
                # 避免控制请求在前端出现两个同名安全 Agent 节点。
                runs.append(safety_run)
                continue

            run, tool_executions = SpecialistAgent(name).run(self.plan, node_context)
            tool_executions = tuple(
                self._budget_execution(item, len(executions) + index, tool_budget)
                for index, item in enumerate(tool_executions)
            )
            executions.extend(tool_executions)
            # 未分配工具的澄清 Agent 也保留节点记录，方便前端说明流程为何结束。
            runs.append(run)

        # 没有显式安全 Agent 的简单问题也必须经过一次只读复核。
        if safety_run is None:
            safety_run = SafetyReviewAgent("safety_review_agent").review(
                context.answer,
                tuple(executions),
                None,
                shared_agents=tuple(run.agent for run in runs),
            )
            runs.append(safety_run)

        workflow_status = "completed"
        if any(run.status == "cancelled" for run in runs):
            workflow_status = "cancelled"
        elif any(run.status == "paused" for run in runs):
            workflow_status = "paused"
        elif any(item.status == "timeout" for item in executions):
            workflow_status = "timeout"
        elif any(run.status == "blocked" for run in runs):
            workflow_status = "blocked"
        elif any(run.status in {"partial", "failed"} for run in runs):
            workflow_status = "degraded"
        return tuple(executions), CollaborationTrace(runs=tuple(runs), status=workflow_status)

    @staticmethod
    def _budget_execution(execution: ToolExecution, completed_count: int, limit: int) -> ToolExecution:
        """把跨专业节点的工具总调用数限制在本次请求预算内。

        超限步骤仍保留在执行列表中，便于 SSE 明确展示被拦截的工具和错误码，
        但不会调用其实际 handler。
        """

        if completed_count < limit:
            return execution
        return ToolExecution(
            tool=execution.tool,
            status="failed",
            summary=f"工具调用已达到本次请求上限（{limit}）",
            source_ids=(),
            read_only=execution.read_only,
            agent=execution.agent,
            attempts=0,
            error="工具调用预算已用尽",
            error_code="TOOL_BUDGET_EXCEEDED",
        )
