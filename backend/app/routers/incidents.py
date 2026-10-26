"""站点事件上报、平台内通知和事件处置路由。"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..data.incidents import _STATION_BACKUP_CONTACTS, _STATION_CONTACTS, _STATION_HEARTBEATS
from ..data.repositories import get_data_source
from ..dependencies import require_roles, require_station_access, user_has_station_access
from ..schemas.incidents import HeartbeatResponse, Incident, IncidentCreateRequest, Notification, StationContact
from ..services.audit import record_audit

# 事件路由覆盖站点上报、心跳、联系人、通知处理和事件关闭。
router = APIRouter(prefix="/api/v1", tags=["站点事件与通知"])
data_source = get_data_source()


def _now() -> datetime:
    """返回统一使用 UTC 的当前时间。"""

    # 所有事件时间统一使用带时区的 UTC，避免通知排序出现歧义。
    return datetime.now(timezone.utc)


def _next_identifier(prefix: str, records: dict, now: datetime) -> str:
    """生成按日期递增的可读业务编号，避免人工面对随机字符串。"""

    # 编号使用业务前缀、日期和三位序号，便于人工阅读和当天追踪。
    date_part = now.strftime("%Y%m%d")
    sequence = 1
    while f"{prefix}-{date_part}-{sequence:03d}" in records:
        sequence += 1
    return f"{prefix}-{date_part}-{sequence:03d}"


def _station_exists(station_id: str) -> bool:
    """判断站点编码是否存在于当前拓扑 Mock 数据。"""

    # 站点数据来自当前 Mock 拓扑，后续真实接入时应替换为站点仓储查询。
    return data_source.stations.get(station_id) is not None


def _find_duplicate(payload: IncidentCreateRequest, station_id: str) -> Incident | None:
    """按站点和事件指纹查找仍未关闭的重复事件。"""

    # 没有事件指纹时无法判断重复上报，直接创建新事件。
    if not payload.deduplication_key:
        return None
    # 已解决或误报事件不再参与重复合并，避免新一轮事件被错误吞并。
    closed_statuses = {"resolved", "false_positive"}
    return next(
        (
            incident
            for incident in data_source.incidents.all().values()
            if incident.station_id == station_id
            and incident.deduplication_key == payload.deduplication_key
            and incident.status not in closed_statuses
        ),
        None,
    )


def _create_notifications(incident: Incident, now: datetime) -> None:
    """按站点联系人配置生成平台内通知。"""

    # 读取站点主联系人；未配置时使用平台默认调度账号。
    recipients = _STATION_CONTACTS.get(incident.station_id, ["dispatch-admin"])
    # 每个主联系人生成一条平台内通知，当前不调用外部短信或电话服务。
    for recipient in recipients:
        # 失败模拟只用于验收通知兜底；正常上报仍保持 sent 状态。
        delivery_failed = incident.simulate_delivery_failure
        notification = Notification(
            id=_next_identifier("通知", data_source.notifications.all(), now),
            incident_id=incident.id,
            recipient=recipient,
            sent_at=now,
            status="failed" if delivery_failed else "sent",
            retry_count=1 if delivery_failed else 0,
            failure_reason="Mock 通知网关模拟失败" if delivery_failed else None,
        )
        data_source.notifications.all()[notification.id] = notification


@router.post("/stations/{station_id}/incidents", response_model=Incident)
def report_incident(station_id: str, payload: IncidentCreateRequest, _: dict = Depends(require_station_access("admin", "operator", required_permissions=("submit_scheme",)))) -> Incident:
    """接收站点事件并生成平台内通知。"""

    # 先确认路径中的站点编号有效，再进入事件去重和创建流程。
    if not _station_exists(station_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="站点不存在")

    now = _now()
    # 使用站点和事件指纹查找未关闭的重复事件。
    duplicate = _find_duplicate(payload, station_id)
    if duplicate is not None:
        # 重复上报只增加次数并刷新描述，不再生成新的通知。
        duplicate.report_count += 1
        duplicate.updated_at = now
        duplicate.description = payload.description
        duplicate.deduplicated = True
        record_audit("deduplicate", "incident", duplicate.id, f"合并站点重复事件：{station_id} {payload.deduplication_key}")
        return duplicate

    # 首次上报创建新的业务事件记录。
    incident = Incident(
        id=_next_identifier("事件", data_source.incidents.all(), now),
        station_id=station_id,
        category=payload.category,
        level=payload.level,
        source=payload.source,
        occurred_at=payload.occurred_at or now,
        reported_by=payload.reported_by,
        description=payload.description,
        deduplication_key=payload.deduplication_key,
        simulate_delivery_failure=payload.simulate_delivery_failure,
        created_at=now,
        updated_at=now,
    )
    # 先保存事件，再根据站点联系人生成平台通知。
    data_source.incidents.all()[incident.id] = incident
    _create_notifications(incident, now)
    record_audit("report", "incident", incident.id, f"站点上报事件：{station_id} {incident.category}")
    return incident


@router.post("/stations/{station_id}/heartbeat", response_model=HeartbeatResponse)
def receive_station_heartbeat(station_id: str, _: dict = Depends(require_station_access("admin", "operator", required_permissions=("submit_scheme",)))) -> HeartbeatResponse:
    """接收站点在线心跳；心跳只表示通信可达，不代表设备运行正常。"""

    # 心跳也要求站点真实存在，避免写入无效站点编号。
    if not _station_exists(station_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="站点不存在")
    now = _now()
    # 仅更新最近心跳时间；心跳在线不代表泵组运行正常。
    _STATION_HEARTBEATS[station_id] = now
    record_heartbeat = getattr(data_source, "record_heartbeat", None)
    if record_heartbeat is not None:
        record_heartbeat(station_id, now)
    record_audit("heartbeat", "station", station_id, f"接收站点心跳：{station_id}")
    return HeartbeatResponse(
        station_id=station_id,
        received_at=now,
        last_seen_at=now,
        status="online",
        is_stale=False,
    )


@router.get("/stations/{station_id}/contacts", response_model=list[StationContact])
def list_station_contacts(station_id: str, _: dict = Depends(require_station_access("admin", "operator"))) -> list[StationContact]:
    """查询站点当前 Mock 调度联系人和备用联系人。"""

    # 权限依赖只负责账号范围校验，这里还要确认站点编码确实存在于拓扑数据。
    if not _station_exists(station_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="站点不存在")
    # 先读取主联系人，再追加一个备用联系人，供前端展示完整通知链路。
    primary_contacts = _STATION_CONTACTS.get(station_id, ["dispatch-admin"])
    contacts = [
        StationContact(
            station_id=station_id,
            contact_type="primary",
            recipient=recipient,
            priority=index,
        )
        for index, recipient in enumerate(primary_contacts, start=1)
    ]
    contacts.append(
        StationContact(
            station_id=station_id,
            contact_type="backup",
            recipient=_STATION_BACKUP_CONTACTS.get(station_id, "dispatch-supervisor"),
            priority=len(contacts) + 1,
        )
    )
    return contacts


@router.get("/incidents", response_model=list[Incident])
def list_incidents(
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    station_id: str | None = Query(default=None, max_length=64),
    user: dict = Depends(require_roles("admin", "operator")),
) -> list[Incident]:
    """按状态和站点查询事件。"""

    # 先读取全部事件，再按账号范围、状态和查询站点逐层过滤。
    rows = list(data_source.incidents.all().values())
    # 如果请求显式指定站点，先校验该站点，避免通过查询参数越权探测。
    if station_id and not user_has_station_access(user, station_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权访问该站点")
    # 先过滤账号可见范围，再按可选状态和站点条件继续缩小结果。
    rows = [incident for incident in rows if user_has_station_access(user, incident.station_id)]
    if status_filter:
        # status 参数只做当前状态的精确匹配，未传时返回全部可见事件。
        rows = [incident for incident in rows if incident.status == status_filter]
    if station_id:
        # 站点参数只保留指定站点的事件；空参数表示不限制站点。
        rows = [incident for incident in rows if incident.station_id == station_id]
    # 事件字典按创建顺序保存，当前列表接口保持该顺序返回。
    return rows


@router.get("/notifications", response_model=list[Notification])
def list_notifications(status_filter: str | None = Query(default=None, alias="status", max_length=32), user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> list[Notification]:
    """查询当前 Mock 调度用户的平台内通知。"""

    # 通知必须通过关联事件判断站点范围，不能仅凭通知编号放行。
    rows = [
        notification
        for notification in data_source.notifications.all().values()
        if (incident := data_source.incidents.get(notification.incident_id)) is not None
        and user_has_station_access(user, incident.station_id)
    ]
    if status_filter:
        # 通知状态筛选与事件站点权限筛选相互独立，仍以关联事件范围为准。
        rows = [notification for notification in rows if notification.status == status_filter]
    # 新通知追加到字典末尾，反转后让最新通知先展示。
    return list(reversed(rows))


@router.post("/notifications/{notification_id}/ack", response_model=Notification)
def acknowledge_notification(notification_id: str, user: dict = Depends(require_roles("admin", "operator", required_permissions=("submit_scheme",)))) -> Notification:
    """确认平台内通知，并同步确认关联事件。"""

    # 先查通知，再通过关联事件校验站点权限。
    notification = data_source.notifications.get(notification_id)
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知不存在")
    incident = data_source.incidents.get(notification.incident_id)
    if incident is None or not user_has_station_access(user, incident.station_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权处理该站点通知")
    # 重复确认保持幂等；首次确认才更新确认时间和事件状态。
    if notification.status != "acknowledged":
        notification.status = "acknowledged"
        notification.acknowledged_at = _now()
        if incident is not None and incident.status == "open":
            incident.status = "acknowledged"
            incident.updated_at = notification.acknowledged_at
        if incident is not None:
            # 同一事件可能已经升级出多条通知，统一同步事件处置状态。
            # 同一事件可能存在主联系人和升级通知，需要同步显示事件状态。
            for related in data_source.notifications.all().values():
                if related.incident_id == incident.id:
                    related.incident_status = incident.status
        record_audit("acknowledge", "notification", notification_id, f"确认站点事件通知：{notification.incident_id}")
    return notification


@router.post("/notifications/{notification_id}/retry", response_model=Notification)
def retry_notification(notification_id: str, user: dict = Depends(require_roles("admin", "operator", required_permissions=("submit_scheme",)))) -> Notification:
    """重试发送失败的 Mock 通知，并保留重试次数和审计记录。"""

    # 先定位通知，再通过关联事件校验站点范围，避免只凭通知编号越权重试。
    notification = data_source.notifications.get(notification_id)
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知不存在")
    incident = data_source.incidents.get(notification.incident_id)
    if incident is None or not user_has_station_access(user, incident.station_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权处理该站点通知")
    # 只有失败通知可以重试；已发送或已确认通知保持幂等边界。
    if notification.status != "failed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有发送失败的通知可以重试")
    notification.status = "sent"
    notification.retry_count += 1
    notification.failure_reason = None
    notification.sent_at = _now()
    record_audit("retry", "notification", notification_id, f"重试发送站点事件通知：{notification.incident_id}")
    return notification


@router.post("/notifications/{notification_id}/escalate", response_model=Notification)
def escalate_notification(notification_id: str, user: dict = Depends(require_roles("admin", "operator", required_permissions=("submit_scheme",)))) -> Notification:
    """将未确认的平台内通知升级给站点备用调度联系人。"""

    # 升级前先定位原通知，并确认操作者拥有关联站点权限。
    notification = data_source.notifications.get(notification_id)
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知不存在")
    incident = data_source.incidents.get(notification.incident_id)
    if incident is None or not user_has_station_access(user, incident.station_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权处理该站点通知")
    # 只有尚未确认且尚未升级的原始通知可以执行升级。
    if notification.status != "sent":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有待确认通知可以升级")
    if notification.escalated_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该通知已经升级")

    # 上面的权限检查已要求关联事件存在；此处保留明确的异常分支，便于维护时理解数据关联前提。
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="关联事件不存在")
    # 使用站点备用联系人生成第二条通知，当前仍是平台内 Mock 投递。
    backup_recipient = _STATION_BACKUP_CONTACTS.get(incident.station_id, "dispatch-supervisor")
    now = _now()
    # 原通知记录升级时间，新通知沿用原事件并把升级等级加一。
    notification.escalated_at = now
    escalated = Notification(
        id=_next_identifier("通知", data_source.notifications.all(), now),
        incident_id=notification.incident_id,
        recipient=backup_recipient,
        channel=notification.channel,
        sent_at=now,
        escalation_level=notification.escalation_level + 1,
    )
    # 保存升级通知；接口返回新通知，前端可直接刷新备用联系人通知状态。
    data_source.notifications.all()[escalated.id] = escalated
    record_audit(
        "escalate",
        "notification",
        notification_id,
        f"升级站点事件通知：{notification.incident_id} -> {backup_recipient}",
    )
    return escalated


@router.post("/incidents/{incident_id}/resolve", response_model=Incident)
def resolve_incident(incident_id: str, user: dict = Depends(require_roles("admin", "operator", required_permissions=("submit_scheme",)))) -> Incident:
    """关闭一个站点事件，不触发任何现场控制动作。"""

    # 关闭事件前先定位记录并校验站点权限。
    incident = data_source.incidents.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="事件不存在")
    if not user_has_station_access(user, incident.station_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权处理该站点事件")
    # 关闭只改变平台事件和通知展示状态，不执行任何现场控制。
    incident.status = "resolved"
    incident.updated_at = _now()
    # 事件关闭后，通知中心中的原始通知和升级通知都应显示已解决。
    # 关联通知同步为已解决，保证通知中心与事件详情一致。
    for related in data_source.notifications.all().values():
        if related.incident_id == incident.id:
            related.incident_status = incident.status
    record_audit("resolve", "incident", incident_id, f"关闭站点事件：{incident.station_id} {incident.category}")
    return incident
