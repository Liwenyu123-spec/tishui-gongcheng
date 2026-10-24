"""规则驱动 Agent 路由。

接口以规则答案和只读工具为事实来源，可选使用大模型完成路由或最终措辞整理。
"""

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..agent.orchestrator import run_plan
from ..dependencies import require_roles
from ..schemas.agent import AgentAnswer, AgentChatRequest
from ..services.audit import record_audit
from ..services.agent_limits import limits_summary
from ..services.agent import build_answer
from ..services.agent_session import prepare_request
from ..services.agent_runs import cancel_run, list_runs, run_status


router = APIRouter(prefix="/api/v1", tags=["Agent"])


@router.post("/agent/runs/{run_id}/cancel")
def cancel_agent_run(run_id: str, user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> dict:
    """标记进程内 Agent 运行取消；工作流在下一个节点边界停止。"""
    cancel_run(run_id)
    return {"run_id": run_id, "status": "cancelled"}


@router.get("/agent/runs/{run_id}")
def get_agent_run(run_id: str, user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> dict:
    """查询当前进程内 Agent 运行状态。"""
    return run_status(run_id)


@router.get("/agent/runs")
def list_agent_runs(limit: int = 50, user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> list[dict]:
    """查询当前进程内最近的 Agent 运行摘要。"""
    return list_runs(limit)


def _sse_event(event: str, data: object) -> str:
    """将结构化数据编码为浏览器 EventSource 可读取的 SSE 事件。"""

    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/chat/stream")
def chat_stream(payload: AgentChatRequest, user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> StreamingResponse:
    """以 SSE 返回规则分析的开始、结果和结束事件。"""

    # 先按账号隔离的进程内会话合并短追问，保证答案、工具和模型看到同一有效问句。
    prepared_payload = prepare_request(payload, user)
    # 先得到确定性的初始分析，再按 Plan & Execute 执行只读工具，最后用工具
    # 实际返回的来源和状态校正答案，避免工具调用只成为展示日志。
    initial_answer = build_answer(prepared_payload, user)
    plan, executions, answer, trace = run_plan(initial_answer, prepared_payload, user)
    answer = answer.model_copy(
        update={
            "session_id": prepared_payload.session_id,
            "effective_question": (
                prepared_payload.message if prepared_payload.message != payload.message else None
            ),
        }
    )
    # 记录一次 Agent 查询的摘要，便于管理员在审计页面追踪请求编号和分析分支。
    # 当前只保存意图、来源和站点编号，不保存完整问题正文，避免审计日志膨胀。
    record_audit(
        "agent_query",
        "agent_run",
        answer.request_id,
        f"Agent 查询：意图={answer.intent}；来源={answer.source}；站点={prepared_payload.station_id or '自动识别'}",
        operator=user.get("username", "mock-admin"),
    )

    def events() -> Iterator[str]:
        # start 事件让前端可以显示“正在分析”，并标注模型参与阶段。
        llm_route_used = answer.source in {"llm-router+mock", "llm-router+answer+mock"}
        llm_answer_used = answer.source in {"llm-answer+mock", "llm-router+answer+mock"}
        yield _sse_event(
            "start",
            {
                "request_id": answer.request_id,
                "run_id": answer.run_id,
                "session_id": prepared_payload.session_id,
                "effective_question": prepared_payload.message if prepared_payload.message != payload.message else None,
                "mode": (
                    "llm-router+answer+rule-tools"
                    if llm_route_used and llm_answer_used
                    else "llm-router+rule-tools"
                    if llm_route_used
                    else "llm-answer+rule-tools"
                    if llm_answer_used
                    else "rule-mock"
                ),
                "llm_route_used": llm_route_used,
                "llm_answer_used": llm_answer_used,
                "planning_source": "llm+backend-guard" if answer.planned_tools else "rule",
                "coordinator": "dispatch_coordinator",
                "execution_mode": trace.execution_mode,
                "shared_state": trace.shared_state,
                "workflow_status": trace.status,
                "primary_agent": plan.primary_agent,
                "collaborating_agents": list(plan.collaborating_agents),
                "allowed_tools": [tool.name for tool in plan.tools],
                # 把本进程当前限额随 start 事件返回，便于前端和接口调试确认实际配置。
                "limits": limits_summary(),
            },
        )
        # agent 事件展示专业节点的真实执行状态，不再只展示计划中的角色名称。
        for agent_run in trace.runs:
            yield _sse_event(
                "agent",
                {"request_id": answer.request_id, "run_id": answer.run_id, **agent_run.as_event()},
            )
        # tool 事件只描述确定性只读步骤，不代表调用了真实现场或外部系统。
        failed_tools = []
        for execution in executions:
            tool = execution.tool
            if execution.attempts > 1:
                yield _sse_event(
                    "retry",
                    {
                        "request_id": answer.request_id,
                        "run_id": answer.run_id,
                        "name": tool.name,
                        "label": tool.label,
                        "agent": execution.agent,
                        "attempts": execution.attempts,
                        "status": execution.status,
                        "error": execution.error,
                        "error_code": execution.error_code,
                        "retryable": execution.retryable,
                    },
                )
            if execution.status in {"failed", "timeout"}:
                failed_tools.append(execution)
                yield _sse_event(
                    "error",
                    {
                        "request_id": answer.request_id,
                        "run_id": answer.run_id,
                        "name": tool.name,
                        "label": tool.label,
                        "agent": execution.agent,
                        "status": execution.status,
                        "attempts": execution.attempts,
                        "error": execution.error or execution.summary,
                        "error_code": execution.error_code,
                    },
                )
            yield _sse_event(
                "tool",
                {
                    "request_id": answer.request_id,
                    "run_id": answer.run_id,
                    "name": tool.name,
                    "label": tool.label,
                    "agent": execution.agent,
                    "status": execution.status,
                    "summary": execution.summary,
                    "source_ids": list(execution.source_ids),
                    "read_only": execution.read_only,
                    "attempts": execution.attempts,
                    "error": execution.error,
                    "tool_version": execution.tool_version,
                    "risk_level": execution.risk_level,
                    "required_permission": execution.required_permission,
                    "started_at": execution.started_at.isoformat() if execution.started_at else None,
                    "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
                    "duration_ms": execution.duration_ms,
                    "error_code": execution.error_code,
                    "retryable": execution.retryable,
                },
            )
        if failed_tools:
            yield _sse_event(
                "fallback",
                {
                    "request_id": answer.request_id,
                    "run_id": answer.run_id,
                    "status": "degraded",
                    "message": "部分只读工具失败或超时，已降级为人工复核提示",
                    "failed_tools": [execution.tool.name for execution in failed_tools],
                },
            )
        # result 事件只返回结构化答案，前端不需要解析自然语言日志。
        yield _sse_event("result", answer.model_dump(mode="json"))
        # done 事件表示本次 SSE 已完整结束，便于前端关闭 loading 状态。
        yield _sse_event("done", {"request_id": answer.request_id, "run_id": answer.run_id, "workflow_status": trace.status})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

