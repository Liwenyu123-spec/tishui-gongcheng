"""统一的数据访问边界。

当前实现仍然使用进程内 Mock 数据，但业务层只依赖这里定义的仓储接口。
后续接入数据库、时序库或现场数据适配器时，替换 ``MockDataSource`` 的组装即可，
不需要让路由和 Agent 再次修改数据读取方式。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..schemas.incidents import Incident, Notification
from ..schemas.audit import AuditEvent
from ..schemas.reports import Report
from ..schemas.reviews import Review
from ..schemas.work_orders import WorkOrderDraft
from .incidents import _INCIDENTS, _NOTIFICATIONS
from .monitoring import _ALARMS, _STATIONS
from .audit import _AUDIT_EVENTS
from .reports import _REPORTS
from .reviews import _REVIEWS
from .supply import _SUPPLY_AREAS
from .users import _TOKENS, _USERS
from .work_orders import _WORK_ORDERS


class StationRepository(Protocol):
    """站点和拓扑基础资料读取接口。"""

    def list(self) -> list[dict]: ...

    def get(self, station_id: str) -> dict | None: ...


class AlarmRepository(Protocol):
    """告警资料读取接口。"""

    def list(self) -> list[dict]: ...

    def get(self, alarm_id: str) -> dict | None: ...


class SupplyRepository(Protocol):
    """片区供需资料读取接口。"""

    def list(self) -> list[dict]: ...


class IncidentRepository(Protocol):
    """站点事件读取接口。"""

    def all(self) -> dict[str, Incident]: ...

    def get(self, incident_id: str) -> Incident | None: ...


class NotificationRepository(Protocol):
    """平台通知读取接口。"""

    def all(self) -> dict[str, Notification]: ...

    def get(self, notification_id: str) -> Notification | None: ...


class UserRepository(Protocol):
    """用户和令牌存储接口。"""

    def users(self) -> dict[str, dict]: ...

    def tokens(self) -> dict[str, str]: ...


class AuditRepository(Protocol):
    """审计事件存储接口。"""

    def all(self) -> list[AuditEvent]: ...

    def append(self, event: AuditEvent) -> None: ...


class ReviewRepository(Protocol):
    """人工审核记录存储接口。"""

    def all(self) -> dict[str, Review]: ...

    def get(self, review_id: str) -> Review | None: ...


class ReportRepository(Protocol):
    """报告存储接口。"""

    def all(self) -> dict[str, Report]: ...

    def get(self, report_id: str) -> Report | None: ...


class WorkOrderRepository(Protocol):
    """工单存储接口。"""

    def all(self) -> dict[str, WorkOrderDraft]: ...

    def get(self, work_order_id: str) -> WorkOrderDraft | None: ...


class MockStationRepository:
    def list(self) -> list[dict]:
        return _STATIONS

    def get(self, station_id: str) -> dict | None:
        return next((item for item in _STATIONS if item["id"] == station_id), None)


class MockAlarmRepository:
    def list(self) -> list[dict]:
        return _ALARMS

    def get(self, alarm_id: str) -> dict | None:
        return next((item for item in _ALARMS if item["id"] == alarm_id), None)


class MockSupplyRepository:
    def list(self) -> list[dict]:
        return _SUPPLY_AREAS


class MockIncidentRepository:
    def all(self) -> dict[str, Incident]:
        return _INCIDENTS

    def get(self, incident_id: str) -> Incident | None:
        return _INCIDENTS.get(incident_id)


class MockNotificationRepository:
    def all(self) -> dict[str, Notification]:
        return _NOTIFICATIONS

    def get(self, notification_id: str) -> Notification | None:
        return _NOTIFICATIONS.get(notification_id)


class MockUserRepository:
    def users(self) -> dict[str, dict]:
        return _USERS

    def tokens(self) -> dict[str, str]:
        return _TOKENS


class MockAuditRepository:
    def all(self) -> list[AuditEvent]:
        return _AUDIT_EVENTS

    def append(self, event: AuditEvent) -> None:
        _AUDIT_EVENTS.append(event)


class MockReviewRepository:
    def all(self) -> dict[str, Review]:
        return _REVIEWS

    def get(self, review_id: str) -> Review | None:
        return _REVIEWS.get(review_id)


class MockReportRepository:
    def all(self) -> dict[str, Report]:
        return _REPORTS

    def get(self, report_id: str) -> Report | None:
        return _REPORTS.get(report_id)


class MockWorkOrderRepository:
    def all(self) -> dict[str, WorkOrderDraft]:
        return _WORK_ORDERS

    def get(self, work_order_id: str) -> WorkOrderDraft | None:
        return _WORK_ORDERS.get(work_order_id)


_MEMORY_VIRTUAL: dict[str, list[dict]] = {}


def _memory_virtual_metrics(station: dict, metrics: list[str]) -> dict[str, list[dict]]:
    """数据库不可用时，每次查询仍在内存里写一条新的测试值。"""

    import random
    from datetime import datetime, timezone

    sequence = int(station.get("sequence") or 1)
    specs = {
        "flow": (1120.0 - (sequence - 1) * 18.0, 24.0, 400.0, 1600.0, 0),
        "pressure": (0.72 - (sequence - 1) * 0.02, 0.03, 0.2, 1.2, 2),
        "level": (3.4 - (sequence - 1) * 0.08, 0.12, 1.2, 5.5, 2),
        "energy": (184.0 + (sequence - 1) * 2.5, 6.0, 80.0, 400.0, 0),
    }
    now = datetime.now(timezone.utc)
    stored: dict[str, list[dict]] = {}
    for metric in metrics:
        if metric not in specs:
            continue
        base, jitter, low, high, digits = specs[metric]
        key = f"{station['id']}:{metric}"
        history = _MEMORY_VIRTUAL.setdefault(key, [])
        start = float(history[0]["value"]) if history else base
        value = round(min(high, max(low, start + random.uniform(-jitter, jitter))), digits)
        history.insert(0, {"observed_at": now, "value": value})
        del history[24:]
        stored[metric] = list(history)
    return stored


@dataclass
class MockDataSource:
    """当前阶段的统一数据源组合；字段类型就是业务层依赖的接口。"""

    stations: StationRepository
    alarms: AlarmRepository
    supply: SupplyRepository
    incidents: IncidentRepository
    notifications: NotificationRepository
    users: UserRepository
    audit: AuditRepository
    reviews: ReviewRepository
    reports: ReportRepository
    work_orders: WorkOrderRepository

    def record_virtual_metrics(self, station: dict, metrics: list[str]) -> dict[str, list[dict]]:
        return _memory_virtual_metrics(station, metrics)


_DATA_SOURCE = MockDataSource(
    stations=MockStationRepository(),
    alarms=MockAlarmRepository(),
    supply=MockSupplyRepository(),
    incidents=MockIncidentRepository(),
    notifications=MockNotificationRepository(),
    users=MockUserRepository(),
    audit=MockAuditRepository(),
    reviews=MockReviewRepository(),
    reports=MockReportRepository(),
    work_orders=MockWorkOrderRepository(),
)


def get_data_source() -> MockDataSource:
    """返回当前进程的数据源。能连上本地 MySQL 时读写 water_dispatch。"""

    return _DATA_SOURCE


def use_mysql_source() -> MockDataSource:
    """用数据库仓储替换内存数据源。路由在导入时已经拿到旧对象，因此要回填字段。"""

    global _DATA_SOURCE
    from .mysql_source import build_mysql_source

    mysql_source = build_mysql_source()
    for key, value in mysql_source.__dict__.items():
        object.__setattr__(_DATA_SOURCE, key, value)
    # 已导入的路由模块持有原来的数据源对象，换类后仍是同一个对象。
    _DATA_SOURCE.__class__ = mysql_source.__class__
    return _DATA_SOURCE
