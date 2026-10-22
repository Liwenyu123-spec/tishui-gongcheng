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
