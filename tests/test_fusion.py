from copy import deepcopy

import pytest

from research_agent.fusion import fuse_min_max, fuse_rrf
from research_agent.models import Source
from research_agent.retrieval import IndexDataError, merge_ranked


def fixture_sources():
    return [Source(source_id=name, title=name, content=f"content {name}",
                   metadata={"nested": {"offset": 10}}) for name in "ABCD"]


def ranked(canonical, names, scores=None):
    lookup = {source.source_id: source for source in canonical}
    scores = scores if scores is not None else [1.0] * len(names)
    return [lookup[name].model_copy(deep=True, update={"score": score})
            for name, score in zip(names, scores, strict=True)]


@pytest.mark.day09_case("F01")
def test_rrf_matches_hand_calculation_and_keeps_omitted_candidate_traces():
    canonical = fixture_sources()
    branches = {"keyword": ranked(canonical, "ABC"), "vector": ranked(canonical, "BDA")}
    result = fuse_rrf(branches, canonical_sources=canonical, top_k=4)
    assert [source.source_id for source in result.sources] == list("BADC")
    assert [source.score for source in result.sources] == pytest.approx([
        1 / 62 + 1 / 61, 1 / 61 + 1 / 63, 1 / 62, 1 / 63,
    ])
    assert result.unique_candidate_count == result.final_count == 4
    top = fuse_rrf(branches, canonical_sources=canonical, top_k=3)
    assert [source.source_id for source in top.sources] == list("BAD")
    assert len(top.traces) == 6  # C 被截掉，但仍有完整的贡献记录。


@pytest.mark.day09_case("F02")
def test_duplicate_is_removed_before_continuous_rank_and_only_contributes_once():
    canonical = fixture_sources()
    vector = ranked(canonical, "BDA")
    expected = fuse_rrf({"keyword": ranked(canonical, "ABC"), "vector": vector},
                        canonical_sources=canonical, top_k=4)
    actual = fuse_rrf({"keyword": ranked(canonical, "AABC"), "vector": vector},
                      canonical_sources=canonical, top_k=4)
    assert actual.sources == expected.sources
    assert actual.traces == expected.traces
    assert actual.content_redundancy_diagnostics == expected.content_redundancy_diagnostics
    assert actual.id_dedup_diagnostics.removed_count_by_branch == {"keyword": 1, "vector": 0}
    assert expected.id_dedup_diagnostics.removed_count_by_branch == {"keyword": 0, "vector": 0}
    assert [trace.rank for trace in actual.traces if trace.branch == "keyword"] == [1, 2, 3]
    assert merge_ranked([ranked(canonical, "AABC"), vector]) == merge_ranked([
        ranked(canonical, "ABC"), vector,
    ])


@pytest.mark.parametrize("field,value", [
    ("content", "changed"), ("title", "changed"), ("file_path", "changed.pdf"),
    ("page", 2), ("url", "https://example.test/changed"),
    ("metadata", {"nested": {"offset": 99}}),
])
@pytest.mark.day09_case("F05")
def test_conflict_including_duplicate_entry_is_not_hidden(field, value):
    canonical = fixture_sources()
    valid = ranked(canonical, "A")[0]
    changed = valid.model_copy(deep=True, update={field: value})
    with pytest.raises(IndexDataError, match="冲突"):
        fuse_rrf({"keyword": [valid, changed]}, canonical_sources=canonical)
    with pytest.raises(IndexDataError, match="冲突"):
        merge_ranked([[valid], [changed]])


@pytest.mark.day09_case("F06")
def test_runtime_fields_are_ignored_inputs_not_modified_and_outputs_are_deep_copies():
    canonical = fixture_sources()
    hits = ranked(canonical, "A", [0.1])
    hits[0].metadata["_retrieval"] = {"metric": "cosine", "distance": 0.9, "rank": 90}
    before, originals = deepcopy(hits), deepcopy(canonical)
    result = fuse_rrf({"vector": hits}, canonical_sources=canonical)
    another = fuse_rrf({"vector": hits}, canonical_sources=canonical)
    another_before = deepcopy(another)
    assert hits == before and canonical == originals
    result.sources[0].metadata["nested"]["offset"] = 99
    result.sources[0].metadata["_retrieval"]["branches"][0]["contribution"] = 99
    assert canonical == originals and hits == before
    assert another == another_before
    assert result.traces[0].contribution == pytest.approx(1 / 61)
    assert result.traces[0].distance == 0.9


