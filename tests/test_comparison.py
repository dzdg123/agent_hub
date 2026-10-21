import csv
import json
from copy import deepcopy

import pytest

from research_agent.comparison import (
    REVIEW_FIELDS, TimedCandidateIndex, aggregate_comparison, compare_query,
    make_review_rows, render_comparison_report,
)
from research_agent.models import Source
from research_agent.retrieval import KeywordIndex
from research_agent.retrieval_errors import RetrievalOperationalError
from research_agent.retrieval_pipeline import TwoBranchRetriever


class RankedIndex(KeywordIndex):
    def __init__(self, canonical, order):
        super().__init__()
        self.add(canonical)
        self.order = order
        self.calls = []
        self.failure = False

    def search(self, query, top_k=5, *, allowed_ids=None):
        self.calls.append((query, top_k, allowed_ids))
        if self.failure:
            raise RetrievalOperationalError("controlled failure")
        lookup = {source.source_id: source for source in self.all()}
        return [lookup[sid].model_copy(deep=True, update={"score": 1 / rank})
                for rank, sid in enumerate(self.order, 1)
                if allowed_ids is None or sid in allowed_ids][:top_k]


def experiment(*, long_evidence=False):
    sources = [Source(source_id=sid, title=sid, content=sid * (3000 if long_evidence and sid == "D" else 10),
                      file_path=f"{sid}.md", metadata={"relative_path": f"{sid}.md", "file_type": "markdown"})
               for sid in "ABCDEF"]
    keyword, vector = RankedIndex(sources, "ABCDEF"), RankedIndex(sources, "DEFBCA")
    indexes = {"keyword": TimedCandidateIndex(keyword), "vector": TimedCandidateIndex(vector)}
    retriever = TwoBranchRetriever(sources, keyword_index=indexes["keyword"], vector_index=indexes["vector"])
    entry = {"query_id": "Q01", "question": "question", "group": "baseline", "filters": {},
             "has_allowed_evidence": True, "evidence_quote": "D evidence", "acceptable_source_ids": ["D"]}
    result = compare_query(retriever, sources, entry, timed_indexes=indexes)
    raw = {"run_id": "controlled-test", "candidate_k": 6, "top_k": 3, "rank_constant": 60,
           "max_context_chars": 2000, "queries": [result]}
    return raw, sources, retriever, keyword, vector, entry


def graded(raw, supporting="D"):
    rows = make_review_rows(raw)
    for row in rows:
        row.update(support_level="2" if row["source_id"] == supporting else "0",
                   reason="controlled evidence judgment", reviewer="human:test", human_checked="yes")
    return rows


def test_each_branch_called_once_with_equal_window_and_rrf_uses_full_candidates():
    raw, sources, _, keyword, vector, _ = experiment()
    query = raw["queries"][0]
    assert len(keyword.calls) == len(vector.calls) == 1
    assert keyword.calls[0][1:] == vector.calls[0][1:]
    assert keyword.calls[0][1] == 6
    assert [item["source_id"] for item in query["methods"]["keyword"]["sources"]] == list("ABC")
    assert [item["source_id"] for item in query["methods"]["vector"]["sources"]] == list("DEF")
    assert query["methods"]["rrf"]["sources"][0]["source_id"] == "D"  # keyword第4名也参与贡献
    assert query["duplicate_diagnostics"]["raw_candidate_count"] == 12
    assert query["duplicate_diagnostics"]["unique_source_count"] == 6
    assert len(make_review_rows(raw)) == 6
    assert all(value is not None for value in query["search_ms"].values())
    assert query["methods"]["rrf"]["hot_retrieval_ms"] == pytest.approx(
        sum(query["search_ms"].values()) + query["fusion_ms"])
    before = deepcopy(sources)
    query["methods"]["rrf"]["sources"][0]["content"] = "changed"
    assert sources == before


