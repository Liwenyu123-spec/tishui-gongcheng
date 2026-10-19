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

    # 知识文档生命周期：新导入文档先待审，设为现行后才允许检索。
    imported_knowledge = expect(
        "导入待审知识文档",
        client.post(
            "/api/v1/knowledge/import",
            headers=admin_headers,
            json={
                "filename": "smoke-retry-procedure.md",
                "title": "Smoke 通知重试规程",
                "version": "1.0",
                "content": "通知失败后核对失败原因并执行重试。",
                "station_ids": ["pump-02"],
            },
        ),
        200,
    )
    pending_search = expect(
        "待审知识不可检索",
        client.get("/api/v1/knowledge/search", headers=station_headers, params={"q": "通知重试规程", "station_id": "pump-02"}),
        200,
    )
    assert not any(hit["source_id"] == imported_knowledge["id"] for hit in pending_search["results"])
    valid_knowledge = expect(
        "批准知识文档",
        client.patch(
            f"/api/v1/knowledge/{imported_knowledge['id']}/status",
            headers=admin_headers,
            json={"status": "valid"},
        ),
        200,
    )
    assert valid_knowledge["status"] == "valid"
    approved_search = expect(
        "现行知识可检索",
        client.get("/api/v1/knowledge/search", headers=station_headers, params={"q": "通知重试规程", "station_id": "pump-02"}),
        200,
    )
    assert any(hit["source_id"] == imported_knowledge["id"] for hit in approved_search["results"])

    # 方案比较：检查目标需求、约束违反项和确定性推荐结果。
    comparison = expect(
        "方案比较约束分析",
        client.post(
            "/api/v1/schemes/compare",
            headers=operator_headers,
            json={
                "schemes": [
                    {"scheme_id": "scheme-a", "name": "方案 A", "supply": 12000, "delay_minutes": 45, "energy": 80, "load_percent": 70, "risk": "low"},
                    {"scheme_id": "scheme-b", "name": "方案 B", "supply": 14000, "delay_minutes": 55, "energy": 60, "load_percent": 75, "risk": "medium"},
                ]
            },
        ),
        200,
    )
    assert comparison["recommended_scheme_id"] == "scheme-b"
    assert comparison["target_demand"] == 13000.0
    assert all("score" in item and "constraint_violations" in item for item in comparison["results"])

    # 报告草稿：结构化指标和来源编号必须随生命周期保留。
    report = expect(
        "报告指标来源",
        client.post(
            "/api/v1/reports/generate",
            headers=operator_headers,
            json={"report_type": "daily", "report_date": "2026-10-19", "from_time": "2026-10-19T00:00:00Z", "to_time": "2026-10-19T23:59:59Z"},
        ),
        200,
    )
    assert report["status"] == "draft"
    assert len(report["metrics"]) == 5 and report["source_ids"]
    edited_report = expect(
        "报告草稿编辑",
        client.patch(f"/api/v1/reports/{report['id']}", headers=operator_headers, json={"summary": "Smoke 报告摘要"}),
        200,
    )
    assert edited_report["summary"] == "Smoke 报告摘要"
    expect("报告跳过复核被拒绝", client.patch(f"/api/v1/reports/{report['id']}/status", headers=admin_headers, json={"status": "archived"}), 409)
    reviewed_report = expect("报告标记复核", client.patch(f"/api/v1/reports/{report['id']}/status", headers=reviewer_headers, json={"status": "reviewed"}), 200)
    archived_report = expect("报告归档", client.patch(f"/api/v1/reports/{report['id']}/status", headers=reviewer_headers, json={"status": "archived"}), 200)
    assert reviewed_report["metrics"] == archived_report["metrics"] and archived_report["status"] == "archived"

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

    # 通知失败兜底：失败通知保存原因和重试次数，重试后恢复为待确认状态。
    failed_incident = expect(
        "模拟通知发送失败",
        client.post(
            "/api/v1/stations/pump-02/incidents",
            headers=operator_headers,
            json={
                "category": "smoke-test-delivery-failure",
                "level": "high",
                "description": "模拟通知网关失败",
                "deduplication_key": "smoke-test-delivery-failure-20261019",
                "simulate_delivery_failure": True,
            },
        ),
        200,
    )
    failed_notifications = expect("查询失败通知", client.get("/api/v1/notifications", headers=reviewer_headers), 200)
    failed_notification = next(item for item in failed_notifications if item["incident_id"] == failed_incident["id"])
    assert failed_notification["status"] == "failed" and failed_notification["failure_reason"] and failed_notification["retry_count"] == 1
    retried_notification = expect(
        "重试失败通知",
        client.post(f"/api/v1/notifications/{failed_notification['id']}/retry", headers=operator_headers),
        200,
    )
    assert retried_notification["status"] == "sent" and retried_notification["retry_count"] == 2 and retried_notification["failure_reason"] is None
    expect("重复重试已恢复通知被拒绝", client.post(f"/api/v1/notifications/{failed_notification['id']}/retry", headers=operator_headers), 409)

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

    # 诊断工具必须真正读到告警编号和本地规程引用，而不是空摘要。
    diagnosis_tools = client.post(
        "/api/v1/chat/stream",
        headers=admin_headers,
        json={"message": "二泵站流量下降后先检查什么？"},
    )
    assert diagnosis_tools.status_code == 200
    assert "alarm-20261015-001" in diagnosis_tools.text
    assert "mock-knowledge-flow-v1.2" in diagnosis_tools.text
    assert "已读取" in diagnosis_tools.text or "已检索" in diagnosis_tools.text
    # 明确提到二泵站时，工具层不得把三四泵站告警一并带出。
    assert "alarm-20261015-002" not in diagnosis_tools.text
    assert "alarm-20261015-003" not in diagnosis_tools.text

    # 控制边界工具只返回只读拒绝摘要，不出现写操作工具名。
    control_tools = client.post("/api/v1/chat/stream", headers=admin_headers, json={"message": "启动二泵站"})
    assert control_tools.status_code == 200
    assert "mock-readonly-policy" in control_tools.text
    assert "未生成泵组/阀门/PLC 写指令" in control_tools.text
    assert "start_pump" not in control_tools.text

    # 站点账号只能看到授权站点范围；诊断工具引用不得越权到其他站点告警。
    station_scope = client.post(
        "/api/v1/chat/stream",
        headers=station_headers,
        json={"message": "二泵站流量下降后先检查什么？"},
    )
    assert station_scope.status_code == 200
    assert '"source_ids": ["pump-02"]' in station_scope.text or "pump-02" in station_scope.text
    assert "alarm-20261015-001" in station_scope.text
    assert "alarm-20261015-002" not in station_scope.text
    assert "pump-04" not in station_scope.text
    assert "可见 1 个站点" in station_scope.text

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
