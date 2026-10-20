"""知识文档的本地文件持久化层。

当前阶段不接数据库：元数据集中写入一个 JSON，正文按文档编号单独存成文本文件。
上层（`data.knowledge`、`routers.knowledge`）只通过本模块读写，将来替换成 MySQL
时只需要重写这一个文件，文档状态机、检索和审计逻辑都不用改。

存储结构：

    backend/data/knowledge/
        documents.json      # 文档元数据数组，与 KnowledgeDocument 字段一致
        content/<id>.txt    # 文档正文，便于人工核对和重建索引

写入采用「临时文件 + os.replace」的原子替换，避免开发时 `--reload` 杀进程
写到一半导致 JSON 损坏。读取时单条数据校验失败只跳过该条并记录错误，
不让整个服务因为一份坏数据起不来。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from pydantic import ValidationError

from ..schemas.knowledge import KnowledgeDocument

# 进程内写锁：FastAPI 默认用线程池执行同步路由，导入和改状态可能并发写。
_LOCK = Lock()

# 最近一次加载时跳过的坏数据说明，供 /knowledge/rag/status 对账展示。
_LOAD_ERRORS: list[str] = []

# 最近一次成功写入 documents.json 的时间，用于判断落盘是否正常。
_LAST_SAVED_AT: datetime | None = None


def _project_root() -> Path:
    """定位项目根目录，默认存储放在 backend/data 下。"""

    return Path(__file__).resolve().parents[3]


def store_dir() -> Path:
    """返回知识库存储目录；可用 KNOWLEDGE_STORE_DIR 覆盖，冒烟测试用它隔离。"""

    configured = os.getenv("KNOWLEDGE_STORE_DIR", "").strip()
    default = _project_root() / "backend" / "data" / "knowledge"
    return Path(configured or default).resolve()


def documents_path() -> Path:
    return store_dir() / "documents.json"


def content_dir() -> Path:
    return store_dir() / "content"


def _content_path(document_id: str) -> Path:
    """正文文件名直接使用文档编号，编号本身由服务端生成，不含路径字符。"""

    return content_dir() / f"{document_id}.txt"


def _ensure_dirs() -> None:
    store_dir().mkdir(parents=True, exist_ok=True)
    content_dir().mkdir(parents=True, exist_ok=True)


def _with_timezone(value: datetime | None) -> datetime | None:
    """把读回来的无时区时间统一按 UTC 处理，与检索层的判断保持一致。"""

    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _normalize(document: KnowledgeDocument) -> KnowledgeDocument:
    """修正反序列化后的时间字段，避免同一份文档在内存和索引里时区不一致。"""

    return document.model_copy(
        update={
            "imported_at": _with_timezone(document.imported_at) or datetime.now(timezone.utc),
            "effective_from": _with_timezone(document.effective_from),
            "effective_to": _with_timezone(document.effective_to),
            "approved_at": _with_timezone(document.approved_at),
        }
    )


def _atomic_write(path: Path, text: str) -> None:
    """先写同目录临时文件再替换，保证任何时刻 documents.json 都是完整 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _read_documents() -> list[dict[str, Any]]:
    """读取元数据数组；文件不存在视为空库，内容损坏时保留原文件并抛出。"""

    path = documents_path()
    if not path.is_file():
        return []
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    payload = json.loads(raw)
    if isinstance(payload, dict):
        # 兼容早期可能写成 {"documents": [...]} 的结构，减少手工改文件的门槛。
        payload = payload.get("documents") or []
    if not isinstance(payload, list):
        raise ValueError("documents.json 顶层必须是数组")
    return [item for item in payload if isinstance(item, dict)]


