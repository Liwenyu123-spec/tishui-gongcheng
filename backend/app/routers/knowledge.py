"""知识库文档列表和导入路由。"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from ..data import knowledge_store
from ..data.knowledge import _KNOWLEDGE, _KNOWLEDGE_CONTENT, reload_from_store
from ..data.monitoring import _STATIONS
from ..dependencies import get_current_user, require_roles, user_has_station_access
from ..schemas.knowledge import KnowledgeDocument, KnowledgeImportRequest, KnowledgeRagAskRequest, KnowledgeRagDebugRequest, KnowledgeSearchHit, KnowledgeSearchResponse, KnowledgeStatusUpdateRequest
from ..services.audit import record_audit
from ..services.document_extract import extract_text, suggested_title
from ..services.knowledge_generate import ask_with_retrieval, generation_status
from ..services.knowledge_search import search_rules
from ..services.rag_chroma import ChromaRagStore, get_rag_store, rag_store_status
from ..services.rag_diagnose import diagnose
from ..services.runtime_env import env_summary

# 知识库接口管理文档生命周期；检索只返回正文摘要，不提供全文读取。
router = APIRouter(prefix="/api/v1", tags=["知识库"])

# 最近一次重建索引的时间；供状态接口展示，重启后从空开始。
_LAST_REINDEX_AT: datetime | None = None


def _is_eligible(document: KnowledgeDocument) -> bool:
    """判断文档是否应进入检索集合：现行且处于有效期窗口内。

    直接复用 Chroma 存储层的判定，避免列表接口和索引层各写一套有效期逻辑，
    否则两份规则一旦不一致就会出现「能搜到但列表查不到」的怪现象。
    """

    return ChromaRagStore._eligible(document.status, document.effective_from, document.effective_to)


def _eligible_ids() -> set[str]:
    """当前应当出现在索引里的文档编号集合。"""

    return {document.id for document in _KNOWLEDGE.values() if _is_eligible(document)}


def _indexed_ids(store) -> set[str]:
    """读取索引里实际存在的文档编号；同一文档的多个分片只算一次。"""

    metadatas = store.collection.get(include=["metadatas"]).get("metadatas") or []
    return {str(metadata.get("document_id")) for metadata in metadatas if metadata}


def _persisted_counts() -> dict:
    """统计落盘文档数量，用于和索引分片数对账。"""

    with_content = sum(1 for document in _KNOWLEDGE.values() if _KNOWLEDGE_CONTENT.get(document.id, "").strip())
    return {
        "persisted_documents": len(_KNOWLEDGE),
        "persisted_with_content": with_content,
        "eligible_documents": len(_eligible_ids()),
    }


def _index_snapshot(store, indexed: set[str] | None = None) -> dict:
    """对比「应进索引」和「实际进索引」，暴露缺失与孤儿文档。

    这是排查「重启后资料还在但搜不到」的关键指标：missing 非空说明索引没建全，
    orphan 非空说明磁盘上已经没有对应文档但分片没删干净。
    """

    if indexed is None:
        indexed = _indexed_ids(store)
    eligible = _eligible_ids()
    return {
        "indexed_documents": len(indexed),
        "consistent": eligible == indexed,
        "missing_documents": sorted(eligible - indexed),
        "orphan_documents": sorted(indexed - eligible),
        "last_reindex_at": _LAST_REINDEX_AT.isoformat() if _LAST_REINDEX_AT else None,
    }


def _prune_ineligible_documents(store) -> None:
    """把已失效或不再现行的文档移出索引，避免跨过有效期后仍被检索到。

    索引写入时做过有效期判断，但服务可能跨过失效时间持续运行，所以需要惰性清理。
    """

    for document in _KNOWLEDGE.values():
        if _is_eligible(document):
            continue
        try:
            # 不可检索时 sync_document 会删除该文档全部分片，这里直接复用同一入口。
            _sync_knowledge_index(document)
        except Exception:  # noqa: BLE001
            # 状态查询不应因为索引清理失败整体报错，索引问题通过 consistent 字段暴露。
            continue


def rebuild_knowledge_index() -> dict:
    """从落盘文件重建内存文档和 Chroma 索引。

    先 reload 再建索引：否则服务重启后内存为空，落盘资料会被全部误判成孤儿删掉，
    这正是之前「导入了规程但一重启就消失」的根因。
    """

    global _LAST_REINDEX_AT
    reload_from_store()
    store = get_rag_store()
    if store is None:
        return {**rag_store_status(), **_persisted_counts()}
    documents = [
        {
            "document_id": document.id,
            "filename": document.filename,
            "title": document.title,
            "version": document.version,
            "category": document.category,
            "content": _KNOWLEDGE_CONTENT.get(document.id, ""),
            "station_ids": document.station_ids,
            "status": document.status,
            "effective_from": document.effective_from,
            "effective_to": document.effective_to,
        }
        for document in _KNOWLEDGE.values()
    ]
    result = store.reindex_documents(documents)
    indexed_ids = _indexed_ids(store)
    for document in _KNOWLEDGE.values():
        # source 标记用于前端区分「已进向量库」和「仅内存回退」，与索引保持一致。
        document.source = "chroma" if document.id in indexed_ids else "mock"
    _LAST_REINDEX_AT = datetime.now(timezone.utc)
    return {
        **result,
        **store.stats(),
        **_persisted_counts(),
        **_index_snapshot(store, indexed_ids),
    }


def _sync_knowledge_index(document: KnowledgeDocument) -> None:
    """把内存中的文档生命周期同步到 Chroma；未安装向量库时保持内存检索。"""

    store = get_rag_store()
    if store is None:
        document.source = "mock"
        return
    chunks = store.sync_document(
        document_id=document.id,
        filename=document.filename,
        title=document.title,
        version=document.version,
        category=document.category,
        content=_KNOWLEDGE_CONTENT.get(document.id, ""),
        station_ids=document.station_ids,
        status=document.status,
        effective_from=document.effective_from,
        effective_to=document.effective_to,
    )
    document.source = "chroma" if chunks else "mock"


@router.get("/knowledge", response_model=list[KnowledgeDocument])
def knowledge(user: dict = Depends(get_current_user)) -> list[KnowledgeDocument]:
    """返回已导入知识文档的元数据。"""

    visible_station_ids = {
        station["id"] for station in _STATIONS if user_has_station_access(user, station["id"])
    }
    # 只返回当前账号可见范围内的元数据，正文不会从 Mock 存储中返回。
    return [
        document
        for document in _KNOWLEDGE.values()
        if not document.station_ids or set(document.station_ids).intersection(visible_station_ids)
    ]


@router.get("/knowledge/search", response_model=KnowledgeSearchResponse)
def search_knowledge(
    q: str = Query(min_length=1, max_length=200),
    metric: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=5, ge=1, le=10),
    station_id: str | None = Query(default=None, max_length=64),
    user: dict = Depends(get_current_user),
) -> KnowledgeSearchResponse:
    """检索内置规则和已批准、当前有效的导入文档。"""

    visible_station_ids = {
        station["id"] for station in _STATIONS if user_has_station_access(user, station["id"])
    }
    if station_id is not None and station_id not in visible_station_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权检索该站点资料")
    hits = search_rules(
        q,
        metric=metric,
        limit=limit,
        station_id=station_id,
        visible_station_ids=visible_station_ids,
    )
    # 服务层使用不可变数据类，路由边界显式转换为 API 响应模型，避免隐式序列化失败。
    results = []
    for hit in hits:
        payload = hit.__dict__.copy()
        payload["station_ids"] = list(hit.station_ids)
        results.append(KnowledgeSearchHit(**payload))
    return KnowledgeSearchResponse(query=q, results=results)


@router.get("/knowledge/rag/status")
def knowledge_rag_status(user: dict = Depends(get_current_user)) -> dict:
    """返回 Chroma 检索状态、文档落盘情况和索引对账结果。

    除原有引擎信息外，新增 `documents`（落盘层）、`index`（索引一致性）、
    `warmup`（模型预热结果）和 `config`（.env 生效情况）四块，
    用于快速判断「资料在不在磁盘」「索引对不对」「模型有没有真正加载」。
    """

    store = get_rag_store()
    config = env_summary()
    if store is None:
        return {
            **rag_store_status(),
            **generation_status(),
            "documents": knowledge_store.store_status(),
            "config": config,
            "index": {
                "indexed_documents": 0,
                "consistent": not _eligible_ids(),
                "missing_documents": [],
                "orphan_documents": [],
                "last_reindex_at": _LAST_REINDEX_AT.isoformat() if _LAST_REINDEX_AT else None,
            },
        }
    # 有效期可能在运行期间跨过，先清掉不该继续被检索的文档。
    _prune_ineligible_documents(store)
    return {
        **rag_store_status(),
        **generation_status(),
        "documents": knowledge_store.store_status(),
        "config": config,
        "index": _index_snapshot(store),
    }


@router.post("/knowledge/rag/reindex")
def knowledge_rag_reindex(_: dict = Depends(require_roles("admin"))) -> dict:
    """用当前内存中的知识文档重建 Chroma 索引。切换 Embedding 后需要调用一次。"""

    if get_rag_store() is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=rag_store_status().get("error"))
    return rebuild_knowledge_index()


@router.post("/knowledge/rag/ask")
def knowledge_rag_ask(
    payload: KnowledgeRagAskRequest,
    user: dict = Depends(require_roles("admin", "operator", "reviewer")),
) -> dict:
    """检索现行有效资料后，用 DeepSeek 生成带引用的规程说明。"""

    visible_station_ids = {
        station["id"] for station in _STATIONS if user_has_station_access(user, station["id"])
    }
    if payload.station_id is not None and payload.station_id not in visible_station_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权检索该站点资料")
    try:
        return ask_with_retrieval(
            payload.question,
            k=payload.k,
            station_id=payload.station_id,
            visible_station_ids=visible_station_ids,
            session_id=payload.session_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/knowledge/rag/debug")
def knowledge_rag_debug(
    payload: KnowledgeRagDebugRequest,
    user: dict = Depends(require_roles("admin")),
) -> dict:
    """检索诊断：返回分项得分、门控判定和可执行结论，不调用生成模型。

    只给管理员：响应里包含分片正文摘要和各路召回细节，属于内部排障信息。
    """

    visible_station_ids = {
        station["id"] for station in _STATIONS if user_has_station_access(user, station["id"])
    }
    if payload.station_id is not None and payload.station_id not in visible_station_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权检索该站点资料")
    return diagnose(
        payload.question,
        limit=payload.k,
        station_id=payload.station_id,
        visible_station_ids=visible_station_ids,
    )


@router.get("/knowledge/{document_id}", response_model=KnowledgeDocument)
def knowledge_detail(document_id: str, user: dict = Depends(get_current_user)) -> KnowledgeDocument:
    """按文档编号查询知识文档元数据。"""

    # 详情接口仍只返回元数据，不把导入正文暴露给当前 Mock API。
    document = _KNOWLEDGE.get(document_id)
    if document is None:
        # 文档编号不存在时返回 404，避免返回一个虚构的空文档。
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识文档不存在")
    visible_station_ids = {
        station["id"] for station in _STATIONS if user_has_station_access(user, station["id"])
    }
    if document.station_ids and not set(document.station_ids).intersection(visible_station_ids):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权查看该站点资料")
    return document


@router.post("/knowledge/extract")
def extract_knowledge_file(
    file: UploadFile = File(...),
    _: dict = Depends(require_roles("admin")),
) -> dict:
    """上传 PDF、Word 或文本，抽出正文供导入表单预览。"""

    payload = file.file.read()
    filename = file.filename or "upload.bin"
    try:
        content, parser = extract_text(filename, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return {
        "filename": filename,
        "title": suggested_title(filename),
        "parser": parser,
        "content": content,
        "content_length": len(content),
    }


@router.post("/knowledge/import", response_model=KnowledgeDocument)
def import_knowledge(
    payload: KnowledgeImportRequest,
    _: dict = Depends(require_roles("admin")),
) -> KnowledgeDocument:
    """保存知识文档元数据和正文。待审资料只留在内存，批准为现行后才写入 Chroma。"""

    # 使用短 UUID 生成文档编号，避免依赖上传文件名的唯一性。
    unknown_stations = sorted({station_id for station_id in payload.station_ids if station_id not in {item["id"] for item in _STATIONS}})
    if unknown_stations:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"未知适用站点：{', '.join(unknown_stations)}")
    if payload.effective_from and payload.effective_to and payload.effective_to <= payload.effective_from:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="失效时间必须晚于生效时间")
    now = datetime.now(timezone.utc)
    # 导入资料先进入待审状态，只有管理员将其设为现行后才会参与检索。
    document = KnowledgeDocument(
        id=f"knowledge-{uuid4().hex[:10]}",
        filename=payload.filename,
        title=payload.title,
        version=payload.version,
        category=payload.category,
        status="pending",
        content_length=len(payload.content),
        imported_at=now,
        station_ids=list(dict.fromkeys(payload.station_ids)),
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
    )
    # 保存元数据和正文；正文只通过检索命中摘要间接返回，不作为全文接口返回。
    _KNOWLEDGE[document.id] = document
    _KNOWLEDGE_CONTENT[document.id] = payload.content
    # 先落盘再同步索引：即使进程随后被 --reload 杀掉，重启后仍能重建索引。
    knowledge_store.save_document(document, payload.content)
    # 新文档默认待审，sync 会拒绝写入检索集合。
    _sync_knowledge_index(document)
    record_audit("import", "knowledge", document.id, f"导入文档 {document.filename}，状态为待审")
    return document


@router.patch("/knowledge/{document_id}/status", response_model=KnowledgeDocument)
def update_knowledge_status(
    document_id: str,
    payload: KnowledgeStatusUpdateRequest,
    _: dict = Depends(require_roles("admin")),
) -> KnowledgeDocument:
    """更新知识文档状态并记录审计事件。"""

    # 只有管理员可以改变文档状态，避免普通查询用户发布或废止资料。
    document = _KNOWLEDGE.get(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识文档不存在")
    # Literal 已限制状态取值；进入现行状态时记录批准时间。
    document.status = payload.status
    document.approved_at = datetime.now(timezone.utc) if payload.status == "valid" else None
    if payload.status == "valid":
        # 同一标题和类别只保留这份现行版本，旧现行版本退出检索。
        for previous in list(_KNOWLEDGE.values()):
            if previous.id == document.id or previous.status != "valid":
                continue
            if previous.title != document.title or previous.category != document.category:
                continue
            previous.status = "revoked"
            previous.approved_at = None
            _sync_knowledge_index(previous)
            # 旧版本被自动废止，状态也要落盘，否则重启后旧版本会重新变成现行。
            knowledge_store.update_document(previous)
            record_audit("status_update", "knowledge", previous.id, f"知识文档 {previous.title} {previous.version} 因新版本生效而废止")
    _sync_knowledge_index(document)
    knowledge_store.update_document(document)
    record_audit("status_update", "knowledge", document_id, f"知识文档 {document.title} 状态更新为 {payload.status}")
    return document


@router.delete("/knowledge/{document_id}")
def delete_knowledge(document_id: str, _: dict = Depends(require_roles("admin"))) -> dict:
    """删除一份知识文档及其索引分片。

    以前只能改状态，导错的文件会永久留在列表里；这里补一个硬删除入口，
    顺序是「删索引 → 删文件 → 清内存」，避免中途失败留下无主分片。
    """

    document = _KNOWLEDGE.get(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识文档不存在")
    store = get_rag_store()
    if store is not None:
        store.delete_document(document_id)
    knowledge_store.delete_document(document_id)
    _KNOWLEDGE.pop(document_id, None)
    _KNOWLEDGE_CONTENT.pop(document_id, None)
    record_audit("delete", "knowledge", document_id, f"删除知识文档 {document.title} {document.version}")
    return {"success": True, "document_id": document_id}
