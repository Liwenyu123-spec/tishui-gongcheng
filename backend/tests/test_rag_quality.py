"""知识库检索与引用可回溯的最小回归用例。

用例自己导入一条规程再检索，不依赖 ``backend/data/knowledge`` 里是否已有资料，
因此在空库、临时目录和离线环境下都能稳定跑通。
"""

from __future__ import annotations

import pytest

from app.services.knowledge_generate import clean_query
from rag_eval import ndcg_at_k, precision_at_k

# 检索问句刻意使用资料原文里的关键词，避免依赖语义模型才能命中。
_QUERY = "通知失败后怎么重试"
# 正文按规程条款组织，与现场资料的导入形态一致。
_CONTENT = (
    "第一条 站点事件通知发送失败时，先检查通知网关是否可用，并记录失败原因和重试次数。\n"
    "第二条 通知失败后在通知中心点击重试，重试成功后通知状态恢复为待确认。\n"
    "第三条 连续重试三次仍失败时，电话联系值班负责人，并保留人工兜底记录。"
)


def test_water_query_terms_are_normalized():
    """常见水务口语应归一化为规程术语，便于关键词和向量检索共同使用。"""

    normalized = clean_query("请问二泵压强和电流过高怎么查？")
    assert "二泵站" in normalized
    assert "压力" in normalized
    assert "运行电流超限" in normalized


def test_keyword_terms_are_used_with_retrieval_score():
    """检索词命中正文时应参与结果分数，保证专用术语不会只依赖向量相似度。"""

    normalized = clean_query("二泵压强")
    assert "二泵站" in normalized and "压力" in normalized


def test_offline_rag_ranking_metrics():
    """离线评测指标应反映命中数量和排序位置。"""

    result_ids = ["doc-b", "doc-a", "doc-c"]
    expected = {"doc-a"}
    assert precision_at_k(result_ids, expected, 1) == 0.0
    assert precision_at_k(result_ids, expected, 3) == pytest.approx(1 / 3)
    assert ndcg_at_k(["doc-a", "doc-b"], expected, 3) == 1.0
    assert 0.0 < ndcg_at_k(result_ids, expected, 3) < 1.0


