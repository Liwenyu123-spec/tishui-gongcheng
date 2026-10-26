"""知识资料文件解析。

对照 chroma 文档管理项目的加载器思路，按后缀抽出纯文本，再交给现有导入和
切块流程。当前不调用大模型，也不把文件写入数据库。
"""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path


SUPPORTED_EXTENSIONS = {".txt", ".md", ".html", ".htm", ".pdf", ".docx", ".csv", ".pptx"}


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
    if suffix == ".csv":
        return _extract_csv(payload), "csv"
    if suffix == ".pptx":
        return _extract_pptx(payload), "pptx-xml"
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


def _is_table_line(line: str) -> bool:
    return line.count("\t") >= 1 or len(re.findall(r"\s{2,}", line.strip())) >= 1


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in re.split(r"\t+|\s{2,}", line.strip()) if cell.strip()]


def format_pdf_pages(pages: list[tuple[int, str]]) -> str:
    """把版面文本按页分块，并把跨页延续的同表头表格合并成一张表。"""
    parts: list[str] = []
    open_table: dict[str, object] | None = None

    def close_table() -> None:
        nonlocal open_table
        if not open_table:
            return
        page_numbers = open_table["pages"]
        assert isinstance(page_numbers, list)
        label = "跨页表格" if len(page_numbers) > 1 else "表格"
        span = "、".join(f"第 {number} 页" for number in page_numbers)
        rows = open_table["rows"]
        assert isinstance(rows, list)
        parts.append(f"[{label} · {span}]\n" + "\n".join("\t".join(row) for row in rows))
        open_table = None

    for page_number, content in pages:
        lines = [line.rstrip() for line in content.splitlines()]
        block_index = 0
        prose: list[str] = []

        def flush_prose() -> None:
            nonlocal block_index, prose
            text = "\n".join(line for line in prose if line.strip()).strip()
            prose = []
            if not text:
                return
            block_index += 1
            parts.append(f"[第 {page_number} 页 · 区块 {block_index}]\n{text}")

        index = 0
        while index < len(lines):
            line = lines[index]
            if line.strip() and _is_table_line(line):
                flush_prose()
                rows = []
                while index < len(lines) and lines[index].strip() and _is_table_line(lines[index]):
                    rows.append(_table_cells(lines[index]))
                    index += 1
                if not rows:
                    continue
                header = tuple(rows[0])
                same_width = bool(open_table and open_table["rows"] and len(open_table["rows"][0]) == len(rows[0]))
                if open_table and (open_table["header"] == header or (same_width and open_table["header"] != header)):
                    saved_rows = open_table["rows"]
                    saved_pages = open_table["pages"]
                    assert isinstance(saved_rows, list) and isinstance(saved_pages, list)
                    saved_rows.extend(rows[1:] if open_table["header"] == header else rows)
                    saved_pages.append(page_number)
                else:
                    close_table()
                    open_table = {"header": header, "rows": rows, "pages": [page_number]}
                continue
            if line.strip():
                close_table()
                prose.append(line.strip())
            index += 1
        flush_prose()
    close_table()
    return "\n\n".join(parts)


def _extract_pdf(payload: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("未安装 pypdf，无法解析 PDF") from exc
    reader = PdfReader(BytesIO(payload))
    pages: list[tuple[int, str]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            content = page.extract_text(extraction_mode="layout") or ""
        except TypeError:
            content = page.extract_text() or ""
        if content.strip():
            pages.append((page_number, content))
    text = format_pdf_pages(pages).strip()
    if not text:
        raise ValueError("PDF 中没有可提取的文字，扫描件需要后续接入多模态")
    return text


def _extract_csv(payload: bytes) -> str:
    import csv

    text = _decode_text(payload)
    rows = ["\t".join(cell.strip() for cell in row) for row in csv.reader(text.splitlines()) if any(cell.strip() for cell in row)]
    if not rows:
        raise ValueError("CSV 中没有可提取的内容")
    return "[表格 · CSV]\n" + "\n".join(rows)


def _extract_pptx(payload: bytes) -> str:
    import zipfile
    from xml.etree import ElementTree

    slides: list[str] = []
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        names = sorted(name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
        for index, name in enumerate(names, start=1):
            root = ElementTree.fromstring(archive.read(name))
            texts = [node.text.strip() for node in root.iter() if node.tag.endswith("}t") and node.text and node.text.strip()]
            if texts:
                slides.append(f"[幻灯片 {index}]\n" + "\n".join(texts))
    if not slides:
        raise ValueError("PPT 中没有可提取的文字")
    return "\n\n".join(slides)


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
