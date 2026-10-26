from __future__ import annotations


def test_agent_status_stream_has_structured_lifecycle(client, admin_headers):
    response = client.post(
        "/api/v1/chat/stream",
        headers=admin_headers,
        json={"message": "现在二泵站的压力是多少？"},
    )
    assert response.status_code == 200
    text = response.text
    assert "event: start" in text
    assert "event: result" in text
    assert "event: done" in text
    assert '"intent": "status"' in text
    assert '"read_only": true' in text
    assert '"limits"' in text
    assert '"workflow_branch"' in text


def test_agent_diagnosis_branches_are_distinguishable(client, admin_headers):
    """规程优先与运行诊断问题应返回不同的工作流分支标识。"""
    procedure = client.post("/api/v1/chat/stream", headers=admin_headers, json={"message": "二泵站通知规程怎么执行"})
    operational = client.post("/api/v1/chat/stream", headers=admin_headers, json={"message": "二泵站压力下降怎么排查"})
    assert procedure.status_code == 200 and operational.status_code == 200
    assert '"workflow_branch": "diagnosis-procedure"' in procedure.text
    assert '"workflow_branch": "diagnosis-operational"' in operational.text
    for response in (procedure, operational):
        text = response.text
        assert '"max_tool_calls"' in text
        assert '"run_id": "run-' in text
        assert '"workflow_status": "completed"' in text
        assert 'event: done' in text and '"workflow_status": "completed"' in text


def test_agent_control_request_stays_read_only(client, admin_headers):
    response = client.post("/api/v1/chat/stream", headers=admin_headers, json={"message": "启动二泵站"})
    assert response.status_code == 200
    assert "mock-readonly-policy" in response.text
    assert "未生成泵组/阀门/PLC 写指令" in response.text
    assert "start_pump" not in response.text


