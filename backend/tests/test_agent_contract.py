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


def test_agent_control_request_stays_read_only(client, admin_headers):
    response = client.post("/api/v1/chat/stream", headers=admin_headers, json={"message": "启动二泵站"})
    assert response.status_code == 200
    assert "mock-readonly-policy" in response.text
    assert "未生成泵组/阀门/PLC 写指令" in response.text
    assert "start_pump" not in response.text