def test_knowledge_search_returns_citable_result(client, admin_headers):
    """导入→批准→检索：命中结果必须带来源编号和标题，便于引用回溯。"""

    imported = client.post(
        "/api/v1/knowledge/import",
        headers=admin_headers,
        json={
            "filename": "pump-02-notification-retry.md",
            "title": "二泵站通知重试规程",
            "version": "1.0",
            "category": "规程",
            "content": _CONTENT,
            "station_ids": ["pump-02"],
        },
    )
    assert imported.status_code == 200, imported.text
    imported_body = imported.json()
    assert len(imported_body["content_hash"]) == 64
    assert len(imported_body["file_hash"]) == 64
    document_id = imported.json()["id"]
    duplicate = client.post(
        "/api/v1/knowledge/import",
        headers=admin_headers,
        json={
            "filename": "renamed-copy.md",
            "title": "同正文副本",
            "version": "1.0",
            "category": "规程",
            "content": _CONTENT,
            "station_ids": ["pump-02"],
        },
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == document_id
    # 新导入资料处于待审状态，只有批准为现行后才进入检索集合。
    approved = client.patch(
        f"/api/v1/knowledge/{document_id}/status",
        headers=admin_headers,
        json={"status": "valid"},
    )
    assert approved.status_code == 200, approved.text

    response = client.get(
        "/api/v1/knowledge/search",
        headers=admin_headers,
        params={"q": _QUERY, "station_id": "pump-02"},
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert isinstance(results, list) and results
    # 引用完整性：每条命中都要能回指到来源编号和标题。
    first = results[0]
    assert first.get("source_id")
    assert first.get("title")
    assert response.json()["source_ids"] == [first["source_id"]]
    assert response.json()["document_count"] == 1


def test_knowledge_search_reports_multiple_document_sources(client, admin_headers):
    """联合检索多个有效文档时，响应应汇总去重后的文档来源。"""
    for index, title in enumerate(("联合引用规程甲", "联合引用规程乙"), start=1):
        imported = client.post(
            "/api/v1/knowledge/import",
            headers=admin_headers,
            json={
                "filename": f"joint-{index}.md",
                "title": title,
                "version": "1.0",
                "category": "规程",
                "content": f"联合引用测试：压力异常时执行第{index}步检查，并记录压力异常处理。",
                "station_ids": ["pump-02"],
            },
        )
        assert imported.status_code == 200, imported.text
        document_id = imported.json()["id"]
        approved = client.patch(
            f"/api/v1/knowledge/{document_id}/status",
            headers=admin_headers,
            json={"status": "valid"},
        )
        assert approved.status_code == 200, approved.text

    response = client.get(
        "/api/v1/knowledge/search",
        headers=admin_headers,
        params={"q": "压力异常处理", "station_id": "pump-02", "limit": 10},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["document_count"] >= 2
    assert len(body["source_ids"]) == body["document_count"]
    assert body["conflicts"] == []


def test_knowledge_search_reports_conflicting_constraints(client, admin_headers):
    """同主题资料出现正反约束时，检索响应应提示人工核对来源。"""
    documents = (
        ("conflict-allow.md", "有限空间作业甲", "有限空间作业可以单人进入，进入前检查通风。"),
        ("conflict-deny.md", "有限空间作业乙", "有限空间作业必须两人以上，禁止单人进入。"),
    )
    for filename, title, content in documents:
        imported = client.post("/api/v1/knowledge/import", headers=admin_headers, json={
            "filename": filename, "title": title, "version": "1.0", "category": "规程",
            "content": content, "station_ids": ["pump-02"],
        })
        assert imported.status_code == 200, imported.text
        client.patch(f"/api/v1/knowledge/{imported.json()['id']}/status", headers=admin_headers, json={"status": "valid"})
    response = client.get("/api/v1/knowledge/search", headers=admin_headers, params={
        "q": "有限空间作业 单人进入", "station_id": "pump-02", "limit": 10,
    })
    assert response.status_code == 200
    conflicts = response.json()["conflicts"]
    assert conflicts and set(conflicts[0]["source_ids"]) <= set(response.json()["source_ids"])


def test_knowledge_version_compare_returns_diff(client, admin_headers):
    """同标题新版本应能返回正文差异摘要。"""
    first = client.post("/api/v1/knowledge/import", headers=admin_headers, json={
        "filename": "version-1.md", "title": "版本对比规程", "version": "1.0",
        "category": "规程", "content": "第一条：先检查压力。", "station_ids": [],
    }).json()
    client.patch(f"/api/v1/knowledge/{first['id']}/status", headers=admin_headers, json={"status": "valid"})
    second = client.post("/api/v1/knowledge/import", headers=admin_headers, json={
        "filename": "version-2.md", "title": "版本对比规程", "version": "2.0",
        "category": "规程", "content": "第一条：先检查压力，再检查电流。", "station_ids": [],
    }).json()
    result = client.get(f"/api/v1/knowledge/{second['id']}/compare", headers=admin_headers)
    assert result.status_code == 200
    assert result.json()["changed"] is True
    assert result.json()["compared_version"] == "1.0"


def test_knowledge_search_rejects_unavailable_station(client, station_headers):
    """站点账号请求无权站点时，检索接口必须直接拒绝。"""
    response = client.get(
        "/api/v1/knowledge/search",
        headers=station_headers,
        params={"q": "压力异常", "station_id": "pump-04"},
    )
    assert response.status_code == 403


def test_expired_knowledge_is_excluded_from_search(client, admin_headers):
    """超过 effective_to 的文档即使已批准，也不能被检索。"""
    imported = client.post("/api/v1/knowledge/import", headers=admin_headers, json={
        "filename": "expired.md", "title": "已过期规程", "version": "1.0",
        "category": "规程", "content": "压力异常过期处理办法", "station_ids": [],
        "effective_to": "2020-01-01T00:00:00Z",
    })
    assert imported.status_code == 200
    document_id = imported.json()["id"]
    assert client.patch(f"/api/v1/knowledge/{document_id}/status", headers=admin_headers, json={"status": "valid"}).status_code == 200
    results = client.get("/api/v1/knowledge/search", headers=admin_headers, params={"q": "压力异常过期处理办法"}).json()["results"]
    assert all(item["source_id"] != document_id for item in results)


def test_knowledge_archive_status_returns_document(client, admin_headers):
    """归档状态应能通过文档响应模型返回，且归档后不再进入检索。"""
    imported = client.post("/api/v1/knowledge/import", headers=admin_headers, json={
        "filename": "archive-check.md", "title": "归档状态检查", "version": "1.0",
        "category": "规程", "content": "归档状态检查压力异常处理办法", "station_ids": [],
    })
    assert imported.status_code == 200
    document_id = imported.json()["id"]
    archived = client.patch(
        f"/api/v1/knowledge/{document_id}/status",
        headers=admin_headers,
        json={"status": "archived"},
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"
    results = client.get(
        "/api/v1/knowledge/search",
        headers=admin_headers,
        params={"q": "归档状态检查压力异常处理办法"},
    ).json()["results"]
    assert all(item["source_id"] != document_id for item in results)
