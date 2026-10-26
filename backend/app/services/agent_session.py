"""Agent 多轮问答的会话记忆。

会话保存最近问句和站点上下文，不保存完整工具结果。
记录写入 MySQL `conversations`。会话键包含用户身份，避免不同账号串用。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from uuid import uuid4

from ..schemas.agent import AgentChatRequest


_STATION_ALIASES = {
    "集泉二站": "jq-02",
    "集泉一站": "jq-01",
    "集泉": "jq-01",
    "上庄倒虹": "sz-invert",
    "上庄": "sz-invert",
    "一泵站": "pump-01",
    "二泵站": "pump-02",
    "三泵站": "pump-03",
    "四泵站": "pump-04",
    "平定侧入口": "pingding-inlet",
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
    last_conclusion: str = ""
    pending_items: list[str] = None  # type: ignore[assignment]
    touched_at: float = 0.0


_SESSIONS: dict[str, _AgentSession] = {}
_SESSION_LOCK = Lock()


def _session_row_id(key: str) -> str:
    import hashlib

    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def _session_payload(session: _AgentSession) -> dict:
    return {
        "last_question": session.last_question,
        "recent_questions": list(session.recent_questions or []),
        "last_station_id": session.last_station_id,
        "last_station_label": session.last_station_label,
        "last_conclusion": session.last_conclusion,
        "pending_items": list(session.pending_items or []),
    }


def _load_session(key: str) -> _AgentSession | None:
    try:
        from ..data.mysql_source import _connect, _load_json

        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM conversations WHERE id=%s", (_session_row_id(key),))
                row = cur.fetchone()
        finally:
            conn.close()
    except Exception:
        return None
    if not row:
        return None
    payload = _load_json(row.get("payload")) or {}
    if not isinstance(payload, dict):
        return None
    return _AgentSession(
        last_question=str(payload.get("last_question") or ""),
        recent_questions=list(payload.get("recent_questions") or []),
        last_station_id=payload.get("last_station_id"),
        last_station_label=payload.get("last_station_label"),
        last_conclusion=str(payload.get("last_conclusion") or ""),
        pending_items=list(payload.get("pending_items") or []),
        touched_at=monotonic(),
    )


def _save_session(key: str, session: _AgentSession) -> None:
    try:
        from datetime import datetime, timezone

        from ..data.mysql_source import _connect, _dump

        user_id = key.split(":", 1)[0][:32]
        conn = _connect()
        try:
            with conn.cursor() as cur:
                try:
                    cur.execute("ALTER TABLE conversations ADD COLUMN payload JSON NULL")
                except Exception as exc:
                    if "Duplicate column" not in str(exc):
                        raise
                cur.execute(
                    """
                    INSERT INTO conversations (id, user_id, created_at, title, payload)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE title=VALUES(title), payload=VALUES(payload)
                    """,
                    (
                        _session_row_id(key),
                        user_id,
                        datetime.now(timezone.utc).replace(tzinfo=None),
                        (session.last_station_label or "调度问答")[:128],
                        _dump(_session_payload(session)),
                    ),
                )
        finally:
            conn.close()
    except Exception:
        return


def _session_id(value: str | None) -> str:
    return (value or "").strip() or f"agent-{uuid4().hex[:12]}"


def _contains_station(text: str) -> tuple[str | None, str | None]:
    for label, station_id in sorted(_STATION_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
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
        if key not in _SESSIONS:
            loaded = _load_session(key)
            if loaded is not None:
                _SESSIONS[key] = loaded
        session = _SESSIONS.setdefault(key, _AgentSession(recent_questions=[], pending_items=[]))
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
        _save_session(key, session)

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
            loaded = _load_session(key)
            if loaded is None:
                return {"session_id": session_id, "question_count": 0, "summary": "", "recent_questions": [], "pending_items": []}
            _SESSIONS[key] = session = loaded
        recent = list(session.recent_questions)
        pending = list(session.pending_items or [])
        station = session.last_station_label or session.last_station_id or "未指定站点"
        conclusion = session.last_conclusion or "；".join(recent[-2:])
        summary = f"站点：{station}。最近结论：{conclusion}"
        if pending:
            summary += "。待确认：" + "；".join(pending[:3])
        return {
            "session_id": session_id,
            "question_count": len(recent),
            "summary": summary,
            "recent_questions": recent,
            "station_id": session.last_station_id,
            "pending_items": pending,
        }


def remember_outcome(session_id: str, user: dict, *, conclusion: str, station_id: str | None, pending_items: list[str]) -> None:
    """记下本轮结论、站点和待确认项，供下一轮摘要使用。"""
    user_key = str(user.get("id") or user.get("username") or "anonymous")
    key = f"{user_key}:{session_id.strip()}"
    with _SESSION_LOCK:
        session = _SESSIONS.get(key)
        if session is None:
            return
        session.last_conclusion = (conclusion or "").strip()[:240]
        session.pending_items = list(pending_items[:5])
        if station_id:
            session.last_station_id = station_id
        _save_session(key, session)
