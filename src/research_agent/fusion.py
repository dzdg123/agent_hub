"""阶段三、五：候选融合、精确 ID 去重及证据来源冗余诊断。"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .models import Source
from .retrieval import IndexDataError
from .evidence_diagnostics import (
    ContentRedundancyDiagnostics, IdDedupDiagnostics,
    analyze_content_redundancy, analyze_id_duplicates,
)


@dataclass
class FusionTrace:
    source_id: str
    branch: str
    raw_score: float
    metric: str
    rank: int
    normalized_score: float | None
    contribution: float
    distance: float | None = None


@dataclass
class FusionResult:
    method: str
    sources: list[Source]
    traces: list[FusionTrace]
    unique_candidate_count: int
    final_count: int
    parameters: dict[str, int | float]
    id_dedup_diagnostics: IdDedupDiagnostics | None = None
    content_redundancy_diagnostics: ContentRedundancyDiagnostics | None = None


def _positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} 必须是正整数，且不能是 bool")


def _identity(source: Source) -> dict:
    """只比较来源；检索轨迹、分数及加载时间不参与冲突判断。"""
    identity = source.model_dump(exclude={"score", "fetched_at"})
    identity["metadata"].pop("_retrieval", None)
    return identity


def _prepare(
    branches: dict[str, list[Source]], canonical_sources: list[Source],
) -> tuple[dict[str, list[Source]], dict[str, Source]]:
    """先校验每条候选，再保留每路首次出现的 ID；列表顺序即排名。"""
    canonical = {}
    for source in canonical_sources:
        if not source.source_id.strip() or source.source_id in canonical:
            raise IndexDataError(f"规范清单包含空或重复 source_id：{source.source_id!r}")
        if "_retrieval" in source.metadata:
            raise IndexDataError("规范 Source 不能包含运行时 _retrieval")
        canonical[source.source_id] = source.model_copy(deep=True)

    prepared = {}
    for branch, hits in branches.items():
        if not isinstance(branch, str) or not branch.strip():
            raise ValueError("分支名必须是非空字符串")
        seen, unique = set(), []
        for hit in hits:
            if (isinstance(hit.score, bool) or not isinstance(hit.score, (int, float))
                    or not math.isfinite(hit.score)):
                raise IndexDataError(f"{branch} 的 score 必须是有限数值：{hit.source_id}")
            if hit.source_id not in canonical:
                raise IndexDataError(f"{branch} 返回未知 source_id：{hit.source_id}")
            if _identity(hit) != _identity(canonical[hit.source_id]):
                raise IndexDataError(f"{branch} 的 Source 正文或来源冲突：{hit.source_id}")
            retrieval = hit.metadata.get("_retrieval", {})
            if not isinstance(retrieval, dict):
                raise IndexDataError("_retrieval 必须是字典")
            # 重复条目也必须先验证，不能用去重掩盖正文冲突。
            if hit.source_id not in seen:
                seen.add(hit.source_id)
                unique.append(hit.model_copy(deep=True))
        prepared[branch] = unique
    return prepared, canonical


def _trace(
    hit: Source, branch: str, rank: int, contribution: float,
    normalized_score: float | None = None,
) -> FusionTrace:
    retrieval = hit.metadata.get("_retrieval", {})
    metric = {"keyword": "token_count_cosine", "vector": "embedding_cosine"}.get(
        branch, retrieval.get("metric", "branch_score")
    )
    return FusionTrace(
        source_id=hit.source_id, branch=branch, raw_score=hit.score,
        metric=metric, rank=rank, normalized_score=normalized_score,
        contribution=contribution, distance=retrieval.get("distance"),
    )


def _finish(
    method: str, canonical: dict[str, Source], traces: list[FusionTrace],
    top_k: int, parameters: dict[str, int | float],
    id_diagnostics: IdDedupDiagnostics,
) -> FusionResult:
    """汇总贡献、稳定排序，并从规范 Source 深复制最终证据。"""
    totals: dict[str, float] = {}
    by_source: dict[str, list[FusionTrace]] = {}
    for trace in traces:
        totals[trace.source_id] = totals.get(trace.source_id, 0.0) + trace.contribution
        by_source.setdefault(trace.source_id, []).append(trace)
    ordered = sorted(totals, key=lambda source_id: (-totals[source_id], source_id))
    sources = []
    for source_id in ordered[:top_k]:
        source = canonical[source_id].model_copy(deep=True, update={"score": totals[source_id]})
        source.metadata["_retrieval"] = {
            "method": method, "metric": f"{method}_fusion",
            "parameters": dict(parameters),
            "branches": [asdict(trace) for trace in by_source[source_id]],
        }
        sources.append(source)
    content_diagnostics = analyze_content_redundancy(list(canonical.values()), selected_ids=set(totals))
    content_diagnostics.scope = "unique_candidates_before_top_k"
    return FusionResult(
        method, sources, traces, len(totals), len(sources), dict(parameters),
        id_diagnostics, content_diagnostics,
    )


def fuse_rrf(
    branches: dict[str, list[Source]],
    *,
    canonical_sources: list[Source],
    top_k: int = 3,
    rank_constant: int = 60,
) -> FusionResult:
    """按去重后的连续排名融合；缺席分支没有贡献，不使用原分数加权。"""
    _positive_int(top_k, "top_k")
    _positive_int(rank_constant, "rank_constant")
    prepared, canonical = _prepare(branches, canonical_sources)
    traces = [
        _trace(hit, branch, rank, 1.0 / (rank_constant + rank))
        for branch, hits in prepared.items()
        for rank, hit in enumerate(hits, start=1)
    ]
    return _finish("rrf", canonical, traces, top_k, {"rank_constant": rank_constant},
                   analyze_id_duplicates(branches))


def fuse_min_max(
    branches: dict[str, list[Source]],
    *,
    canonical_sources: list[Source],
    top_k: int = 3,
    equal_score_value: float = 1.0,
) -> FusionResult:
    """关键词/向量各占 0.5；全部同分时统一赋 1 或 0，仅作教学对照。"""
    _positive_int(top_k, "top_k")
    if (isinstance(equal_score_value, bool)
            or not isinstance(equal_score_value, (int, float))
            or equal_score_value not in (0.0, 1.0)):
        raise ValueError("equal_score_value 只能是 0 或 1，且不能是 bool")
    if set(branches) - {"keyword", "vector"}:
        raise ValueError("等权 min-max 仅接受 keyword 和 vector 分支")
    prepared, canonical = _prepare(branches, canonical_sources)
    traces = []
    for branch, hits in prepared.items():
        if not hits:
            continue
        low, high = min(hit.score for hit in hits), max(hit.score for hit in hits)
        for rank, hit in enumerate(hits, start=1):
            if high == low:
                normalized = float(equal_score_value)
            elif math.isfinite(high - low):
                normalized = (hit.score - low) / (high - low)
            else:
                # 有限极大正负值相减可能溢出，先同比缩放再计算。
                scale = max(abs(low), abs(high))
                normalized = (hit.score / scale - low / scale) / (high / scale - low / scale)
            traces.append(_trace(hit, branch, rank, 0.5 * normalized, normalized))
    return _finish("min_max", canonical, traces, top_k, {
        "keyword_weight": 0.5, "vector_weight": 0.5,
        "equal_score_value": float(equal_score_value),
    }, analyze_id_duplicates(branches))
