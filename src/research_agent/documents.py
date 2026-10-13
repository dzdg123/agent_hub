from __future__ import annotations

import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from .models import Source
from copy import deepcopy
from typing import Any

FILE_TYPES = {
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
    ".pdf": "pdf",
}


@dataclass(slots=True)
class DocumentFileError:
    relative_path: str
    error_code: str
    message: str


@dataclass(slots=True)
class DocumentWarning:
    relative_path: str
    page: int
    warning_code: str
    message: str


@dataclass(slots=True)
class DocumentBatchResult:
    sources: list[Source] = field(default_factory=list)
    errors: list[DocumentFileError] = field(default_factory=list)
    warnings: list[DocumentWarning] = field(default_factory=list)
    loaded_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0

class DocumentLoadError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code


SUPPORTED_SUFFIXES = {".txt", ".md", ".markdown", ".pdf"}


def normalize_document_text(text: str) -> str:
    """规范化文档文本。

    当前规则：
    1. 删除空行；
    2. 删除每行首尾空白；
    3. 使用换行符重新连接。

    已知限制：会破坏 Markdown 缩进和代码块的原始排版。
    """
    return "\n".join(
        line.strip()
        for line in text.splitlines()
        if line.strip()
    )

def safe_document_path(root: Path, candidate: Path) -> Path:
    root = root.resolve()
    path = candidate.resolve()

    try:
        path.relative_to(root)
    except ValueError as exc:
        raise DocumentLoadError(
            "文件不在允许的文档目录中",
            code="outside_root",
        ) from exc

    return path


def content_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:16]


def load_document(path: Path, root: Path) -> list[Source]:
    root = root.resolve()
    path = safe_document_path(root, path)

    if not path.exists():
        raise DocumentLoadError(
            "文件不存在",
            code="not_found",
        )

    if not path.is_file():
        raise DocumentLoadError(
            "路径不是文件",
            code="not_a_file",
        )

    suffix = path.suffix.lower()

    if suffix not in SUPPORTED_SUFFIXES:
        raise DocumentLoadError(
            f"不支持的文件类型: {path.suffix}",
            code="unsupported_type",
        )

    file_metadata = {
        "content_kind": "local_document",
        "file_name": path.name,
        "relative_path": path.relative_to(root).as_posix(),
        "file_type": FILE_TYPES[suffix],
    }

    if suffix == ".pdf":
        return _load_pdf(
            path,
            base_metadata=file_metadata,
        )

    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentLoadError(
            "文件不是受支持的 UTF-8 编码",
            code="encoding_error",
        ) from exc
    except OSError as exc:
        raise DocumentLoadError(
            "文档读取失败",
            code="parse_error",
        ) from exc

    if not text.strip():
        raise DocumentLoadError(
            "文档没有可用文本",
            code="empty_document",
        )

    return _chunk_sources(
        text,
        title=path.name,
        file_path=str(path),
        base_metadata=file_metadata,
    )


def _load_pdf(
    path: Path,
    *,
    base_metadata: dict[str, Any],
) -> list[Source]:
    try:
        import pymupdf
    except ImportError as exc:
        raise DocumentLoadError(
            "读取 PDF 需要安装 pymupdf",
            code="dependency_missing",
        ) from exc

    sources: list[Source] = []
    empty_pages: list[int] = []

    try:
        with pymupdf.open(path) as document:
            if document.needs_pass:
                raise DocumentLoadError(
                    "PDF 需要密码",
                    code="password_required",
                )

            for page_number, page in enumerate(document, start=1):
                text = page.get_text("text").strip()

                if not text:
                    empty_pages.append(page_number)
                    continue

                page_metadata = {
                    **base_metadata,
                    "page": page_number,
                }

                sources.extend(
                    _chunk_sources(
                        text,
                        title=f"{path.name} 第 {page_number} 页",
                        file_path=str(path),
                        page=page_number,
                        base_metadata=page_metadata,
                    )
                )

    except (
        pymupdf.FileDataError,
        pymupdf.FileNotFoundError,
        OSError,
    ) as exc:
        raise DocumentLoadError(
            "文档解析失败：请检查文件是否损坏",
            code="parse_error",
        ) from exc

    if not sources:
        raise DocumentLoadError(
            "PDF 没有可提取文本，可能是扫描件",
            code="no_extractable_text",
        )

    if empty_pages:
        warning = (
                "以下页面未提取到文本："
                + ", ".join(str(page) for page in empty_pages)
        )

        for source in sources:
            source.metadata["empty_pages"] = empty_pages.copy()
            source.metadata["warnings"] = [warning]

    return sources


