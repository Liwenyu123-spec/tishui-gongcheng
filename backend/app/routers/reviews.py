"""审核记录的创建、查询和状态处理路由。"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from ..data.repositories import get_data_source
from ..dependencies import require_roles
from ..schemas.reviews import Review, ReviewCreateRequest, ReviewUpdateRequest
from ..services.audit import record_audit

# 审核路由负责记录人工复核结果，不执行现场控制。
router = APIRouter(prefix="/api/v1", tags=["审核"])
data_source = get_data_source()

# 待补充材料返回后可以再次进入审核；已通过或已驳回记录保持终态。
_REVIEW_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"approved", "rejected", "supplement"},
    "supplement": {"approved", "rejected", "supplement"},
    "approved": {"approved"},
    "rejected": {"rejected"},
}


@router.post("/reviews", response_model=Review)
def create_review(
    payload: ReviewCreateRequest,
    user: dict = Depends(require_roles("admin", "operator", required_permissions=("submit_scheme",))),
) -> Review:
    """创建一条待人工处理的审核记录。"""

    # Agent 转办主题带有唯一请求编号；重复点击时直接返回原待办，避免生成重复审核记录。
    if payload.subject.startswith("Agent "):
        existing = next(
            (item for item in data_source.reviews.all().values() if item.subject == payload.subject and item.status == "pending"),
            None,
        )
        if existing is not None:
            return existing
    # 使用统一 UTC 时间记录创建和更新时间，避免跨时区比较产生歧义。
    now = datetime.now(timezone.utc)
    # 新建记录固定为 pending，审核人后续通过 PATCH 接口提交结论。
    review = Review(
        id=f"review-{uuid4().hex[:10]}",
        **payload.model_dump(),
        status="pending",
        created_at=now,
        updated_at=now,
    )
    # Mock 阶段将审核记录放入进程内字典，重启服务后会清空。
    data_source.reviews.all()[review.id] = review
    commit = getattr(data_source, "commit_review", None)
    if commit is not None and not commit(review, creating=True):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="审核记录未能写入数据库")
    # 记录转人工复核的操作人，便于管理员在审计页面追踪 Agent 转办来源。
    record_audit(
        "create",
        "review",
        review.id,
        f"创建人工复核记录：{review.subject}",
        operator=user.get("username", "mock-admin"),
    )
    return review


@router.get("/reviews", response_model=list[Review])
def list_reviews(_: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> list[Review]:
    """查询当前进程内的审核记录。"""

    # 列表接口只返回当前进程内已经创建的审核记录。
    return list(data_source.reviews.all().values())


@router.get("/reviews/{review_id}", response_model=Review)
def get_review(review_id: str, _: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> Review:
    """按 ID 查询审核详情。"""

    # 使用路径中的审核编号查找详情，不存在时返回 404。
    review = data_source.reviews.get(review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审核记录不存在")
    return review


@router.patch("/reviews/{review_id}", response_model=Review)
def update_review(
    review_id: str,
    payload: ReviewUpdateRequest,
    _: dict = Depends(require_roles("admin", "reviewer", required_permissions=("review",))),
) -> Review:
    """更新审核结论并写入审计事件。"""

    # 先按路径编号查找记录，再判断当前记录是否仍处于待审核状态。
    review = data_source.reviews.get(review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审核记录不存在")
    # 按状态流转表校验当前记录，允许补充材料后再次审核，已通过或已驳回记录保持终态。
    allowed_statuses = _REVIEW_STATUS_TRANSITIONS.get(review.status, {review.status})
    if payload.status not in allowed_statuses:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该审核记录已结束，不能再次修改")
    # 相同状态的重复请求保持幂等，但仍可更新补充意见。
    review.status = payload.status
    if payload.comment is not None:
        # 未提交 comment 时保留原有意见，避免 PATCH 清空已有内容。
        review.comment = payload.comment
    # 每次状态变更都刷新更新时间，并记录一条审计事件。
    review.updated_at = datetime.now(timezone.utc)
    commit = getattr(data_source, "commit_review", None)
    if commit is not None and not commit(review, creating=False):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="审核记录已被其他人更新，请刷新后再提交")
    record_audit(payload.status, "review", review_id, f"审核记录 {review.subject} 状态更新为 {payload.status}")
    return review
