"""报告生成和详情查询路由。"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from ..data.repositories import get_data_source
from ..dependencies import require_roles, user_has_station_access
from ..schemas.reports import Report, ReportContentUpdateRequest, ReportGenerateRequest, ReportMetric, ReportStatusUpdateRequest
from ..services.audit import record_audit

# 报告路由只生成待人工复核的 Mock 草稿。
router = APIRouter(prefix="/api/v1", tags=["报告"])
data_source = get_data_source()

# 报告只能按“草稿 → 已复核 → 已归档”顺序流转；重复提交当前状态保持幂等。
_REPORT_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"draft", "reviewed"},
    "reviewed": {"reviewed", "archived"},
    "archived": {"archived"},
}


def _report_station_ids(report: Report) -> set[str]:
    """从报告来源编号反推出报告覆盖的站点范围。"""

    station_ids: set[str] = set()
    for source_id in report.source_ids:
        if source_id.startswith("supply:"):
            station_ids.add(source_id.removeprefix("supply:"))
            continue
        alarm = data_source.alarms.get(source_id)
        if alarm is not None:
            station_ids.add(str(alarm["station_id"]))
    return station_ids


def _report_visible(report: Report, user: dict) -> bool:
    """报告必须完全落在当前账号的站点范围内。"""

    if user.get("role") == "admin":
        return True
    return all(user_has_station_access(user, station_id) for station_id in _report_station_ids(report))


def _build_report_metrics(user: dict) -> tuple[list[ReportMetric], list[str]]:
    """按当前账号可见站点汇总报告指标，并返回扁平化来源编号。"""

    # 报告只能使用当前账号可见的片区和告警，避免在导出内容中串出越权站点。
    visible_areas = [
        area for area in data_source.supply.list() if user_has_station_access(user, area["station_id"])
    ]
    visible_alarms = [
        alarm for alarm in data_source.alarms.list() if user_has_station_access(user, alarm["station_id"])
    ]
    area_sources = [f"supply:{area['station_id']}" for area in visible_areas]
    alarm_sources = [str(alarm["id"]) for alarm in visible_alarms]
    total_supply = sum(float(area["supply"]) for area in visible_areas)
    total_demand = sum(float(area["demand"]) for area in visible_areas)
    balance = total_supply - total_demand
    bottleneck = min(
        visible_areas,
        key=lambda area: float(area["supply"]) - float(area["demand"]),
        default=None,
    )
    metrics = [
        ReportMetric(
            key="total_supply",
            label="总供水量",
            value=round(total_supply, 2),
            unit="m³/d",
            source_ids=area_sources,
        ),
        ReportMetric(
            key="total_demand",
            label="总需求量",
            value=round(total_demand, 2),
            unit="m³/d",
            source_ids=area_sources,
        ),
        ReportMetric(
            key="total_balance",
            label="供需结余",
            value=round(balance, 2),
            unit="m³/d",
            source_ids=area_sources,
        ),
        ReportMetric(
            key="alarm_count",
            label="关联告警数",
            value=float(len(visible_alarms)),
            unit="条",
            source_ids=alarm_sources,
        ),
    ]
    if bottleneck is not None:
        metrics.append(
            ReportMetric(
                key="bottleneck_balance",
                label=f"瓶颈片区：{bottleneck['area']}",
                value=round(float(bottleneck["supply"]) - float(bottleneck["demand"]), 2),
                unit="m³/d",
                source_ids=[f"supply:{bottleneck['station_id']}"],
            )
        )
    source_ids = list(dict.fromkeys(area_sources + alarm_sources))
    return metrics, source_ids


@router.post("/reports/generate", response_model=Report)
def generate_report(
    payload: ReportGenerateRequest,
    user: dict = Depends(require_roles("admin", "operator", required_permissions=("submit_scheme",))),
) -> Report:
    """生成一份需要人工复核的报告草稿。"""

    # 报告生成时间统一使用 UTC，便于和审计记录对齐。
    now = datetime.now(timezone.utc)
    # 未提供报告日期时使用服务器当前日期；新报告统一处于草稿状态。
    report_date = payload.report_date or now.date().isoformat()
    metrics, source_ids = _build_report_metrics(user)
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
        metrics=metrics,
        source_ids=source_ids,
    )
    # 当前阶段仅在内存中保存草稿，服务重启后记录会清空。
    data_source.reports.all()[report.id] = report
    record_audit(
        "generate",
        "report",
        report.id,
        f"生成报告草稿：{report.title}，来源 {len(report.source_ids)} 条",
        operator=user.get("username", "mock-admin"),
    )
    return report


@router.get("/reports", response_model=list[Report])
def list_reports(user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> list[Report]:
    """返回当前进程内的报告草稿列表。"""

    from ..data.supply import vary_supply_areas

    vary_supply_areas(list(data_source.supply.list()))
    metrics, source_ids = _build_report_metrics(user)
    visible = [report for report in data_source.reports.all().values() if _report_visible(report, user)]
    for report in visible:
        report.metrics = metrics
        report.source_ids = source_ids
    return visible


@router.get("/reports/{report_id}", response_model=Report)
def get_report(report_id: str, user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> Report:
    """按 ID 查询报告草稿。"""

    # 根据报告编号读取详情，前端刷新详情时调用此接口。
    report = data_source.reports.get(report_id)
    if report is None:
        # 找不到编号时返回 404，不伪造空报告。
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    if not _report_visible(report, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权查看该报告")
    return report


@router.patch("/reports/{report_id}", response_model=Report)
def update_report_content(
    report_id: str,
    payload: ReportContentUpdateRequest,
    user: dict = Depends(require_roles("admin", "operator", required_permissions=("submit_scheme",))),
) -> Report:
    """编辑报告草稿的标题和摘要，复核或归档后禁止修改。"""

    # 生成报告属于调度工作，审批负责人只负责复核，不参与草稿内容编辑。
    report = data_source.reports.get(report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    if not _report_visible(report, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权修改该报告")
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
    report = data_source.reports.get(report_id)
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
