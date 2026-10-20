"""检索诊断：把一次检索的每个环节摊开，给出可执行结论。

排查 RAG 问题时最常见的三种困惑：
1. 「明明有资料，为什么答不上来」—— 没召回、排序靠后，还是被门控拦了？
2. 「为什么答非所问」—— 召回错了，还是门控没拦住弱相关片段？
3. 「配置是不是没生效」—— 是否悄悄退化成了哈希向量、重排没加载？

本模块只做只读诊断，不写索引、不调用生成模型。
结论用 reason 代码 + 中文说明给出，前端据此上色，避免让使用者自己解读分数。
"""

from __future__ import annotations

import time
from typing import Any

from .knowledge_generate import ask_min_rerank, ask_min_score, select_strong_hits
from .knowledge_search import KnowledgeHit
from .rag_chroma import (
    _RERANKER,
    _RERANKER_ERROR,
    _RERANKER_NAME,
    get_rag_store,
    rag_store_status,
    warmup_status,
)

# 结论代码 → 中文说明。文案集中在这里，避免前后端两处措辞不一致。
REASON_TEXT = {
    "ok": "检索通过，片段可交给生成模型作答",
    "no_documents": "知识库里没有可检索的分片，先导入并批准资料",
    "no_candidates": "没有任何片段进入候选，问句与现有资料缺少交集",
    "gate_score": "最高分低于分数门槛，判定为资料不足",
    "gate_rerank": "分数够但重排概率低于下限，资料里很可能没有答案",
    "below_rerank": "候选中存在可引用片段，但都没过门槛",
}


def _explain_components(top: dict[str, Any] | None) -> list[str]:
    """把 top1 的分项拆成给人看的句子，指出分数主要来自哪里。"""

    if not top:
        return ["没有候选片段。"]
    components = top.get("components") or {}
    if not components:
        return [f"综合分 {top.get('score')}（诊断分项不可用）。"]
    notes = [
        f"关键词 {components.get('lexical', 0)} 分",
        f"向量相似度 {components.get('vector_similarity', 0)}（加 {components.get('vector_bonus', 0)} 分）",
        f"BM25 {components.get('bm25_raw', 0)}（加 {components.get('bm25_bonus', 0)} 分）",
    ]
    if components.get("rerank_probability") is not None:
        notes.append(
            f"重排概率 {components['rerank_probability']}（加 {components.get('rerank_bonus', 0)} 分）"
        )
    notes.append(f"合计 {top.get('score')} 分，候选来源 {components.get('candidate_from', '未知')}")
    return notes


