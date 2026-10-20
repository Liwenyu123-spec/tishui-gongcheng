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

    def _encode(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


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
        self.collection_name = os.getenv("RAG_CHROMA_COLLECTION", "water_project_knowledge")
        self.embedding = LocalHashEmbedding()
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

    def stats(self) -> dict[str, Any]:
        return {
            "available": True,
            "path": str(self.persist_path),
            "collection": self.collection_name,
            "chunks": self.collection.count(),
            "embedding": self.embedding.name(),
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
