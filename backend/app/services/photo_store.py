"""现场照片与 Chinese-CLIP 图文匹配。

照片只保存到本地磁盘（默认 backend/data/site_photos），向量特征保存在
backend/data/photo_index.json。不连接业务数据库。模型优先加载
H:\\二阶段\\chinese-clip-vit-base-patch16；不可用时会给出降级提示。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image

_DEFAULT_MODEL_DIR = Path(r"H:\二阶段\chinese-clip-vit-base-patch16")
_DEFAULT_STORE_DIR = Path(__file__).resolve().parents[2] / "data" / "site_photos"
_INDEX_NAME = "photo_index.json"
_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


@dataclass
class PhotoRecord:
    """一张现场照片的元数据。"""

    photo_id: str
    filename: str
    path: str
    station_id: str | None = None
    station_name: str | None = None
    caption: str | None = None
    uploaded_at: str = ""
    embedding_ready: bool = False
    labels: list[str] = field(default_factory=list)


class PhotoIndex:
    """进程内照片索引；模型加载一次复用。"""

    def __init__(self) -> None:
        self.store_dir = Path(os.getenv("PHOTO_STORE_DIR", str(_DEFAULT_STORE_DIR))).resolve()
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.store_dir / _INDEX_NAME
        self.model_dir = Path(os.getenv("PHOTO_CLIP_MODEL", str(_DEFAULT_MODEL_DIR))).resolve()
        self._records: dict[str, PhotoRecord] = {}
        self._embeddings: dict[str, list[float]] = {}
        self._model = None
        self._processor = None
        self._model_error: str | None = None
        self._load_index()

    def _load_index(self) -> None:
        if not self.index_path.is_file():
            return
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for item in raw.get("records", []):
            record = PhotoRecord(**item)
            self._records[record.photo_id] = record
        self._embeddings = {str(k): v for k, v in (raw.get("embeddings") or {}).items()}

    def _save_index(self) -> None:
        payload = {
            "records": [asdict(item) for item in self._records.values()],
            "embeddings": self._embeddings,
            "model": str(self.model_dir),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        self.index_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _load_model(self) -> tuple[Any, Any] | tuple[None, None]:
        if self._model is not None:
            return self._model, self._processor
        if self._model_error is not None:
            return None, None
        if not self.model_dir.is_dir():
            self._model_error = f"本地 Chinese-CLIP 不存在：{self.model_dir}"
            return None, None
        try:
            import torch
            from transformers import AutoModel, AutoProcessor

            processor = AutoProcessor.from_pretrained(str(self.model_dir), local_files_only=True)
            model = AutoModel.from_pretrained(str(self.model_dir), local_files_only=True)
            model.eval()
            self._processor = processor
            self._model = model
            return model, processor
        except Exception as exc:  # noqa: BLE001
            self._model_error = str(exc)
            return None, None

    def status(self) -> dict[str, Any]:
        self._load_model()
        return {
            "available": self._model is not None,
            "model_dir": str(self.model_dir),
            "error": self._model_error,
            "photos": len(self._records),
            "embedded": len(self._embeddings),
            "store_dir": str(self.store_dir),
        }

    def register(
        self,
        *,
        filename: str,
        payload: bytes,
        station_id: str | None = None,
        station_name: str | None = None,
        caption: str | None = None,
    ) -> PhotoRecord:
        suffix = Path(filename or "photo").suffix.lower() or ".jpg"
        if suffix not in _ALLOWED_SUFFIXES:
            raise ValueError(f"不支持的照片类型 {suffix}，可选 {', '.join(sorted(_ALLOWED_SUFFIXES))}")
        try:
            Image.open(BytesIO(payload)).verify()
        except Exception as exc:  # noqa: BLE001
            raise ValueError("文件不是可读取的图片") from exc
        photo_id = f"photo-{uuid4().hex[:10]}"
        safe_name = f"{photo_id}{suffix}"
        target = self.store_dir / safe_name
        target.write_bytes(payload)
        record = PhotoRecord(
            photo_id=photo_id,
            filename=filename or safe_name,
            path=str(target),
            station_id=station_id,
            station_name=station_name,
            caption=caption,
            uploaded_at=datetime.now(timezone.utc).isoformat(),
        )
        self._records[photo_id] = record
        self.embed_photo(photo_id)
        self._save_index()
        return self._records[photo_id]

    def embed_photo(self, photo_id: str) -> bool:
        record = self._records.get(photo_id)
        if record is None:
            return False
        model, processor = self._load_model()
        if model is None:
            return False
        try:
            import torch

            image = Image.open(record.path).convert("RGB")
            inputs = processor(images=image, return_tensors="pt")
            with torch.no_grad():
                if hasattr(model, "get_image_features"):
                    features = model.get_image_features(**inputs)
                else:
                    outputs = model(**inputs)
                    features = outputs.image_embeds
            vector = features[0].tolist()
            norm = sum(v * v for v in vector) ** 0.5 or 1.0
            self._embeddings[photo_id] = [v / norm for v in vector]
            record.embedding_ready = True
            return True
        except Exception:  # noqa: BLE001
            record.embedding_ready = False
            return False

    def list_photos(self) -> list[PhotoRecord]:
        return sorted(self._records.values(), key=lambda item: item.uploaded_at, reverse=True)

    def search(self, query: str, *, k: int = 3) -> list[dict[str, Any]]:
        """用中文描述检索照片，返回相似度和元数据。"""

        model, processor = self._load_model()
        if model is None:
            raise RuntimeError(self._model_error or "Chinese-CLIP 不可用")
        try:
            import torch

            inputs = processor(text=[query], return_tensors="pt", padding=True)
            with torch.no_grad():
                if hasattr(model, "get_text_features"):
                    text_features = model.get_text_features(**inputs)
                else:
                    outputs = model(**inputs)
                    text_features = outputs.text_embeds
            text_vector = text_features[0].tolist()
            norm = sum(v * v for v in text_vector) ** 0.5 or 1.0
            text_vector = [v / norm for v in text_vector]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"文本编码失败：{exc}") from exc
        scored: list[tuple[float, str]] = []
        for photo_id, vector in self._embeddings.items():
            score = sum(a * b for a, b in zip(text_vector, vector))
            scored.append((score, photo_id))
        scored.sort(key=lambda item: -item[0])
        results: list[dict[str, Any]] = []
        for score, photo_id in scored[:k]:
            record = self._records[photo_id]
            results.append(
                {
                    "photo_id": record.photo_id,
                    "filename": record.filename,
                    "station_id": record.station_id,
                    "station_name": record.station_name,
                    "caption": record.caption,
                    "score": round(score, 4),
                    "path": record.path,
                }
            )
        return results


_INDEX: PhotoIndex | None = None


def get_photo_index() -> PhotoIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = PhotoIndex()
    return _INDEX


# 默认中文提示词：把照片和本站告警类别对齐。
DEFAULT_QUERY_LABELS = (
    "流量异常 泵站流量下降",
    "压力异常 输水压力下降",
    "水位异常 泵站水位下降",
    "电流异常 泵组电流偏高",
    "正常巡检 无异常",
)
