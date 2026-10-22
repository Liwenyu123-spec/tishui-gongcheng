"""进程内 Agent 运行控制；重启后状态清空。"""

from threading import Lock

_runs: dict[str, dict[str, object]] = {}
_lock = Lock()


def cancel_run(run_id: str) -> bool:
    with _lock:
        _runs.setdefault(run_id, {})["status"] = "cancelled"
    return True


def is_cancelled(run_id: str | None) -> bool:
    return bool(run_id) and _runs.get(run_id, {}).get("status") == "cancelled"


def set_run_status(run_id: str, status: str) -> None:
    with _lock:
        _runs.setdefault(run_id, {})["status"] = status


def run_status(run_id: str) -> dict[str, object]:
    with _lock:
        return {"run_id": run_id, **_runs.get(run_id, {"status": "unknown"})}
