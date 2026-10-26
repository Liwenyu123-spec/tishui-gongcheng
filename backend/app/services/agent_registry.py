"""专业 Agent 注册目录。自定义 Agent 写入本地 JSON，重启后仍可参加协作。"""

import json
from pathlib import Path
from threading import Lock

from ..agent.workflow import _AGENT_ROLES, _AGENT_TOOL_NAMES

_STORE = Path(__file__).resolve().parents[2] / "data" / "agent_registry.json"
_CUSTOM_AGENTS: dict[str, dict[str, object]] = {}
_LOCK = Lock()


def _load() -> None:
    if not _STORE.exists():
        return
    try:
        payload = json.loads(_STORE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if isinstance(payload, dict):
        for name, item in payload.items():
            if isinstance(item, dict):
                _CUSTOM_AGENTS[str(name)] = item


def _persist() -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    _STORE.write_text(json.dumps(_CUSTOM_AGENTS, ensure_ascii=False, indent=2), encoding="utf-8")


def list_registered_agents() -> list[dict[str, object]]:
    builtins = [
        {
            "name": name,
            "role": role,
            "tool_names": list(_AGENT_TOOL_NAMES.get(name, ())),
            "read_only": True,
        }
        for name, role in _AGENT_ROLES.items()
    ]
    with _LOCK:
        return [*builtins, *[dict(item) for item in _CUSTOM_AGENTS.values()]]


def register_agent(name: str, role: str, tool_names: list[str]) -> dict[str, object]:
    if not name or not role or not tool_names:
        raise ValueError("Agent 名称、职责和工具列表不能为空")
    allowed = set(_AGENT_TOOL_NAMES.values())
    known_tools = {tool for tools in allowed for tool in tools}
    unknown = sorted(set(tool_names) - known_tools)
    if unknown:
        raise ValueError(f"存在未注册工具：{', '.join(unknown)}")
    if name in _AGENT_ROLES:
        raise ValueError("内置 Agent 不允许覆盖")
    item = {"name": name, "role": role, "tool_names": list(dict.fromkeys(tool_names)), "read_only": True, "custom": True}
    with _LOCK:
        _CUSTOM_AGENTS[name] = item
        _persist()
    return dict(item)


def get_registered_agent(name: str) -> dict[str, object] | None:
    if name in _AGENT_ROLES:
        return {
            "name": name,
            "role": _AGENT_ROLES[name],
            "tool_names": list(_AGENT_TOOL_NAMES.get(name, ())),
            "read_only": True,
        }
    with _LOCK:
        item = _CUSTOM_AGENTS.get(name)
        return dict(item) if item else None


_load()
