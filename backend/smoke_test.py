"""模拟阶段后端接口的最小回归检查脚本。

本脚本使用 FastAPI 的 TestClient 在进程内调用接口，不会启动端口，也不会连接数据库。
每次单独运行都会加载一份全新的内存 Mock 数据。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# 允许从项目根目录执行 `python backend/smoke_test.py` 时导入 app 包。
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient

from app.main import app


def expect(label: str, response: Any, status_code: int) -> Any:
    """校验 HTTP 状态码，并返回 JSON 响应。"""

    # 统一错误输出，失败时直接停止脚本，避免把后续结果误认为通过。
    if response.status_code != status_code:
        raise AssertionError(f"{label}: 期望 HTTP {status_code}，实际为 {response.status_code}: {response.text}")
    return response.json()


def run_smoke_checks() -> None:
    """按业务链路执行认证、权限、监控、事件和审计检查。"""

    client = TestClient(app)
    admin_headers = {"Authorization": "Bearer mock-token-admin"}
    operator_headers = {"Authorization": "Bearer mock-token-operator"}
    station_headers = {"Authorization": "Bearer mock-token-station-operator"}
    reviewer_headers = {"Authorization": "Bearer mock-token-reviewer"}

    # 健康检查不要求认证；登录接口仍应返回当前账号角色和固定 Mock Token。
    health = expect("健康检查", client.get("/api/v1/health"), 200)
    assert health["status"] == "ok"
    login = expect("管理员登录", client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"}), 200)
    assert login["user"]["role"] == "admin"

    # Agent 待确认项可转为人工审核待办；创建记录应保留操作人并可被审核员查询。
    review = expect(
        "人工复核创建",
        client.post(
            "/api/v1/reviews",
            headers=operator_headers,
            json={"subject": "Agent 诊断复核", "recommendation": "现场确认泵组状态", "comment": "Mock 转人工"},
        ),
        200,
    )
    assert review["status"] == "pending"
    duplicate_review = expect(
        "重复人工复核幂等",
        client.post(
            "/api/v1/reviews",
            headers=operator_headers,
            json={"subject": "Agent 诊断复核", "recommendation": "现场确认泵组状态", "comment": "Mock 转人工"},
        ),
        200,
    )
    assert duplicate_review["id"] == review["id"]
    expect("审核员查询人工复核", client.get("/api/v1/reviews", headers=reviewer_headers), 200)

    # 本地规程检索只返回版本化规则引用，不依赖数据库或向量库。
    knowledge_search = expect(
        "本地规程检索",
        client.get("/api/v1/knowledge/search", headers=admin_headers, params={"q": "流量异常核查", "metric": "flow"}),
        200,
    )
    assert knowledge_search["data_quality"] == "mock"
    assert knowledge_search["results"] and knowledge_search["results"][0]["source_id"] == "mock-knowledge-flow-v1.2"

    # 管理员可以查看全部站点；站点账号只能访问授权的二泵站。
    stations = expect("管理员站点列表", client.get("/api/v1/stations", headers=admin_headers), 200)
    assert len(stations) >= 1
    expect("站点账号访问授权站点", client.get("/api/v1/stations/pump-02", headers=station_headers), 200)
    expect("站点账号访问未授权站点", client.get("/api/v1/stations/pump-01", headers=station_headers), 403)
    expect("审核员访问告警接口", client.get("/api/v1/alarms", headers=reviewer_headers), 403)

    # CSV 接口分别检查完整有效行和缺字段场景，确认只校验、不落库。
    valid_csv = "station_id,observed_at,metric,value,unit\npump-02,2026-10-18T10:00:00Z,pressure,0.7,MPa\n"
    csv_result = expect(
        "有效 CSV 校验",
        client.post(
            "/api/v1/imports/telemetry-csv",
            headers={**admin_headers, "X-Filename": "smoke.csv"},
            content=valid_csv.encode("utf-8"),
        ),
        200,
    )
    assert csv_result["success"] is True and csv_result["accepted_rows"] == 1
    invalid_csv = "station_id,observed_at,metric\npump-02,2026-10-18T10:00:00Z,pressure\n"
    invalid_result = expect(
        "缺字段 CSV 校验",
        client.post("/api/v1/imports/telemetry-csv", headers=admin_headers, content=invalid_csv.encode("utf-8")),
        200,
    )
    assert invalid_result["success"] is False and invalid_result["errors"]

    # 告警确认应更新内存状态，并在审计接口中留下记录。
    alarms = expect("告警列表", client.get("/api/v1/alarms?status=unconfirmed", headers=operator_headers), 200)
    alarm_id = alarms[0]["id"]
    acknowledged_alarm = expect("告警确认", client.post(f"/api/v1/alarms/{alarm_id}/ack", headers=operator_headers), 200)
    assert acknowledged_alarm["status"] == "confirmed"

    # 站点事件首次上报生成通知；相同指纹再次上报应合并而不是生成新事件。
    incident_payload = {
        "category": "smoke-test-pressure",
        "level": "high",
        "description": "冒烟检查事件",
        "deduplication_key": "smoke-test-20261018",
    }
    incident = expect("站点事件上报", client.post("/api/v1/stations/pump-02/incidents", headers=operator_headers, json=incident_payload), 200)
    duplicate = expect("重复事件合并", client.post("/api/v1/stations/pump-02/incidents", headers=operator_headers, json=incident_payload), 200)
    assert duplicate["id"] == incident["id"] and duplicate["report_count"] == 2
    notifications = expect("通知查询", client.get("/api/v1/notifications", headers=reviewer_headers), 200)
    notification = next(item for item in notifications if item["incident_id"] == incident["id"])
    escalated = expect("通知升级", client.post(f"/api/v1/notifications/{notification['id']}/escalate", headers=operator_headers), 200)
    acknowledged = expect("升级通知确认", client.post(f"/api/v1/notifications/{escalated['id']}/ack", headers=operator_headers), 200)
    assert acknowledged["status"] == "acknowledged"

    # Agent 诊断应读取同一站点的未关闭事件和平台通知，并把它们作为引用返回。
    agent_with_event = client.post(
        "/api/v1/chat/stream",
        headers=operator_headers,
        json={"message": "二泵站流量下降后先检查什么？"},
    )
    assert agent_with_event.status_code == 200
    assert incident["id"] in agent_with_event.text
    assert escalated["id"] in agent_with_event.text

    resolved = expect("事件关闭", client.post(f"/api/v1/incidents/{incident['id']}/resolve", headers=operator_headers), 200)
    assert resolved["status"] == "resolved"

    # 规则驱动 Agent 只读取 Mock 数据；SSE 必须按 start、result、done 顺序结束。
    agent_questions = [
        ("现在二泵站的压力是多少？", '"intent": "status"'),
        ("过去两小时哪个泵站波动最大？", '"intent": "trend"'),
        ("二泵站流量下降后先检查什么？", '"intent": "diagnosis"'),
        ("当前哪个片区供需缺口最大？", '"intent": "supply"'),
        ("启动二泵站", '"intent": "control_rejected"'),
    ]
    for question, expected_intent in agent_questions:
        agent_response = client.post("/api/v1/chat/stream", headers=admin_headers, json={"message": question})
        assert agent_response.status_code == 200
        assert expected_intent in agent_response.text
        assert '"confidence":' in agent_response.text
        assert '"pending_items":' in agent_response.text
        assert '"time_range":' in agent_response.text
        assert '"observed_at":' in agent_response.text
        assert '"freshness":' in agent_response.text
        assert '"coordinator": "dispatch_coordinator"' in agent_response.text
        assert '"allowed_tools":' in agent_response.text
        assert '"read_only": true' in agent_response.text
        assert '"summary":' in agent_response.text
        assert '"source_ids":' in agent_response.text
        assert "start_pump" not in agent_response.text
        assert "event: start" in agent_response.text
        assert "event: result" in agent_response.text
        assert "event: done" in agent_response.text
    unauthorized_agent = client.post(
        "/api/v1/chat/stream",
        headers=station_headers,
        json={"message": "现在四泵站的压力是多少？"},
    )
    assert unauthorized_agent.status_code == 403

    # 管理员可以查询前面操作产生的审计记录，普通调度员不能查询审计接口。
    audit_events = expect("审计查询", client.get("/api/v1/audit-events", headers=admin_headers), 200)
    assert any(event["action"] == "acknowledge" for event in audit_events)
    expect("调度员审计权限", client.get("/api/v1/audit-events", headers=operator_headers), 403)


if __name__ == "__main__":
    run_smoke_checks()
    print("后端 Mock API 冒烟检查通过")