def test_reviewed_metrics_include_budget_losses_and_duplicate_denominator():
    raw, *_ = experiment(long_evidence=True)
    summary = aggregate_comparison(raw, graded(raw))
    methods = summary["groups"]["baseline"]["methods"]
    assert methods["keyword"]["hit_at_3"] == 0
    assert methods["vector"]["hit_at_3"] == methods["rrf"]["hit_at_3"] == 1
    assert methods["vector"]["top1_support_rate"] == 1
    assert methods["vector"]["context_retained_hit_rate"] == 0
    assert methods["rrf"]["context_retained_hit_rate"] == 0
    assert summary["groups"]["baseline"]["candidate_repetition"]["rate"] == 0.5
    for result in raw["queries"][0]["methods"].values():
        assert result["context"]["used_chars"] == len(result["context"]["text"]) <= 2000
    text = render_comparison_report(raw, summary, graded(raw))
    assert "向量优势：Q01" in text
    assert "已审核样本未观察到" in text


def test_pending_reviews_do_not_become_automatic_scores():
    raw, *_ = experiment()
    rows = make_review_rows(raw)
    summary = aggregate_comparison(raw, rows)
    assert summary["pending_candidate_rows"] == 6
    for method in summary["groups"]["baseline"]["methods"].values():
        assert method["hit_at_3"] is None
    assert "尚不宣称优势" in render_comparison_report(raw, summary, rows)


def test_keyword_advantage_top1_changes_and_new_unsupported_candidates_are_visible():
    raw, *_ = experiment()
    rows = graded(raw, supporting="A")
    summary = aggregate_comparison(raw, rows)
    query = summary["per_query"][0]
    assert query["methods"]["keyword"]["hit"] == 1
    assert query["methods"]["vector"]["hit"] == 0
    # RRF引入B，审核为0级；不是把跨路重合本身当成坏事。
    assert "B" in query["rrf_added_unsupported_ids_vs_vector"]
    assert "关键词优势：Q01" in render_comparison_report(raw, summary, rows)


def test_groups_have_independent_denominators():
    raw, *_ = experiment()
    challenge = deepcopy(raw["queries"][0])
    challenge.update(query_id="C01", group="challenge")
    probe = deepcopy(challenge)
    probe.update(query_id="C02", has_allowed_evidence=False)
    raw["queries"] += [challenge, probe]
    summary = aggregate_comparison(raw, graded(raw))
    assert summary["groups"]["baseline"]["positive_denominator"] == 1
    assert summary["groups"]["challenge"]["positive_denominator"] == 1
    assert summary["groups"]["challenge"]["no_evidence_count"] == 1


def test_empty_results_are_misses_and_probe_does_not_change_denominator():
    raw, sources, retriever, keyword, vector, entry = experiment()
    keyword.order = vector.order = ""
    empty = compare_query(retriever, sources, {**entry, "query_id": "Q02"})
    probe = compare_query(retriever, sources, {**entry, "query_id": "N01", "has_allowed_evidence": False})
    raw["queries"] += [empty, probe]
    summary = aggregate_comparison(raw, graded(raw))
    group = summary["groups"]["baseline"]
    assert group["positive_denominator"] == 2
    assert group["no_evidence_count"] == 1
    assert group["methods"]["vector"]["hit_at_3"] == 0.5
    assert summary["per_query"][1]["methods"]["vector"]["hit"] == 0


def test_failed_questions_remain_in_denominator_and_invalidate_full_score():
    raw, sources, retriever, _, vector, entry = experiment()
    vector.failure = True
    failed = compare_query(retriever, sources, {**entry, "query_id": "Q02"})
    raw["queries"].append(failed)
    summary = aggregate_comparison(raw, graded(raw))
    group = summary["groups"]["baseline"]
    assert group["positive_denominator"] == 2
    assert summary["failed_query_ids"] == ["Q02"]
    assert all(score["hit_at_3"] is None for score in group["methods"].values())
    assert failed["methods"] == {}


