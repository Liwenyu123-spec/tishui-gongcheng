"""RAG 检索评测基准。

目的：在改分数权重、重排开关、门控阈值前，先有一个可重复的量化基线，
避免「改完感觉变好了」这种无法验证的调参。

两种模式：
1. 默认（内置语料）：把 `data/rag_eval_corpus.json` 写进临时 Chroma 目录后评测。
   不读写真实索引，可安全反复运行，作为回归测试。
2. `--live`：直接评测当前真实索引，问句文件里的 expected 必须是真实文档 id。
   用于上线前确认现场资料的实际召回情况。

指标：
- Recall@K：正确文档是否出现在前 K 名（只统计可回答问句）。
- Precision@K：前 K 个结果中相关文档所占比例。
- nDCG@K：按相关文档排名折损后的排序质量。
- MRR@5：正确文档排名的倒数均值，越接近 1 说明排得越靠前。
- 门控：无答案问句是否被 `RAG_ASK_MIN_SCORE` 拦住（abstain accuracy），
  以及可回答问句是否被误拦（误拒率）。这一对指标必须同时看，
  单看召回会把阈值调得越低越好，最后模型被弱相关片段带偏。
- 引用完整性：正确来源是否携带稳定编号、标题、版本和可核对正文，
  防止「召回命中了但答案无法回指原文」。

用法：
    python backend/rag_eval.py
    python backend/rag_eval.py --no-rerank
    python backend/rag_eval.py --k 5 --verbose
    python backend/rag_eval.py --live --cases backend/data/rag_eval_live.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
# 让脚本既能从仓库根目录也能从 backend 目录运行。
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DEFAULT_CORPUS = BACKEND_DIR / "data" / "rag_eval_corpus.json"
DEFAULT_CASES = BACKEND_DIR / "data" / "rag_eval.jsonl"
DEFAULT_MIN_SCORE = 8


def precision_at_k(result_ids: list[str], expected_ids: set[str], k: int) -> float:
    """计算单条问句的 Precision@K，分母固定为 K。"""

    if k <= 0:
        return 0.0
    return sum(item in expected_ids for item in result_ids[:k]) / k


def ndcg_at_k(result_ids: list[str], expected_ids: set[str], k: int) -> float:
    """计算二值相关性 nDCG@K；正确文档越靠前得分越高。"""

    import math

    if k <= 0 or not expected_ids:
        return 0.0
    dcg = sum(1.0 / math.log2(index + 2) for index, item in enumerate(result_ids[:k]) if item in expected_ids)
    ideal = sum(1.0 / math.log2(index + 2) for index in range(min(len(expected_ids), k)))
    return dcg / ideal if ideal else 0.0


def load_corpus(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    # 允许顶层直接是数组，也允许包一层 documents 便于加注释字段。
    documents = payload.get("documents") if isinstance(payload, dict) else payload
    if not isinstance(documents, list) or not documents:
        raise SystemExit(f"语料文件没有可用文档：{path}")
    return documents


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            cases.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path} 第 {line_no} 行不是合法 JSON：{exc}") from exc
    if not cases:
        raise SystemExit(f"问句文件为空：{path}")
    return cases


def build_temp_store(corpus: list[dict[str, Any]], provider: str):
    """在临时目录建立评测用索引，返回 (store, 临时目录)。"""

    # 目录必须在系统临时区，避免测试数据落进仓库被提交。
    directory = tempfile.mkdtemp(prefix="rag_eval_")
    os.environ["RAG_CHROMA_DIR"] = directory
    os.environ["RAG_CHROMA_COLLECTION"] = "rag_eval"
    os.environ["RAG_EMBEDDING_PROVIDER"] = provider
    from app.services.rag_chroma import ChromaRagStore

    store = ChromaRagStore()
    for document in corpus:
        store.sync_document(
            document_id=document["document_id"],
            filename=document.get("filename") or f"{document['document_id']}.md",
            title=document.get("title") or document["document_id"],
            version=document.get("version") or "1.0",
            content=document["content"],
            station_ids=document.get("station_ids") or [],
            status=document.get("status") or "valid",
        )
    return store, directory


def evaluate(
    store,
    cases: list[dict[str, Any]],
    *,
    k: int,
    min_score: int,
    known_source_ids: set[str] | None = None,
) -> dict[str, Any]:
    """跑完所有问句并汇总指标。"""

    rank_hits = {1: 0, 3: 0, 5: 0}
    precision_sum = {1: 0.0, 3: 0.0, 5: 0.0}
    ndcg_sum = {3: 0.0, 5: 0.0}
    reciprocal_sum = 0.0
    answerable = 0
    abstain_total = 0
    # 同时统计「只看分数」和「线上真实门控（分数 + 重排下限）」，
    # 前者用来解释阈值调整的影响方向，后者才是产品实际行为。
    abstain_correct = {"score": 0, "live": 0}
    false_reject = {"score": 0, "live": 0}
    citation_valid = 0
    citation_errors = 0
    rows: list[dict[str, Any]] = []
    min_rerank_value: float | None = None

    from app.services.knowledge_generate import clean_query, select_strong_hits
    from app.services.knowledge_search import KnowledgeHit

    known_source_ids = known_source_ids or set()

    def search_variants(query: str) -> tuple[list[dict[str, Any]], str]:
        """按线上问句清洗逻辑检索，并合并原问句与归一化问句结果。"""

        variants = list(dict.fromkeys((query.strip(), clean_query(query))))
        merged: dict[str, dict[str, Any]] = {}
        for variant in variants:
            for item in store.search(variant, limit=max(k, 5)):
                document_id = str(item.get("document_id") or "")
                previous = merged.get(document_id)
                if previous is None or int(item.get("score") or 0) > int(previous.get("score") or 0):
                    merged[document_id] = item
        return (
            sorted(merged.values(), key=lambda item: (-int(item.get("score") or 0), str(item.get("document_id") or ""))),
            clean_query(query),
        )

    def citation_ok(hit: dict[str, Any] | None, expected: str | None) -> bool:
        """评测引用最小闭环：编号属于语料，且元数据和正文可供核对。"""

        if hit is None or not expected or str(hit.get("document_id") or "") != expected:
            return False
        metadata = hit.get("metadata") or {}
        return bool(
            expected in known_source_ids
            and str(metadata.get("title") or "").strip()
            and str(metadata.get("version") or "").strip()
            and str(hit.get("text") or "").strip()
        )

    for case in cases:
        query = case["query"]
        expected = case.get("expected")
        expected_ids = {str(item) for item in expected} if isinstance(expected, list) else ({str(expected)} if expected is not None else set())
        hits, effective_query = search_variants(query)
        ids = [hit["document_id"] for hit in hits]
        top_score = hits[0]["score"] if hits else 0
        # 与线上门控保持一致：直接复用生产函数，避免脚本和实现两套逻辑漂移。
        strong, gate_info = select_strong_hits(
            [
                KnowledgeHit(
                    source_id=hit["document_id"],
                    title=str(hit["metadata"].get("title") or ""),
                    version=str(hit["metadata"].get("version") or ""),
                    detail=str(hit.get("text") or ""),
                    score=int(hit["score"]),
                    confidence=str(hit.get("confidence") or "normal"),
                    rerank=hit.get("rerank"),
                )
                for hit in hits
            ],
            min_score=min_score,
        )
        gated = top_score < min_score
        gated_live = not gate_info["passed"]
        if gate_info["min_rerank"] is not None:
            min_rerank_value = gate_info["min_rerank"]

        row: dict[str, Any] = {
            "id": case.get("id"),
            "query": query,
            "effective_query": effective_query,
            "expected": expected,
            "rank": None,
            "top_score": top_score,
            "top_rerank": gate_info["top_rerank"],
            "gated": gated_live,
            "top_ids": ids[:k],
            "note": case.get("note"),
            "citation_valid": None,
        }

        if expected is None:
            abstain_total += 1
            # 无答案问句：被门控拦住才算正确；返回了高相关片段就是误答。
            abstain_correct["score"] += 1 if gated else 0
            abstain_correct["live"] += 1 if gated_live else 0
            row["result"] = "abstain_ok" if gated_live else f"abstain_fail(top={ids[0] if ids else None})"
        else:
            answerable += 1
            rank = min((ids.index(item) + 1 for item in expected_ids if item in ids), default=None)
            row["rank"] = rank
            if rank is None:
                row["result"] = "miss"
            else:
                row["citation_valid"] = citation_ok(hits[rank - 1], expected)
                if row["citation_valid"]:
                    citation_valid += 1
                else:
                    citation_errors += 1
                false_reject["score"] += 1 if gated else 0
                false_reject["live"] += 1 if gated_live else 0
                if gated_live:
                    # 排对了但被门控拦住：召回够、门控过严，会直接表现为「答不上来」。
                    row["result"] = f"false_reject(rank={rank})"
                else:
                    row["result"] = f"hit(rank={rank})"
            for cutoff in rank_hits:
                if rank is not None and rank <= cutoff:
                    rank_hits[cutoff] += 1
                precision_sum[cutoff] += precision_at_k(ids, expected_ids, cutoff)
            for cutoff in ndcg_sum:
                ndcg_sum[cutoff] += ndcg_at_k(ids, expected_ids, cutoff)
            if rank is not None and rank <= 5:
                reciprocal_sum += 1.0 / rank
        rows.append(row)

    def ratio(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    return {
        "cases": len(cases),
        "answerable": answerable,
        "abstain_cases": abstain_total,
        "recall_at_1": ratio(rank_hits[1], answerable),
        "recall_at_3": ratio(rank_hits[3], answerable),
        "recall_at_5": ratio(rank_hits[5], answerable),
        "precision_at_1": round(precision_sum[1] / answerable, 4) if answerable else 0.0,
        "precision_at_3": round(precision_sum[3] / answerable, 4) if answerable else 0.0,
        "precision_at_5": round(precision_sum[5] / answerable, 4) if answerable else 0.0,
        "ndcg_at_3": round(ndcg_sum[3] / answerable, 4) if answerable else 0.0,
        "ndcg_at_5": round(ndcg_sum[5] / answerable, 4) if answerable else 0.0,
        "mrr_at_5": round(reciprocal_sum / answerable, 4) if answerable else 0.0,
        "abstain_accuracy": ratio(abstain_correct["live"], abstain_total),
        "false_reject_rate": ratio(false_reject["live"], answerable),
        "abstain_accuracy_score_only": ratio(abstain_correct["score"], abstain_total),
        "false_reject_rate_score_only": ratio(false_reject["score"], answerable),
        "citation_coverage": ratio(citation_valid, answerable),
        "citation_integrity_errors": citation_errors,
        "min_score": min_score,
        "min_rerank": min_rerank_value,
        "k": k,
        "rows": rows,
    }


def print_report(summary: dict[str, Any], *, verbose: bool) -> None:
    print()
    print(f"问句总数 {summary['cases']}｜可回答 {summary['answerable']}｜无答案 {summary['abstain_cases']}")
    print(f"Recall@1 {summary['recall_at_1']:.2%}   Recall@3 {summary['recall_at_3']:.2%}   "
          f"Recall@5 {summary['recall_at_5']:.2%}   MRR@5 {summary['mrr_at_5']:.4f}")
    print(f"Precision@1 {summary['precision_at_1']:.2%}   Precision@3 {summary['precision_at_3']:.2%}   "
          f"Precision@5 {summary['precision_at_5']:.2%}   nDCG@3 {summary['ndcg_at_3']:.4f}   nDCG@5 {summary['ndcg_at_5']:.4f}")
    print(f"门控阈值 score>={summary['min_score']}"
          f"｜rerank>={summary['min_rerank'] if summary['min_rerank'] is not None else '未启用'}")
    print(f"  线上门控：无答案正确弃答 {summary['abstain_accuracy']:.2%}，可回答误拒 {summary['false_reject_rate']:.2%}")
    print(f"  只看分数：无答案正确弃答 {summary['abstain_accuracy_score_only']:.2%}，"
          f"可回答误拒 {summary['false_reject_rate_score_only']:.2%}")
    print(f"  引用完整性：正确来源可回指 {summary['citation_coverage']:.2%}，"
          f"字段/来源错误 {summary['citation_integrity_errors']} 条")

    def is_success(row: dict[str, Any]) -> bool:
        """命中或正确弃答都算达标；误拒、漏检、误答才算未达标。"""

        result = str(row.get("result", ""))
        return result.startswith("hit") or result == "abstain_ok"

    failures = [row for row in summary["rows"] if not is_success(row)]
    if failures:
        print(f"\n未达标 {len(failures)} 条：")
        for row in failures:
            if verbose:
                print(f"  [{row['id']}] {row['result']}｜期望={row['expected']}｜top={row['top_ids']}｜"
                      f"分数={row['top_score']}｜引用={row['citation_valid']}｜{row['query']}")
            else:
                print(f"  [{row['id']}] {row['result']}｜{row['query']}")
    else:
        print("\n全部达标。")


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG 检索评测基准")
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS), help="评测语料 JSON 路径")
    parser.add_argument("--cases", default=str(DEFAULT_CASES), help="问句 JSONL 路径")
    parser.add_argument("--live", action="store_true", help="评测当前真实索引，而不是临时索引")
    parser.add_argument("--provider", default="sentence-transformers", choices=["sentence-transformers", "hash"],
                        help="临时索引使用的编码器")
    parser.add_argument("--no-rerank", action="store_true", help="关闭重排，用于对比")
    parser.add_argument("--k", type=int, default=5, help="展示前 K 名，默认 5")
    parser.add_argument("--min-score", type=int, default=None, help="门控阈值，默认读 RAG_ASK_MIN_SCORE")
    parser.add_argument("--verbose", action="store_true", help="未达标问句打印完整详情")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出汇总，便于脚本比对")
    args = parser.parse_args()

    cases = load_cases(Path(args.cases))
    if args.no_rerank:
        os.environ["RAG_RERANK_ENABLED"] = "0"
    min_score = args.min_score
    if min_score is None:
        from app.services.runtime_env import windows_env

        raw = (windows_env("RAG_ASK_MIN_SCORE") or str(DEFAULT_MIN_SCORE)).strip()
        min_score = int(raw) if raw.isdigit() else DEFAULT_MIN_SCORE

    cleanup_dir: str | None = None
    try:
        if args.live:
            from app.services.rag_chroma import get_rag_store

            store = get_rag_store()
            if store is None:
                print("真实索引不可用，请先启动服务或检查 RAG_CHROMA_DIR", file=sys.stderr)
                return 2
            print(f"模式：真实索引｜{store.embedding.name()}｜chunks={store.collection.count()}")
            known_source_ids = {str(case["expected"]) for case in cases if case.get("expected")}
        else:
            corpus = load_corpus(Path(args.corpus))
            store, cleanup_dir = build_temp_store(corpus, args.provider)
            print(f"模式：临时索引｜{store.embedding.name()}｜文档 {len(corpus)}｜chunks={store.collection.count()}")
            known_source_ids = {str(item["document_id"]) for item in corpus if item.get("document_id")}

        from app.services import rag_chroma

        rag_chroma.get_reranker()
        # 必须读模块属性：from ... import 拿到的是 import 时的快照，
        # 而 _RERANKER_NAME 是 get_reranker() 执行后才被赋值的。
        rerank_label = rag_chroma._RERANKER_NAME or ("关闭" if rag_chroma._RERANKER_ERROR else "未加载")
        summary = evaluate(
            store,
            cases,
            k=args.k,
            min_score=min_score,
            known_source_ids=known_source_ids,
        )
        summary["rerank"] = rerank_label
        summary["embedding"] = store.embedding.name()
        summary["mode"] = "live" if args.live else "temp"

        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(f"重排：{rerank_label}")
            print_report(summary, verbose=args.verbose)
        # 成功标准：召回和「不乱答」都要达标。误拒会被用户感知为「明明有资料却说不知道」，
        # 所以和弃答准确率一起卡，避免用降低阈值的方式刷高召回。
        return 0 if (
            summary["recall_at_3"] >= 0.9
            and summary["precision_at_1"] >= 0.8
            and summary["ndcg_at_3"] >= 0.8
            and summary["abstain_accuracy"] >= 0.75
            and summary["false_reject_rate"] <= 0.1
            and summary["citation_coverage"] >= 0.9
            and summary["citation_integrity_errors"] == 0
        ) else 1
    finally:
        if cleanup_dir:
            shutil.rmtree(cleanup_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
