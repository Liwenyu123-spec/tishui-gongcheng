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