def diagnose(
    question: str,
    *,
    limit: int = 5,
    station_id: str | None = None,
    visible_station_ids: set[str] | None = None,
) -> dict[str, Any]:
    """对一条问句跑完整检索链路并解释结果。"""

    started = time.monotonic()
    store = get_rag_store()
    status = rag_store_status()
    warmup = warmup_status()

    def elapsed() -> int:
        return int((time.monotonic() - started) * 1000)

    if store is None:
        return {
            "question": question,
            "reason": "no_documents",
            "reason_text": status.get("error") or "Chroma 不可用",
            "verdict": "无法诊断：向量存储未初始化",
            "notes": ["检查 RAG_CHROMA_DIR 是否可写、chromadb 是否安装正常。"],
            "environment": status,
            "environment_notes": [],
            "gate": None,
            "hits": [],
            "elapsed_ms": elapsed(),
        }

    # 环境问题优先级最高：引擎退化时，后面的分数解释意义不大。
    environment_notes: list[str] = []
    if store.embedding_fallback:
        environment_notes.append(f"向量模型回退为哈希：{store.embedding_fallback}")
    if not warmup.get("attempted"):
        environment_notes.append("启动预热未执行，首次检索会明显变慢。")
    if _RERANKER is None:
        environment_notes.append(f"重排未加载：{_RERANKER_ERROR or '尚未初始化'}")

    if store.collection.count() == 0:
        return {
            "question": question,
            "reason": "no_documents",
            "reason_text": REASON_TEXT["no_documents"],
            "verdict": "知识库为空，无法检索",
            "notes": ["先导入资料并把状态改为现行，然后调用 POST /knowledge/rag/reindex。"],
            "environment": {**status, "warmup": warmup, "degraded": True},
            "environment_notes": environment_notes,
            "gate": None,
            "hits": [],
            "elapsed_ms": elapsed(),
        }

    raw_hits = store.search(
        question,
        limit=limit,
        station_id=station_id,
        visible_station_ids=visible_station_ids,
        debug=True,
    )

    # 转成业务数据类，用线上同一个门控函数判定，保证诊断结论与实际行为一致。
    hits = [
        KnowledgeHit(
            source_id=item["document_id"],
            title=str(item["metadata"].get("title") or item["document_id"]),
            version=str(item["metadata"].get("version") or ""),
            detail=str(item.get("text") or ""),
            score=int(item["score"]),
            source="chroma-document",
            filename=str(item["metadata"].get("filename") or ""),
            chunk_index=item["metadata"].get("chunk_index"),
            location=str(item["metadata"].get("location") or "正文"),
            category=str(item["metadata"].get("category") or ""),
            confidence=str(item.get("confidence") or "normal"),
            rerank=item.get("rerank"),
        )
        for item in raw_hits
    ]
    strong, gate = select_strong_hits(hits)
    passed_ids = {hit.source_id for hit in strong}

    payload_hits = [
        {
            "document_id": hit.source_id,
            "title": hit.title,
            "version": hit.version,
            "category": hit.category,
            "location": hit.location,
            "chunk_index": hit.chunk_index,
            "score": hit.score,
            "rerank": hit.rerank,
            "confidence": hit.confidence,
            # 逐条标出能否交给模型，前端据此区分「排上了」和「过了门槛」。
            "passed": hit.source_id in passed_ids,
            "components": item.get("components") or {},
            "excerpt": hit.detail[:240],
        }
        for item, hit in zip(raw_hits, hits)
    ]

    min_score = ask_min_score()
    min_rerank = ask_min_rerank()
    top = payload_hits[0] if payload_hits else None

    if strong:
        reason = "ok"
        verdict = f"通过：Top1《{top['title']}》得分 {top['score']}，可交给生成模型"
        notes = _explain_components(top)
        rejected = [item for item in payload_hits if not item["passed"]]
        if rejected:
            notes.append(f"另 {len(rejected)} 条未过门槛，不会作为引用。")
    elif not payload_hits:
        reason = "no_candidates"
        verdict = "没有候选：问句与现有资料没有交集"
        notes = [
            "向量相似度低于 0.35，且关键词、BM25 均为 0，说明连语义关联都很弱。",
            "确认问句用词是否属于本站资料范围，或该主题确实没有导入。",
        ]
    else:
        score_ok = top is not None and top["score"] >= min_score
        rerank_ok = top is not None and (top["rerank"] is None or top["rerank"] >= min_rerank)
        if not score_ok:
            reason = "gate_score"
            verdict = f"被分数门槛拦住：Top1 得分 {top['score']} < {min_score}"
            notes = _explain_components(top)
            notes.append(
                f"缺口 {min_score - top['score']} 分。若确认资料里有答案，"
                "检查切片是否把关键句切断了。"
            )
        elif not rerank_ok:
            reason = "gate_rerank"
            verdict = f"被重排下限拦住：Top1 概率 {top['rerank']} < {min_rerank}"
            notes = _explain_components(top)
            notes.append(
                "这是「同领域但资料里没有答案」的典型表现：关键词能对上，"
                "但重排认为这段资料答不了这个问题。"
            )
        else:
            reason = "below_rerank"
            verdict = "所有候选都被门槛拦掉"
            notes = _explain_components(top)

    return {
        "question": question,
        "reason": reason,
        "reason_text": REASON_TEXT.get(reason, ""),
        "verdict": verdict,
        "notes": notes,
        "environment": {
            **status,
            "warmup": warmup,
            "rerank_model": _RERANKER_NAME,
            "rerank_error": None if _RERANKER is not None else _RERANKER_ERROR,
            # 在环境块里直接给结论，前端不必自己判断是否退化。
            "degraded": bool(store.embedding_fallback) or _RERANKER is None,
        },
        "environment_notes": environment_notes,
        "gate": gate,
        "hits": payload_hits,
        "elapsed_ms": elapsed(),
    }
