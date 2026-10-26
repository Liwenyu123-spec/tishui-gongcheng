"""Agent 运行控制。

运行摘要和可恢复任务快照写入 MySQL `agent_runs`。本地 JSON 只在库不可用时兜底，
并在第一次成功连接时把已有 JSON 导入数据库。
"""

import json
from pathlib import Path
from threading import Lock
from datetime import datetime, timedelta, timezone

_STORE = Path(__file__).resolve().parents[2] / "data" / "agent_run_history.json"
_runs: dict[str, dict[str, object]] = {}
_tasks: dict[str, dict[str, object]] = {}
_lock = Lock()
_TASK_TTL = timedelta(minutes=30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _apply_payload(runs: dict, tasks: dict) -> None:
    for run_id, entry in runs.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("status") == "running":
            entry["status"] = "interrupted"
            entry["updated_at"] = _now().isoformat()
            entry["recovery"] = "restart"
        _runs[str(run_id)] = entry
    for run_id, entry in tasks.items():
        if isinstance(entry, dict):
            _tasks[str(run_id)] = entry


def _load_file() -> None:
    if not _STORE.exists():
        return
    try:
        payload = json.loads(_STORE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    runs = payload.get("runs") if isinstance(payload, dict) else None
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    _apply_payload(runs if isinstance(runs, dict) else {}, tasks if isinstance(tasks, dict) else {})


def _persist_file() -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    _STORE.write_text(json.dumps({"runs": _runs, "tasks": _tasks}, ensure_ascii=False, indent=2), encoding="utf-8")


def _ensure_columns(cur) -> None:
    for statement in (
        "ALTER TABLE agent_runs ADD COLUMN payload JSON NULL",
        "ALTER TABLE agent_runs ADD COLUMN task_payload JSON NULL",
    ):
        try:
            cur.execute(statement)
        except Exception as exc:
            if "Duplicate column" not in str(exc):
                raise


def _load_mysql() -> bool:
    from ..data.mysql_source import _connect, _load_json

    conn = _connect()
    try:
        with conn.cursor() as cur:
            _ensure_columns(cur)
            cur.execute("SELECT id, payload, task_payload FROM agent_runs")
            rows = cur.fetchall()
    finally:
        conn.close()
    if not rows:
        return False
    runs = {}
    tasks = {}
    for row in rows:
        entry = _load_json(row.get("payload")) or {}
        if isinstance(entry, dict):
            runs[row["id"]] = entry
        task = _load_json(row.get("task_payload"))
        if isinstance(task, dict):
            tasks[row["id"]] = task
    _apply_payload(runs, tasks)
    return True


def _load() -> None:
    """启动时从数据库读回历史。库是空的时候，把旧 JSON 导入后再读。"""

    try:
        if _load_mysql():
            return
        _load_file()
        if _runs or _tasks:
            _persist()
    except Exception:
        _load_file()


def _persist() -> None:
    try:
        from ..data.mysql_source import _connect, _dump

        conn = _connect()
        try:
            with conn.cursor() as cur:
                _ensure_columns(cur)
                for run_id, entry in _runs.items():
                    task = _tasks.get(run_id)
                    cur.execute(
                        """
                        INSERT INTO agent_runs (id, intent, tools_used, status, payload, task_payload)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                          intent=VALUES(intent), tools_used=VALUES(tools_used), status=VALUES(status),
                          payload=VALUES(payload), task_payload=VALUES(task_payload)
                        """,
                        (
                            str(run_id)[:32],
                            str(entry.get("intent") or "")[:32] or None,
                            str(entry.get("tools_used") or "")[:255] or None,
                            str(entry.get("status") or "")[:16] or None,
                            _dump(entry),
                            _dump(task) if task else None,
                        ),
                    )
                if _runs:
                    placeholders = ",".join(["%s"] * len(_runs))
                    cur.execute(
                        f"DELETE FROM agent_runs WHERE id NOT IN ({placeholders})",
                        tuple(str(run_id)[:32] for run_id in _runs),
                    )
        finally:
            conn.close()
    except Exception:
        _persist_file()


def cleanup_expired_tasks(now: datetime | None = None) -> list[str]:
    """删除超过 30 分钟仍未恢复的审批快照，并标记对应运行为过期。"""
    current = now or _now()
    removed: list[str] = []
    with _lock:
        for run_id, snapshot in list(_tasks.items()):
            saved_at = _parse_time(snapshot.get("saved_at"))
            if saved_at and current - saved_at > _TASK_TTL:
                _tasks.pop(run_id, None)
                entry = _runs.setdefault(run_id, {"created_at": saved_at.isoformat()})
                entry["status"] = "expired"
                entry["updated_at"] = current.isoformat()
                removed.append(run_id)
        if removed:
            _persist()
    return removed


def cancel_run(run_id: str) -> bool:
    with _lock:
        entry = _runs.setdefault(run_id, {"created_at": datetime.now(timezone.utc).isoformat()})
        entry["status"] = "cancelled"
        entry["updated_at"] = _now().isoformat()
        _persist()
    return True


def pause_run(run_id: str) -> bool:
    with _lock:
        entry = _runs.setdefault(run_id, {"created_at": datetime.now(timezone.utc).isoformat()})
        entry["status"] = "paused"
        entry["updated_at"] = _now().isoformat()
        _persist()
    return True


def decide_run(run_id: str, decision: str, reason: str) -> dict[str, object]:
    """记录人工通过或驳回。驳回后清除快照，恢复接口不能再执行。"""
    if decision not in {"approve", "reject"}:
        raise ValueError("decision 只能是 approve 或 reject")
    with _lock:
        entry = _runs.setdefault(run_id, {"created_at": _now().isoformat()})
        entry["decision"] = decision
        entry["decision_reason"] = reason.strip()
        entry["status"] = "approved" if decision == "approve" else "rejected"
        entry["updated_at"] = _now().isoformat()
        if decision == "reject":
            _tasks.pop(run_id, None)
        _persist()
        return {"run_id": run_id, **entry}


def resume_run(run_id: str) -> bool:
    with _lock:
        entry = _runs.setdefault(run_id, {"created_at": datetime.now(timezone.utc).isoformat()})
        entry["status"] = "running"
        entry["updated_at"] = _now().isoformat()
        _persist()
    return True


def is_cancelled(run_id: str | None) -> bool:
    return bool(run_id) and _runs.get(run_id, {}).get("status") == "cancelled"


def is_paused(run_id: str | None) -> bool:
    return bool(run_id) and _runs.get(run_id, {}).get("status") == "paused"


def set_run_status(run_id: str, status: str) -> None:
    with _lock:
        entry = _runs.setdefault(run_id, {"created_at": datetime.now(timezone.utc).isoformat()})
        entry["status"] = status
        entry["updated_at"] = _now().isoformat()
        _persist()


def run_status(run_id: str) -> dict[str, object]:
    with _lock:
        return {"run_id": run_id, **_runs.get(run_id, {"status": "unknown"})}


def list_runs(limit: int = 50) -> list[dict[str, object]]:
    """返回最近的 Agent 运行摘要，并先清掉过期审批任务。"""
    cleanup_expired_tasks()
    with _lock:
        items = [{"run_id": run_id, **entry} for run_id, entry in _runs.items()]
    return list(reversed(items[-max(1, min(limit, 100)) :]))


def save_task_snapshot(run_id: str, snapshot: dict[str, object]) -> None:
    """保存可恢复任务的最小请求快照；当前仅存在进程内。"""
    with _lock:
        _tasks[run_id] = {**snapshot, "run_id": run_id, "saved_at": _now().isoformat()}
        _persist()


def task_snapshot(run_id: str) -> dict[str, object] | None:
    cleanup_expired_tasks()
    with _lock:
        snapshot = _tasks.get(run_id)
        return dict(snapshot) if snapshot else None


def clear_task_snapshot(run_id: str) -> None:
    with _lock:
        _tasks.pop(run_id, None)
        _persist()


_load()

