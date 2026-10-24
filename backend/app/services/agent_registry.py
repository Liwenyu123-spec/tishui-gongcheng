"""进程内专业 Agent 注册目录；当前只读，后续可接配置持久化。"""

from ..agent.workflow import _AGENT_ROLES, _AGENT_TOOL_NAMES
from threading import Lock

_CUSTOM_AGENTS: dict[str, dict[str, object]] = {}
_LOCK = Lock()


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
