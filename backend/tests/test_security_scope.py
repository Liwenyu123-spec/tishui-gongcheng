from __future__ import annotations


def test_station_operator_is_limited_to_assigned_station(client, station_headers):
    assert client.get("/api/v1/stations/pump-02", headers=station_headers).status_code == 200
    assert client.get("/api/v1/stations/pump-01", headers=station_headers).status_code == 403

    response = client.post(
        "/api/v1/chat/stream",
        headers=station_headers,
        json={"message": "现在四泵站的压力是多少？"},
    )
    assert response.status_code == 403


def test_audit_is_admin_only(client, admin_headers):
    assert client.get("/api/v1/audit-events", headers=admin_headers).status_code == 200


def test_station_operator_cannot_manage_knowledge_lifecycle(client, admin_headers, station_headers):
    """站点账号只能检索授权范围，不能读取审核历史或改变文档状态。"""
    imported = client.post("/api/v1/knowledge/import", headers=admin_headers, json={
        "filename": "permission-check.md", "title": "权限矩阵检查", "version": "1.0",
        "category": "规程", "content": "权限矩阵检查正文", "station_ids": ["pump-02"],
    })
    assert imported.status_code == 200
    document_id = imported.json()["id"]
    assert client.get(f"/api/v1/knowledge/{document_id}/history", headers=station_headers).status_code == 403
    assert client.patch(
        f"/api/v1/knowledge/{document_id}/status",
        headers=station_headers,
        json={"status": "archived"},
    ).status_code == 403
    assert client.post(
        "/api/v1/knowledge/status/batch",
        headers=station_headers,
        json={"document_ids": [document_id], "status": "archived"},
    ).status_code == 403
