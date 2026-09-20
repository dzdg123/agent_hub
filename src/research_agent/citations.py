from __future__ import annotations

import re

from .models import Source


CITATION_PATTERN = re.compile(r"\[([^\[\]]+)\]")


def citation_ids(report: str) -> set[str]:
    return {match for match in CITATION_PATTERN.findall(report) if match.startswith(("doc-", "web-"))}


def validate_citations(report: str, sources: list[Source]) -> list[str]:
    known = {source.source_id for source in sources}
    return sorted(citation_ids(report) - known)


def append_references(report: str, sources: list[Source]) -> str:
    used = citation_ids(report)
    references: list[str] = []
    for source in sources:
        if source.source_id not in used:
            continue
        location = source.url or source.file_path or "未知来源"
        if source.page:
            location = f"{location}，第 {source.page} 页"
        references.append(f"- [{source.source_id}] {source.title} — {location}")
    if not references:
        return report.rstrip()
    return f"{report.rstrip()}\n\n## 参考资料\n\n" + "\n".join(references)

