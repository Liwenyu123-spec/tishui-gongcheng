"""基于已过滤检索片段的规程说明生成。

对照 chroma 文档管理项目的 /ask：先检索，再把片段交给 DeepSeek。
数值、告警和拓扑仍由只读工具计算，模型不得编造测点。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .knowledge_search import KnowledgeHit, search_rules


def _load_env_file() -> None:
    """读取项目根目录 .env，便于使用 DEEPSEEK_API_KEY。已有环境变量不覆盖。"""

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


_load_env_file()

SYSTEM_PROMPT = (
    "你是提水工程调度平台的规程助手。"
    "只能根据用户问题和给出的资料片段作答，用简体中文。"
    "必须标明引用了哪份资料的标题和版本。"
    "不要编造流量、压力、水位等实时数字，也不要给出泵组或阀门操作指令。"
    "资料不足以回答时，明确说资料不足，并列出还缺什么。"
)


def generation_status() -> dict[str, Any]:
    enabled = os.getenv("RAG_GENERATION_ENABLED", "1").strip().lower() not in {"0", "false", "off", "none"}
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat"
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
    hits = [
        hit
        for hit in search_rules(
            question,
            limit=k,
            station_id=station_id,
            visible_station_ids=visible_station_ids,
        )
        if hit.confidence != "low"
    ]
    sources = [_hit_payload(hit) for hit in hits]
    if not hits:
        return {
            "question": question,
            "answer": "当前没有可引用的现行资料，无法生成说明。请先导入并批准相关规程。",
            "sources": [],
            "generation": "skipped",
            **status,
        }
    if not status["generation_ready"]:
        raise RuntimeError(status["generation_error"] or "生成问答不可用")
    answer = _complete(question, hits)
    return {
        "question": question,
        "answer": answer,
        "sources": sources,
        "generation": "deepseek",
        **status,
    }


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


def _complete(question: str, hits: list[KnowledgeHit]) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("未安装 openai，无法调用 DeepSeek") from exc
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat"
    context = "\n\n".join(
        f"[{index}] {hit.title}（{hit.location}）\n{hit.detail}" for index, hit in enumerate(hits, start=1)
    )
    client = OpenAI(api_key=key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"问题：{question}\n\n资料片段：\n{context}",
            },
        ],
    )
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise RuntimeError("DeepSeek 没有返回说明文本")
    return content
