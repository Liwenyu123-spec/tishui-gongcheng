from datetime import datetime, timezone

from app.agent.tools import AgentPlan, READ_ONLY_TOOLS
from app.agent.workflow import DispatchWorkflow
from app.agent.executor import ToolContext
from app.schemas.agent import AgentAnswer, AgentChatRequest


def _context() -> ToolContext:
    answer = AgentAnswer(
        request_id="test-request",
        intent="status",
        answer="测试",
        generated_at=datetime.now(timezone.utc),
    )
    request = AgentChatRequest(message="二泵站压力")
    return ToolContext(user={"role": "admin"}, request=request, answer=answer)


def test_tool_budget_blocks_steps_after_limit(monkeypatch):
    monkeypatch.setattr("app.agent.workflow.max_tool_calls", lambda: 1)
    plan = AgentPlan(
        "station_monitor_agent",
        ("station_monitor_agent",),
        (READ_ONLY_TOOLS["check_scope"], READ_ONLY_TOOLS["read_telemetry"]),
    )
    executions, _ = DispatchWorkflow(plan).run(_context())
    assert len(executions) == 2
    assert executions[0].status == "completed"
    assert executions[1].error_code == "TOOL_BUDGET_EXCEEDED"

