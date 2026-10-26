"""从结构化数据重新生成 Markdown；预览和正式报告使用不同入口。"""

from copy import deepcopy
from html import escape
from pathlib import Path, PureWindowsPath
import re
from urllib.parse import quote, urlsplit, urlunsplit

from .models import Source
from .rag_models import AnswerResult, ResolvedEvidence, ValidationIssue
from .rag_review import can_publish_answer
from .rag_validation import build_canonical_source_map, review_fingerprint, validate_draft_layers


def _escape_text(value: str) -> str:
    """自由文字始终按普通文本显示；不允许它创建 HTML、链接或新段落。"""
    value = re.sub(r"([\\`*_{}\[\]()#+\-.!|~:])", r"\\\1", value)
    value = escape(value, quote=True)
    return value.replace("\r", "&#13;").replace("\n", "&#10;").replace("\t", "&#9;")


def _safe_web_url(value: str) -> str | None:
    # 不请求 URL，只限制能成为可点击链接的协议及边界字符。
    if any(ord(char) < 32 or ord(char) == 127 for char in value) or "\\" in value:
        return None
    try:
        parts = urlsplit(value)
        if (
            parts.scheme.lower() not in {"http", "https"} or not parts.hostname
            or parts.username is not None or parts.password is not None
            or any(char.isspace() or char in '<>"\'' for char in parts.netloc)
        ):
            return None
        parts.port  # 校验端口格式。
        return urlunsplit((
            parts.scheme.lower(), parts.netloc,
            quote(parts.path, safe="/:@=&+,-._~%"),
            quote(parts.query, safe="&=/?@:+,;%-._~"),
            quote(parts.fragment, safe="=&/?@:+,;%-._~"),
        ))
    except ValueError:
        return None


def _local_path(value: str, base_dir: Path | None) -> Path | None:
    """只识别文件路径，不将 file:/javascript:/UNC 等字符串转成链接。"""
    if not value or any(ord(char) < 32 for char in value):
        return None
    windows = PureWindowsPath(value)
    if value.startswith(("//", "\\\\")):
        return None
    if ":" in value and not (windows.is_absolute() and len(windows.drive) == 2):
        return None
    if windows.is_absolute():
        return Path(value)
    path = Path(value.replace("\\", "/"))
    if path.is_absolute():
        return path
    return (base_dir / path).resolve() if base_dir is not None else None


def _render_source_location(source: Source, base_dir: Path | None) -> str:
    parts = []
    if source.url:
        target = _safe_web_url(source.url)
        label = _escape_text(source.url)
        parts.append(f"网址：[{label}](<{target}>)" if target else f"网址（仅文本）：{label}")
    if source.file_path:
        parts.append(f"文件：{_escape_text(source.file_path)}")
        path = _local_path(source.file_path, base_dir)
        if path is not None and path.suffix.lower() == ".pdf":
            target = quote(str(path).replace("\\", "/"), safe="/:")
            if source.page is not None:
                target += f"#page={source.page}"
            parts.append(f"[打开 PDF](<{target}>)")
    if source.page is not None:
        parts.append(f"物理页：{source.page}")
    return "；".join(parts) if parts else "来源地址未知"


def _render_positions(locations: list[ResolvedEvidence]) -> str:
    # 同一个来源被多次引用时，不重复展示完全相同的位置。
    local_ranges = dict.fromkeys(
        (item.local_start, item.local_end)
        for location in locations for item in location.occurrences
    )
    normalized = dict.fromkeys(
        (location.offset_basis, item.normalized_start, item.normalized_end)
        for location in locations for item in location.occurrences
        if item.normalized_start is not None
    )
    parts = ["片段内字符位置：" + "、".join(f"[{start}, {end})" for start, end in local_ranges)]
    if normalized:
        labels = {"normalized_page_text": "规范化页文本", "normalized_document_text": "规范化文档文本"}
        parts.append("规范化位置：" + "、".join(
            f"{labels[basis]} [{start}, {end})" for basis, start, end in normalized
        ))
    else:
        parts.append("规范化位置未知")
    return "；".join(parts)


def _prepare_render(result: AnswerResult, sources: list[Source]):
    if (
        result.status != "program_validated" or result.draft is None or result.question is None
        or result.structural_validation != "passed" or result.source_validation != "passed"
    ):
        raise ValueError("只有结构和来源层通过的草稿才能渲染")
    report = validate_draft_layers(result.draft, sources)
    if report.issues:
        raise ValueError("草稿已不符合结构或来源校验")
    if result.review_fingerprint != review_fingerprint(result.question, result.draft, sources):
        raise ValueError("草稿、问题或来源已变化，请重新校验")
    if result.resolved_evidence != report.resolved_evidence:
        raise ValueError("引用定位信息与规范来源不一致")
    return report