def _chunk_sources(
    text: str,
    *,
    title: str,
    file_path: str,
    page: int | None = None,
    chunk_size: int = 900,
    overlap: int = 120,
    base_metadata: dict[str, Any] | None = None,
) -> list[Source]:
    if (
        not isinstance(chunk_size, int)
        or isinstance(chunk_size, bool)
        or chunk_size <= 0
    ):
        raise ValueError("chunk_size 必须是正整数")

    if (
        not isinstance(overlap, int)
        or isinstance(overlap, bool)
        or overlap < 0
        or overlap >= chunk_size
    ):
        raise ValueError(
            "overlap 必须是非负整数且小于 chunk_size"
        )

    normalized = normalize_document_text(text)

    if not normalized:
        return []

    chunks: list[Source] = []
    start = 0

    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)

        if end < len(normalized):
            boundary = max(
                normalized.rfind("。", start, end),
                normalized.rfind("\n", start, end),
            )

            if boundary > start + chunk_size // 2:
                end = boundary + 1

        raw = normalized[start:end]
        content = raw.strip()

        # 修正 strip() 删除的前导空白所造成的偏移
        left_trim = len(raw) - len(raw.lstrip())
        content_start = start + left_trim
        content_end = content_start + len(content)

        if content:
            identity = (
                f"{file_path}:{page}:{content_start}:{content}"
            )

            offset_basis = (
                "normalized_page_text"
                if page is not None
                else "normalized_document_text"
            )

            chunk_metadata = deepcopy(base_metadata or {})

            chunk_metadata.update(
                {
                    "chunk_index": len(chunks),
                    "offset": content_start,
                    "end_offset": content_end,
                    "offset_basis": (
                        "normalized_page_text"
                        if page is not None
                        else "normalized_document_text"
                    ),
                }
            )

            chunks.append(
                Source(
                    source_id=f"doc-{content_id(identity)}",
                    title=title,
                    content=content,
                    file_path=file_path,
                    page=page,
                    metadata=chunk_metadata,
                )
            )

        if end >= len(normalized):
            break

        # 下一片仍按原始切片边界推进
        start = max(end - overlap, start + 1)

    return chunks


def load_all_documents(root: Path) -> list[Source]:
    # 旧入口保留自动创建目录的行为
    root.mkdir(parents=True, exist_ok=True)

    result = load_all_documents_detailed(root)

    return result.sources



def load_all_documents_detailed(
    root: Path,
) -> DocumentBatchResult:
    root = root.resolve()

    if not root.exists():
        raise DocumentLoadError(
            "文档目录不存在",
            code="not_found",
        )

    if not root.is_dir():
        raise DocumentLoadError(
            "文档根路径不是目录",
            code="not_a_directory",
        )

    result = DocumentBatchResult()

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue

        relative_path = path.relative_to(root).as_posix()
        suffix = path.suffix.lower()

        if suffix not in SUPPORTED_SUFFIXES:
            result.skipped_files += 1
            continue

        try:
            file_sources = load_document(path, root)
        except DocumentLoadError as exc:
            result.failed_files += 1
            result.errors.append(
                DocumentFileError(
                    relative_path=relative_path,
                    error_code=exc.code or "document_load_error",
                    message=str(exc),
                )
            )
            continue

        # 只要成功产生 Source，就算一个成功文件
        result.loaded_files += 1
        result.sources.extend(file_sources)

        # 每个文件的空白页只汇总一次，避免每个 chunk 重复报告
        empty_pages = sorted(
            {
                page_number
                for source in file_sources
                for page_number in source.metadata.get(
                    "empty_pages",
                    [],
                )
            }
        )

        for page_number in empty_pages:
            result.warnings.append(
                DocumentWarning(
                    relative_path=relative_path,
                    page=page_number,
                    warning_code="no_text_on_page",
                    message=(
                        f"第 {page_number} 页未提取到文本"
                    ),
                )
            )

    return result