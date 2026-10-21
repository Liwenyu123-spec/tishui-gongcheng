from __future__ import annotations


def test_knowledge_search_returns_citable_result(client, admin_headers):
    response = client.get(
        "/api/v1/knowledge/search",
        headers=admin_headers,
        params={"q": "通知失败后怎么重试", "station_id": "pump-02"},
    )
    assert response.status_code == 200
    results = response.json()
    assert isinstance(results, list)
    assert results
    first = results[0]
    assert first.get("source_id")
    assert first.get("title")
