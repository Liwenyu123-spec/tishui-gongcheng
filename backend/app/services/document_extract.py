"""知识资料文件解析。

对照 chroma 文档管理项目的加载器思路，按后缀抽出纯文本，再交给现有导入和
切块流程。当前不调用大模型，也不把文件写入数据库。
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path


SUPPORTED_EXTENSIONS = {".txt", ".md", ".html", ".htm", ".pdf", ".docx"}


def extract_text(filename: str, payload: bytes) -> tuple[str, str]:
    """按文件名后缀解析正文。返回正文和解析器名称。"""

    suffix = Path(filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"暂不支持 {suffix or '未知类型'}，可选 {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
    if not payload:
        raise ValueError("上传文件为空")
    if suffix in {".txt", ".md", ".html", ".htm"}:
        return _decode_text(payload), "plain-text"
    if suffix == ".pdf":
        return _extract_pdf(payload), "pypdf"
    return _extract_docx(payload), "python-docx"


def suggested_title(filename: str) -> str:
    """用文件名去掉后缀作为资料标题初值。"""

    return Path(filename or "未命名资料").stem.strip() or "未命名资料"


def _decode_text(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = payload.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = payload.decode("utf-8", errors="ignore")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise ValueError("没有解析到可用正文")
    return normalized


def _extract_pdf(payload: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("未安装 pypdf，无法解析 PDF") from exc
    reader = PdfReader(BytesIO(payload))
    pages = []
    for page_number, page in enumerate(reader.pages, start=1):
        content = (page.extract_text() or "").strip()
        if content:
            pages.append(f"[第 {page_number} 页]\n{content}")
    text = "\n\n".join(item for item in pages if item).strip()
    if not text:
        raise ValueError("PDF 中没有可提取的文字，扫描件需要后续接入多模态")
    return text


def _extract_docx(payload: bytes) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("未安装 python-docx，无法解析 Word") from exc
    document = Document(BytesIO(payload))
    parts = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    # 将 Word 表格按行保留为制表符分隔文本，避免设备编号、阈值和单位在导入时丢失。
    for table_index, table in enumerate(document.tables, start=1):
        rows = []
        for row in table.rows:
            cells = [cell.text.replace("\n", " ").strip() for cell in row.cells]
            if any(cells):
                rows.append("\t".join(cells))
        if rows:
            parts.append(f"[表格 {table_index}]\n" + "\n".join(rows))
    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("Word 文档中没有可提取的文字")
    return text
