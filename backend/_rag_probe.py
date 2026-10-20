"""一次性检查语义向量、重建索引和废止过滤。"""

import os
import sys

os.environ["RAG_EMBEDDING_PROVIDER"] = "sentence-transformers"
sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
headers = {"Authorization": "Bearer " + login.json()["access_token"]}
imported = client.post(
    "/api/v1/knowledge/import",
    headers=headers,
    json={
        "filename": "flow.md",
        "title": "泵站流量异常核查补充",
        "version": "9.9",
        "content": "二泵站流量下降时，先核对入口压力、泵组运行电流和下游压力，再决定是否升级人工处置。",
        "station_ids": ["pump-02"],
    },
)
document = imported.json()
print("import", imported.status_code, document.get("status"), document.get("source"))
pending = client.get(
    "/api/v1/knowledge/search",
    headers=headers,
    params={"q": "二泵站流量下降先核查什么", "station_id": "pump-02"},
)
assert document["id"] not in [item["source_id"] for item in pending.json()["results"]]
reindex = client.post("/api/v1/knowledge/rag/reindex", headers=headers)
print("reindex", {key: reindex.json()[key] for key in ("indexed_documents", "skipped_documents", "chunks", "embedding")})
still_pending = client.get(
    "/api/v1/knowledge/search",
    headers=headers,
    params={"q": "入口压力 下游压力", "station_id": "pump-02"},
)
assert document["id"] not in [item["source_id"] for item in still_pending.json()["results"]]
approved = client.patch(f"/api/v1/knowledge/{document['id']}/status", headers=headers, json={"status": "valid"})
print("approve", approved.status_code, approved.json().get("source"))
found = client.get(
    "/api/v1/knowledge/search",
    headers=headers,
    params={"q": "流量下降后先核对入口压力还是先停泵", "station_id": "pump-02"},
)
rows = found.json()["results"]
print("search", [(item["source_id"], item["source"], item["score"], item["title"]) for item in rows])
assert any(item["source_id"] == document["id"] and item["source"] == "chroma-document" for item in rows)
revoked = client.patch(f"/api/v1/knowledge/{document['id']}/status", headers=headers, json={"status": "revoked"})
print("revoke", revoked.status_code, revoked.json().get("source"))
after = client.get(
    "/api/v1/knowledge/search",
    headers=headers,
    params={"q": "流量下降后先核对入口压力", "station_id": "pump-02"},
)
assert document["id"] not in [item["source_id"] for item in after.json()["results"]]
print("PASS")
