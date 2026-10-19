import copy
import csv

import pytest

from examples.day08_evaluate_retrieval import (
    FIELDS, aggregate, digest, report, review_rows, write_json,
)


def fake_run():
    queries = []
    for number in range(1, 13):
        positive = number <= 10
        queries.append({
            "query_id": f"Q{number:02}" if positive else f"N{number-10:02}",
            "question": "测试问题", "kind": "positive" if positive else "probe",
            "expected_relative_path": "notes.md", "expected_page": None,
            "evidence_quote": "直接证据", "reason": "无目标答案",
            "candidates": [{
                "rank": rank, "source_id": f"doc-{rank}",
                "relative_path": "notes.md", "file_path": "notes.md", "page": None,
                "content": "主题有关，是否支持需看正文", "distance": rank / 10,
                "score": 1 - rank / 10,
                "preannotated_evidence_match": rank == 1 and positive,
            } for rank in range(1, 4)],
        })
    return {"run_id": "fake", "config": {"resolved_model_commit": "test"},
            "queries": queries, "preannotation_id_hit_at_3": 1.0}


def csv_rows(raw):
    return [{key: str(value) for key, value in row.items()} for row in review_rows(raw)]


def graded_rows(raw):
    rows = csv_rows(raw)
    for row in rows:
        row["support_level"] = "2" if row["rank"] == "1" else "1"
        row["reason"] = "测试指定的原文证据判断"
    return rows


def test_automatic_label_hit_does_not_replace_pending_manual_review():
    raw = fake_run()
    summary = aggregate(raw, csv_rows(raw))
    assert summary["preannotation_id_hit_at_3"] == 1.0
    assert summary["manual_hit_at_3"] is None
    assert summary["pending_candidate_rows"] == 36
    assert summary["teaching_target_met"] is None


def test_only_direct_support_counts_and_probes_do_not_change_denominator():
    raw = fake_run()
    rows = graded_rows(raw)
    for row in rows:
        if row["query_id"] in {"Q09", "Q10"}:
            row["support_level"] = "1"
    summary = aggregate(raw, rows)
    assert summary["manual_hit_count"] == 8
    assert summary["manual_hit_at_3"] == 0.8
    assert summary["positive_denominator"] == 10
    assert summary["teaching_target_met"] is True


def test_partial_review_does_not_shrink_positive_denominator():
    raw = fake_run()
    rows = graded_rows(raw)
    rows[0]["support_level"] = ""
    summary = aggregate(raw, rows)
    assert summary["reviewed_positive_questions"] == 9
    assert summary["manual_hit_at_3"] is None


@pytest.mark.parametrize("change", ["remove", "duplicate", "content", "grade", "reason"])
def test_invalid_or_tampered_review_is_rejected(change):
    raw = fake_run()
    rows = graded_rows(raw)
    if change == "remove":
        rows.pop()
    elif change == "duplicate":
        rows[1] = copy.deepcopy(rows[0])
    elif change == "content":
        rows[0]["content"] = "修改过的证据"
    elif change == "grade":
        rows[0]["support_level"] = "3"
    else:
        rows[0]["reason"] = ""
    with pytest.raises(ValueError):
        aggregate(raw, rows)


def test_report_runs_offline_and_retains_review_history(tmp_path):
    raw = fake_run()
    write_json(tmp_path / "raw_results.json", raw)
    write_json(tmp_path / "raw_integrity.json", {"sha256": digest(tmp_path / "raw_results.json")})
    with (tmp_path / "review.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(graded_rows(raw))
    assert report(tmp_path)["manual_hit_at_3"] == 1.0
    assert (tmp_path / "review.md").is_file()
    assert len(list((tmp_path / "reports").glob("*.json"))) == 1
    raw["queries"].pop()
    write_json(tmp_path / "raw_results.json", raw)
    with pytest.raises(ValueError, match="原始检索结果被改动"):
        report(tmp_path)
