"""Day 09：共同语料、过滤、两路候选、RRF 和显式失败/降级契约。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Literal, Protocol
from uuid import uuid4

from research_agent.models import Source
from research_agent.retrieval import IndexDataError
from research_agent.fusion import FusionResult, fuse_rrf
from research_agent.source_filters import normalize_filters, resolve_allowed_ids
from research_agent.retrieval_errors import RetrievalOperationalError


class CandidateIndex(Protocol):
    """协调层依赖的最小接口；关键词和向量索引都遵循它。"""

    def all(self) -> list[Source]: ...

    def search(
        self, query: str, top_k: int = 5, *, allowed_ids: set[str] | None = None,
    ) -> list[Source]: ...


class LazyCandidateIndex:
    """将模型加载、打开/建立索引等准备工作放到请求的计时和错误边界内。"""

    def __init__(self, factory: Callable[[], CandidateIndex]) -> None:
        self._factory = factory
        self._index: CandidateIndex | None = None

    def ready(self) -> CandidateIndex:
        # 只缓存成功创建的索引；后续请求可重新尝试之前失败的初始化。
        if self._index is None:
            self._index = self._factory()
        return self._index

    def all(self) -> list[Source]:
        return self.ready().all()

    def search(self, query: str, top_k: int = 5, *, allowed_ids: set[str] | None = None) -> list[Source]:
        return self.ready().search(query, top_k, allowed_ids=allowed_ids)


@dataclass
class RetrievalTrace:
    source_id: str
    branch: str
    raw_score: float
    metric: str
    rank: int
    distance: float | None = None
    fusion_contribution: float | None = None


@dataclass
class BranchResult:
    sources: list[Source]
    traces: list[RetrievalTrace]
    status: Literal["ok", "empty", "skipped", "failed"]
    elapsed_ms: float
    candidate_count: int | None
    skip_reason: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    failure_stage: str | None = None
    error_operation: str | None = None


@dataclass
class CandidateResult:
    branches: dict[str, BranchResult]
    requested_candidate_k: int
    effective_candidate_k: int
    requested_top_k: int
    total_source_count: int
    allowed_source_count: int
    # 尚未融合或整体失败时 None；完成融合但没有结果时才是 [] / 0。
    final_sources: list[Source] | None = None
    final_count: int | None = None
    degraded_reason: str | None = None
    fusion: FusionResult | None = None
    filters: dict[str, list[str]] | None = None
    requested_allowed_ids: list[str] | None = None
    query_id: str = ""
    status: Literal["ok", "empty", "skipped", "degraded", "failed"] = "ok"
    allow_degraded: bool = False
    failure_reason: str | None = None


def _positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} 必须是正整数，且不能是 bool")


def _source_map(sources: list[Source]) -> dict[str, Source]:
    result = {}
    for source in sources:
        if not source.source_id.strip():
            raise IndexDataError("source_id 不能为空")
        if source.source_id in result:
            raise IndexDataError(f"重复 source_id：{source.source_id}")
        if "_retrieval" in source.metadata:
            raise IndexDataError("规范 Source 不能包含运行时 _retrieval")
        result[source.source_id] = source.model_copy(deep=True)
    return result


def _source_identity(source: Source) -> dict:
    # fetched_at 是加载时间，不代表正文版本；score 是查询运行时字段。
    return source.model_dump(exclude={"score", "fetched_at"})


class TwoBranchRetriever:
    """协调两路候选与 RRF；全库来源一致性检查适用于当前小语料。"""

    def __init__(
        self, sources: list[Source], *, keyword_index: CandidateIndex,
        vector_index: CandidateIndex,
    ) -> None:
        self._canonical = _source_map(sources)
        self._indexes = {"keyword": keyword_index, "vector": vector_index}
        for branch, index in self._indexes.items():
            if isinstance(index, LazyCandidateIndex):
                continue
            try:
                self._validate_index(branch, index)
            except RetrievalOperationalError:
                # 运行故障延后到请求内计时并报告；一致性错误始终抛出。
                pass

    def _validate_index(self, branch: str, index: CandidateIndex) -> None:
        # 检查额外 ID、缺失 ID 及同 ID 内容不同；不自动修改或清空持久化库。
        actual = _source_map(index.all())
        if actual.keys() != self._canonical.keys():
            raise IndexDataError(f"{branch} 的 ID 集合与规范 Source 不一致")
        for source_id, source in actual.items():
            if _source_identity(source) != _source_identity(self._canonical[source_id]):
                raise IndexDataError(f"{branch} 的 Source 内容或来源冲突：{source_id}")

    def search(
        self, query: str, *, candidate_k: int = 6, top_k: int = 3,
        allowed_ids: set[str] | None = None, rank_constant: int = 60,
        filters: dict[str, set[str]] | None = None,
        allow_degraded: bool = False, query_id: str | None = None,
    ) -> CandidateResult:
        """两路召回后执行 RRF，返回候选、最终证据和融合轨迹。"""
        _positive_int(rank_constant, "rank_constant")
        result = self.retrieve_candidates(
            query, candidate_k=candidate_k, top_k=top_k, allowed_ids=allowed_ids,
            filters=filters, allow_degraded=allow_degraded, query_id=query_id,
        )
        if result.status == "failed":
            return result  # 失败的 final_sources/final_count/fusion 保持 None。
        fusion = fuse_rrf(
            {name: branch.sources for name, branch in result.branches.items()
             if branch.status != "failed"},
            canonical_sources=list(self._canonical.values()),
            top_k=top_k, rank_constant=rank_constant,
        )
        result.fusion = fusion
        result.final_sources = [source.model_copy(deep=True) for source in fusion.sources]
        result.final_count = fusion.final_count
        contributions = {(trace.branch, trace.source_id): trace.contribution for trace in fusion.traces}
        for name, branch in result.branches.items():
            for trace in branch.traces:
                trace.fusion_contribution = contributions[(name, trace.source_id)]
        return result

    def retrieve_candidates(
        self, query: str, *, candidate_k: int = 6, top_k: int = 3,
        allowed_ids: set[str] | None = None,
        filters: dict[str, set[str]] | None = None,
        allow_degraded: bool = False, query_id: str | None = None,
    ) -> CandidateResult:
        _positive_int(candidate_k, "candidate_k")
        _positive_int(top_k, "top_k")
        if candidate_k < top_k:
            raise ValueError("candidate_k 不能小于 top_k")
        if not isinstance(query, str):
            raise TypeError("query 必须是字符串")
        if type(allow_degraded) is not bool:
            raise TypeError("allow_degraded 必须是 bool")
        if query_id is not None and (not isinstance(query_id, str) or not query_id.strip()):
            raise ValueError("query_id 必须是非空字符串或 None")
        if allowed_ids is not None and (
            not isinstance(allowed_ids, (set, frozenset))
            or any(not isinstance(item, str) for item in allowed_ids)
        ):
            raise TypeError("allowed_ids 必须是字符串集合或 None")

        normalized_filters = normalize_filters(filters)
        filter_ids = resolve_allowed_ids(list(self._canonical.values()), normalized_filters)
        allowed = set(self._canonical)
        if filter_ids is not None:
            allowed.intersection_update(filter_ids)
        if allowed_ids is not None:
            allowed.intersection_update(allowed_ids)
        effective_k = min(candidate_k, len(allowed))
        result = CandidateResult(
            branches={}, requested_candidate_k=candidate_k,
            effective_candidate_k=effective_k, requested_top_k=top_k,
            total_source_count=len(self._canonical), allowed_source_count=len(allowed),
            filters={name: sorted(values) for name, values in normalized_filters.items()} or None,
            requested_allowed_ids=sorted(allowed_ids) if allowed_ids is not None else None,
            query_id=query_id if query_id is not None else uuid4().hex,
            allow_degraded=allow_degraded,
        )
        if not query.strip() or not allowed:
            reason = "blank_query" if not query.strip() else "no_allowed_sources"
            result.branches = {
                branch: BranchResult([], [], "skipped", 0.0, 0, reason)
                for branch in self._indexes
            }
            result.status = "skipped"
            return result

        # 再检查一次，防止创建协调器后其中一个索引发生改变。
        metrics = {"keyword": "token_count_cosine", "vector": "embedding_cosine"}
        for branch, index in self._indexes.items():
            started = perf_counter()
            stage = "validation_read"
            try:
                if isinstance(index, LazyCandidateIndex):
                    stage = "initialization"
                    index = index.ready()
                stage = "validation_read"
                self._validate_index(branch, index)
                stage = "search"
                hits = index.search(query, top_k=effective_k, allowed_ids=set(allowed))
            except RetrievalOperationalError as exc:
                result.branches[branch] = BranchResult(
                    sources=[], traces=[], status="failed",
                    elapsed_ms=(perf_counter() - started) * 1000, candidate_count=None,
                    error_type=exc.error_type, error_message=str(exc),
                    failure_stage=stage, error_operation=exc.operation,
                )
                continue
            elapsed_ms = (perf_counter() - started) * 1000
            if len(hits) > effective_k:
                raise IndexDataError(f"{branch} 返回数量超过候选上限")
            seen = set()
            copies, traces = [], []
            for rank, hit in enumerate(hits, start=1):
                if not math.isfinite(hit.score):
                    raise IndexDataError(f"{branch} 返回了非法 score")
                if hit.source_id not in allowed or hit.source_id in seen:
                    raise IndexDataError(f"{branch} 返回了越界或重复 ID：{hit.source_id}")
                seen.add(hit.source_id)
                comparable = hit.model_copy(deep=True)
                retrieval = comparable.metadata.pop("_retrieval", {})
                if not isinstance(retrieval, dict):
                    raise IndexDataError(f"{branch} 的 _retrieval 必须是字典")
                if _source_identity(comparable) != _source_identity(self._canonical[hit.source_id]):
                    raise IndexDataError(f"{branch} 查询结果与规范 Source 冲突：{hit.source_id}")
                copies.append(hit.model_copy(deep=True))
                traces.append(RetrievalTrace(
                    source_id=hit.source_id, branch=branch, raw_score=hit.score,
                    metric=metrics[branch], rank=rank,
                    distance=retrieval.get("distance") if branch == "vector" else None,
                ))
            result.branches[branch] = BranchResult(
                sources=copies, traces=traces, status="ok" if hits else "empty",
                elapsed_ms=elapsed_ms, candidate_count=len(hits),
            )
        failures = [name for name, branch in result.branches.items() if branch.status == "failed"]
        if failures:
            detail = "; ".join(
                f"{name}: {result.branches[name].error_type}: {result.branches[name].error_message}"
                for name in failures
            )
            if len(failures) == len(self._indexes) or not allow_degraded:
                result.status = "failed"
                result.failure_reason = ("两路均失败" if len(failures) == len(self._indexes)
                                         else "未允许降级") + "; " + detail
            else:
                result.status = "degraded"
                result.degraded_reason = detail
        else:
            result.status = "ok" if any(branch.sources for branch in result.branches.values()) else "empty"
        return result