@pytest.mark.parametrize("branches", [{}, {"keyword": []}, {"keyword": [], "vector": []}])
@pytest.mark.day09_case("F04", "N01")
def test_empty_branches(branches):
    for fuse in (fuse_rrf, fuse_min_max):
        result = fuse(branches, canonical_sources=[])
        assert result.sources == result.traces == []
        assert result.final_count == result.unique_candidate_count == 0


@pytest.mark.day09_case("F04")
def test_ties_use_source_id_and_rrf_uses_rank_not_raw_score():
    canonical = fixture_sources()
    result = fuse_rrf({"keyword": ranked(canonical, "B", [0.01]),
                       "vector": ranked(canonical, "A", [0.99])}, canonical_sources=canonical)
    assert [hit.source_id for hit in result.sources] == ["A", "B"]
    reordered_scores = fuse_rrf({"keyword": ranked(canonical, "AB", [-1, 1])},
                                canonical_sources=canonical)
    assert [hit.source_id for hit in reordered_scores.sources] == ["A", "B"]


@pytest.mark.parametrize("name", ["top_k", "rank_constant"])
@pytest.mark.parametrize("value", [0, -1, True, False, 1.5, "3", None])
def test_rrf_invalid_parameters_even_with_empty_input(name, value):
    with pytest.raises(ValueError, match=name):
        fuse_rrf({}, canonical_sources=[], **{name: value})
    with pytest.raises(ValueError, match=name):
        merge_ranked([], **{name: value})


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_scores_and_unknown_id_are_rejected(score):
    canonical = fixture_sources()
    for fuse in (fuse_rrf, fuse_min_max):
        with pytest.raises(IndexDataError, match="有限"):
            fuse({"keyword": ranked(canonical, "A", [score])}, canonical_sources=canonical)
        with pytest.raises(IndexDataError, match="未知"):
            fuse({"keyword": [Source(source_id="unknown", title="?", content="?")]},
                 canonical_sources=canonical)


@pytest.mark.day09_case("N01")
def test_min_max_negative_scores_missing_branch_and_zero_candidates_retained():
    canonical = fixture_sources()
    hits = ranked(canonical, "ABC", [-0.8, -0.2, 0.4])
    for hit in hits:
        hit.metadata["_retrieval"] = {"distance": 1 - hit.score, "metric": "cosine"}
    result = fuse_min_max({"keyword": [], "vector": hits}, canonical_sources=canonical)
    assert [trace.normalized_score for trace in result.traces] == pytest.approx([0, 0.5, 1])
    assert [hit.source_id for hit in result.sources] == list("CBA")
    assert [hit.score for hit in result.sources] == pytest.approx([0.5, 0.25, 0])
    assert hits[0].score == -0.8  # 没有再次转换 distance，也没有改输入。


@pytest.mark.parametrize("names", ["A", "ABC"])
@pytest.mark.parametrize("equal", [0.0, 1.0])
@pytest.mark.day09_case("N01")
def test_singleton_and_all_equal_policy(names, equal):
    canonical = fixture_sources()
    result = fuse_min_max({"keyword": ranked(canonical, names, [0.001] * len(names)),
                           "vector": []}, canonical_sources=canonical, equal_score_value=equal)
    assert all(trace.normalized_score == equal for trace in result.traces)
    assert all(hit.score == 0.5 * equal for hit in result.sources)
    assert result.final_count == len(names)


def test_equal_score_policy_can_change_rank_and_candidate_window_changes_normalization():
    canonical = fixture_sources()
    branches = {"keyword": ranked(canonical, "A", [0.001]),
                "vector": ranked(canonical, "BD", [0.9, 0.3])}
    one = fuse_min_max(branches, canonical_sources=canonical, equal_score_value=1)
    zero = fuse_min_max(branches, canonical_sources=canonical, equal_score_value=0)
    assert one.sources[0].source_id == "A"  # 同分按 ID 排；差候选也被赋 1。
    assert zero.sources[0].source_id == "B"
    vector = ranked(canonical, "ABC", [0.9, 0.8, 0.1])
    small = fuse_min_max({"vector": vector[:2]}, canonical_sources=canonical)
    large = fuse_min_max({"vector": vector}, canonical_sources=canonical)
    assert small.traces[1].normalized_score == 0
    assert large.traces[1].normalized_score == pytest.approx(0.875)


