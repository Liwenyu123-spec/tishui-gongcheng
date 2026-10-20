"""模拟阶段后端接口的最小回归检查脚本。

本脚本使用 FastAPI 的 TestClient 在进程内调用接口，不会启动端口，也不会连接数据库。
每次单独运行都会加载一份全新的内存 Mock 数据。
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import tempfile
from typing import Any

# 允许从项目根目录执行 `python backend/smoke_test.py` 时导入 app 包。
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# 冒烟固定哈希向量并关闭重排，避免首次运行加载语义模型和重排模型。
os.environ["RAG_EMBEDDING_PROVIDER"] = "hash"
os.environ["RAG_RERANK_ENABLED"] = "0"
os.environ["RAG_GENERATION_ENABLED"] = "0"


def smoke_temp_root() -> str:
    """返回可安全使用的绝对临时目录，避免临时文件落进仓库。

    TEMP / TMP 被设成相对路径（例如 `.smoke-temp`）时，`tempfile` 会按当前
    工作目录展开，冒烟产物就会写进 backend/ 并被 git 自动提交；chromadb 的
    sqlite 也会读这个变量，相对路径会直接导致「unable to open database file」。
    所以这里只接受绝对路径，仓库内目录一律不用，其余情况回退到系统临时目录。
    """

    repo_root = BACKEND_DIR.parent.resolve()
    for name in ("TEMP", "TMP", "TMPDIR"):
        candidate = (os.environ.get(name) or "").strip()
        if not candidate:
            continue
        path = Path(candidate)
        # 相对路径不信任，避免随当前工作目录漂移。
        if not path.is_absolute():
            continue
        resolved = path.resolve()
        # 仓库内的目录不用于临时文件，否则会被 git 提交。
        if resolved == repo_root or repo_root in resolved.parents:
            continue
        if resolved.is_dir():
            return str(resolved)
    fallback = Path.home() / "AppData" / "Local" / "Temp"
    fallback.mkdir(parents=True, exist_ok=True)
    return str(fallback)


# 统一进程内的临时目录设置：tempfile 缓存、sqlite 读取的 TEMP/TMP 都指向同一处。
_SMOKE_TMP_ROOT = smoke_temp_root()
for _name in ("TEMP", "TMP", "TMPDIR"):
    os.environ[_name] = _SMOKE_TMP_ROOT
tempfile.tempdir = _SMOKE_TMP_ROOT

# 向量库和知识文档落盘都指向临时目录，避免冒烟读写真实的 backend/data。
os.environ["RAG_CHROMA_DIR"] = tempfile.mkdtemp(prefix="smoke_rag_chroma_", dir=_SMOKE_TMP_ROOT)
os.environ["KNOWLEDGE_STORE_DIR"] = tempfile.mkdtemp(prefix="smoke_knowledge_store_", dir=_SMOKE_TMP_ROOT)

from fastapi.testclient import TestClient

from app.main import app


def expect(label: str, response: Any, status_code: int) -> Any:
    """校验 HTTP 状态码，并返回 JSON 响应。"""

    # 统一错误输出，失败时直接停止脚本，避免把后续结果误认为通过。
    if response.status_code != status_code:
        raise AssertionError(f"{label}: 期望 HTTP {status_code}，实际为 {response.status_code}: {response.text}")
    return response.json()


def check_chroma_index_policy() -> None:
    """用临时目录确认待审不入库、现行可检索、废止后删除。"""

    try:
        import chromadb  # noqa: F401
    except ImportError:
        return
    from app.services.rag_chroma import ChromaRagStore

    previous = {
        key: os.environ.get(key)
        for key in ("RAG_CHROMA_DIR", "RAG_CHROMA_COLLECTION", "RAG_EMBEDDING_PROVIDER")
    }
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        os.environ["RAG_CHROMA_DIR"] = directory
        os.environ["RAG_CHROMA_COLLECTION"] = "smoke_knowledge"
        os.environ["RAG_EMBEDDING_PROVIDER"] = "hash"
        store = ChromaRagStore()
        now = datetime.now(timezone.utc)
        pending = store.sync_document(
            document_id="doc-pending",
            filename="pending.md",
            title="待审规程",
            version="1.0",
            content="待审正文不应被检索。",
            station_ids=["pump-02"],
            status="pending",
        )
        assert pending == 0 and store.collection.count() == 0
        chunks = store.sync_document(
            document_id="doc-valid",
            filename="valid.md",
            title="通知重试规程",
            version="1.0",
            content="通知失败后核对失败原因并执行重试。",
            station_ids=["pump-02"],
            status="valid",
            effective_from=now - timedelta(days=1),
            effective_to=now + timedelta(days=1),
        )
        assert chunks >= 1
        hits = store.search("通知重试规程", station_id="pump-02")
        assert hits and hits[0]["document_id"] == "doc-valid"
        store.sync_document(
            document_id="doc-other",
            filename="other.md",
            title="无关流量记录",
            version="1.0",
            content="这里只记录泵站流量下降和入口压力，不涉及通知。",
            station_ids=["pump-02"],
            status="valid",
            effective_from=now - timedelta(days=1),
            effective_to=now + timedelta(days=1),
        )
        keyword_hits = store.search("通知重试规程", station_id="pump-02")
        assert keyword_hits and keyword_hits[0]["document_id"] == "doc-valid"
        store.sync_document(
            document_id="doc-other",
            filename="other.md",
            title="无关流量记录",
            version="1.0",
            content="这里只记录泵站流量下降和入口压力，不涉及通知。",
            station_ids=["pump-02"],
            status="revoked",
        )
        removed = store.sync_document(
            document_id="doc-valid",
            filename="valid.md",
            title="通知重试规程",
            version="1.0",
            content="通知失败后核对失败原因并执行重试。",
            station_ids=["pump-02"],
            status="revoked",
        )
        assert removed == 0 and store.collection.count() == 0
        store.client.clear_system_cache()
        del store
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def check_knowledge_store_persistence() -> None:
    """确认知识文档写入磁盘后能重新加载，且时间字段带回时区。"""

    from app.data import knowledge_store
    from app.data.knowledge import _KNOWLEDGE, reload_from_store
    from app.schemas.knowledge import KnowledgeDocument

    content = "冒烟持久化规程：通知失败后先核对原因，再执行重试。"
    now = datetime.now(timezone.utc)
    document = KnowledgeDocument(
        id="knowledge-smoke-persist",
        filename="persist.md",
        title="冒烟持久化规程",
        version="1.0",
        status="valid",
        content_length=len(content),
        imported_at=now,
        station_ids=["pump-02"],
        effective_from=now - timedelta(days=1),
        effective_to=now + timedelta(days=1),
    )
    knowledge_store.save_document(document, content)

    # 模拟服务重启：清空内存视图后只从磁盘恢复。
    _KNOWLEDGE.clear()
    reload_from_store()
    assert "knowledge-smoke-persist" in _KNOWLEDGE
    restored = _KNOWLEDGE["knowledge-smoke-persist"]
    assert restored.title == document.title
    # 读回的时间必须带 UTC 时区，否则有效期判断会和索引层不一致。
    assert restored.effective_from is not None and restored.effective_from.tzinfo is not None

    status = knowledge_store.store_status()
    assert status["persisted"] >= 1 and status["with_content"] >= 1
    assert not status["errors"]

    # 删除后也要从磁盘消失，避免重启又把删掉的资料捡回来。
    assert knowledge_store.delete_document("knowledge-smoke-persist") is True
    reload_from_store()
    assert "knowledge-smoke-persist" not in _KNOWLEDGE


def run_smoke_checks() -> None:
    check_chroma_index_policy()
    check_knowledge_store_persistence()
    # TestClient 不用 with 时不会触发 startup 事件，这里显式跑一次重建，
    # 既验证启动路径，也保证用例从与真实启动一致的索引状态开始。
    from app.routers.knowledge import rebuild_knowledge_index

    rebuild_knowledge_index()
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

    from app.services.knowledge_generate import (
        check_groundedness,
        clean_query,
        compress_detail,
        resolve_follow_up,
        select_strong_hits,
    )
    from app.services.knowledge_search import KnowledgeHit

    # 照片索引落盘在临时目录；模型加载耗时，冒烟只做注册/列表，不编码图片。
    with tempfile.TemporaryDirectory() as photo_dir:
        os.environ["PHOTO_STORE_DIR"] = photo_dir
        from app.services import photo_store
        from app.services.photo_store import PhotoIndex

        class _SkipEmbedIndex(PhotoIndex):
            def embed_photo(self, photo_id: str) -> bool:
                return False

        index = _SkipEmbedIndex()
        tiny_png = Path(r"C:\Users\lenovo\AppData\Local\Temp\smoke_photo.png").read_bytes()
        record = index.register(
            filename="smoke_test.png",
            payload=tiny_png,
            station_id="pump-02",
            station_name="二泵站",
            caption="冒烟测试占位图",
        )
        assert record.photo_id.startswith("photo-")
        assert index.status()["photos"] == 1
        listed = index.list_photos()
        assert listed and listed[0].photo_id == record.photo_id
        assert photo_store.get_photo_index is not None

    assert "泵站" in clean_query("帮我看看水泵流量掉下去先看啥")
    assert "下降" in clean_query("帮我看看水泵流量掉下去先看啥")
    compressed = compress_detail(
        "流量下降先核查什么",
        "先核对入口压力、泵组运行电流和下游压力。无关的设备台账编号是 ABC-001。再决定是否升级人工处置。",
    )
    assert "入口压力" in compressed
    assert "ABC-001" not in compressed
    clarify = resolve_follow_up("流量下降后先核查什么", session_id="smoke-ask-1")
    assert clarify["needs_clarification"] is True
    merged = resolve_follow_up("二泵站", session_id="smoke-ask-1")
    assert merged["needs_clarification"] is False
    assert "流量下降" in merged["effective_question"] and "二泵站" in merged["effective_question"]
    resolve_follow_up("二泵站流量下降后先核查什么", session_id="smoke-ask-ellip")
    follow = resolve_follow_up("那电流呢", session_id="smoke-ask-ellip")
    assert follow["merged"] is True
    assert "电流" in follow["effective_question"] and "二泵站" in follow["effective_question"]
    reuse = resolve_follow_up("压力异常怎么查", session_id="smoke-ask-ellip")
    assert "二泵站" in reuse["effective_question"] and "压力" in reuse["effective_question"]
    grounded_hit = KnowledgeHit(
        source_id="smoke-ground-1",
        title="泵站流量异常核查规程 1.2",
        version="1.2",
        detail="先核对入口压力、泵组运行电流和下游压力，再决定是否升级人工处置。",
        score=80,
    )
    grounded_ok = check_groundedness(
        "根据泵站流量异常核查规程，先核对入口压力和泵组运行电流。",
        [grounded_hit],
    )
    assert grounded_ok["grounded"] is True and grounded_ok["status"] == "grounded"
    grounded_bad = check_groundedness(
        "建议立即启动泵，把流量调到 9999。",
        [grounded_hit],
    )
    assert grounded_bad["grounded"] is False and grounded_bad["warnings"]
    weak_hit = KnowledgeHit(
        source_id="smoke-weak-1",
        title="弱相关样例",
        version="1.0",
        detail="台账编号备忘",
        score=3,
    )
    strong_only, weak_gate = select_strong_hits([weak_hit, grounded_hit], min_score=8)
    assert weak_gate["passed"] is True and len(strong_only) == 1 and strong_only[0].source_id == grounded_hit.source_id
    none_strong, none_gate = select_strong_hits([weak_hit], min_score=8)
    assert none_strong == [] and none_gate["passed"] is False and none_gate["top_score"] == 3

    markdown_extract = expect(
        "解析 Markdown 规程",
        client.post(
            "/api/v1/knowledge/extract",
            headers=admin_headers,
            files={"file": ("pump-02-flow.md", "二泵站流量下降时先核对入口压力。".encode("utf-8"), "text/markdown")},
        ),
        200,
    )
    assert markdown_extract["parser"] == "plain-text"
    assert "入口压力" in markdown_extract["content"]
    assert markdown_extract["title"] == "pump-02-flow"
    clarify_api = expect(
        "缺站点时先补问",
        client.post("/api/v1/knowledge/rag/ask", headers=admin_headers, json={"question": "流量下降后先核查什么", "session_id": "smoke-api-ask"}),
        200,
    )
    assert clarify_api["needs_clarification"] is True and clarify_api["generation"] == "clarify"
    expect(
        "生成问答在冒烟中关闭",
        client.post(
            "/api/v1/knowledge/rag/ask",
            headers=admin_headers,
            json={"question": "二泵站流量下降先核查什么", "session_id": "smoke-api-ask-ready"},
        ),
        503,
    )

    # 本地规程检索只返回版本化规则引用，不依赖数据库或向量库。
    knowledge_search = expect(
        "本地规程检索",
        client.get("/api/v1/knowledge/search", headers=admin_headers, params={"q": "流量异常核查", "metric": "flow"}),
        200,
    )
    assert knowledge_search["data_quality"] == "mock"
    assert knowledge_search["results"] and knowledge_search["results"][0]["source_id"] == "mock-knowledge-flow-v1.2"
    assert knowledge_search["results"][0]["location"] == "内置规程"
    long_query = expect(
        "连续中文问法命中流量规程",
        client.get(
            "/api/v1/knowledge/search",
            headers=admin_headers,
            params={"q": "二泵站流量下降后按规程先核查什么", "metric": "flow"},
        ),
        200,
    )
    assert long_query["results"] and long_query["results"][0]["source_id"] == "mock-knowledge-flow-v1.2"

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
    assert imported_knowledge["source"] == "mock"
    assert valid_knowledge["source"] in {"mock", "chroma"}
    approved_search = expect(
        "现行知识可检索",
        client.get("/api/v1/knowledge/search", headers=station_headers, params={"q": "通知重试规程", "station_id": "pump-02"}),
        200,
    )
    assert any(hit["source_id"] == imported_knowledge["id"] for hit in approved_search["results"])

    # 模拟重启：清空内存视图后只从磁盘恢复，已批准的文档应仍在且状态不变。
    from app.data.knowledge import _KNOWLEDGE as knowledge_docs, reload_from_store as reload_knowledge

    knowledge_docs.clear()
    reload_knowledge()
    listed = expect("重启后知识文档仍在", client.get("/api/v1/knowledge", headers=admin_headers), 200)
    assert any(item["id"] == imported_knowledge["id"] and item["status"] == "valid" for item in listed)
    rag_status = expect(
        "RAG 状态含落盘与索引对账",
        client.get("/api/v1/knowledge/rag/status", headers=admin_headers),
        200,
    )
    assert rag_status["documents"]["persisted"] >= 1
    assert rag_status["documents"]["with_content"] >= 1
    assert "consistent" in rag_status["index"] and "missing_documents" in rag_status["index"]

    newer_knowledge = expect(
        "导入同一规程新版本",
        client.post(
            "/api/v1/knowledge/import",
            headers=admin_headers,
            json={
                "filename": "smoke-retry-procedure-v2.md",
                "title": "Smoke 通知重试规程",
                "version": "2.0",
                "category": "规程",
                "content": "通知失败后先核对失败原因，再由管理员执行重试。",
                "station_ids": ["pump-02"],
            },
        ),
        200,
    )
    expect(
        "批准新版本并废止旧版",
        client.patch(
            f"/api/v1/knowledge/{newer_knowledge['id']}/status",
            headers=admin_headers,
            json={"status": "valid"},
        ),
        200,
    )
    version_search = expect(
        "旧版本不再检索",
        client.get("/api/v1/knowledge/search", headers=station_headers, params={"q": "通知重试规程", "station_id": "pump-02"}),
        200,
    )
    assert any(hit["source_id"] == newer_knowledge["id"] for hit in version_search["results"])
    assert not any(hit["source_id"] == imported_knowledge["id"] for hit in version_search["results"])

    # 硬删除：删掉的文档不应再出现在列表，磁盘记录也要同步清理。
    delete_result = expect(
        "删除知识文档",
        client.delete(f"/api/v1/knowledge/{imported_knowledge['id']}", headers=admin_headers),
        200,
    )
    assert delete_result["success"] is True
    after_delete = expect("删除后知识列表", client.get("/api/v1/knowledge", headers=admin_headers), 200)
    assert not any(item["id"] == imported_knowledge["id"] for item in after_delete)
    reload_knowledge()
    assert imported_knowledge["id"] not in knowledge_docs

    # 固定问法：流量下降必须命中流量规程；过期资料和其他站点资料不得出现。
    flow_question = expect(
        "固定问法命中流量规程",
        client.get(
            "/api/v1/knowledge/search",
            headers=admin_headers,
            params={"q": "二泵站流量下降先核查什么", "metric": "flow", "station_id": "pump-02"},
        ),
        200,
    )
    assert flow_question["results"][0]["source_id"] == "mock-knowledge-flow-v1.2"
    expired_knowledge = expect(
        "导入已过期规程",
        client.post(
            "/api/v1/knowledge/import",
            headers=admin_headers,
            json={
                "filename": "expired-flow.md",
                "title": "过期流量核查规程",
                "version": "0.1",
                "content": "过期流量核查规程不应再被引用。",
                "station_ids": ["pump-02"],
                "effective_from": "2020-01-01T00:00:00Z",
                "effective_to": "2020-02-01T00:00:00Z",
            },
        ),
        200,
    )
    expect(
        "批准过期规程",
        client.patch(f"/api/v1/knowledge/{expired_knowledge['id']}/status", headers=admin_headers, json={"status": "valid"}),
        200,
    )
    expired_search = expect(
        "过期规程不可检索",
        client.get("/api/v1/knowledge/search", headers=admin_headers, params={"q": "过期流量核查规程", "station_id": "pump-02"}),
        200,
    )
    assert not any(hit["source_id"] == expired_knowledge["id"] for hit in expired_search["results"])
    other_station_knowledge = expect(
        "导入四泵站资料",
        client.post(
            "/api/v1/knowledge/import",
            headers=admin_headers,
            json={
                "filename": "pump-04-seal.md",
                "title": "四泵站专用密封规程",
                "version": "1.0",
                "content": "四泵站专用密封规程只允许四泵站账号检索。",
                "station_ids": ["pump-04"],
            },
        ),
        200,
    )
    expect(
        "批准四泵站资料",
        client.patch(f"/api/v1/knowledge/{other_station_knowledge['id']}/status", headers=admin_headers, json={"status": "valid"}),
        200,
    )
    station_hidden = expect(
        "站点账号看不到其他站资料",
        client.get("/api/v1/knowledge/search", headers=station_headers, params={"q": "四泵站专用密封规程"}),
        200,
    )
    assert not any(hit["source_id"] == other_station_knowledge["id"] for hit in station_hidden["results"])
    expect(
        "站点账号不能指定其他站点",
        client.get("/api/v1/knowledge/search", headers=station_headers, params={"q": "四泵站专用密封规程", "station_id": "pump-04"}),
        403,
    )

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
        if expected_intent == '"intent": "diagnosis"':
            assert "规程说明" in agent_response.text or '"protocol_explanation"' in agent_response.text
            assert "mock-knowledge-flow-v1.2" in agent_response.text
        assert '"coordinator": "dispatch_coordinator"' in agent_response.text
        assert '"allowed_tools":' in agent_response.text
        assert '"read_only": true' in agent_response.text
        assert "工具证据" in agent_response.text
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
    assert diagnosis_tools.text.find('"name": "read_alarms"') < diagnosis_tools.text.find('"name": "search_knowledge"')
    assert diagnosis_tools.text.find('"name": "search_knowledge"') < diagnosis_tools.text.find('"name": "explain_protocol"')
    assert "已整理规程说明" in diagnosis_tools.text
    procedure_question = client.post("/api/v1/chat/stream", headers=admin_headers, json={"message": "二泵站按规程应该怎么核查？"})
    assert procedure_question.status_code == 200
    assert procedure_question.text.find('"name": "search_knowledge"') < procedure_question.text.find('"name": "explain_protocol"')
    assert procedure_question.text.find('"name": "explain_protocol"') < procedure_question.text.find('"name": "read_alarms"')
    missing_station = client.post("/api/v1/chat/stream", headers=admin_headers, json={"message": "流量下降后先检查什么？"})
    assert missing_station.status_code == 200
    assert "补充要核查的泵站" in missing_station.text

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
