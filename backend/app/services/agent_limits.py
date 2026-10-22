"""Agent 运行限额和进程内并发控制。

本阶段只做单进程治理，不依赖数据库、Redis 或部署组件。
"""

from __future__ import annotations

from contextlib import contextmanager
from threading import BoundedSemaphore

from .runtime_env import windows_env


def _int_env(name: str, default: int, minimum: int = 1, maximum: int = 1000) -> int:
    """读取整数配置并限制在安全范围内；非法值回退到默认值。"""
    try:
        value = int(windows_env(name) or str(default))
    except ValueError:
        value = default
    return min(max(value, minimum), maximum)


def max_tool_calls() -> int:
    """返回一次 Agent 请求允许执行的最大工具数。"""
    return _int_env("AGENT_MAX_TOOL_CALLS", 8, 1, 100)


def max_model_calls() -> int:
    """返回一次 Agent 请求允许使用的模型调用预算。"""
    return _int_env("AGENT_MAX_MODEL_CALLS", 3, 0, 100)


def max_concurrency() -> int:
    """返回单个后端进程允许同时运行的 Agent 请求数。"""
    return _int_env("AGENT_MAX_CONCURRENCY", 4, 1, 100)


_CONCURRENCY_LIMIT = max_concurrency()
# 信号量在模块加载时建立，因此本进程启动后固定并发容量；修改配置需重启后端。
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
    """返回当前配置，便于健康检查、调试接口或日志展示。"""
    return {
        "max_tool_calls": max_tool_calls(),
        "max_model_calls": max_model_calls(),
        "max_concurrency": max_concurrency(),
    }
