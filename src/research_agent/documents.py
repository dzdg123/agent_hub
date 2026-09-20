from __future__ import annotations

import hashlib
from pathlib import Path

from .models import Source


class DocumentLoadError(RuntimeError):
    pass


SUPPORTED_SUFFIXES = {".txt", ".md", ".markdown", ".pdf"}


def safe_document_path(root: Path, candidate: Path) -> Path:
    root = root.resolve()
    path = candidate.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise DocumentLoadError("文件不在允许的文档目录中") from exc
    return path


def content_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:16]


def load_document(path: Path, root: Path) -> list[Source]:
    path = safe_document_path(root, path)
    if not path.is_file():
        raise DocumentLoadError("文件不存在")
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise DocumentLoadError(f"不支持的文件类型: {path.suffix}")
    if path.suffix.lower() == ".pdf":
        return _load_pdf(path)
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        raise DocumentLoadError("文档没有可用文本")
    return _chunk_sources(text, title=path.name, file_path=str(path))


def _load_pdf(path: Path) -> list[Source]:
    try:
        import fitz
    except ImportError as exc:
        raise DocumentLoadError("读取 PDF 需要安装 pymupdf") from exc
    sources: list[Source] = []
    with fitz.open(path) as document:
        for page_number, page in enumerate(document, 1):
            text = page.get_text("text").strip()
            if not text:
                continue
            sources.extend(
                _chunk_sources(
                    text,
                    title=f"{path.name} 第 {page_number} 页",
                    file_path=str(path),
                    page=page_number,
                )
            )
    if not sources:
        raise DocumentLoadError("PDF 没有可提取文本，可能是扫描件")
    return sources


def _chunk_sources(
    text: str,
    *,
    title: str,
    file_path: str,
    page: int | None = None,
    chunk_size: int = 900,
    overlap: int = 120,
) -> list[Source]:
    if chunk_size <= overlap:
        raise ValueError("chunk_size 必须大于 overlap")
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    chunks: list[Source] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        if end < len(normalized):
            boundary = max(normalized.rfind("。", start, end), normalized.rfind("\n", start, end))
            if boundary > start + chunk_size // 2:
                end = boundary + 1
        content = normalized[start:end].strip()
        if content:
            identity = f"{file_path}:{page}:{start}:{content}"
            chunks.append(
                Source(
                    source_id=f"doc-{content_id(identity)}",
                    title=title,
                    content=content,
                    file_path=file_path,
                    page=page,
                    metadata={"offset": start},
                )
            )
        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)
    return chunks


def load_all_documents(root: Path) -> list[Source]:
    root.mkdir(parents=True, exist_ok=True)
    sources: list[Source] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            try:
                sources.extend(load_document(path, root))
            except DocumentLoadError:
                continue
    return sources

