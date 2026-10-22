"""Agent 运行限额和进程内并发控制。

本阶段只做单进程治理，不依赖数据库、Redis 或部署组件。
"""

from __future__ import annotations

from contextlib import contextmanager
from threading import BoundedSemaphore

from .runtime_env import windows_env


def _int_env(name: str, default: int, minimum: int = 1, maximum: int = 1000) -> int:
    try:
        value = int(windows_env(name) or str(default))
    except ValueError:
        value = default
    return min(max(value, minimum), maximum)


def max_tool_calls() -> int:
    return _int_env("AGENT_MAX_TOOL_CALLS", 8, 1, 100)


def max_model_calls() -> int:
    return _int_env("AGENT_MAX_MODEL_CALLS", 3, 0, 100)


def max_concurrency() -> int:
    return _int_env("AGENT_MAX_CONCURRENCY", 4, 1, 100)


_CONCURRENCY_LIMIT = max_concurrency()
_CONCURRENCY_SEMAPHORE = BoundedSemaphore(_CONCURRENCY_LIMIT)


@contextmanager
def agent_slot():
    """占用一个 Agent 全局并发槽位；超载时由调用方快速失败。"""

    acquired = _CONCURRENCY_SEMAPHORE.acquire(blocking=False)
    if not acquired:
        yield False
        return
    try:
        yield True
    finally:
        _CONCURRENCY_SEMAPHORE.release()


def limits_summary() -> dict[str, int]:
    return {
        "max_tool_calls": max_tool_calls(),
        "max_model_calls": max_model_calls(),
        "max_concurrency": max_concurrency(),
    }
