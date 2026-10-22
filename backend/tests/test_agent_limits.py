from datetime import datetime, timezone

from app.agent.tools import AgentPlan, READ_ONLY_TOOLS, ReadOnlyTool
from app.agent.executor import execute_tool
from app.agent.workflow import DispatchWorkflow
from app.agent.executor import ToolContext
from app.schemas.agent import AgentAnswer, AgentChatRequest


def _context() -> ToolContext:
    """构造最小的只读 Agent 上下文，避免测试依赖 HTTP、登录和外部模型。"""
    answer = AgentAnswer(
        request_id="test-request",
        intent="status",
        answer="测试",
        generated_at=datetime.now(timezone.utc),
    )
    request = AgentChatRequest(message="二泵站压力")
    return ToolContext(user={"role": "admin"}, request=request, answer=answer)


def test_tool_budget_blocks_steps_after_limit(monkeypatch):
    """验证工作流跨专业节点累计工具数，超过预算后返回结构化错误码。"""
    monkeypatch.setattr("app.agent.workflow.max_tool_calls", lambda: 1)
    # 计划包含范围校验和遥测读取两个工具；预算为 1 时第二步必须被拦截。
    plan = AgentPlan(
        "station_monitor_agent",
        ("station_monitor_agent",),
        (READ_ONLY_TOOLS["check_scope"], READ_ONLY_TOOLS["read_telemetry"]),
    )
    executions, _ = DispatchWorkflow(plan).run(_context())
    assert len(executions) == 2
    assert executions[0].status == "completed"
    assert executions[1].error_code == "TOOL_BUDGET_EXCEEDED"


def test_unknown_tool_returns_structured_error():
    """未注册工具不能抛出异常，必须返回不可重试错误码。"""
    tool = ReadOnlyTool(name="not_registered", label="未知工具", description="测试")
    result = execute_tool(tool, _context())
    assert result.status == "failed"
    assert result.error_code == "TOOL_NOT_FOUND"
    assert result.retryable is False


def test_source_failure_is_retryable(monkeypatch):
    """数据源异常耗尽重试后应返回 SOURCE_UNAVAILABLE 且可重试。"""
    tool = READ_ONLY_TOOLS["read_telemetry"]
    monkeypatch.setattr("app.agent.executor._tool_retry_limit", lambda: 0)
    monkeypatch.setitem(__import__("app.agent.executor", fromlist=["_TOOL_HANDLERS"])._TOOL_HANDLERS, tool.name, lambda *_: (_ for _ in ()).throw(RuntimeError("mock source down")))
    result = execute_tool(tool, _context())
    assert result.error_code == "SOURCE_UNAVAILABLE"
    assert result.retryable is True