def _render(result: AnswerResult, sources: list[Source], *, preview: bool, base_dir: Path | None) -> str:
    report = _prepare_render(result, sources)
    by_id = build_canonical_source_map(sources)
    anchors: dict[str, str] = {}
    # 按原始 claims/evidence 顺序分配，而非按重排后的章节或文件名分配。
    for claim in result.draft.claims:
        for ref in claim.evidence:
            if ref.source_id not in anchors:
                anchors[ref.source_id] = f"ref-{len(anchors) + 1}"

    def render_claim(claim) -> str:
        ids = dict.fromkeys(ref.source_id for ref in claim.evidence)
        citations = " ".join(f"[{_escape_text(sid)}](#{anchors[sid]})" for sid in ids)
        return f"- {_escape_text(claim.text)} {citations}"

    lines = [f"# {_escape_text(result.question)}", ""]
    if preview:
        lines.extend(["> 草稿预览：尚未作为正式报告发布。语义审核状态：待审核。", ""])
    if result.draft.status == "partial":
        lines.extend(["当前资料仅能回答部分问题。", ""])
    elif result.draft.status == "insufficient_evidence":
        lines.extend(["当前提供的资料不足以回答该问题。", ""])

    facts = [claim for claim in result.draft.claims if claim.kind == "fact"]
    if facts:
        lines.extend(["## 待审核的事实说法" if preview else "## 有证据支持的内容", ""])
        lines.extend(render_claim(claim) for claim in facts)
        lines.append("")
    inferences = [claim for claim in result.draft.claims if claim.kind == "inference"]
    if inferences or result.draft.limitations:
        lines.extend(["## 推断与局限", ""])
        lines.extend(render_claim(claim).replace("- ", "- 推断：", 1) for claim in inferences)
        lines.extend(f"- 局限：{_escape_text(text)}" for text in result.draft.limitations)
        lines.append("")

    if anchors:
        lines.extend(["## 参考资料", "", "位置为左闭右开的字符区间，不是原文件字节位置。", ""])
        for sid, anchor in anchors.items():
            source = by_id[sid]
            locations = [location for location in report.resolved_evidence if location.source_id == sid]
            lines.extend([
                f'<a id="{anchor}"></a>', "",
                f"- {_escape_text(sid)}：{_escape_text(source.title)}；"
                f"{_render_source_location(source, base_dir)}；{_escape_text(_render_positions(locations))}",
                "",
            ])
    return "\n".join(lines).rstrip() + "\n"


def render_answer_markdown(
    result: AnswerResult, visible_sources: list[Source], *, base_dir: Path | None = None,
) -> str:
    """正式渲染：逐项内容审核通过后才能调用，不修改原数据。"""
    result, sources = deepcopy(result), deepcopy(visible_sources)
    if not can_publish_answer(result, sources):
        raise ValueError("回答尚未通过完整审核，不能作为正式报告渲染")
    return _render(result, sources, preview=False, base_dir=base_dir)


def render_answer_preview(
    result: AnswerResult, visible_sources: list[Source], *, base_dir: Path | None = None,
) -> str:
    """仅渲染待审草稿；审核失败的内容不能通过预览伪装成正常报告。"""
    result, sources = deepcopy(result), deepcopy(visible_sources)
    if result.support_review != "pending":
        raise ValueError("预览仅用于 pending 草稿；已通过的使用正式入口，已失败的只看诊断")
    return _render(result, sources, preview=True, base_dir=base_dir)


def audit_reference_locations(
    result: AnswerResult, visible_sources: list[Source], *, base_dir: Path,
) -> list[ValidationIssue]:
    """显式检查实际引用的本地文件/PDF 页码；不请求网页，也不执行文件。"""
    _prepare_render(result, visible_sources)
    by_id = build_canonical_source_map(visible_sources)
    ids = dict.fromkeys(ref.source_id for claim in result.draft.claims for ref in claim.evidence)
    issues = []
    for sid in ids:
        source = by_id[sid]
        if source.url and _safe_web_url(source.url) is None:
            issues.append(ValidationIssue(
                code="unsafe_source_url", path=f"sources[{sid}].url",
                message="来源网址不是可点击的有效 http/https URL，将仅显示文本",
            ))
        if source.file_path:
            path = _local_path(source.file_path, base_dir)
            if path is None or not path.is_file():
                issues.append(ValidationIssue(
                    code="source_file_missing", path=f"sources[{sid}].file_path",
                    message="规范来源中的本地文件不存在或不是受支持的文件路径",
                ))
                continue
            if path.suffix.lower() == ".pdf":
                try:
                    import pymupdf

                    with pymupdf.open(path) as pdf:
                        if source.page is None or not 1 <= source.page <= pdf.page_count:
                            issues.append(ValidationIssue(
                                code="pdf_page_out_of_range", path=f"sources[{sid}].page",
                                message="物理页码缺失或超出实际 PDF 页数",
                            ))
                except (OSError, RuntimeError, ValueError):
                    issues.append(ValidationIssue(
                        code="pdf_unreadable", path=f"sources[{sid}].file_path",
                        message="无法读取实际 PDF 以核对物理页码",
                    ))
    return issues
