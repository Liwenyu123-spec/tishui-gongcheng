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
from ..services.agent_session import prepare_request, session_summary
from ..services.agent_registry import list_registered_agents, register_agent
from ..services.agent_skills import list_skills
from ..services.agent_runs import cancel_run, clear_task_snapshot, decide_run, list_runs, pause_run, resume_run, run_status, save_task_snapshot, task_snapshot


router = APIRouter(prefix="/api/v1", tags=["Agent"])


@router.get("/agent/skills")
def get_agent_skills(user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> list[dict]:
    """查看只读技能目录：场景、权限、允许的工具和是否需要人工确认。"""
    return list_skills()


@router.get("/agent/registry")
def get_agent_registry(user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> list[dict]:
    """查看当前进程内专业 Agent 注册目录。"""
    return list_registered_agents()


@router.post("/agent/registry")
def register_agent_endpoint(payload: dict, user: dict = Depends(require_roles("admin"))) -> dict:
    """管理员注册进程内只读 Agent；服务重启后清空。"""
    try:
        return register_agent(str(payload.get("name", "")), str(payload.get("role", "")), list(payload.get("tool_names", [])))
    except (TypeError, ValueError) as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/agent/runs/{run_id}/cancel")
def cancel_agent_run(run_id: str, user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> dict:
    """标记进程内 Agent 运行取消；工作流在下一个节点边界停止。"""
    cancel_run(run_id)
    return {"run_id": run_id, "status": "cancelled"}


@router.get("/agent/runs/{run_id}")
def get_agent_run(run_id: str, user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> dict:
    """查询当前进程内 Agent 运行状态。"""
    return run_status(run_id)


@router.post("/agent/runs/{run_id}/pause")
def pause_agent_run(run_id: str, user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> dict:
    """标记运行进入人工审批暂停状态。"""
    pause_run(run_id)
    return {"run_id": run_id, "status": "paused"}


@router.post("/agent/runs/{run_id}/decision")
def decide_agent_run(run_id: str, payload: dict, user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> dict:
    """人工审批：approve 允许随后恢复，reject 停止并删除快照。"""
    try:
        return decide_run(run_id, str(payload.get("decision") or ""), str(payload.get("reason") or ""))
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/agent/runs/{run_id}/resume")
def resume_agent_run(run_id: str, user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> dict:
    """恢复人工审批暂停的运行。"""
    resume_run(run_id)
    return {"run_id": run_id, "status": "running"}


@router.post("/agent/runs/{run_id}/resume-stream")
def resume_agent_stream(run_id: str, user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> StreamingResponse:
    """恢复一个已保存的审批任务，并重新返回同一问题的 SSE 流。"""
    current = run_status(run_id)
    if current.get("status") == "rejected":
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="该运行已被驳回，不能恢复")
    snapshot = task_snapshot(run_id)
    if snapshot is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="可恢复任务不存在或已过期")
    if str(snapshot.get("user_id")) != str(user.get("id") or user.get("username")):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="无权恢复其他账号的任务")
    clear_task_snapshot(run_id)
    resume_run(run_id)
    payload = AgentChatRequest(message=str(snapshot["message"]), station_id=snapshot.get("station_id"), session_id=snapshot.get("session_id"))
    return chat_stream(payload, user)


@router.get("/agent/runs")
def list_agent_runs(limit: int = 50, user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> list[dict]:
    """查询当前进程内最近的 Agent 运行摘要。"""
    return list_runs(limit)


@router.get("/agent/sessions/{session_id}/summary")
def get_agent_session_summary(session_id: str, user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> dict:
    """查询当前账号 Agent 会话的短上下文摘要。"""
    return session_summary(session_id, user)


def _sse_event(event: str, data: object) -> str:
    """将结构化数据编码为浏览器 EventSource 可读取的 SSE 事件。"""

    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/chat/stream")
def chat_stream(payload: AgentChatRequest, user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> StreamingResponse:
    """以 SSE 返回规则分析的开始、结果和结束事件。"""

    # 先按账号隔离的进程内会话合并短追问，保证答案、工具和模型看到同一有效问句。
    prepared_payload = prepare_request(payload, user)
    if payload.require_approval:
        from uuid import uuid4
        run_id = f"run-{uuid4().hex[:16]}"
        save_task_snapshot(run_id, {
            "user_id": user.get("id") or user.get("username"),
            "message": prepared_payload.message,
            "station_id": prepared_payload.station_id,
            "session_id": prepared_payload.session_id,
        })
        pause_run(run_id)

        def paused_events() -> Iterator[str]:
            yield _sse_event("start", {"run_id": run_id, "workflow_status": "paused", "requires_approval": True})
            yield _sse_event("done", {"run_id": run_id, "workflow_status": "paused"})

        return StreamingResponse(paused_events(), media_type="text/event-stream")
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

    from ..services.agent_session import remember_outcome
    remember_outcome(
        prepared_payload.session_id or "",
        user,
        conclusion=answer.answer,
        station_id=prepared_payload.station_id,
        pending_items=list(answer.pending_items or []),
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
                "workflow_branch": (
                    "control-boundary" if answer.intent == "control_rejected"
                    else "knowledge-procedure" if answer.intent == "knowledge"
                    else "diagnosis-procedure" if answer.intent == "diagnosis" and "规程" in prepared_payload.message and not any(word in prepared_payload.message for word in ("告警", "下降", "压力", "流量", "水位", "电流"))
                    else "diagnosis-operational" if answer.intent == "diagnosis"
                    else f"{answer.intent}-analysis"
                ),
                "coordinator": "dispatch_coordinator",
                "execution_mode": trace.execution_mode,
                "shared_state": trace.shared_state,
                "workflow_status": trace.status,
                "primary_agent": plan.primary_agent,
                "collaborating_agents": list(plan.collaborating_agents),
                "allowed_tools": [tool.name for tool in plan.tools],
                "skill_id": plan.skill_id,
                "skill_summary": plan.skill_summary,
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