def test_filters_apply_to_all_three_methods_and_contexts():
    _, sources, retriever, _, _, entry = experiment()
    result = compare_query(retriever, sources, {**entry, "filters": {"relative_paths": ["D.md"]}})
    assert result["allowed_source_ids"] == ["D"]
    for method in result["methods"].values():
        assert [source["source_id"] for source in method["sources"]] == ["D"]
        assert method["context"]["included_source_ids"] == ["D"]
        assert method["filter_violation_count"] == method["context_filter_violation_count"] == 0


@pytest.mark.parametrize("change", ["delete", "duplicate", "content", "grade", "reason", "reviewer"])
def test_review_validation_rejects_tampering_and_incomplete_annotations(change):
    raw, *_ = experiment()
    rows = graded(raw)
    if change == "delete": rows.pop()
    elif change == "duplicate": rows[-1] = deepcopy(rows[0])
    elif change == "content": rows[0]["content"] = "altered"
    elif change == "grade": rows[0]["support_level"] = "3"
    else: rows[0][change] = ""
    with pytest.raises(ValueError):
        aggregate_comparison(raw, rows)


def test_report_round_trip_and_raw_integrity(tmp_path):
    from examples.day09_compare import digest, report, save_review, write_json
    raw, *_ = experiment()
    write_json(tmp_path / "raw_results.json", raw)
    write_json(tmp_path / "raw_integrity.json", {"sha256": digest(tmp_path / "raw_results.json")})
    save_review(tmp_path, raw)
    before = (tmp_path / "review.csv").read_bytes()
    report(tmp_path)
    assert (tmp_path / "review.csv").read_bytes() == before
    with (tmp_path / "review.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(graded(raw))
    assert report(tmp_path)["groups"]["baseline"]["methods"]["vector"]["hit_at_3"] == 1
    assert len(list((tmp_path / "reports").glob("*.json"))) == 2
    raw["candidate_k"] = 99
    write_json(tmp_path / "raw_results.json", raw)
    with pytest.raises(ValueError, match="原始结果"):
        report(tmp_path)


def test_fixed_challenges_keep_baseline_and_resolve_filtered_evidence():
    from examples.day09_compare import DEFAULT_CHALLENGES, DEFAULT_DATASET, load_questions
    sources = [Source.model_validate(json.loads(line)) for line in
               (DEFAULT_DATASET / "sources.jsonl").read_text(encoding="utf-8").splitlines()]
    labels = json.loads((DEFAULT_DATASET / "resolved_labels.json").read_text(encoding="utf-8"))
    before = deepcopy(labels)
    entries = load_questions(labels, sources, DEFAULT_CHALLENGES)
    assert labels == before
    assert len(entries) == 18
    assert sum(entry["has_allowed_evidence"] for entry in entries if entry["group"] == "baseline") == 10
    assert sum(entry["has_allowed_evidence"] for entry in entries if entry["group"] == "challenge") == 5
    assert entries[-1]["acceptable_source_ids"] == []


def test_challenge_evidence_flag_is_verified_before_running(tmp_path):
    from examples.day09_compare import DEFAULT_CHALLENGES, DEFAULT_DATASET, load_questions
    sources = [Source.model_validate(json.loads(line)) for line in
               (DEFAULT_DATASET / "sources.jsonl").read_text(encoding="utf-8").splitlines()]
    labels = json.loads((DEFAULT_DATASET / "resolved_labels.json").read_text(encoding="utf-8"))
    entries = [json.loads(line) for line in DEFAULT_CHALLENGES.read_text(encoding="utf-8").splitlines()]
    entries[-1]["has_allowed_evidence"] = True
    changed = tmp_path / "challenge-v2.jsonl"
    changed.write_text("\n".join(json.dumps(entry) for entry in entries), encoding="utf-8")
    with pytest.raises(ValueError, match="证据声明"):
        load_questions(labels, sources, changed)


def test_other_top_k_is_rejected_to_keep_hit_at_3_definition():
    _, sources, retriever, _, _, entry = experiment()
    with pytest.raises(ValueError, match="top_k=3"):
        compare_query(retriever, sources, entry, top_k=2)
