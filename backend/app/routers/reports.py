"""报告生成和详情查询路由。"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from ..data.reports import _REPORTS
from ..dependencies import require_roles
from ..schemas.reports import Report, ReportGenerateRequest, ReportStatusUpdateRequest
from ..services.audit import record_audit

# 报告路由只生成待人工复核的 Mock 草稿。
router = APIRouter(prefix="/api/v1", tags=["报告"])


@router.post("/reports/generate", response_model=Report)
def generate_report(
    payload: ReportGenerateRequest,
    _: dict = Depends(require_roles("admin", "operator")),
) -> Report:
    """生成一份需要人工复核的报告草稿。"""

    # 报告生成时间统一使用 UTC，便于和审计记录对齐。
    now = datetime.now(timezone.utc)
    # 未提供报告日期时使用服务器当前日期；新报告统一处于草稿状态。
    report = Report(
        id=f"report-{uuid4().hex[:10]}",
        report_type=payload.report_type,
        report_date=payload.report_date or now.date().isoformat(),
        status="draft",
        title=f"{payload.report_type}运行报告",
        summary="报告已根据当前模拟监控和供需数据生成草稿，需人工复核。",
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
    # 状态取值由请求模型限制，更新时保留报告正文和生成时间。
    report.status = payload.status
    record_audit("status_update", "report", report_id, f"报告 {report.title} 状态更新为 {payload.status}")
    return report
