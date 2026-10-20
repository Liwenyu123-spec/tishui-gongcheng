"""规则驱动 Agent 路由。

当前接口只输出 Mock 数据分析和安全边界提示，不调用大模型。
"""

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..agent.orchestrator import run_plan
from ..dependencies import require_roles
from ..schemas.agent import AgentAnswer, AgentChatRequest
from ..services.audit import record_audit
from ..services.agent import build_answer


router = APIRouter(prefix="/api/v1", tags=["Agent"])


def _sse_event(event: str, data: object) -> str:
    """将结构化数据编码为浏览器 EventSource 可读取的 SSE 事件。"""

    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/chat/stream")
def chat_stream(payload: AgentChatRequest, user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> StreamingResponse:
    """以 SSE 返回规则分析的开始、结果和结束事件。"""

    # 先得到确定性的初始分析，再按 Plan & Execute 执行只读工具，最后用工具
    # 实际返回的来源和状态校正答案，避免工具调用只成为展示日志。
    initial_answer = build_answer(payload, user)
    plan, executions, answer = run_plan(initial_answer, payload, user)
    # 记录一次 Agent 查询的摘要，便于管理员在审计页面追踪请求编号和分析分支。
    # 当前只保存意图、来源和站点编号，不保存完整问题正文，避免审计日志膨胀。
    record_audit(
        "agent_query",
        "agent_run",
        answer.request_id,
        f"Agent 查询：意图={answer.intent}；来源={answer.source}；站点={payload.station_id or '自动识别'}",
        operator=user.get("username", "mock-admin"),
    )

    def events() -> Iterator[str]:
        # start 事件让前端可以显示“正在分析”，同时明确当前不使用模型。
        yield _sse_event(
            "start",
            {
                "request_id": answer.request_id,
                "mode": "rule-mock",
                "coordinator": "dispatch_coordinator",
                "primary_agent": plan.primary_agent,
                "collaborating_agents": list(plan.collaborating_agents),
                "allowed_tools": [tool.name for tool in plan.tools],
            },
        )
        # tool 事件只描述确定性只读步骤，不代表调用了真实现场或外部系统。
        for execution in executions:
            tool = execution.tool
            yield _sse_event(
                "tool",
                {
                    "request_id": answer.request_id,
                    "name": tool.name,
                    "label": tool.label,
                    "agent": plan.primary_agent,
                    "status": execution.status,
                    "summary": execution.summary,
                    "source_ids": list(execution.source_ids),
                    "read_only": execution.read_only,
                },
            )
        # result 事件只返回结构化答案，前端不需要解析自然语言日志。
        yield _sse_event("result", answer.model_dump(mode="json"))
        # done 事件表示本次 SSE 已完整结束，便于前端关闭 loading 状态。
        yield _sse_event("done", {"request_id": answer.request_id})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

