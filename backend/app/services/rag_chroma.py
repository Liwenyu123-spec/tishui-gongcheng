"""轻量 Chroma RAG 存储层。

对齐 chroma 文档管理项目里「只检索、不调用大模型」的用法：切块写入 Chroma，
再用向量距离和关键词重合做混合打分。当前不加载句子向量模型，也不连接外部
RAG 引擎或业务数据库。编码器仍保持 Chroma EmbeddingFunction 接口，以后替换
真实 Embedding 时不必改路由。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _tokenize(text: str) -> list[str]:
    """提取中文字符 n-gram、英文词和数字，避免依赖外部分词模型。"""

    value = (text or "").lower()
    tokens: list[str] = []
    for block in re.findall(r"[\u4e00-\u9fff]+|[a-z][a-z0-9_-]*|\d+(?:\.\d+)?", value):
        if re.fullmatch(r"[\u4e00-\u9fff]+", block):
            tokens.extend(block[i : i + 2] for i in range(max(1, len(block) - 1)))
            tokens.extend(block[i : i + 3] for i in range(max(1, len(block) - 2)))
        else:
            tokens.append(block)
    return tokens or ["empty"]


class LocalHashEmbedding:
    """无需下载模型的 Chroma EmbeddingFunction。

    这是测试阶段的兜底实现，能稳定复现同一文本的向量，不代表生产语义模型质量。
    """

    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    def name(self) -> str:
        return "local-hash-embedding-v1"

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [self._encode(text) for text in input]

    # Chroma 1.x 会优先调用这两个方法，保留 __call__ 兼容旧版 Chroma。
    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self(input)

    def embed_query(self, input: str | list[str]) -> list[float] | list[list[float]]:
        if isinstance(input, str):
            return self._encode(input)
        return self(input)

    def _encode(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class SentenceTransformerEmbedding:
    """可选的真实语义 Embedding 适配器。

    依赖和模型均采用延迟加载，默认测试模式不会触发下载或初始化大模型。
    """

    def __init__(self, model_name: str) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "未安装 sentence-transformers，无法启用真实 Embedding；"
                "请安装后再设置 RAG_EMBEDDING_PROVIDER=sentence-transformers"
            ) from exc
        self.model_name = model_name
        try:
            self.model = SentenceTransformer(model_name)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Embedding 模型加载失败：{model_name}；{exc}") from exc

    def name(self) -> str:
        return f"sentence-transformers:{self.model_name}"

    def __call__(self, input: list[str]) -> list[list[float]]:
        vectors = self.model.encode(input, normalize_embeddings=True)
        return vectors.tolist()

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self(input)

    def embed_query(self, input: str | list[str]) -> list[float] | list[list[float]]:
        if isinstance(input, str):
            return self([input])[0]
        return self(input)


def split_text(text: str, chunk_size: int = 500, overlap: int = 80) -> list[str]:
    """按段落和句子切分文本，保留少量重叠上下文。"""

    normalized = re.sub(r"\r\n?", "\n", text or "").strip()
    if not normalized:
        return []
    sentences = [item.strip() for item in re.split(r"(?<=[。！？；.!?;])\s*|\n{2,}", normalized) if item.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > chunk_size:
            chunks.append(current.strip())
            tail = current[-overlap:] if overlap else ""
            current = f"{tail}\n{sentence}".strip()
        else:
            current = f"{current}\n{sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


class ChromaRagStore:
    """当前项目的 Chroma 存储适配器。"""

    def __init__(self) -> None:
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - 由健康接口展示
            raise RuntimeError("未安装 chromadb，请先安装 RAG 依赖") from exc

        default_path = _project_root() / "backend" / "data" / "rag_chroma_db"
        self.persist_path = Path(os.getenv("RAG_CHROMA_DIR", str(default_path))).resolve()
        self.persist_path.mkdir(parents=True, exist_ok=True)
        base_collection_name = os.getenv("RAG_CHROMA_COLLECTION", "water_project_knowledge")
        # 默认使用中文语义向量。模型或依赖不可用时回退哈希，避免检索接口整体不可用。
        embedding_provider = os.getenv("RAG_EMBEDDING_PROVIDER", "sentence-transformers").strip().lower()
        self.embedding_fallback: str | None = None
        if embedding_provider in {"hash", "local", "fallback"}:
            self.embedding = LocalHashEmbedding()
        elif embedding_provider in {"sentence-transformers", "sentence_transformers", "st"}:
            model_name = os.getenv("RAG_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5").strip()
            try:
                self.embedding = SentenceTransformerEmbedding(model_name)
            except RuntimeError as exc:
                self.embedding = LocalHashEmbedding()
                self.embedding_fallback = str(exc)
        else:
            raise RuntimeError(
                f"不支持的 RAG_EMBEDDING_PROVIDER：{embedding_provider}；"
                "可选 hash 或 sentence-transformers"
            )
        # 不同模型的向量维度和语义空间不同，切换模型时使用独立集合，避免混写。
        self.collection_name = base_collection_name
        if not isinstance(self.embedding, LocalHashEmbedding):
            suffix = hashlib.sha256(self.embedding.name().encode("utf-8")).hexdigest()[:10]
            self.collection_name = f"{base_collection_name}_{suffix}"
        self.client = chromadb.PersistentClient(path=str(self.persist_path))
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine", "embedding_model": self.embedding.name()},
            embedding_function=self.embedding,
        )
        self._lock = Lock()

    @staticmethod
    def _metadata(
        *,
        document_id: str,
        filename: str,
        title: str,
        version: str,
        category: str,
        station_ids: list[str],
        status: str,
        effective_from: datetime | None,
        effective_to: datetime | None,
        chunk_index: int,
    ) -> dict[str, str | int]:
        return {
            "document_id": document_id,
            "filename": filename,
            "title": title,
            "version": version,
            "category": category,
            "station_ids": json.dumps(station_ids, ensure_ascii=False),
            "status": status,
            "effective_from": effective_from.isoformat() if effective_from else "",
            "effective_to": effective_to.isoformat() if effective_to else "",
            "chunk_index": chunk_index,
        }

    @staticmethod
    def _eligible(status: str, effective_from: datetime | None, effective_to: datetime | None) -> bool:
        """只有现行且处于有效期内的资料才允许进入检索集合。"""

        if status != "valid":
            return False
        now = datetime.now(timezone.utc)
        start = effective_from if effective_from is None or effective_from.tzinfo else effective_from.replace(tzinfo=timezone.utc)
        end = effective_to if effective_to is None or effective_to.tzinfo else effective_to.replace(tzinfo=timezone.utc)
        if start and now < start:
            return False
        if end and now >= end:
            return False
        return True

    def delete_document(self, document_id: str) -> int:
        """按文档编号删除全部分片，废止或撤回时调用。"""

        with self._lock:
            existing = self.collection.get(where={"document_id": document_id})
            count = len(existing.get("ids") or [])
            if count:
                self.collection.delete(where={"document_id": document_id})
            return count

    def sync_document(
        self,
        *,
        document_id: str,
        filename: str,
        title: str,
        version: str,
        content: str,
        station_ids: list[str],
        status: str,
        category: str = "规程",
        effective_from: datetime | None = None,
        effective_to: datetime | None = None,
    ) -> int:
        """按生命周期同步索引：不可检索时删除，现行有效时重建分片。"""

        if not self._eligible(status, effective_from, effective_to):
            self.delete_document(document_id)
            return 0
        return self.upsert_document(
            document_id=document_id,
            filename=filename,
            title=title,
            version=version,
            category=category,
            content=content,
            station_ids=station_ids,
            status=status,
            effective_from=effective_from,
            effective_to=effective_to,
        )

    def upsert_document(
        self,
        *,
        document_id: str,
        filename: str,
        title: str,
        version: str,
        content: str,
        station_ids: list[str],
        status: str,
        category: str = "规程",
        effective_from: datetime | None = None,
        effective_to: datetime | None = None,
    ) -> int:
        chunks = split_text(content)
        if not chunks:
            return 0
        ids = [f"{document_id}:chunk:{index}" for index in range(len(chunks))]
        metadatas = [
            self._metadata(
                document_id=document_id,
                filename=filename,
                title=title,
                version=version,
                category=category,
                station_ids=station_ids,
                status=status,
                effective_from=effective_from,
                effective_to=effective_to,
                chunk_index=index,
            )
            for index in range(len(chunks))
        ]
        with self._lock:
            self.collection.delete(where={"document_id": document_id})
            self.collection.add(ids=ids, documents=chunks, metadatas=metadatas)
        return len(chunks)

    def reindex_documents(self, documents: list[dict[str, Any]]) -> dict[str, Any]:
        """按当前内存文档重建检索集合，并删掉已不在文档列表中的分片。"""

        known_ids = {str(item["document_id"]) for item in documents}
        indexed = 0
        for item in documents:
            chunks = self.sync_document(
                document_id=str(item["document_id"]),
                filename=str(item["filename"]),
                title=str(item["title"]),
                version=str(item["version"]),
                category=str(item.get("category") or "规程"),
                content=str(item.get("content") or ""),
                station_ids=list(item.get("station_ids") or []),
                status=str(item["status"]),
                effective_from=item.get("effective_from"),
                effective_to=item.get("effective_to"),
            )
            if chunks:
                indexed += 1
        existing = self.collection.get(include=["metadatas"])
        orphan_ids = {
            str(metadata.get("document_id"))
            for metadata in (existing.get("metadatas") or [])
            if metadata and str(metadata.get("document_id") or "") not in known_ids
        }
        for document_id in orphan_ids:
            self.delete_document(document_id)
        return {
            "indexed_documents": indexed,
            "skipped_documents": len(documents) - indexed,
            "removed_orphans": len(orphan_ids),
            "chunks": self.collection.count(),
        }

    @staticmethod
    def _parse_time(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    @classmethod
    def _visible(cls, metadata: dict[str, Any], station_id: str | None, visible_station_ids: set[str] | None) -> bool:
        if metadata.get("status") != "valid":
            return False
        now = datetime.now(timezone.utc)
        start = cls._parse_time(metadata.get("effective_from"))
        end = cls._parse_time(metadata.get("effective_to"))
        if start and now < start:
            return False
        if end and now >= end:
            return False
        try:
            station_ids = set(json.loads(str(metadata.get("station_ids") or "[]")))
        except (TypeError, ValueError, json.JSONDecodeError):
            station_ids = set()
        if station_id and station_ids and station_id not in station_ids:
            return False
        if visible_station_ids is not None and station_ids and not station_ids.intersection(visible_station_ids):
            return False
        return True

    @staticmethod
    def _lexical_score(query: str, text: str, title: str) -> int:
        """用与内存规程相同量级的关键词分，避免向量分把弱相关结果排到前面。"""

        normalized = query.strip().lower()
        terms = tuple(_tokenize(normalized))
        if terms == ("empty",):
            terms = ()
        searchable = f"{title} {text}".lower()
        score = 0
        for term in terms:
            if term in searchable:
                score += 2
            if term in title.lower():
                score += 2
        if normalized and normalized in searchable:
            score += 3
        return score

    def _visible_rows(self, station_id: str | None, visible_station_ids: set[str] | None) -> list[tuple[str, dict[str, Any]]]:
        """读取集合中当前可见的分片，供关键词检索使用。"""

        data = self.collection.get(include=["documents", "metadatas"])
        rows: list[tuple[str, dict[str, Any]]] = []
        for text, metadata in zip(data.get("documents") or [], data.get("metadatas") or []):
            if not metadata or not self._visible(metadata, station_id, visible_station_ids):
                continue
            rows.append((str(text or ""), metadata))
        return rows

    @staticmethod
    def _bm25_scores(query: str, rows: list[tuple[str, dict[str, Any]]]) -> dict[str, float]:
        """对可见分片做 BM25。对齐参考项目的稀疏检索，但不依赖外部分词模型。"""

        if not rows:
            return {}
        documents = [_tokenize(f"{metadata.get('title') or ''} {text}") for text, metadata in rows]
        query_terms = _tokenize(query)
        doc_count = len(documents)
        avg_len = sum(len(tokens) for tokens in documents) / doc_count
        df: dict[str, int] = {}
        for tokens in documents:
            for token in set(tokens):
                df[token] = df.get(token, 0) + 1
        scores: dict[str, float] = {}
        k1 = 1.5
        b = 0.75
        for (text, metadata), tokens in zip(rows, documents):
            counts: dict[str, int] = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            score = 0.0
            for term in query_terms:
                if term not in counts:
                    continue
                idf = math.log(1 + (doc_count - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5))
                freq = counts[term]
                denom = freq + k1 * (1 - b + b * len(tokens) / (avg_len or 1))
                score += idf * freq * (k1 + 1) / (denom or 1)
            document_id = str(metadata.get("document_id"))
            if score > scores.get(document_id, 0.0):
                scores[document_id] = score
                scores[f"{document_id}:text"] = text  # 保留最高分片正文，下面会拆开
                scores[f"{document_id}:meta"] = metadata  # type: ignore[assignment]
        return scores

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        station_id: str | None = None,
        visible_station_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        total = self.collection.count()
        if not query.strip() or total == 0:
            return []
        rows = self._visible_rows(station_id, visible_station_ids)
        if not rows:
            return []
        sparse = self._bm25_scores(query, rows)
        result = self.collection.query(
            query_texts=[query],
            n_results=min(max(limit * 8, 24), total),
            include=["documents", "metadatas", "distances"],
        )
        vector_best: dict[str, tuple[float, str, dict[str, Any]]] = {}
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        for document, metadata, distance in zip(documents, metadatas, distances):
            if not metadata or not self._visible(metadata, station_id, visible_station_ids):
                continue
            document_id = str(metadata.get("document_id"))
            similarity = 1.0 - float(distance)
            current = vector_best.get(document_id)
            if current is None or similarity > current[0]:
                vector_best[document_id] = (similarity, str(document), metadata)
        candidate_ids = set(vector_best) | {key for key in sparse if ":" not in key and sparse[key] > 0}
        max_sparse = max((float(sparse.get(key) or 0.0) for key in candidate_ids), default=0.0)
        best: dict[str, dict[str, Any]] = {}
        for document_id in candidate_ids:
            similarity, vector_text, vector_meta = vector_best.get(document_id, (0.0, "", {}))
            text = vector_text or str(sparse.get(f"{document_id}:text") or "")
            metadata = vector_meta or sparse.get(f"{document_id}:meta") or {}
            lexical = self._lexical_score(query, text, str(metadata.get("title") or ""))
            sparse_score = float(sparse.get(document_id) or 0.0)
            # 向量和 BM25 都只作小幅加分，关键词重合仍决定主要排序。
            if lexical == 0 and similarity < 0.35 and sparse_score <= 0:
                continue
            vector_bonus = round(max(0.0, similarity) * 6) if similarity >= 0.2 else 0
            sparse_bonus = round(sparse_score / max_sparse * 4) if max_sparse and sparse_score > 0 else 0
            score = int(lexical + vector_bonus + sparse_bonus)
            if score <= 0:
                continue
            best[document_id] = {
                "document_id": document_id,
                "metadata": metadata,
                "text": text,
                "score": score,
                "confidence": "normal",
            }
        hits = sorted(best.values(), key=lambda item: (-int(item["score"]), str(item["document_id"])))
        reranker = get_reranker()
        if reranker is not None and hits:
            pairs = [(query, f"{item['metadata'].get('title') or ''} {item['text']}") for item in hits]
            try:
                raw_scores = reranker.predict(pairs)
                probabilities = [_as_probability(float(value)) for value in raw_scores]
                for item, probability in zip(hits, probabilities):
                    item["score"] = int(item["score"]) + round(probability * 4)
                    # 低于阈值只标记，仍返回给页面，诊断引用会跳过。
                    item["confidence"] = "low" if probability < 0.35 else "normal"
                hits.sort(key=lambda item: (-int(item["score"]), str(item["document_id"])))
            except Exception as exc:  # noqa: BLE001
                global _RERANKER_ERROR
                _RERANKER_ERROR = str(exc)
        return hits[:limit]

    def ask(self, question: str, *, k: int = 5, preset: str | None = None) -> dict[str, Any]:
        """生成式问答暂不启用，避免在未接模型时调用外部 RAG 项目。"""

        del question, k, preset
        raise RuntimeError("当前阶段只提供 Chroma 检索，不调用大模型生成回答")

    def stats(self) -> dict[str, Any]:
        return {
            "available": True,
            "path": str(self.persist_path),
            "collection": self.collection_name,
            "chunks": self.collection.count(),
            "embedding": self.embedding.name(),
            "embedding_fallback": self.embedding_fallback,
            "engine_mode": "local-hash" if isinstance(self.embedding, LocalHashEmbedding) else "sentence-transformers",
            "retrieval": "vector+bm25",
            "rerank": _RERANKER_NAME or ("disabled" if _RERANKER_ERROR else "pending"),
            "rerank_error": None if _RERANKER is not None else _RERANKER_ERROR,
            "generation": "disabled",
        }


_STORE: ChromaRagStore | None = None
_STORE_ERROR: str | None = None
_RERANKER: Any | None = None
_RERANKER_ERROR: str | None = None
_RERANKER_NAME: str | None = None


def get_reranker() -> Any | None:
    """延迟加载本地 bge-reranker。模型不存在或关闭开关时跳过精排。"""

    global _RERANKER, _RERANKER_ERROR, _RERANKER_NAME
    if _RERANKER is not None or _RERANKER_ERROR is not None:
        return _RERANKER
    enabled = os.getenv("RAG_RERANK_ENABLED", "1").strip().lower()
    if enabled in {"0", "false", "off", "none"}:
        _RERANKER_ERROR = "重排已关闭"
        return None
    model_path = Path(os.getenv("RAG_RERANK_MODEL", r"H:\二阶段\bge-reranker-base"))
    if not model_path.is_dir():
        _RERANKER_ERROR = f"本地重排模型不存在：{model_path}"
        return None
    try:
        from sentence_transformers import CrossEncoder

        _RERANKER = CrossEncoder(str(model_path), local_files_only=True)
        _RERANKER_NAME = model_path.name
        return _RERANKER
    except Exception as exc:  # noqa: BLE001
        _RERANKER_ERROR = str(exc)
        return None


def _as_probability(value: float) -> float:
    """把重排输出压到 0 到 1。已经是概率时保持原值。"""

    if 0.0 <= value <= 1.0:
        return value
    return 1.0 / (1.0 + math.exp(-value))


def get_rag_store() -> ChromaRagStore | None:
    global _STORE, _STORE_ERROR
    if _STORE is not None:
        return _STORE
    if _STORE_ERROR:
        return None
    try:
        _STORE = ChromaRagStore()
    except Exception as exc:  # noqa: BLE001
        _STORE_ERROR = str(exc)
        return None
    return _STORE


def rag_store_status() -> dict[str, Any]:
    store = get_rag_store()
    if store is None:
        return {"available": False, "error": _STORE_ERROR or "Chroma 未初始化"}
    return store.stats()