def test_min_max_deduplicates_before_extrema_and_handles_large_finite_scores():
    canonical = fixture_sources()
    result = fuse_min_max({"keyword": ranked(canonical, "AAB", [0.9, -100, 0.1])},
                          canonical_sources=canonical)
    assert [trace.normalized_score for trace in result.traces] == [1, 0]
    result = fuse_min_max({"vector": ranked(canonical, "AB", [-1e308, 1e308])},
                          canonical_sources=canonical)
    assert [trace.normalized_score for trace in result.traces] == [0, 1]


@pytest.mark.parametrize("value", [True, False, 0.5, "1", None, float("nan")])
def test_min_max_invalid_equal_policy(value):
    with pytest.raises(ValueError, match="equal_score_value"):
        fuse_min_max({}, canonical_sources=[], equal_score_value=value)


@pytest.mark.parametrize("value", [0, True, 1.5])
def test_min_max_invalid_top_k(value):
    with pytest.raises(ValueError, match="top_k"):
        fuse_min_max({}, canonical_sources=[], top_k=value)


@pytest.mark.day09_case("F03")
def test_legacy_merge_accepts_canonical_and_preserves_trace():
    canonical = fixture_sources()
    results = merge_ranked([ranked(canonical, "AB"), ranked(canonical, "BA")],
                           canonical_sources=canonical, top_k=1, rank_constant=10)
    assert results[0].source_id == "A"
    assert len(results[0].metadata["_retrieval"]["branches"]) == 2
    assert results[0].score == pytest.approx(1 / 11 + 1 / 12)


@pytest.mark.day09_case("F03")
def test_shared_id_is_one_source_with_two_independent_branch_contributions():
    canonical = fixture_sources()
    result = fuse_rrf({"keyword": ranked(canonical, "A"), "vector": ranked(canonical, "A")},
                      canonical_sources=canonical, top_k=4)
    assert [source.source_id for source in result.sources] == ["A"]
    assert result.final_count == result.unique_candidate_count == 1
    assert result.sources[0].score == pytest.approx(2 / 61)
    assert {(trace.branch, trace.rank) for trace in result.traces} == {("keyword", 1), ("vector", 1)}
    assert [trace.contribution for trace in result.traces] == pytest.approx([1 / 61, 1 / 61])
    stored = result.sources[0].metadata["_retrieval"]["branches"]
    assert {trace["branch"] for trace in stored} == {"keyword", "vector"}
    assert sum(trace["contribution"] for trace in stored) == pytest.approx(result.sources[0].score)


def test_demo_saves_three_independent_results_and_normalization_examples(tmp_path, monkeypatch, capsys):
    import json
    from examples.day09_fusion import main

    monkeypatch.setattr("sys.argv", ["day09_fusion.py", "--demo", "--top-k", "4",
                                    "--output-root", str(tmp_path)])
    main()
    assert "B (0.032522) > A (0.032266)" in capsys.readouterr().out
    payload = json.loads(next(tmp_path.glob("*/fusion.json")).read_text(encoding="utf-8"))
    assert [source["source_id"] for source in payload["results"]["rrf"]["sources"]] == list("BADC")
    examples = payload["normalization_examples"]
    assert examples["singleton_policy"]["1"]["sources"][0]["source_id"] == "A"
    assert examples["singleton_policy"]["0"]["sources"][0]["source_id"] == "B"
    assert examples["candidate_window"]["2"]["traces"][1]["normalized_score"] == 0
    assert examples["candidate_window"]["3"]["traces"][1]["normalized_score"] == pytest.approx(0.875)


def test_saved_smoke_candidates_can_be_replayed_without_modification(tmp_path):
    import json
    from examples.day09_fusion import load_saved_candidates, compare_fusions

    source = Source(source_id="doc-offset", title="doc-offset", content="offset 记录原文位置")
    payload = {"mode": "smoke_controlled_vectors_not_semantic_evaluation", "query": "offset",
               "result": {"branches": {"keyword": {"sources": [source.model_dump(mode="json")]},
                                        "vector": {"sources": []}}}}
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    original = path.read_bytes()
    _, canonical, branches = load_saved_candidates(path, tmp_path)
    results = compare_fusions(branches, canonical)
    assert results["rrf"].final_count == 1
    results["min_max_equal_1"].sources[0].metadata["changed"] = True
    assert "changed" not in results["rrf"].sources[0].metadata
    assert path.read_bytes() == original
