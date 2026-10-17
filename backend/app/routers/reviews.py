"""审核记录的创建、查询和状态处理路由。"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from ..data.reviews import _REVIEWS
from ..dependencies import require_roles
from ..schemas.reviews import Review, ReviewCreateRequest, ReviewUpdateRequest
from ..services.audit import record_audit

# 审核路由负责记录人工复核结果，不执行现场控制。
router = APIRouter(prefix="/api/v1", tags=["审核"])


@router.post("/reviews", response_model=Review)
def create_review(
    payload: ReviewCreateRequest,
    _: dict = Depends(require_roles("admin", "operator")),
) -> Review:
    """创建一条待人工处理的审核记录。"""

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
    _REVIEWS[review.id] = review
    return review


@router.get("/reviews", response_model=list[Review])
def list_reviews(_: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> list[Review]:
    """查询当前进程内的审核记录。"""

    # 列表接口只返回当前进程内已经创建的审核记录。
    return list(_REVIEWS.values())


@router.get("/reviews/{review_id}", response_model=Review)
def get_review(review_id: str, _: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> Review:
    """按 ID 查询审核详情。"""

    # 使用路径中的审核编号查找详情，不存在时返回 404。
    review = _REVIEWS.get(review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审核记录不存在")
    return review


@router.patch("/reviews/{review_id}", response_model=Review)
def update_review(
    review_id: str,
    payload: ReviewUpdateRequest,
    _: dict = Depends(require_roles("admin", "reviewer")),
) -> Review:
    """更新审核结论并写入审计事件。"""

    # 先按路径编号查找记录，再判断当前记录是否仍处于待审核状态。
    review = _REVIEWS.get(review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审核记录不存在")
    # 只有待审核记录可以被处理，已处理记录禁止重复修改。
    if review.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该审核记录已处理")
    # 按请求更新审核结论，并保留可选的人工备注。
    review.status = payload.status
    if payload.comment is not None:
        # 未提交 comment 时保留原有意见，避免 PATCH 清空已有内容。
        review.comment = payload.comment
    # 每次状态变更都刷新更新时间，并记录一条审计事件。
    review.updated_at = datetime.now(timezone.utc)
    record_audit(payload.status, "review", review_id, f"审核记录 {review.subject} 状态更新为 {payload.status}")
    return review
