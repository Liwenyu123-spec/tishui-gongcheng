"""进程启动阶段状态。

启动状态只保存在内存中，用于让本地开发和单地址模式区分「接口已经启动」
与「RAG 模型仍在后台准备」。它不保存业务数据，也不依赖数据库。
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any


_LOCK = Lock()
_STATE: dict[str, Any] = {
    "status": "not_started",
    "mode": None,
    "phase": "idle",
    "message": "启动任务尚未开始",
    "started_at": None,
    "finished_at": None,
    "elapsed_seconds": None,
    "error": None,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def startup_status() -> dict[str, Any]:
    """返回启动阶段的快照，避免调用方直接读取可变全局状态。"""

    with _LOCK:
        return dict(_STATE)


def mark_starting(mode: str) -> None:
    with _LOCK:
        _STATE.update(
            {
                "status": "starting",
                "mode": mode,
                "phase": "initializing",
                "message": "正在准备 RAG 模型和知识索引",
                "started_at": _now(),
                "finished_at": None,
                "elapsed_seconds": None,
                "error": None,
            }
        )


def mark_phase(phase: str, message: str) -> None:
    with _LOCK:
        _STATE.update({"phase": phase, "message": message})


def mark_finished(*, elapsed_seconds: float, degraded: bool, message: str) -> None:
    with _LOCK:
        _STATE.update(
            {
                "status": "degraded" if degraded else "ready",
                "phase": "completed",
                "message": message,
                "finished_at": _now(),
                "elapsed_seconds": round(elapsed_seconds, 2),
                "error": None,
            }
        )


def mark_failed(*, elapsed_seconds: float, error: str) -> None:
    with _LOCK:
        _STATE.update(
            {
                "status": "failed",
                "phase": "failed",
                "message": "RAG 启动准备失败，普通接口仍可使用",
                "finished_at": _now(),
                "elapsed_seconds": round(elapsed_seconds, 2),
                "error": error,
            }
        )