def test_agent_run_cancel_endpoint(client, admin_headers):
    """取消接口应返回统一的运行编号和 cancelled 状态。"""
    response = client.post("/api/v1/agent/runs/run-test-cancel/cancel", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == {"run_id": "run-test-cancel", "status": "cancelled"}


def test_agent_run_status_endpoint(client, admin_headers):
    """运行状态接口对未知运行返回统一 unknown 状态。"""
    response = client.get("/api/v1/agent/runs/run-not-found", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == {"run_id": "run-not-found", "status": "unknown"}


def test_agent_run_pause_and_resume_endpoints(client, admin_headers):
    """人工审批控制接口应能切换进程内运行状态。"""
    paused = client.post("/api/v1/agent/runs/run-approval-test/pause", headers=admin_headers)
    assert paused.status_code == 200
    assert paused.json() == {"run_id": "run-approval-test", "status": "paused"}
    resumed = client.post("/api/v1/agent/runs/run-approval-test/resume", headers=admin_headers)
    assert resumed.status_code == 200
    assert resumed.json() == {"run_id": "run-approval-test", "status": "running"}


def test_agent_approval_snapshot_can_resume_stream(client, admin_headers):
    paused = client.post(
        "/api/v1/chat/stream",
        headers=admin_headers,
        json={"message": "现在二泵站的压力是多少？", "require_approval": True},
    )
    assert paused.status_code == 200
    assert '"workflow_status": "paused"' in paused.text
    import json
    start_line = next(line for line in paused.text.splitlines() if line.startswith("data: "))
    run_id = json.loads(start_line[6:])["run_id"]
    resumed = client.post(f"/api/v1/agent/runs/{run_id}/resume-stream", headers=admin_headers)
    assert resumed.status_code == 200
    assert "event: result" in resumed.text
    assert '"workflow_status": "completed"' in resumed.text


def test_agent_run_history_endpoint(client, admin_headers):
    """运行历史接口应返回列表，即使当前进程还没有完成的运行。"""
    response = client.get("/api/v1/agent/runs?limit=10", headers=admin_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_agent_registry_endpoint(client, admin_headers):
    response = client.get("/api/v1/agent/registry", headers=admin_headers)
    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert "dispatch_coordinator" in names
    assert all(item["read_only"] is True for item in response.json())


def test_agent_custom_registry_requires_admin_and_known_tools(client, admin_headers, station_headers):
    payload = {"name": "custom_read_agent", "role": "自定义只读检查", "tool_names": ["read_telemetry"]}
    denied = client.post("/api/v1/agent/registry", headers=station_headers, json=payload)
    assert denied.status_code == 403
    created = client.post("/api/v1/agent/registry", headers=admin_headers, json=payload)
    assert created.status_code == 200
    assert created.json()["read_only"] is True
    invalid = client.post("/api/v1/agent/registry", headers=admin_headers, json={**payload, "name": "bad_agent", "tool_names": ["write_plc"]})
    assert invalid.status_code == 400


def test_agent_completed_stream_is_recorded_in_history(client, admin_headers):
    """完整 SSE 请求结束后，运行历史应能查到对应的 completed 状态。"""
    response = client.post(
        "/api/v1/chat/stream",
        headers=admin_headers,
        json={"message": "现在二泵站的压力是多少？"},
    )
    assert response.status_code == 200
    events = response.text.split('event: start\n', 1)
    assert len(events) == 2
    start_payload = events[1].split('data: ', 1)[1].split('\n', 1)[0]
    import json
    run_id = json.loads(start_payload)["run_id"]
    history = client.get("/api/v1/agent/runs", headers=admin_headers)
    assert history.status_code == 200
    matching = [item for item in history.json() if item.get("run_id") == run_id]
    assert matching and matching[0]["status"] == "completed"


def test_agent_session_summary_is_user_scoped(client, admin_headers, station_headers):
    """相同 session_id 在不同账号下不能互相读取问句摘要。"""
    response = client.post(
        "/api/v1/chat/stream",
        headers=admin_headers,
        json={"message": "现在二泵站的压力是多少？", "session_id": "scope-check"},
    )
    assert response.status_code == 200
    admin_summary = client.get("/api/v1/agent/sessions/scope-check/summary", headers=admin_headers)
    station_summary = client.get("/api/v1/agent/sessions/scope-check/summary", headers=station_headers)
    assert admin_summary.status_code == 200 and admin_summary.json()["question_count"] >= 1
    assert station_summary.status_code == 200 and station_summary.json()["question_count"] == 0


def test_agent_cancel_is_reflected_in_sse_lifecycle(client, admin_headers, monkeypatch):
    """节点边界取消后，SSE 必须以 cancelled 状态结束并保留 done 事件。"""
    from app.agent import workflow
    from app.services.agent_runs import cancel_run

    original_execute_tool = workflow.execute_tool

    def cancel_after_first_tool(tool, context):
        result = original_execute_tool(tool, context)
        cancel_run(context.run_id)
        return result

    monkeypatch.setattr(workflow, "execute_tool", cancel_after_first_tool)
    response = client.post(
        "/api/v1/chat/stream",
        headers=admin_headers,
        json={"message": "现在二泵站的压力是多少？"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"status": "cancelled"' in response.text
    assert '"workflow_status": "cancelled"' in response.text
    assert "event: done" in response.text


def test_agent_sse_error_and_fallback_events_remain_ordered(client, admin_headers, monkeypatch):
    """工具异常时，SSE 仍按 error、fallback、result、done 完整收尾。"""
    from app.agent import workflow
    from app.agent.executor import ToolExecution

    def failed_execute_tool(tool, context):
        return ToolExecution(
            tool=tool,
            status="failed",
            summary="测试注入的工具异常",
            error="test failure",
            error_code="TEST_TOOL_FAILURE",
            retryable=True,
            agent="test_agent",
        )

    monkeypatch.setattr(workflow, "execute_tool", failed_execute_tool)
    response = client.post(
        "/api/v1/chat/stream",
        headers=admin_headers,
        json={"message": "现在二泵站的压力是多少？"},
    )

    assert response.status_code == 200
    text = response.text
    assert text.index("event: error") < text.index("event: fallback") < text.index("event: result") < text.index("event: done")
    assert "TEST_TOOL_FAILURE" in text
