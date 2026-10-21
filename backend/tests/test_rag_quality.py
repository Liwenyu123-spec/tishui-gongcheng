"""知识库检索与引用可回溯的最小回归用例。

用例自己导入一条规程再检索，不依赖 ``backend/data/knowledge`` 里是否已有资料，
因此在空库、临时目录和离线环境下都能稳定跑通。
"""

from __future__ import annotations

# 检索问句刻意使用资料原文里的关键词，避免依赖语义模型才能命中。
_QUERY = "通知失败后怎么重试"
# 正文按规程条款组织，与现场资料的导入形态一致。
_CONTENT = (
    "第一条 站点事件通知发送失败时，先检查通知网关是否可用，并记录失败原因和重试次数。\n"
    "第二条 通知失败后在通知中心点击重试，重试成功后通知状态恢复为待确认。\n"
    "第三条 连续重试三次仍失败时，电话联系值班负责人，并保留人工兜底记录。"
)


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
    document_id = imported.json()["id"]
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
