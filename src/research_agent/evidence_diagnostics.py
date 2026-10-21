"""阶段五：只统计候选重复与坐标重叠，不删除或合并证据。"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from .models import Source
from .retrieval import IndexDataError


@dataclass
class IdDedupDiagnostics:
    raw_count_by_branch: dict[str, int]
    unique_count_by_branch: dict[str, int]
    removed_count_by_branch: dict[str, int]
    shared_source_ids: list[str]
    unique_source_count: int
    raw_candidate_count: int
    within_branch_duplicate_count: int
    across_branch_extra_count: int
    repeated_candidate_rate: float


@dataclass
class EvidenceLocation:
    source_id: str
    title: str
    file_path: str | None
    page: int | None
    url: str | None
    offset: int | None
    end_offset: int | None
    offset_basis: str | None
    chunk_index: int | None


@dataclass
class DuplicateContentGroup:
    source_ids: list[str]
    locations: list[EvidenceLocation]


@dataclass
class OverlapPair:
    left_source_id: str
    right_source_id: str
    file_path: str
    page: int | None
    offset_basis: str
    overlap_start: int
    overlap_end: int
    overlap_chars: int


@dataclass
class CoordinateIssue:
    source_ids: list[str]
    reason: str


@dataclass
class ContentRedundancyDiagnostics:
    scope: str
    selected_source_ids: list[str]
    source_count: int
    duplicate_content_groups: list[DuplicateContentGroup]
    duplicate_content_group_count: int
    duplicate_content_extra_count: int
    adjacent_pairs_checked: int
    overlapping_adjacent_pair_count: int
    overlap_pairs: list[OverlapPair]
    coordinate_issues: list[CoordinateIssue]
    overlap_check_complete: bool


def analyze_id_duplicates(branches: dict[str, list[Source]]) -> IdDedupDiagnostics:
    """原始条目数为分母；每个 ID 每路最多计一次跨路出现。"""
    raw, unique, removed = {}, {}, {}
    branch_appearances: Counter[str] = Counter()
    for branch, hits in branches.items():
        ids = {source.source_id for source in hits}
        raw[branch], unique[branch] = len(hits), len(ids)
        removed[branch] = len(hits) - len(ids)
        branch_appearances.update(ids)
    raw_count = sum(raw.values())
    unique_count = len(branch_appearances)
    return IdDedupDiagnostics(
        raw, unique, removed,
        sorted(source_id for source_id, count in branch_appearances.items() if count > 1),
        unique_count, raw_count, sum(removed.values()), sum(unique.values()) - unique_count,
        (raw_count - unique_count) / raw_count if raw_count else 0.0,
    )


def _nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _location(source: Source) -> EvidenceLocation:
    metadata = source.metadata
    return EvidenceLocation(
        source.source_id, source.title, source.file_path, source.page, source.url,
        metadata.get("offset") if _nonnegative_int(metadata.get("offset")) else None,
        metadata.get("end_offset") if _nonnegative_int(metadata.get("end_offset")) else None,
        metadata.get("offset_basis") if isinstance(metadata.get("offset_basis"), str) else None,
        metadata.get("chunk_index") if _nonnegative_int(metadata.get("chunk_index")) else None,
    )


def _coordinate_error(source: Source) -> str | None:
    """只接受加载器的字符坐标契约；未知或损坏坐标不用于重叠统计。"""
    metadata = source.metadata
    if not source.file_path:
        return "missing_file_path"
    if any(name not in metadata for name in ("offset", "end_offset", "offset_basis", "chunk_index")):
        return "missing_coordinates"
    start, end = metadata["offset"], metadata["end_offset"]
    if not _nonnegative_int(start) or not _nonnegative_int(end) or end < start:
        return "invalid_interval"
    if end - start != len(source.content):
        return "coordinate_content_length_mismatch"
    if not _nonnegative_int(metadata["chunk_index"]):
        return "invalid_chunk_index"
    basis = metadata["offset_basis"]
    if basis not in ("normalized_document_text", "normalized_page_text"):
        return "unsupported_offset_basis"
    if basis == "normalized_page_text" and (
        not _nonnegative_int(source.page) or source.page == 0
    ):
        return "invalid_page_coordinates"
    if basis == "normalized_document_text" and source.page is not None:
        return "invalid_document_coordinates"
    return None


def analyze_content_redundancy(
    canonical_sources: list[Source], *, selected_ids: set[str] | None = None,
) -> ContentRedundancyDiagnostics:
    """只分析选中唯一 ID；相邻关系取自完整规范清单，不能跨越遗漏片段。"""
    canonical = {}
    for source in canonical_sources:
        if not source.source_id.strip() or source.source_id in canonical:
            raise IndexDataError("规范清单包含空或重复 source_id")
        canonical[source.source_id] = source
    if selected_ids is not None and (
        not isinstance(selected_ids, (set, frozenset))
        or any(not isinstance(source_id, str) for source_id in selected_ids)
    ):
        raise TypeError("selected_ids 必须是字符串集合或 None")
    selected = set(canonical) if selected_ids is None else set(selected_ids)
    if selected - canonical.keys():
        raise IndexDataError("selected_ids 包含未知 source_id")

    # 使用原始完整字符串作为键；不改空白、标点、大小写，也不做近似合并。
    contents: dict[str, list[str]] = defaultdict(list)
    for source_id in sorted(selected):
        contents[canonical[source_id].content].append(source_id)
    duplicates = [
        DuplicateContentGroup(ids, [_location(canonical[source_id]) for source_id in ids])
        for ids in contents.values() if len(ids) > 1
    ]
    duplicates.sort(key=lambda group: group.source_ids)

    issues, overlaps = [], []
    # 完整清单用于发现同坐标空间的重复 chunk_index，避免误认相邻关系。
    positions: dict[tuple[str, int | None, str], dict[int, list[Source]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for source in canonical_sources:
        error = _coordinate_error(source)
        if error:
            if source.source_id in selected:
                issues.append(CoordinateIssue([source.source_id], error))
            continue
        key = (source.file_path, source.page, source.metadata["offset_basis"])
        positions[key][source.metadata["chunk_index"]].append(source)

    checked = 0
    for group in positions.values():
        for members in group.values():
            selected_members = sorted(source.source_id for source in members if source.source_id in selected)
            if len(members) > 1 and selected_members:
                issues.append(CoordinateIssue(selected_members, "ambiguous_chunk_index"))
        for index, members in sorted(group.items()):
            next_members = group.get(index + 1, [])
            if len(members) != 1 or len(next_members) != 1:
                continue
            left, right = members[0], next_members[0]
            if left.source_id not in selected or right.source_id not in selected:
                continue
            if right.metadata["offset"] < left.metadata["offset"]:
                issues.append(CoordinateIssue([left.source_id, right.source_id], "nonmonotonic_offsets"))
                continue
            checked += 1
            start = max(left.metadata["offset"], right.metadata["offset"])
            end = min(left.metadata["end_offset"], right.metadata["end_offset"])
            if end <= start:
                continue
            left_text = left.content[start - left.metadata["offset"]:end - left.metadata["offset"]]
            right_text = right.content[start - right.metadata["offset"]:end - right.metadata["offset"]]
            if left_text != right_text:
                issues.append(CoordinateIssue([left.source_id, right.source_id], "overlap_text_mismatch"))
                continue
            overlaps.append(OverlapPair(
                left.source_id, right.source_id, left.file_path, left.page,
                left.metadata["offset_basis"], start, end, end - start,
            ))
    overlaps.sort(key=lambda pair: (pair.left_source_id, pair.right_source_id))
    issues.sort(key=lambda issue: (issue.source_ids, issue.reason))
    return ContentRedundancyDiagnostics(
        "canonical_corpus" if selected_ids is None else "selected_unique_sources",
        sorted(selected), len(selected), duplicates, len(duplicates),
        sum(len(group.source_ids) - 1 for group in duplicates),
        checked, len(overlaps), overlaps, issues, not issues,
    )
