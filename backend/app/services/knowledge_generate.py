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

_STATION_ALIASES = ("集泉", "一泵站", "二泵站", "三泵站", "四泵站", "平定入口")
_METRIC_WORDS = ("流量", "压力", "水位", "液位", "电流", "下降", "异常", "核查", "规程")


@dataclass
class _AskSession:
    """进程内多轮补问状态；重启后清空。"""

    pending_question: str | None = None
    last_answer: str | None = None


_SESSIONS: dict[str, _AskSession] = {}
_SESSION_LOCK = Lock()


def _load_env_file() -> None:
    """读取项目根目录 .env。进程里已有的变量不覆盖。"""

    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _windows_env(name: str) -> str:
    """对照 chroma 文档管理：进程环境、.env、用户变量、系统变量。"""

    value = os.getenv(name, "").strip()
    if value:
        return value
    if sys.platform != "win32":
        return ""
    try:
        import winreg
    except ImportError:
        return ""
    for root, path in (
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    ):
        try:
            with winreg.OpenKey(root, path) as key:
                found, _ = winreg.QueryValueEx(key, name)
        except OSError:
            continue
        text = str(found or "").strip()
        if text:
            return text
    return ""


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


def ask_with_retrieval(
    question: str,
    *,
    k: int = 5,
    station_id: str | None = None,
    visible_station_ids: set[str] | None = None,
) -> dict[str, Any]:
    """检索现行有效资料后生成说明。没有密钥或没有可用片段时不调用模型。"""

    status = generation_status()
    cleaned = clean_query(question)
    rewritten = cleaned
    if status["generation_ready"]:
        rewritten = _rewrite_query(cleaned) or cleaned
    hits = _search_queries(
        [question, cleaned, rewritten],
        k=k,
        station_id=station_id,
        visible_station_ids=visible_station_ids,
    )
    if not hits:
        return {
            "question": question,
            "rewritten_query": rewritten,
            "answer": "当前没有可引用的现行资料，无法生成说明。请先导入并批准相关规程。",
            "sources": [],
            "compression": {"enabled": False, "chars_before": 0, "chars_after": 0, "reduced": 0},
            "generation": "skipped",
            **status,
        }
    if not status["generation_ready"]:
        raise RuntimeError(status["generation_error"] or "生成问答不可用")
    # 对照参考项目的句级压缩：只把和问句相关的句子送给模型。
    compressed_hits, compress_stats = compress_hits(hits, rewritten or cleaned or question)
    answer = _complete(question, compressed_hits)
    return {
        "question": question,
        "rewritten_query": rewritten,
        "answer": answer,
        "sources": [_hit_payload(hit) for hit in compressed_hits],
        "compression": compress_stats,
        "generation": "deepseek",
        **status,
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