def load_all() -> tuple[dict[str, KnowledgeDocument], dict[str, str]]:
    """加载全部文档，返回（元数据字典, 正文字典）。

    单条记录校验失败时记录到 `_LOAD_ERRORS` 并跳过；重复编号以后出现的为准。
    正文文件缺失不算致命错误，文档仍可列出，只是检索时没有内容可切块。
    """

    global _LOAD_ERRORS
    errors: list[str] = []
    documents: dict[str, KnowledgeDocument] = {}
    contents: dict[str, str] = {}

    try:
        items = _read_documents()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        # 元数据整体不可读时不覆盖原文件，交给运维人员人工检查。
        _LOAD_ERRORS = [f"读取 documents.json 失败：{exc}"]
        return documents, contents

    for index, item in enumerate(items):
        try:
            document = _normalize(KnowledgeDocument(**item))
        except (ValidationError, ValueError, TypeError) as exc:
            errors.append(f"第 {index + 1} 条文档校验失败：{exc}")
            continue
        documents[document.id] = document
        content_path = _content_path(document.id)
        try:
            contents[document.id] = content_path.read_text(encoding="utf-8")
        except OSError:
            errors.append(f"文档 {document.id} 缺少正文文件：{content_path.name}")

    _LOAD_ERRORS = errors
    return documents, contents


def _write_all(documents: dict[str, KnowledgeDocument]) -> None:
    """把当前内存文档整体写回 JSON；调用方负责持有 _LOCK。"""

    global _LAST_SAVED_AT
    _ensure_dirs()
    payload = [document.model_dump(mode="json") for document in documents.values()]
    # 固定按导入时间排序，文件 diff 稳定，便于用 git 查看资料变化。
    payload.sort(key=lambda item: (str(item.get("imported_at") or ""), str(item.get("id") or "")))
    _atomic_write(documents_path(), json.dumps(payload, ensure_ascii=False, indent=2))
    _LAST_SAVED_AT = datetime.now(timezone.utc)


def save_document(document: KnowledgeDocument, content: str) -> None:
    """新增或覆盖一条文档及正文。

    元数据整体重写，正文单独原子写入；两次写入之间有极短窗口可能不一致，
    但重启后以 JSON 为准，正文缺失只影响该文档的切块。
    """

    with _LOCK:
        _ensure_dirs()
        _atomic_write(_content_path(document.id), content or "")
        # 直接重读磁盘再合并，避免内存视图和文件被不同代码路径改乱。
        merged, _ = load_all()
        merged[document.id] = _normalize(document)
        _write_all(merged)


def update_document(document: KnowledgeDocument) -> None:
    """只更新元数据（状态、审批时间），不动已存在的正文文件。"""

    with _LOCK:
        merged, _ = load_all()
        merged[document.id] = _normalize(document)
        _write_all(merged)


def delete_document(document_id: str) -> bool:
    """删除元数据和正文；返回是否真的删掉了元数据记录。"""

    with _LOCK:
        merged, _ = load_all()
        removed = merged.pop(document_id, None) is not None
        if removed:
            _write_all(merged)
        try:
            _content_path(document_id).unlink()
        except FileNotFoundError:
            pass
        return removed


def store_status() -> dict[str, Any]:
    """返回落盘层状态，供 /knowledge/rag/status 与索引分片数对账。"""

    directory = store_dir()
    path = documents_path()
    persisted = 0
    with_content = 0
    try:
        for item in _read_documents():
            document_id = str(item.get("id") or "")
            if not document_id:
                continue
            persisted += 1
            if _content_path(document_id).is_file():
                with_content += 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "dir": str(directory),
            "documents_file": str(path),
            "file_exists": path.is_file(),
            "persisted": 0,
            "with_content": 0,
            "last_saved_at": None,
            "errors": [f"读取 documents.json 失败：{exc}"],
        }
    return {
        "dir": str(directory),
        "documents_file": str(path),
        "file_exists": path.is_file(),
        "persisted": persisted,
        "with_content": with_content,
        "last_saved_at": _LAST_SAVED_AT.isoformat() if _LAST_SAVED_AT else None,
        "errors": list(_LOAD_ERRORS),
    }


def clear_all() -> None:
    """清空存储目录内容（仅供测试和本地重置使用）。"""

    with _LOCK:
        _ensure_dirs()
        _atomic_write(documents_path(), "[]")
        for path in content_dir().glob("*.txt"):
            try:
                path.unlink()
            except OSError:
                pass
