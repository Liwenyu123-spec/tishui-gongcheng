"""轻量 Chroma RAG 存储层。

第一阶段不依赖 DeepSeek 或在线模型，使用确定性的本地向量编码完成检索闭环。
编码器保持 Chroma ``EmbeddingFunction`` 接口，后续可以替换成目标项目里的
Chinese-CLIP / HuggingFace Embedding，而不需要改动路由和 Agent 层。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
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
        embedding_provider = os.getenv("RAG_EMBEDDING_PROVIDER", "hash").strip().lower()
        if embedding_provider in {"hash", "local", "fallback"}:
            self.embedding = LocalHashEmbedding()
        elif embedding_provider in {"sentence-transformers", "sentence_transformers", "st"}:
            model_name = os.getenv("RAG_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5").strip()
            self.embedding = SentenceTransformerEmbedding(model_name)
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
        self.target_engine = self._init_target_engine()
        self.target_sources: dict[str, tuple[str, dict[str, Any]]] = {}

    def _init_target_engine(self) -> Any | None:
        """按目标项目的 SemanticSearchEngine 尝试启用真实 Embedding/Rerank。"""

        mode = os.getenv("RAG_ENGINE_MODE", "auto").strip().lower()
        if mode in {"local", "hash", "fallback"}:
            return None
        root = Path(
            os.getenv("RAG_TARGET_ROOT", r"H:\Python工程\rag\chroma文档管理")
        ).resolve()
        if not root.is_dir():
            self.target_error = f"目标 RAG 项目目录不存在：{root}"
            if mode == "target":
                raise RuntimeError(self.target_error)
            return None
        try:
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            # 目标项目读取自己的 CHROMA_PERSIST_DIR。给它独立目录，避免与本地
            # 测试集合混用；正式部署时可通过环境变量覆盖。
            os.environ.setdefault("CHROMA_PERSIST_DIR", str(self.persist_path / "target_engine"))
            from semantic_search.app.engine import SemanticSearchEngine

            engine = SemanticSearchEngine()
            self.target_error = None
            return engine
        except Exception as exc:  # noqa: BLE001
            self.target_error = str(exc)
            if mode == "target":
                raise RuntimeError(f"目标 RAG 引擎初始化失败：{exc}") from exc
            return None

    @staticmethod
    def _metadata(
        *,
        document_id: str,
        filename: str,
        title: str,
        version: str,
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
            "station_ids": json.dumps(station_ids, ensure_ascii=False),
            "status": status,
            "effective_from": effective_from.isoformat() if effective_from else "",
            "effective_to": effective_to.isoformat() if effective_to else "",
            "chunk_index": chunk_index,
        }

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
        if self.target_engine is not None:
            target_name = f"text-{hashlib.sha256(content.encode('utf-8')).hexdigest()[:12]}"
            try:
                self.target_engine.delete_by_file_name(target_name)
                self.target_engine.add_documents([content])
                self.target_sources[target_name] = (document_id, metadatas[0])
            except Exception as exc:  # noqa: BLE001
                self.target_error = str(exc)
                self.target_engine = None
        return len(chunks)

    def update_status(self, document_id: str, status: str) -> int:
        with self._lock:
            result = self.collection.get(where={"document_id": document_id}, include=["metadatas"])
            metadatas = result.get("metadatas") or []
            ids = result.get("ids") or []
            for metadata in metadatas:
                metadata["status"] = status
            if ids and metadatas:
                self.collection.update(ids=ids, metadatas=metadatas)
            return len(ids)

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

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        station_id: str | None = None,
        visible_station_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not query.strip() or self.collection.count() == 0:
            return []
        if self.target_engine is not None:
            try:
                target_hits = self.target_engine.search(query, k=max(limit * 2, limit))
                hits: list[dict[str, Any]] = []
                seen: set[str] = set()
                for item in target_hits:
                    target_name = str(item.get("file_name") or "")
                    source = self.target_sources.get(target_name)
                    if source is None:
                        continue
                    document_id, metadata = source
                    if document_id in seen or not self._visible(metadata, station_id, visible_station_ids):
                        continue
                    seen.add(document_id)
                    similarity = float(item.get("similarity") or 0.0)
                    hits.append(
                        {
                            "document_id": document_id,
                            "metadata": metadata,
                            "text": str(item.get("snippet") or item.get("document") or ""),
                            "score": max(1, min(100, round(similarity * 100))),
                        }
                    )
                    if len(hits) >= limit:
                        return hits
            except Exception as exc:  # noqa: BLE001
                self.target_error = str(exc)
                self.target_engine = None
        result = self.collection.query(
            query_texts=[query],
            n_results=min(max(limit * 4, limit), max(1, self.collection.count())),
            include=["documents", "metadatas", "distances"],
        )
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        hits: list[dict[str, Any]] = []
        seen: set[str] = set()
        for document, metadata, distance in zip(documents, metadatas, distances):
            if not self._visible(metadata, station_id, visible_station_ids):
                continue
            document_id = str(metadata.get("document_id"))
            if document_id in seen:
                continue
            seen.add(document_id)
            score = max(1, min(100, round((1.0 - float(distance)) * 100)))
            hits.append({"document_id": document_id, "metadata": metadata, "text": document, "score": score})
            if len(hits) >= limit:
                break
        return hits

    def ask(self, question: str, *, k: int = 5, preset: str | None = None) -> dict[str, Any]:
        """调用目标项目的 RagAskService，提供完整的检索优化和生成编排。"""

        if self.target_engine is None:
            reason = getattr(self, "target_error", None) or "目标 RAG 引擎未启用"
            raise RuntimeError(f"完整 RAG 问答暂不可用：{reason}")
        from semantic_search.app.service.rag_service import RagAskService

        return RagAskService(self.target_engine).ask(
            question,
            k=k,
            preset=preset or "custom",
            doc_scope="business",
        )

    def stats(self) -> dict[str, Any]:
        return {
            "available": True,
            "path": str(self.persist_path),
            "collection": self.collection_name,
            "chunks": self.collection.count(),
            "embedding": self.embedding.name(),
            "engine_mode": "target" if self.target_engine is not None else "local-fallback",
            "target_engine_error": getattr(self, "target_error", None),
        }


_STORE: ChromaRagStore | None = None
_STORE_ERROR: str | None = None


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
