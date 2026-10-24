"""Agent 多轮问答的轻量进程内会话记忆。

会话只保存最近一轮有效问句和站点上下文，不保存完整工具结果，也不写入数据库。
会话键包含用户身份，避免同一个 session_id 在不同账号之间串用站点上下文。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from uuid import uuid4

from ..schemas.agent import AgentChatRequest


_STATION_ALIASES = {
    "集泉": "jq-01",
    "一泵站": "pump-01",
    "二泵站": "pump-02",
    "三泵站": "pump-03",
    "四泵站": "pump-04",
    "平定入口": "pingding-inlet",
}
_STATION_LABELS = {station_id: label for label, station_id in _STATION_ALIASES.items()}
_FOLLOW_MARKERS = ("那", "呢", "然后", "另外", "还有", "继续", "这个", "该站")
_METRIC_WORDS = ("流量", "压力", "水位", "能耗", "电流", "状态")
_MAX_SESSIONS = 256


@dataclass
class _AgentSession:
    last_question: str = ""
    recent_questions: list[str] = None  # type: ignore[assignment]
    last_station_id: str | None = None
    last_station_label: str | None = None
    touched_at: float = 0.0


_SESSIONS: dict[str, _AgentSession] = {}
_SESSION_LOCK = Lock()


def _session_id(value: str | None) -> str:
    return (value or "").strip() or f"agent-{uuid4().hex[:12]}"


def _contains_station(text: str) -> tuple[str | None, str | None]:
    for label, station_id in _STATION_ALIASES.items():
        if label in text:
            return station_id, label
    return None, None


def _is_follow_up(text: str) -> bool:
    cleaned = re.sub(r"\s+", "", text or "")
    if not cleaned or len(cleaned) > 24:
        return False
    if any(marker in cleaned for marker in _FOLLOW_MARKERS):
        return True
    return any(metric in cleaned for metric in _METRIC_WORDS) and not _contains_station(cleaned)[0]


def prepare_request(payload: AgentChatRequest, user: dict) -> AgentChatRequest:
    """合并当前账号会话里的短追问，并返回供后续工具统一使用的请求。"""

    sid = _session_id(payload.session_id)
    user_key = str(user.get("id") or user.get("username") or "anonymous")
    key = f"{user_key}:{sid}"
    raw = payload.message.strip()

    with _SESSION_LOCK:
        if key not in _SESSIONS and len(_SESSIONS) >= _MAX_SESSIONS:
            oldest = min(_SESSIONS, key=lambda item: _SESSIONS[item].touched_at)
            _SESSIONS.pop(oldest, None)
        session = _SESSIONS.setdefault(key, _AgentSession(recent_questions=[]))
        effective = raw
        station_id = payload.station_id
        station_label = None
        found_id, found_label = _contains_station(raw)
        if found_id:
            station_id = station_id or found_id
            station_label = found_label
        elif station_id:
            station_label = _STATION_LABELS.get(station_id)

        merged = False
        if session.last_question and _is_follow_up(raw):
            prefix = station_label or session.last_station_label
            if prefix and prefix not in raw:
                topic = raw
                for marker in _FOLLOW_MARKERS:
                    topic = topic.replace(marker, "")
                topic = re.sub(r"\s+", "", topic) or raw
                effective = f"{prefix}{topic}"
            else:
                effective = f"{session.last_question}；补充追问：{raw}"
            merged = True
            station_id = station_id or session.last_station_id
            station_label = station_label or session.last_station_label

        session.last_question = effective
        session.recent_questions = [*session.recent_questions[-4:], effective]
        session.last_station_id = station_id or session.last_station_id
        session.last_station_label = station_label or session.last_station_label
        session.touched_at = monotonic()

    # ``merged`` 仅用于调试/测试；不写入答案正文，避免污染调度员看到的结论。
    _ = merged
    return payload.model_copy(update={"message": effective, "station_id": station_id, "session_id": sid})


def session_summary(session_id: str, user: dict) -> dict[str, object]:
    """返回当前账号会话的短上下文摘要，不暴露其他账号会话。"""
    user_key = str(user.get("id") or user.get("username") or "anonymous")
    key = f"{user_key}:{session_id.strip()}"
    with _SESSION_LOCK:
        session = _SESSIONS.get(key)
        if session is None:
            return {"session_id": session_id, "question_count": 0, "summary": "", "recent_questions": []}
        recent = list(session.recent_questions)
        return {
            "session_id": session_id,
            "question_count": len(recent),
            "summary": "；".join(recent[-3:]),
            "recent_questions": recent,
        }
