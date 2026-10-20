"""基于已过滤检索片段的规程说明生成。

对照 chroma 文档管理项目的 /ask：先检索，再把片段交给 DeepSeek。
数值、告警和拓扑仍由只读工具计算，模型不得编造测点。
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

from dataclasses import dataclass, replace
from threading import Lock
from uuid import uuid4

from .knowledge_search import KnowledgeHit, _terms, search_rules
from .runtime_env import load_env_file, windows_env

_STATION_ALIASES = ("集泉", "一泵站", "二泵站", "三泵站", "四泵站", "平定入口")
_METRIC_WORDS = ("流量", "压力", "水位", "液位", "电流", "下降", "异常", "核查", "规程")


@dataclass
class _AskSession:
    """进程内多轮补问状态；重启后清空。"""

    pending_question: str | None = None
    last_answer: str | None = None
    last_effective_question: str | None = None
    last_station: str | None = None


_SESSIONS: dict[str, _AskSession] = {}
_SESSION_LOCK = Lock()
_FOLLOW_MARKERS = ("那", "呢", "还", "再", "同上", "继续", "另外", "还有")


def _load_env_file() -> None:
    """读取项目根目录 .env。实际逻辑在 runtime_env，这里保留旧名兼容调用方。"""

    load_env_file()


def _windows_env(name: str) -> str:
    """对照 chroma 文档管理：进程环境、.env、用户变量、系统变量。"""

    return windows_env(name)


def _deepseek_api_key() -> str:
    """优先读 DEEPSEEK_API_KEY，其次兼容 DEEPSEEKAPIKEY。"""

    return _windows_env("DEEPSEEK_API_KEY") or _windows_env("DEEPSEEKAPIKEY")


_load_env_file()

REWRITE_PROMPT = (
    "你是提水工程知识库的检索改写助手。"
    "把用户问题改写成更适合检索调度规程的一句中文。"
    "只输出改写后的问句，不要解释，不要引号。"
    "保留泵站、流量、压力、水位、电流、核查等关键词，去掉客套话。"
    "不要编造规程名称，不要写出实时数字或开关泵指令。"
)

_FILLERS = ("嗯", "啊", "那个", "这个", "帮我看看", "帮我查一下", "请问一下", "请问", "麻烦", "一下")
_TERM_MAP = {
    "水泵": "泵站",
    "掉下去": "下降",
    "掉了": "下降",
    "怎么查": "如何核查",
    "咋查": "如何核查",
    "先看啥": "先核查什么",
}


def clean_query(text: str) -> str:
    """去掉口语填充并把常见说法换成规程用词。"""

    query = (text or "").strip()
    for filler in _FILLERS:
        query = query.replace(filler, " ")
    for src, dst in _TERM_MAP.items():
        query = query.replace(src, dst)
    query = re.sub(r"[?？!！。.~～…]+", " ", query)
    query = re.sub(r"\s+", " ", query).strip()
    return query or (text or "").strip()


SYSTEM_PROMPT = (
    "你是提水工程调度平台的规程助手。"
    "只能根据用户问题和给出的资料片段作答，用简体中文。"
    "必须标明引用了哪份资料的标题和版本。"
    "不要编造流量、压力、水位等实时数字，也不要给出泵组或阀门操作指令。"
    "资料不足以回答时，明确说资料不足，并列出还缺什么。"
)


def generation_status() -> dict[str, Any]:
    enabled = os.getenv("RAG_GENERATION_ENABLED", "1").strip().lower() not in {"0", "false", "off", "none"}
    key = _deepseek_api_key()
    model = _windows_env("DEEPSEEK_MODEL") or "deepseek-chat"
    return {
        "generation": "deepseek" if enabled and key else "disabled",
        "generation_model": model if enabled else None,
        "generation_ready": bool(enabled and key),
        "generation_error": None if (enabled and key) else ("未配置 DEEPSEEK_API_KEY" if enabled else "生成已关闭"),
    }


def _has_station(text: str, station_id: str | None = None) -> bool:
    if station_id:
        return True
    return any(alias in (text or "") for alias in _STATION_ALIASES)


def _extract_station(text: str) -> str | None:
    for alias in _STATION_ALIASES:
        if alias in (text or ""):
            return alias
    return None


def _needs_station(text: str) -> bool:
    """提到测点或核查，但没写泵站时，先补问站点。"""

    if not any(word in (text or "") for word in _METRIC_WORDS):
        return False
    return not _has_station(text)


def _looks_like_station_reply(text: str) -> bool:
    """短回复只含站点名时，视为对上一轮补问的回答。"""

    cleaned = clean_query(text)
    if not cleaned:
        return False
    if any(alias == cleaned or cleaned.endswith(alias) or alias in cleaned for alias in _STATION_ALIASES):
        # 「二泵站」或「就二泵站吧」这类短补充
        return len(cleaned) <= 12 or cleaned in _STATION_ALIASES
    return False


def _is_elliptical_follow_up(text: str) -> bool:
    """短句追问：缺主语站点，或带「那/呢」等省略标记。"""

    cleaned = clean_query(text)
    if not cleaned or _looks_like_station_reply(cleaned):
        return False
    if any(marker in cleaned for marker in _FOLLOW_MARKERS) and len(cleaned) <= 24:
        return True
    # 「电流呢」「压力怎么查」这类短追问
    if len(cleaned) <= 16 and any(word in cleaned for word in _METRIC_WORDS) and not _has_station(cleaned):
        return True
    return False


def _expand_follow_up(follow_up: str, *, last_question: str, last_station: str | None) -> str:
    """把省略追问拼成可检索的完整问句，不依赖模型。"""

    station = last_station or _extract_station(last_question) or ""
    topic = clean_query(follow_up)
    for marker in _FOLLOW_MARKERS:
        topic = topic.replace(marker, " ")
    topic = re.sub(r"\s+", " ", topic).strip(" ，,") or clean_query(follow_up)
    if station and station not in topic:
        return f"{station}{topic}按规程如何核查"
    if last_question:
        return f"{last_question}；补充追问：{topic}"
    return topic


def _get_session(session_id: str | None) -> tuple[str, _AskSession]:
    sid = (session_id or "").strip() or f"ask-{uuid4().hex[:12]}"
    with _SESSION_LOCK:
        session = _SESSIONS.get(sid)
        if session is None:
            session = _AskSession()
            _SESSIONS[sid] = session
        return sid, session


def resolve_follow_up(question: str, *, session_id: str | None = None, station_id: str | None = None) -> dict[str, Any]:
    """合并补问与省略追问。返回有效问句，或 needs_clarification 提示。"""

    sid, session = _get_session(session_id)
    raw = (question or "").strip()
    effective = raw
    merged = False
    if session.pending_question and (_looks_like_station_reply(raw) or (_has_station(raw) and len(raw) <= 20)):
        effective = f"{session.pending_question}（站点：{raw}）"
        session.pending_question = None
        merged = True
    elif session.last_effective_question and _is_elliptical_follow_up(raw):
        effective = _expand_follow_up(
            raw,
            last_question=session.last_effective_question,
            last_station=session.last_station,
        )
        session.pending_question = None
        merged = True
    elif _needs_station(raw) and not station_id:
        # 同会话已有泵站时，直接带上，避免重复补问。
        known_station = session.last_station or _extract_station(session.last_effective_question or "")
        if known_station:
            effective = f"{known_station}{raw}"
            session.pending_question = None
            merged = True
        else:
            session.pending_question = raw
            return {
                "session_id": sid,
                "question": raw,
                "effective_question": raw,
                "needs_clarification": True,
                "clarification": "请补充要核查的泵站，例如二泵站，或直接回复站点名称继续。",
                "answer": "请补充要核查的泵站，例如二泵站，或直接回复站点名称继续。",
                "merged": False,
                "sources": [],
                "compression": {"enabled": False, "chars_before": 0, "chars_after": 0, "reduced": 0},
                "generation": "clarify",
                "rewritten_query": "",
            }
    else:
        session.pending_question = None
    station = _extract_station(effective) or session.last_station
    if station:
        session.last_station = station
    # 成功进入检索前就记住本轮有效问句，便于下一轮省略追问。
    session.last_effective_question = effective
    return {
        "session_id": sid,
        "question": raw,
        "effective_question": effective,
        "needs_clarification": False,
        "clarification": "",
        "merged": merged,
    }


def ask_with_retrieval(
    question: str,
    *,
    k: int = 5,
    station_id: str | None = None,
    visible_station_ids: set[str] | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """检索现行有效资料后生成说明。没有密钥或没有可用片段时不调用模型。"""

    status = generation_status()
    turn = resolve_follow_up(question, session_id=session_id, station_id=station_id)
    if turn.get("needs_clarification"):
        # 补问阶段不调用模型；保留 clarify，同时带回密钥是否可用。
        return {**status, **turn}
    sid = str(turn["session_id"])
    effective = str(turn["effective_question"])
    cleaned = clean_query(effective)
    rewritten = cleaned
    if status["generation_ready"]:
        rewritten = _rewrite_query(cleaned) or cleaned
    hits = _search_queries(
        [effective, cleaned, rewritten],
        k=k,
        station_id=station_id,
        visible_station_ids=visible_station_ids,
    )
    if not hits:
        with _SESSION_LOCK:
            session = _SESSIONS.setdefault(sid, _AskSession())
            session.pending_question = effective
        return {
            **status,
            "session_id": sid,
            "question": question,
            "effective_question": effective,
            "rewritten_query": rewritten,
            "merged": bool(turn.get("merged")),
            "needs_clarification": True,
            "clarification": "当前没有可引用的现行资料。请补充资料关键词，或先导入并批准相关规程后再继续。",
            "answer": "当前没有可引用的现行资料。请补充资料关键词，或先导入并批准相关规程后再继续。",
            "sources": [],
            "compression": {"enabled": False, "chars_before": 0, "chars_after": 0, "reduced": 0},
            "retrieval_gate": {"passed": False, "min_score": ask_min_score(), "top_score": 0},
            "generation": "clarify",
        }
    strong_hits, gate = select_strong_hits(hits)
    if not strong_hits:
        with _SESSION_LOCK:
            session = _SESSIONS.setdefault(sid, _AskSession())
            session.pending_question = effective
        message = (
            f"检索相关度偏低（最高 {gate['top_score']}，门槛 {gate['min_score']}）。"
            "请补充泵站、指标或规程关键词后再问，勿依据弱相关片段作答。"
        )
        return {
            **status,
            "session_id": sid,
            "question": question,
            "effective_question": effective,
            "rewritten_query": rewritten,
            "merged": bool(turn.get("merged")),
            "needs_clarification": True,
            "clarification": message,
            "answer": message,
            "sources": [_hit_payload(hit) for hit in hits[:3]],
            "compression": {"enabled": False, "chars_before": 0, "chars_after": 0, "reduced": 0},
            "retrieval_gate": gate,
            "generation": "abstain",
        }
    if not status["generation_ready"]:
        raise RuntimeError(status["generation_error"] or "生成问答不可用")
    # 对照参考项目的句级压缩：只把和问句相关的句子送给模型。
    compressed_hits, compress_stats = compress_hits(strong_hits, rewritten or cleaned or effective)
    answer = _complete(effective, compressed_hits)
    groundedness = check_groundedness(answer, compressed_hits)
    if not groundedness["grounded"]:
        answer = (
            f"{answer}\n\n【忠实度提示】本轮说明与检索资料重合偏低或含资料外数字/操作用语，"
            "请以引用原文为准，勿直接作为操作依据。"
        )
    with _SESSION_LOCK:
        session = _SESSIONS.setdefault(sid, _AskSession())
        session.pending_question = None
        session.last_answer = answer
        session.last_effective_question = effective
        session.last_station = _extract_station(effective) or session.last_station
    return {
        "session_id": sid,
        "question": question,
        "effective_question": effective,
        "rewritten_query": rewritten,
        "merged": bool(turn.get("merged")),
        "needs_clarification": False,
        "clarification": "",
        "answer": answer,
        "sources": [_hit_payload(hit) for hit in compressed_hits],
        "compression": compress_stats,
        "groundedness": groundedness,
        "retrieval_gate": {**gate, "passed": True},
        "generation": "deepseek",
        **status,
    }


def ask_min_score() -> int:
    """生成问答最低相关度；低于此分不调用模型。可用 RAG_ASK_MIN_SCORE 调整。"""

    raw = os.getenv("RAG_ASK_MIN_SCORE", "8").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 8


def select_strong_hits(hits: list[KnowledgeHit], *, min_score: int | None = None) -> tuple[list[KnowledgeHit], dict[str, Any]]:
    """按相关度门槛筛出可送给模型的命中。"""

    threshold = ask_min_score() if min_score is None else max(0, min_score)
    top_score = max((hit.score for hit in hits), default=0)
    strong = [hit for hit in hits if hit.score >= threshold]
    return strong, {
        "passed": bool(strong),
        "min_score": threshold,
        "top_score": top_score,
        "kept": len(strong),
        "total": len(hits),
    }


def check_groundedness(answer: str, hits: list[KnowledgeHit]) -> dict[str, Any]:
    """本地校验：回答是否主要落在检索资料上，并拦截资料外数字与操作用语。"""

    text = (answer or "").strip()
    if not text:
        return {
            "grounded": False,
            "overlap": 0.0,
            "cited_titles": [],
            "warnings": ["空回答"],
            "status": "ungrounded",
        }
    if "资料不足" in text:
        return {
            "grounded": True,
            "overlap": 1.0,
            "cited_titles": [],
            "warnings": [],
            "status": "abstain",
        }

    evidence = "\n".join(f"{hit.title}\n{hit.detail}" for hit in hits)
    evidence_terms = set(_terms(evidence))
    answer_terms = set(_terms(text))
    overlap = (len(answer_terms & evidence_terms) / len(answer_terms)) if answer_terms else 0.0

    cited_titles: list[str] = []
    for hit in hits:
        title_core = re.sub(r"\s+\d+(?:\.\d+)*\s*$", "", hit.title or "").strip() or (hit.title or "")
        if title_core and title_core in text:
            cited_titles.append(hit.title)

    warnings: list[str] = []
    evidence_nums = set(re.findall(r"\d+(?:\.\d+)?", evidence))
    answer_nums = set(re.findall(r"\d+(?:\.\d+)?", text))
    invented = sorted(num for num in answer_nums if num not in evidence_nums and len(num) >= 2)
    if invented:
        warnings.append(f"回答中出现资料未给出的数字：{', '.join(invented[:5])}")
    for word in ("启动泵", "停泵", "开阀", "关阀", "下发指令"):
        if word in text:
            warnings.append(f"回答含操作指令用语：{word}")

    grounded = overlap >= 0.2 or (bool(cited_titles) and overlap >= 0.12)
    if invented or any("操作指令" in item for item in warnings):
        grounded = False
    return {
        "grounded": grounded,
        "overlap": round(overlap, 3),
        "cited_titles": cited_titles,
        "warnings": warnings,
        "status": "grounded" if grounded else "ungrounded",
    }


def _search_queries(
    queries: list[str],
    *,
    k: int,
    station_id: str | None,
    visible_station_ids: set[str] | None,
) -> list[KnowledgeHit]:
    """用原问句和改写问句各检索一次，按资料编号合并，保留更高分。"""

    merged: dict[str, KnowledgeHit] = {}
    for query in dict.fromkeys(item.strip() for item in queries if item and item.strip()):
        for hit in search_rules(
            query,
            limit=k,
            station_id=station_id,
            visible_station_ids=visible_station_ids,
        ):
            if hit.confidence == "low":
                continue
            current = merged.get(hit.source_id)
            if current is None or hit.score > current.score:
                merged[hit.source_id] = hit
    return sorted(merged.values(), key=lambda item: (-item.score, item.source_id))[:k]


def _hit_payload(hit: KnowledgeHit) -> dict[str, Any]:
    return {
        "source_id": hit.source_id,
        "title": hit.title,
        "version": hit.version,
        "filename": hit.filename,
        "location": hit.location,
        "category": hit.category,
        "detail": hit.detail,
        "score": hit.score,
        "confidence": hit.confidence,
    }


def _split_sentences(text: str) -> list[str]:
    """按中英文句末标点和空行切句，对齐参考项目的中文切句。"""

    parts = re.split(r"(?<=[。！？；.!?;])\s*|\n+", text or "")
    return [item.strip() for item in parts if item.strip()]


def compress_detail(query: str, detail: str, *, keep_ratio: float = 0.6) -> str:
    """按与问句的词重合保留相关句子；短文本不压缩。"""

    sentences = _split_sentences(detail)
    if len(sentences) <= 1:
        return (detail or "").strip()
    query_terms = set(_terms(query))
    if not query_terms:
        return (detail or "").strip()
    scored: list[tuple[int, int, str]] = []
    for index, sentence in enumerate(sentences):
        overlap = len(query_terms.intersection(_terms(sentence)))
        scored.append((overlap, index, sentence))
    scored.sort(key=lambda item: (-item[0], item[1]))
    keep_count = max(1, min(len(sentences), round(len(sentences) * keep_ratio)))
    # 至少保留有重合的句子；若全无重合则保留原文前几句，避免空上下文。
    selected = [item for item in scored if item[0] > 0][:keep_count] or scored[:keep_count]
    selected.sort(key=lambda item: item[1])
    return "".join(item[2] if item[2].endswith(("。", "！", "？", "；", ".", "!", "?", ";")) else f"{item[2]}。" for item in selected)


def compress_hits(hits: list[KnowledgeHit], query: str) -> tuple[list[KnowledgeHit], dict[str, Any]]:
    """压缩命中摘要，返回压缩后的命中和前后字数统计。"""

    before = sum(len(hit.detail or "") for hit in hits)
    compressed = [replace(hit, detail=compress_detail(query, hit.detail)) for hit in hits]
    after = sum(len(hit.detail or "") for hit in compressed)
    return compressed, {
        "enabled": True,
        "chars_before": before,
        "chars_after": after,
        "reduced": max(0, before - after),
    }


def _rewrite_query(query: str) -> str:
    text = _chat(
        [{"role": "system", "content": REWRITE_PROMPT}, {"role": "user", "content": f"用户问题：{query}\n改写："}],
        temperature=0,
    )
    rewritten = (text or "").splitlines()[0].strip().strip("\"“”")
    return rewritten if rewritten and rewritten != query else query


def _complete(question: str, hits: list[KnowledgeHit]) -> str:
    context = "\n\n".join(
        f"[{index}] {hit.title}（{hit.location}）\n{hit.detail}" for index, hit in enumerate(hits, start=1)
    )
    content = _chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"问题：{question}\n\n资料片段：\n{context}"},
        ],
        temperature=0.2,
    )
    if not content:
        raise RuntimeError("DeepSeek 没有返回说明文本")
    return content


def _chat(messages: list[dict[str, str]], *, temperature: float) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("未安装 openai，无法调用 DeepSeek") from exc
    client = OpenAI(
        api_key=_deepseek_api_key(),
        base_url=_windows_env("DEEPSEEK_BASE_URL") or "https://api.deepseek.com",
    )
    model = _windows_env("DEEPSEEK_MODEL") or "deepseek-chat"
    response = client.chat.completions.create(model=model, temperature=temperature, messages=messages)
    return (response.choices[0].message.content or "").strip()
