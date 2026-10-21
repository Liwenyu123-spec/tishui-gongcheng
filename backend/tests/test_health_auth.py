from __future__ import annotations


def test_health_reports_rag_lifecycle(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["rag"]["status"] in {"starting", "ready", "degraded", "failed"}
    assert "phase" in body["rag"]


def test_protected_routes_require_valid_token(client):
    assert client.get("/api/v1/stations").status_code == 401
    assert client.get("/api/v1/stations", headers={"Authorization": "Bearer invalid-token"}).status_code == 401
