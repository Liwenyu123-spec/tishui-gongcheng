"""进程内 Agent 运行控制；重启后状态清空。"""

from threading import Lock
from datetime import datetime, timezone

_runs: dict[str, dict[str, object]] = {}
_tasks: dict[str, dict[str, object]] = {}
_lock = Lock()


def cancel_run(run_id: str) -> bool:
    with _lock:
        entry = _runs.setdefault(run_id, {"created_at": datetime.now(timezone.utc).isoformat()})
        entry["status"] = "cancelled"
        entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    return True


def pause_run(run_id: str) -> bool:
    with _lock:
        entry = _runs.setdefault(run_id, {"created_at": datetime.now(timezone.utc).isoformat()})
        entry["status"] = "paused"
        entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    return True


def resume_run(run_id: str) -> bool:
    with _lock:
        entry = _runs.setdefault(run_id, {"created_at": datetime.now(timezone.utc).isoformat()})
        entry["status"] = "running"
        entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    return True


def is_cancelled(run_id: str | None) -> bool:
    return bool(run_id) and _runs.get(run_id, {}).get("status") == "cancelled"


def is_paused(run_id: str | None) -> bool:
    return bool(run_id) and _runs.get(run_id, {}).get("status") == "paused"


def set_run_status(run_id: str, status: str) -> None:
    with _lock:
        entry = _runs.setdefault(run_id, {"created_at": datetime.now(timezone.utc).isoformat()})
        entry["status"] = status
        entry["updated_at"] = datetime.now(timezone.utc).isoformat()


def run_status(run_id: str) -> dict[str, object]:
    with _lock:
        return {"run_id": run_id, **_runs.get(run_id, {"status": "unknown"})}


def list_runs(limit: int = 50) -> list[dict[str, object]]:
    """返回当前进程内最近的 Agent 运行摘要。"""
    with _lock:
        items = [{"run_id": run_id, **entry} for run_id, entry in _runs.items()]
    return list(reversed(items[-max(1, min(limit, 100)) :]))


def save_task_snapshot(run_id: str, snapshot: dict[str, object]) -> None:
    """保存可恢复任务的最小请求快照；当前仅存在进程内。"""
    with _lock:
        _tasks[run_id] = {**snapshot, "run_id": run_id, "saved_at": datetime.now(timezone.utc).isoformat()}


def task_snapshot(run_id: str) -> dict[str, object] | None:
    with _lock:
        snapshot = _tasks.get(run_id)
        return dict(snapshot) if snapshot else None


def clear_task_snapshot(run_id: str) -> None:
    with _lock:
        _tasks.pop(run_id, None)

