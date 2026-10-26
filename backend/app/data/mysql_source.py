"""把业务仓储接到本地 MySQL。

接口仍返回原来的字典和模型对象。每次请求结束后把这些对象写回 payload 字段，
因此审核、告警确认、用户和事件修改会留在 water_dispatch，而不是进程内存。
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone

import pymysql

from ..services.runtime_env import windows_env

from ..schemas.audit import AuditEvent
from ..schemas.incidents import Incident, Notification
from ..schemas.reports import Report
from ..schemas.reviews import Review
from ..schemas.work_orders import WorkOrderDraft
from .audit import _AUDIT_EVENTS
from .monitoring import _ALARMS, _STATIONS
from .supply import _SUPPLY_AREAS
from .users import _TOKENS, _USERS
from .repositories import (
    MockAlarmRepository,
    MockAuditRepository,
    MockDataSource,
    apply_level_status,
    MockIncidentRepository,
    MockNotificationRepository,
    MockReportRepository,
    MockReviewRepository,
    MockStationRepository,
    MockSupplyRepository,
    MockUserRepository,
    MockWorkOrderRepository,
)


def _connect():
    from ..services.runtime_env import load_env_file

    load_env_file()
    password = os.getenv("MYSQL_PASSWORD", "")
    if not password:
        raise RuntimeError("未设置 MYSQL_PASSWORD，拒绝使用写在代码里的默认密码")
    return pymysql.connect(
        host=windows_env("MYSQL_HOST") or "127.0.0.1",
        port=int(windows_env("MYSQL_PORT") or "3306"),
        user=windows_env("MYSQL_USER") or "root",
        password=password,
        database=windows_env("MYSQL_DATABASE") or "water_dispatch",
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _as_models(rows: list, model):
    loaded = {}
    for item in rows:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        try:
            loaded[item["id"]] = model.model_validate(item)
        except Exception:
            continue
    return loaded


def _dump(value) -> str:
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="json")
    else:
        payload = value
    return json.dumps(payload, ensure_ascii=False, default=str)


def _load_json(raw):
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


class MysqlDataSource(MockDataSource):
    """与内存数据源字段相同，读写落到 MySQL。"""

    def reload_stations_and_users(self) -> None:
        """每次接口请求前重新读取站点、账号、告警、事件、通知、审核、报告、供需、工单和审计。"""

        stations = getattr(self, "_station_rows", None)
        users = getattr(self, "_user_rows", None)
        tokens = getattr(self, "_token_rows", None)
        alarms = getattr(self, "_alarm_rows", None)
        incidents = getattr(self, "_incident_rows", None)
        reviews = getattr(self, "_review_rows", None)
        reports = getattr(self, "_report_rows", None)
        notices = getattr(self, "_notice_rows", None)
        supply = getattr(self, "_supply_rows", None)
        orders = getattr(self, "_order_rows", None)
        audit = getattr(self, "_audit_rows", None)
        if stations is None or users is None or tokens is None:
            return
        conn = _connect()
        try:
            loaded = [item for item in _rows(conn, "stations") if isinstance(item, dict) and "metrics" in item]
            loaded_users = {
                item["username"]: item
                for item in _rows(conn, "users_roles")
                if isinstance(item, dict) and item.get("username")
            }
            loaded_alarms = [item for item in _rows(conn, "alarms") if isinstance(item, dict)]
            loaded_incidents = _rows(conn, "incidents")
            loaded_reviews = _rows(conn, "dispatch_reviews")
            loaded_reports = _rows(conn, "reports")
            loaded_notices = _rows(conn, "notifications")
            loaded_supply = [item for item in _rows(conn, "supply_areas") if isinstance(item, dict)]
            loaded_orders = _rows(conn, "work_orders")
            loaded_audit = _rows(conn, "audit_events")
            with conn.cursor() as cur:
                cur.execute("SELECT token, username FROM auth_tokens")
                loaded_tokens = {row["token"]: row["username"] for row in cur.fetchall()}
        finally:
            conn.close()
        if loaded:
            stations[:] = loaded
        if loaded_users:
            users.clear()
            users.update(loaded_users)
        tokens.clear()
        tokens.update(loaded_tokens)
        if alarms is not None:
            alarms[:] = loaded_alarms
        if incidents is not None:
            incidents.clear()
            incidents.update(_as_models(loaded_incidents, Incident))
        if reviews is not None:
            reviews.clear()
            reviews.update(_as_models(loaded_reviews, Review))
        if reports is not None:
            reports.clear()
            reports.update(_as_models(loaded_reports, Report))
        if notices is not None:
            notices.clear()
            notices.update(_as_models(loaded_notices, Notification))
        if supply is not None:
            supply[:] = loaded_supply
        if orders is not None:
            orders.clear()
            orders.update(_as_models(loaded_orders, WorkOrderDraft))
        if audit is not None:
            audit[:] = list(_as_models(loaded_audit, AuditEvent).values())

    def import_telemetry_rows(self, rows: list[dict]) -> int:
        """把已通过校验的遥测行写入 telemetry_readings。"""

        with _connect() as conn:
            with conn.cursor() as cur:
                for row in rows:
                    observed = row["observed_at"]
                    if getattr(observed, "tzinfo", None) is not None:
                        observed = observed.replace(tzinfo=None)
                    cur.execute(
                        """
                        INSERT INTO telemetry_readings (point_id, observed_at, value, quality, source_batch, is_stale)
                        VALUES (%s, %s, %s, 'good', 'csv-import', 0)
                        """,
                        (f"{row['station_id']}:{row['metric']}"[:32], observed, row["value"]),
                    )
        return len(rows)

    # 下面这几个方法只写被改到的那一行。查询接口不再调用 flush() 把整表重写一遍。
    def commit_incident(self, item) -> None:
        self._commit([(
            """
            INSERT INTO incidents (id, station_id, category, level, source, status, reported_by, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE status=VALUES(status), payload=VALUES(payload)
            """,
            (item.id, item.station_id, item.category, item.level, item.source, item.status, item.reported_by, _dump(item)),
        )])

    def commit_notification(self, item) -> None:
        self._commit([(
            """
            INSERT INTO notifications (id, incident_id, recipient, channel, status, payload)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE status=VALUES(status), payload=VALUES(payload)
            """,
            (item.id, item.incident_id, item.recipient, item.channel, item.status, _dump(item)),
        )])

    def commit_report(self, item) -> None:
        self._commit([(
            "INSERT INTO reports (id, payload) VALUES (%s, %s) ON DUPLICATE KEY UPDATE payload=VALUES(payload)",
            (item.id, _dump(item)),
        )])

    def commit_order(self, item) -> None:
        self._commit([(
            """
            INSERT INTO work_orders (id, object_id, description, status, payload)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE status=VALUES(status), payload=VALUES(payload)
            """,
            (item.id, item.station_id or item.id, item.issue[:255], item.status, _dump(item)),
        )])

    def commit_audit(self, event) -> None:
        occurred = event.occurred_at.replace(tzinfo=None) if isinstance(event.occurred_at, datetime) else None
        self._commit([(
            """
            INSERT INTO audit_events (id, user_id, action, object_type, object_id, created_at, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE payload=VALUES(payload)
            """,
            (event.id, None, event.action, event.resource, event.resource_id, occurred, _dump(event)),
        )])

    def commit_token(self, token: str, username: str) -> None:
        self._commit([(
            "INSERT INTO auth_tokens (token, username) VALUES (%s, %s) ON DUPLICATE KEY UPDATE username=VALUES(username)",
            (token, username),
        )])

    def flush(self) -> None:
        """同一连接、同一事务写回本轮业务对象。中途失败则整批回滚。"""

        conn = _connect()
        try:
            conn.autocommit(False)
            with conn.cursor() as cur:
                self._save_stations(cur)
                self._save_supply(cur)
                self._save_incidents(cur)
                self._save_notifications(cur)
                self._save_reports(cur)
                self._save_orders(cur)
                self._save_tokens(cur)
                self._save_audit(cur)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def read_virtual_metric(self, station_id: str, metric: str, limit: int = 24) -> list[dict]:
        """读取已写入的测试遥测，不新增记录。最新一条在前。"""

        point_id = f"{station_id}:{metric}"
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT observed_at, value FROM telemetry_readings
                    WHERE point_id=%s ORDER BY observed_at DESC, id DESC LIMIT %s
                    """,
                    (point_id, limit),
                )
                rows = cur.fetchall()
        points = []
        for item in rows:
            observed = item["observed_at"]
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            points.append({"observed_at": observed, "value": float(item["value"])})
        return points

    def read_virtual_levels(self, station_id: str, limit: int = 24) -> list[dict]:
        return self.read_virtual_metric(station_id, "level", limit)

    def record_virtual_metrics(self, station: dict, metrics: list[str]) -> dict[str, list[dict]]:
        """每个测点新写一条测试值，并返回各自最近记录。"""

        import random

        sequence = int(station.get("sequence") or 1)
        specs = {
            "flow": (1120.0 - (sequence - 1) * 18.0, 24.0, 400.0, 1600.0, 0),
            "pressure": (0.72 - (sequence - 1) * 0.02, 0.03, 0.2, 1.2, 2),
            "level": (3.4 - (sequence - 1) * 0.08, 0.12, 1.2, 5.5, 2),
            "energy": (184.0 + (sequence - 1) * 2.5, 6.0, 80.0, 400.0, 0),
        }
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        latest_level: float | None = None
        with _connect() as conn:
            with conn.cursor() as cur:
                for metric in metrics:
                    if metric not in specs:
                        continue
                    base, jitter, low, high, digits = specs[metric]
                    point_id = f"{station['id']}:{metric}"
                    cur.execute(
                        "SELECT value FROM telemetry_readings WHERE point_id=%s ORDER BY observed_at DESC, id DESC LIMIT 1",
                        (point_id,),
                    )
                    row = cur.fetchone()
                    start = float(row["value"]) if row and row["value"] is not None else base
                    value = round(min(high, max(low, start + random.uniform(-jitter, jitter))), digits)
                    if metric == "level":
                        latest_level = value
                    cur.execute(
                        """
                        INSERT INTO telemetry_readings (point_id, observed_at, value, quality, source_batch, is_stale)
                        VALUES (%s, %s, %s, 'good', 'virtual-reading', 0)
                        """,
                        (point_id, now, value),
                    )
                    cur.execute(
                        """
                        DELETE FROM telemetry_readings
                        WHERE point_id=%s AND id NOT IN (
                          SELECT id FROM (
                            SELECT id FROM telemetry_readings
                            WHERE point_id=%s
                            ORDER BY observed_at DESC, id DESC
                            LIMIT 24
                          ) keep_rows
                        )
                        """,
                        (point_id, point_id),
                    )
        if latest_level is not None:
            apply_level_status(station, latest_level)
        return {metric: self.read_virtual_metric(station["id"], metric) for metric in metrics if metric in specs}

    def record_virtual_level(self, station: dict) -> list[dict]:
        return self.record_virtual_metrics(station, ["level"]).get("level", [])

    def _commit(self, statements: list[tuple[str, tuple]]) -> bool:
        """执行一组写入。最后一条是带版本条件的更新时，未命中则整批回滚。"""

        conn = _connect()
        try:
            conn.autocommit(False)
            with conn.cursor() as cur:
                for index, (sql, params) in enumerate(statements):
                    cur.execute(sql, params)
                    if index == 0 and cur.rowcount != 1 and sql.lstrip().upper().startswith("UPDATE"):
                        conn.rollback()
                        return False
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def commit_alarm(self, alarm: dict) -> bool:
        """按行版本确认告警。版本不符时不覆盖数据库里的新状态。"""

        expected = int(alarm.get("row_version") or 0)
        alarm["row_version"] = expected + 1
        ok = self._commit([
            (
                """
                UPDATE alarms SET status=%s, payload=%s
                WHERE id=%s AND (
                  JSON_EXTRACT(payload, '$.row_version') = %s
                  OR (%s = 0 AND JSON_EXTRACT(payload, '$.row_version') IS NULL)
                )
                """,
                (alarm.get("status"), _dump(alarm), alarm["id"], expected, expected),
            )
        ])
        if not ok:
            alarm["row_version"] = expected
        return ok

    def commit_review(self, review, *, creating: bool) -> bool:
        """新建或按行版本更新一条审核。"""

        expected = int(getattr(review, "row_version", 0) or 0)
        review.row_version = expected + 1
        payload = review.model_dump(mode="json")
        if creating:
            return self._commit([
                (
                    """
                    INSERT INTO dispatch_reviews (id, recommendation, decision, payload)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (review.id, review.recommendation[:255], review.status, _dump(payload)),
                )
            ])
        ok = self._commit([
            (
                """
                UPDATE dispatch_reviews SET decision=%s, payload=%s
                WHERE id=%s AND (
                  JSON_EXTRACT(payload, '$.row_version') = %s
                  OR (%s = 0 AND JSON_EXTRACT(payload, '$.row_version') IS NULL)
                )
                """,
                (review.status, _dump(payload), review.id, expected, expected),
            )
        ])
        if not ok:
            review.row_version = expected
        return ok

    def commit_user(self, username: str, user: dict, *, creating: bool) -> bool:
        """新建或按行版本更新一个账号。"""

        expected = int(user.get("row_version") or 0)
        user["row_version"] = expected + 1
        params_head = (
            username,
            user.get("role") or "",
            ",".join(user.get("station_ids") or []),
            "",
            _dump(user),
        )
        if creating:
            return self._commit([
                (
                    """
                    INSERT INTO users_roles (user_id, role_code, station_scope, area_scope, payload)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    params_head,
                )
            ])
        ok = self._commit([
            (
                """
                UPDATE users_roles
                SET role_code=%s, station_scope=%s, payload=%s
                WHERE user_id=%s AND (
                  JSON_EXTRACT(payload, '$.row_version') = %s
                  OR (%s = 0 AND JSON_EXTRACT(payload, '$.row_version') IS NULL)
                )
                """,
                (user.get("role") or "", ",".join(user.get("station_ids") or []), _dump(user), username, expected, expected),
            )
        ])
        if not ok:
            user["row_version"] = expected
        return ok

    def delete_user(self, username: str) -> None:
        """删除账号及其登录令牌。"""

        self._commit([
            ("DELETE FROM auth_tokens WHERE username=%s", (username,)),
            ("DELETE FROM users_roles WHERE user_id=%s", (username,)),
        ])

    def record_heartbeat(self, station_id: str, seen_at: datetime) -> None:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO external_factors (id, factor_type, effective_at, payload, source)
                    VALUES (%s, 'heartbeat', %s, %s, 'platform')
                    ON DUPLICATE KEY UPDATE effective_at=VALUES(effective_at), payload=VALUES(payload)
                    """,
                    (f"hb-{station_id}", seen_at.replace(tzinfo=None), _dump({"station_id": station_id})),
                )

    def record_scheme(self, comparison_id: str, payload: dict) -> None:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO scheme_comparisons (id, request_id, options_json, metrics_json, created_by)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE options_json=VALUES(options_json), metrics_json=VALUES(metrics_json)
                    """,
                    (comparison_id, comparison_id, _dump(payload), _dump(payload.get("results")), "platform"),
                )

    def mirror_knowledge(self, document_id: str, payload: dict) -> None:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO knowledge_documents (id, title, doc_type, version, status, source, payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE title=VALUES(title), status=VALUES(status), payload=VALUES(payload)
                    """,
                    (
                        document_id,
                        str(payload.get("title") or document_id)[:128],
                        str(payload.get("doc_type") or payload.get("category") or "知识")[:32],
                        str(payload.get("version") or "1")[:16],
                        str(payload.get("status") or "待审")[:16],
                        "knowledge_store",
                        _dump(payload),
                    ),
                )

    def _save_stations(self, cur) -> None:
                for item in self.stations.list():
                    cur.execute(
                        """
                        INSERT INTO stations (id, code, name, station_type, sequence_no, enabled, payload)
                        VALUES (%s, %s, %s, %s, %s, 1, %s)
                        ON DUPLICATE KEY UPDATE name=VALUES(name), payload=VALUES(payload)
                        """,
                        (item["id"], item["id"], item["name"], item.get("station_type") or "泵站", int(item.get("sequence") or 0), _dump(item)),
                    )

    def _save_alarms(self, cur) -> None:
                for item in self.alarms.list():
                    cur.execute(
                        """
                        INSERT INTO alarms (id, object_id, level, status, payload)
                        VALUES (%s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE status=VALUES(status), payload=VALUES(payload)
                        """,
                        (item["id"], item["station_id"], item.get("level"), item.get("status"), _dump(item)),
                    )

    def _save_supply(self, cur) -> None:
                for item in self.supply.list():
                    cur.execute(
                        """
                        INSERT INTO supply_areas (id, code, name, payload)
                        VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE name=VALUES(name), payload=VALUES(payload)
                        """,
                        (item["area"], item["station_id"], item["area"], _dump(item)),
                    )

    def _save_incidents(self, cur) -> None:
                for item in self.incidents.all().values():
                    cur.execute(
                        """
                        INSERT INTO incidents (id, station_id, category, level, source, status, reported_by, payload)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE status=VALUES(status), payload=VALUES(payload)
                        """,
                        (item.id, item.station_id, item.category, item.level, item.source, item.status, item.reported_by, _dump(item)),
                    )

    def _save_notifications(self, cur) -> None:
                for item in self.notifications.all().values():
                    cur.execute(
                        """
                        INSERT INTO notifications (id, incident_id, recipient, channel, status, payload)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE status=VALUES(status), payload=VALUES(payload)
                        """,
                        (item.id, item.incident_id, item.recipient, item.channel, item.status, _dump(item)),
                    )

    def _save_reviews(self, cur) -> None:
                for item in self.reviews.all().values():
                    cur.execute(
                        """
                        INSERT INTO dispatch_reviews (id, recommendation, decision, payload)
                        VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE decision=VALUES(decision), payload=VALUES(payload)
                        """,
                        (item.id, item.recommendation[:255], item.status, _dump(item)),
                    )

    def _save_reports(self, cur) -> None:
                for item in self.reports.all().values():
                    cur.execute(
                        "INSERT INTO reports (id, payload) VALUES (%s, %s) ON DUPLICATE KEY UPDATE payload=VALUES(payload)",
                        (item.id, _dump(item)),
                    )

    def _save_orders(self, cur) -> None:
                for item in self.work_orders.all().values():
                    cur.execute(
                        """
                        INSERT INTO work_orders (id, object_id, description, status, payload)
                        VALUES (%s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE status=VALUES(status), payload=VALUES(payload)
                        """,
                        (item.id, item.station_id or item.id, item.issue[:255], item.status, _dump(item)),
                    )

    def _save_users(self, cur) -> None:
                for username, user in self.users.users().items():
                    cur.execute(
                        """
                        INSERT INTO users_roles (user_id, role_code, station_scope, area_scope, payload)
                        VALUES (%s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE role_code=VALUES(role_code), station_scope=VALUES(station_scope), payload=VALUES(payload)
                        """,
                        (
                            username,
                            user.get("role") or "",
                            ",".join(user.get("station_ids") or []),
                            "",
                            _dump(user),
                        ),
                    )

    def _save_tokens(self, cur) -> None:
                for token, username in self.users.tokens().items():
                    cur.execute(
                        "INSERT INTO auth_tokens (token, username) VALUES (%s, %s) ON DUPLICATE KEY UPDATE username=VALUES(username)",
                        (token, username),
                    )

    def _save_audit(self, cur) -> None:
                for event in self.audit.all():
                    cur.execute(
                        """
                        INSERT INTO audit_events (id, user_id, action, object_type, object_id, created_at, payload)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE payload=VALUES(payload)
                        """,
                        (
                            event.id,
                            None,
                            event.action,
                            event.resource,
                            event.resource_id,
                            event.occurred_at.replace(tzinfo=None) if isinstance(event.occurred_at, datetime) else None,
                            _dump(event),
                        ),
                    )


def apply_migrations(conn) -> None:
    """只执行尚未记录的 SQL 文件。已有库不会在每次启动时重复改表。"""

    from pathlib import Path

    sql_dir = Path(__file__).resolve().parents[2] / "sql"
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              version VARCHAR(64) PRIMARY KEY,
              applied_at DATETIME NOT NULL
            ) COMMENT = '已执行的 SQL 迁移版本'
            """
        )
        cur.execute("SELECT version FROM schema_migrations")
        done = {row["version"] for row in cur.fetchall()}
        if "001" not in done:
            cur.execute("INSERT INTO schema_migrations (version, applied_at) VALUES ('001', NOW())")
        if "002" in done:
            return
        script = (sql_dir / "002_payload_columns.sql").read_text(encoding="utf-8")
        for statement in [part.strip() for part in script.split(";") if part.strip()]:
            try:
                cur.execute(statement)
            except pymysql.err.OperationalError as exc:
                if exc.args and exc.args[0] in {1060, 1061}:
                    continue
                raise
        cur.execute("INSERT INTO schema_migrations (version, applied_at) VALUES ('002', NOW())")


def _rows(conn, table: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT payload FROM {table} WHERE payload IS NOT NULL")
        return [_load_json(row["payload"]) for row in cur.fetchall()]


def build_mysql_source() -> MysqlDataSource:
    """连接 water_dispatch，装载已有记录，并在缺业务站点时写入当前平台所需的初始记录。"""

    conn = _connect()
    apply_migrations(conn)
    stations = _rows(conn, "stations")
    alarms = _rows(conn, "alarms")
    supply = _rows(conn, "supply_areas")
    reviews = {item["id"]: Review.model_validate(item) for item in _rows(conn, "dispatch_reviews")}
    reports = {item["id"]: Report.model_validate(item) for item in _rows(conn, "reports")}
    orders = {item["id"]: WorkOrderDraft.model_validate(item) for item in _rows(conn, "work_orders")}
    incidents = {item["id"]: Incident.model_validate(item) for item in _rows(conn, "incidents")}
    notifications = {item["id"]: Notification.model_validate(item) for item in _rows(conn, "notifications")}
    users = {item["username"]: item for item in _rows(conn, "users_roles")}
    with conn.cursor() as cur:
        cur.execute("SELECT token, username FROM auth_tokens")
        tokens = {row["token"]: row["username"] for row in cur.fetchall()}
        cur.execute("SELECT payload FROM audit_events WHERE payload IS NOT NULL ORDER BY created_at")
        audit = [AuditEvent.model_validate(_load_json(row["payload"])) for row in cur.fetchall()]
    conn.close()

    app_stations = [item for item in stations if isinstance(item, dict) and "metrics" in item]
    if not app_stations:
        app_stations = [dict(item) for item in _STATIONS]
    if not alarms:
        alarms = [dict(item) for item in _ALARMS]
    if not supply:
        supply = [dict(item) for item in _SUPPLY_AREAS]
    if not users:
        users = {key: dict(value) for key, value in _USERS.items()}
    if not tokens:
        tokens = dict(_TOKENS)

    station_repo = MockStationRepository()
    station_repo.list = lambda app_stations=app_stations: app_stations  # type: ignore[method-assign]
    station_repo.get = lambda station_id, app_stations=app_stations: next((item for item in app_stations if item["id"] == station_id), None)  # type: ignore[method-assign]
    alarm_repo = MockAlarmRepository()
    alarm_repo.list = lambda alarms=alarms: alarms  # type: ignore[method-assign]
    alarm_repo.get = lambda alarm_id, alarms=alarms: next((item for item in alarms if item["id"] == alarm_id), None)  # type: ignore[method-assign]
    supply_repo = MockSupplyRepository()
    supply_repo.list = lambda supply=supply: supply  # type: ignore[method-assign]
    incident_repo = MockIncidentRepository()
    incident_repo.all = lambda incidents=incidents: incidents  # type: ignore[method-assign]
    incident_repo.get = lambda incident_id, incidents=incidents: incidents.get(incident_id)  # type: ignore[method-assign]
    notice_repo = MockNotificationRepository()
    notice_repo.all = lambda notifications=notifications: notifications  # type: ignore[method-assign]
    notice_repo.get = lambda notification_id, notifications=notifications: notifications.get(notification_id)  # type: ignore[method-assign]
    user_repo = MockUserRepository()
    user_repo.users = lambda users=users: users  # type: ignore[method-assign]
    user_repo.tokens = lambda tokens=tokens: tokens  # type: ignore[method-assign]
    audit_repo = MockAuditRepository()
    audit_repo.all = lambda audit=audit: audit  # type: ignore[method-assign]
    audit_repo.append = lambda event, audit=audit: audit.append(event)  # type: ignore[method-assign]
    review_repo = MockReviewRepository()
    review_repo.all = lambda reviews=reviews: reviews  # type: ignore[method-assign]
    review_repo.get = lambda review_id, reviews=reviews: reviews.get(review_id)  # type: ignore[method-assign]
    report_repo = MockReportRepository()
    report_repo.all = lambda reports=reports: reports  # type: ignore[method-assign]
    report_repo.get = lambda report_id, reports=reports: reports.get(report_id)  # type: ignore[method-assign]
    order_repo = MockWorkOrderRepository()
    order_repo.all = lambda orders=orders: orders  # type: ignore[method-assign]
    order_repo.get = lambda work_order_id, orders=orders: orders.get(work_order_id)  # type: ignore[method-assign]

    source = MysqlDataSource(
        stations=station_repo,
        alarms=alarm_repo,
        supply=supply_repo,
        incidents=incident_repo,
        notifications=notice_repo,
        users=user_repo,
        audit=audit_repo,
        reviews=review_repo,
        reports=report_repo,
        work_orders=order_repo,
    )
    source._station_rows = app_stations
    source._user_rows = users
    source._token_rows = tokens
    source._alarm_rows = alarms
    source._incident_rows = incidents
    source._review_rows = reviews
    source._report_rows = reports
    source._notice_rows = notifications
    source._supply_rows = supply
    source._order_rows = orders
    source._audit_rows = audit
    source._request_gate = threading.Lock()
    if not _AUDIT_EVENTS:
        pass
    source.flush()
    return source
