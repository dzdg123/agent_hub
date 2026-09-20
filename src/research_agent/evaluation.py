from __future__ import annotations

from dataclasses import dataclass

from .citations import citation_ids, validate_citations
from .models import Source


@dataclass(frozen=True)
class EvaluationResult:
    total: int
    passed: int

    @property
    def rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


def retrieval_hit_rate(results: list[list[Source]], expected_ids: list[set[str]]) -> EvaluationResult:
    if len(results) != len(expected_ids):
        raise ValueError("results 与 expected_ids 数量必须一致")
    passed = sum(bool({item.source_id for item in found} & expected) for found, expected in zip(results, expected_ids))
    return EvaluationResult(total=len(results), passed=passed)


def citation_integrity(report: str, sources: list[Source]) -> EvaluationResult:
    cited = citation_ids(report)
    invalid = set(validate_citations(report, sources))
    return EvaluationResult(total=len(cited), passed=len(cited - invalid))


def task_success_rate(statuses: list[str]) -> EvaluationResult:
    return EvaluationResult(total=len(statuses), passed=sum(status == "completed" for status in statuses))

