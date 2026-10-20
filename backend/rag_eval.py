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
- MRR@5：正确文档排名的倒数均值，越接近 1 说明排得越靠前。
- 门控：无答案问句是否被 `RAG_ASK_MIN_SCORE` 拦住（abstain accuracy），
  以及可回答问句是否被误拦（误拒率）。这一对指标必须同时看，
  单看召回会把阈值调得越低越好，最后模型被弱相关片段带偏。

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


def evaluate(store, cases: list[dict[str, Any]], *, k: int, min_score: int) -> dict[str, Any]:
    """跑完所有问句并汇总指标。"""

    rank_hits = {1: 0, 3: 0, 5: 0}
    reciprocal_sum = 0.0
    answerable = 0
    abstain_total = 0
    abstain_correct = 0
    false_reject = 0
    rows: list[dict[str, Any]] = []

    for case in cases:
        query = case["query"]
        expected = case.get("expected")
        hits = store.search(query, limit=max(k, 5))
        ids = [hit["document_id"] for hit in hits]
        top_score = hits[0]["score"] if hits else 0
        # 与线上门控保持一致：最高分不足阈值即视为「资料不足」。
        gated = top_score < min_score

        row: dict[str, Any] = {
            "id": case.get("id"),
            "query": query,
            "expected": expected,
            "rank": None,
            "top_score": top_score,
            "gated": gated,
            "top_ids": ids[:k],
            "note": case.get("note"),
        }

        if expected is None:
            abstain_total += 1
            # 无答案问句：被门控拦住才算正确；返回了高相关片段就是误答。
            if gated:
                abstain_correct += 1
                row["result"] = "abstain_ok"
            else:
                row["result"] = f"abstain_fail(top={ids[0] if ids else None})"
        else:
            answerable += 1
            rank = ids.index(expected) + 1 if expected in ids else None
            row["rank"] = rank
            if rank is None:
                row["result"] = "miss"
            elif gated:
                # 排对了但被阈值拦住：召回够、门控过严，会直接表现为「答不上来」。
                false_reject += 1
                row["result"] = f"false_reject(rank={rank})"
            else:
                row["result"] = f"hit(rank={rank})"
            for cutoff in rank_hits:
                if rank is not None and rank <= cutoff:
                    rank_hits[cutoff] += 1
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
        "mrr_at_5": round(reciprocal_sum / answerable, 4) if answerable else 0.0,
        "abstain_accuracy": ratio(abstain_correct, abstain_total),
        "false_reject_rate": ratio(false_reject, answerable),
        "min_score": min_score,
        "k": k,
        "rows": rows,
    }


def print_report(summary: dict[str, Any], *, verbose: bool) -> None:
    print()
    print(f"问句总数 {summary['cases']}｜可回答 {summary['answerable']}｜无答案 {summary['abstain_cases']}")
    print(f"Recall@1 {summary['recall_at_1']:.2%}   Recall@3 {summary['recall_at_3']:.2%}   "
          f"Recall@5 {summary['recall_at_5']:.2%}   MRR@5 {summary['mrr_at_5']:.4f}")
    print(f"无答案正确弃答 {summary['abstain_accuracy']:.2%}   可回答误拒 {summary['false_reject_rate']:.2%}   "
          f"门控阈值 {summary['min_score']}")

    failures = [row for row in summary["rows"] if not str(row.get("result", "")).startswith("hit")]
    if failures:
        print(f"\n未达标 {len(failures)} 条：")
        for row in failures:
            if verbose:
                print(f"  [{row['id']}] {row['result']}｜期望={row['expected']}｜top={row['top_ids']}｜"
                      f"分数={row['top_score']}｜{row['query']}")
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
        else:
            corpus = load_corpus(Path(args.corpus))
            store, cleanup_dir = build_temp_store(corpus, args.provider)
            print(f"模式：临时索引｜{store.embedding.name()}｜文档 {len(corpus)}｜chunks={store.collection.count()}")

        from app.services.rag_chroma import _RERANKER_ERROR, _RERANKER_NAME, get_reranker

        get_reranker()
        rerank_label = _RERANKER_NAME or ("关闭" if _RERANKER_ERROR else "未加载")
        summary = evaluate(store, cases, k=args.k, min_score=min_score)
        summary["rerank"] = rerank_label
        summary["embedding"] = store.embedding.name()
        summary["mode"] = "live" if args.live else "temp"

        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(f"重排：{rerank_label}")
            print_report(summary, verbose=args.verbose)
        # 返回码便于 CI 判断基线是否退化。
        return 0 if summary["recall_at_3"] >= 0.8 and summary["abstain_accuracy"] >= 0.75 else 1
    finally:
        if cleanup_dir:
            shutil.rmtree(cleanup_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
