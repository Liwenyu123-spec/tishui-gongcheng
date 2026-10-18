"""报告生成和详情查询路由。"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from ..data.reports import _REPORTS
from ..dependencies import require_roles
from ..schemas.reports import Report, ReportContentUpdateRequest, ReportGenerateRequest, ReportStatusUpdateRequest
from ..services.audit import record_audit

# 报告路由只生成待人工复核的 Mock 草稿。
router = APIRouter(prefix="/api/v1", tags=["报告"])

# 报告只能按“草稿 → 已复核 → 已归档”顺序流转；重复提交当前状态保持幂等。
_REPORT_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"draft", "reviewed"},
    "reviewed": {"reviewed", "archived"},
    "archived": {"archived"},
}


@router.post("/reports/generate", response_model=Report)
def generate_report(
    payload: ReportGenerateRequest,
    _: dict = Depends(require_roles("admin", "operator")),
) -> Report:
    """生成一份需要人工复核的报告草稿。"""

    # 报告生成时间统一使用 UTC，便于和审计记录对齐。
    now = datetime.now(timezone.utc)
    # 未提供报告日期时使用服务器当前日期；新报告统一处于草稿状态。
    report_date = payload.report_date or now.date().isoformat()
    report = Report(
        id=f"report-{uuid4().hex[:10]}",
        report_type=payload.report_type,
        report_date=report_date,
        status="draft",
        title=f"{payload.report_type}运行报告",
        summary="报告已根据当前模拟监控和供需数据生成草稿，需人工复核。",
        from_time=payload.from_time or f"{report_date}T00:00:00Z",
        to_time=payload.to_time or f"{report_date}T23:59:59Z",
        data_version="mock-monitoring-v1",
        created_at=now,
    )
    # 当前阶段仅在内存中保存草稿，服务重启后记录会清空。
    _REPORTS[report.id] = report
    return report


@router.get("/reports", response_model=list[Report])
def list_reports(_: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> list[Report]:
    """返回当前进程内的报告草稿列表。"""

    # 报告按创建顺序保存在字典中，列表接口保持该顺序供前端展示。
    return list(_REPORTS.values())


@router.get("/reports/{report_id}", response_model=Report)
def get_report(report_id: str, _: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> Report:
    """按 ID 查询报告草稿。"""

    # 根据报告编号读取详情，前端刷新详情时调用此接口。
    report = _REPORTS.get(report_id)
    if report is None:
        # 找不到编号时返回 404，不伪造空报告。
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    return report


@router.patch("/reports/{report_id}", response_model=Report)
def update_report_content(
    report_id: str,
    payload: ReportContentUpdateRequest,
    _: dict = Depends(require_roles("admin", "operator")),
) -> Report:
    """编辑报告草稿的标题和摘要，复核或归档后禁止修改。"""

    # 生成报告属于调度工作，审批负责人只负责复核，不参与草稿内容编辑。
    report = _REPORTS.get(report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    # 报告进入复核流程后需要保留已提交版本，避免修改已审核内容。
    if report.status != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有草稿状态的报告可以编辑")
    # 至少提交一个字段，避免把空请求误记为一次内容变更。
    if payload.title is None and payload.summary is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="至少填写标题或摘要")
    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="报告标题不能为空")
        report.title = title
    if payload.summary is not None:
        summary = payload.summary.strip()
        if not summary:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="报告摘要不能为空")
        report.summary = summary
    record_audit("content_update", "report", report_id, f"报告 {report.title} 草稿内容已编辑")
    return report


@router.patch("/reports/{report_id}/status", response_model=Report)
def update_report_status(
    report_id: str,
    payload: ReportStatusUpdateRequest,
    _: dict = Depends(require_roles("admin", "reviewer")),
) -> Report:
    """更新报告草稿状态并记录审计事件。"""

    # 只有管理员或审核负责人可以确认、归档报告，普通调度员只读查看。
    report = _REPORTS.get(report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    # 状态取值由请求模型限制，更新时还要检查生命周期顺序，避免跳过人工复核。
    allowed_statuses = _REPORT_STATUS_TRANSITIONS.get(report.status, {report.status})
    if payload.status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"报告不能从 {report.status} 直接变更为 {payload.status}，请按草稿、已复核、已归档顺序处理",
        )
    # 相同状态的重复请求视为幂等操作，不重复写入状态变化审计。
    if report.status == payload.status:
        return report
    report.status = payload.status
    record_audit("status_update", "report", report_id, f"报告 {report.title} 状态更新为 {payload.status}")
    return report
