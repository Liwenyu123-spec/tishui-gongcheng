"""进程内 Agent 运行控制；重启后状态清空。"""

from threading import Lock
from datetime import datetime, timezone

_runs: dict[str, dict[str, object]] = {}
_lock = Lock()


def cancel_run(run_id: str) -> bool:
    with _lock:
        entry = _runs.setdefault(run_id, {"created_at": datetime.now(timezone.utc).isoformat()})
        entry["status"] = "cancelled"
        entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    return True


def is_cancelled(run_id: str | None) -> bool:
    return bool(run_id) and _runs.get(run_id, {}).get("status") == "cancelled"


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
