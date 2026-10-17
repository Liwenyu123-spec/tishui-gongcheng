"""知识库文档列表和导入路由。"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from ..data.knowledge import _KNOWLEDGE
from ..dependencies import get_current_user, require_roles
from ..schemas.knowledge import KnowledgeDocument, KnowledgeImportRequest, KnowledgeStatusUpdateRequest
from ..services.audit import record_audit

# 知识库接口只管理文档元数据，当前不返回文档正文。
router = APIRouter(prefix="/api/v1", tags=["知识库"])


@router.get("/knowledge", response_model=list[KnowledgeDocument])
def knowledge(_: dict = Depends(get_current_user)) -> list[KnowledgeDocument]:
    """返回已导入知识文档的元数据。"""

    # 只返回当前进程内的元数据，正文不会从 Mock 存储中返回。
    return list(_KNOWLEDGE.values())


@router.get("/knowledge/{document_id}", response_model=KnowledgeDocument)
def knowledge_detail(document_id: str, _: dict = Depends(get_current_user)) -> KnowledgeDocument:
    """按文档编号查询知识文档元数据。"""

    # 详情接口仍只返回元数据，不把导入正文暴露给当前 Mock API。
    document = _KNOWLEDGE.get(document_id)
    if document is None:
        # 文档编号不存在时返回 404，避免返回一个虚构的空文档。
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识文档不存在")
    return document


@router.post("/knowledge/import", response_model=KnowledgeDocument)
def import_knowledge(
    payload: KnowledgeImportRequest,
    _: dict = Depends(require_roles("admin")),
) -> KnowledgeDocument:
    """保存知识文档元数据并记录正文长度。"""

    # 使用短 UUID 生成文档编号，避免依赖上传文件名的唯一性。
    # 记录文件名、版本和正文长度；正文只用于计算长度，不直接返回。
    document = KnowledgeDocument(
        id=f"knowledge-{uuid4().hex[:10]}",
        filename=payload.filename,
        title=payload.title,
        version=payload.version,
        content_length=len(payload.content),
        imported_at=datetime.now(timezone.utc),
    )
    # 保存导入结果，并通过审计日志记录可追踪的文档编号。
    _KNOWLEDGE[document.id] = document
    record_audit("import", "knowledge", document.id, f"导入文档 {document.filename}")
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
    # Literal 已限制状态取值，这里只更新状态并保留原有元数据。
    document.status = payload.status
    record_audit("status_update", "knowledge", document_id, f"知识文档 {document.title} 状态更新为 {payload.status}")
    return document
