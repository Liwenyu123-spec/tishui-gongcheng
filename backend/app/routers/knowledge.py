"""知识库文档列表和导入路由。"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..data.knowledge import _KNOWLEDGE, _KNOWLEDGE_CONTENT
from ..data.monitoring import _STATIONS
from ..dependencies import get_current_user, require_roles, user_has_station_access
from ..schemas.knowledge import KnowledgeDocument, KnowledgeImportRequest, KnowledgeRagAskRequest, KnowledgeSearchHit, KnowledgeSearchResponse, KnowledgeStatusUpdateRequest
from ..services.audit import record_audit
from ..services.knowledge_search import search_rules
from ..services.rag_chroma import get_rag_store, rag_store_status

# 知识库接口管理文档生命周期；检索只返回正文摘要，不提供全文读取。
router = APIRouter(prefix="/api/v1", tags=["知识库"])


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
    return KnowledgeSearchResponse(query=q, results=[KnowledgeSearchHit(**hit.__dict__) for hit in hits])


@router.get("/knowledge/rag/status")
def knowledge_rag_status(user: dict = Depends(get_current_user)) -> dict:
    """返回第一阶段 Chroma RAG 的本地状态，便于联调和排查。"""

    return rag_store_status()


@router.post("/knowledge/rag/ask")
def knowledge_rag_ask(
    payload: KnowledgeRagAskRequest,
    _: dict = Depends(require_roles("admin", "operator", "reviewer")),
) -> dict:
    """调用目标项目的完整 RAG 编排；缺少模型依赖时返回明确的 503。"""

    store = get_rag_store()
    if store is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=rag_store_status().get("error"))
    try:
        return store.ask(payload.question, k=payload.k, preset=payload.preset)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


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


@router.post("/knowledge/import", response_model=KnowledgeDocument)
def import_knowledge(
    payload: KnowledgeImportRequest,
    _: dict = Depends(require_roles("admin")),
) -> KnowledgeDocument:
    """保存知识文档元数据并记录正文长度。"""

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
    store = get_rag_store()
    if store is not None:
        store.upsert_document(
            document_id=document.id,
            filename=document.filename,
            title=document.title,
            version=document.version,
            content=payload.content,
            station_ids=document.station_ids,
            status=document.status,
            effective_from=document.effective_from,
            effective_to=document.effective_to,
        )
        document.source = "chroma"
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
    store = get_rag_store()
    if store is not None:
        store.update_status(document_id, payload.status)
    record_audit("status_update", "knowledge", document_id, f"知识文档 {document.title} 状态更新为 {payload.status}")
    return document
