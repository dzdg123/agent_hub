from copy import deepcopy

import pytest

from research_agent.documents import _chunk_sources
from research_agent.evidence_diagnostics import analyze_content_redundancy, analyze_id_duplicates
from research_agent.fusion import fuse_min_max, fuse_rrf
from research_agent.models import Source
from research_agent.retrieval import IndexDataError


def chunk(source_id, content, *, path="guide.pdf", page=1, index=0, offset=0):
    return Source(source_id=source_id, title=source_id, content=content, file_path=path, page=page,
                  metadata={"chunk_index": index, "offset": offset,
                            "end_offset": offset + len(content),
                            "offset_basis": "normalized_page_text" if page is not None else "normalized_document_text",
                            "nested": {"tags": ["original"]}})


def test_id_diagnostics_separate_within_branch_duplicates_from_cross_branch_overlap():
    lookup = {name: chunk(name, name) for name in "ABCD"}
    branches = {"keyword": [lookup[name] for name in "AABC"],
                "vector": [lookup[name] for name in "BDA"]}
    before = deepcopy(branches)
    result = analyze_id_duplicates(branches)
    assert result.raw_count_by_branch == {"keyword": 4, "vector": 3}
    assert result.unique_count_by_branch == {"keyword": 3, "vector": 3}
    assert result.removed_count_by_branch == {"keyword": 1, "vector": 0}
    assert result.shared_source_ids == ["A", "B"]
    assert result.raw_candidate_count == 7
    assert result.unique_source_count == 4
    assert result.within_branch_duplicate_count == 1
    assert result.across_branch_extra_count == 2
    assert result.repeated_candidate_rate == pytest.approx(3 / 7)
    assert branches == before
    assert analyze_id_duplicates({}).repeated_candidate_rate == 0


@pytest.mark.parametrize("fuse", [fuse_rrf, fuse_min_max])
@pytest.mark.day09_case("D01")
def test_distinct_ids_with_identical_content_and_different_pages_are_retained(fuse):
    canonical = [chunk("A", "same", page=1), chunk("B", "same", page=2),
                 chunk("C", "same", path="another.pdf", page=5)]
    branches = {"keyword": [canonical[0], canonical[0], canonical[1]],
                "vector": [canonical[1], canonical[2], canonical[0]]}
    before_sources, before_branches = deepcopy(canonical), deepcopy(branches)
    result = fuse(branches, canonical_sources=canonical, top_k=3)
    assert {source.source_id for source in result.sources} == {"A", "B", "C"}
    assert len(result.sources) == 3
    diagnostics = result.content_redundancy_diagnostics
    assert diagnostics.scope == "unique_candidates_before_top_k"
    assert diagnostics.source_count == 3
    assert diagnostics.duplicate_content_group_count == 1
    assert diagnostics.duplicate_content_extra_count == 2
    assert diagnostics.duplicate_content_groups[0].source_ids == ["A", "B", "C"]
    assert [location.page for location in diagnostics.duplicate_content_groups[0].locations] == [1, 2, 5]
    assert diagnostics.overlap_pairs == []  # 相同 offset、不同页或文件不构成重叠。
    assert diagnostics.overlap_check_complete
    a = next(source for source in result.sources if source.source_id == "A")
    assert len(a.metadata["_retrieval"]["branches"]) == 2
    if fuse is fuse_rrf:
        assert a.score == pytest.approx(1 / 61 + 1 / 63)
    for source in result.sources:
        original = next(item for item in canonical if item.source_id == source.source_id)
        assert source.content == original.content
        assert source.file_path == original.file_path
        assert source.page == original.page
        assert source.metadata["offset"] == original.metadata["offset"]
        assert source.metadata["end_offset"] == original.metadata["end_offset"]
    result.sources[0].metadata["nested"]["tags"].append("changed")
    diagnostics.duplicate_content_groups[0].locations[0].title = "changed"
    assert canonical == before_sources
    assert branches == before_branches


def test_overlapping_adjacent_coordinates_are_verified_against_text():
    canonical = [chunk("A", "abcdef", index=0), chunk("B", "efghij", index=1, offset=4)]
    before = deepcopy(canonical)
    result = analyze_content_redundancy(canonical)
    assert result.adjacent_pairs_checked == result.overlapping_adjacent_pair_count == 1
    pair = result.overlap_pairs[0]
    assert (pair.left_source_id, pair.right_source_id) == ("A", "B")
    assert (pair.overlap_start, pair.overlap_end, pair.overlap_chars) == (4, 6, 2)
    assert result.coordinate_issues == []
    assert canonical == before
    canonical[1].content = "XYghij"
    bad = analyze_content_redundancy(canonical)
    assert bad.overlapping_adjacent_pair_count == 0
    assert bad.coordinate_issues[0].reason == "overlap_text_mismatch"
    assert not bad.overlap_check_complete


def test_touching_intervals_are_not_overlap_and_nonconsecutive_candidates_are_not_neighbors():
    canonical = [chunk("A", "abc", index=0), chunk("B", "def", index=1, offset=3),
                 chunk("C", "ghi", index=2, offset=6)]
    full = analyze_content_redundancy(canonical)
    assert full.adjacent_pairs_checked == 2
    assert full.overlap_pairs == []
    subset = analyze_content_redundancy(canonical, selected_ids={"A", "C"})
    assert subset.adjacent_pairs_checked == 0
    assert subset.selected_source_ids == ["A", "C"]
    assert subset.overlap_check_complete


def test_real_loader_character_coordinates_are_compatible_with_overlap_analysis():
    canonical = _chunk_sources("abcdefghijklmnopqrstuvwxyz", title="letters", file_path="letters.txt",
                               chunk_size=8, overlap=3)
    result = analyze_content_redundancy(canonical)
    assert result.adjacent_pairs_checked == len(canonical) - 1
    assert result.overlapping_adjacent_pair_count == len(canonical) - 1
    assert all(pair.overlap_chars == 3 for pair in result.overlap_pairs)
    assert result.coordinate_issues == []


@pytest.mark.parametrize("change,reason", [
    ({"offset": -1}, "invalid_interval"),
    ({"offset": True}, "invalid_interval"),
    ({"end_offset": 2}, "coordinate_content_length_mismatch"),
    ({"chunk_index": True}, "invalid_chunk_index"),
    ({"offset_basis": "byte_offset"}, "unsupported_offset_basis"),
])
def test_invalid_coordinates_are_reported_instead_of_claiming_no_overlap(change, reason):
    source = chunk("A", "abc")
    source.metadata.update(change)
    result = analyze_content_redundancy([source])
    assert result.coordinate_issues[0].reason == reason
    assert not result.overlap_check_complete
    assert result.overlap_pairs == []


def test_missing_coordinates_ambiguous_positions_and_nonmonotonic_offsets_are_explicit():
    source = chunk("A", "abc")
    source.metadata.pop("offset")
    assert analyze_content_redundancy([source]).coordinate_issues[0].reason == "missing_coordinates"
    first, second = chunk("A", "abc"), chunk("B", "abc")
    result = analyze_content_redundancy([first, second], selected_ids={"A"})
    assert result.coordinate_issues[0].reason == "ambiguous_chunk_index"
    first, second = chunk("A", "abc", offset=10), chunk("B", "abc", index=1, offset=0)
    assert analyze_content_redundancy([first, second]).coordinate_issues[0].reason == "nonmonotonic_offsets"
    first.page = None
    assert analyze_content_redundancy([first]).coordinate_issues[0].reason == "invalid_page_coordinates"


def test_exact_content_grouping_preserves_whitespace_case_and_scope_before_top_k():
    canonical = [chunk("A", "same", page=1), chunk("B", "same", page=2),
                 chunk("C", "Same", page=3), chunk("D", "same ", page=4)]
    result = fuse_rrf({"keyword": canonical[:3]}, canonical_sources=canonical, top_k=1)
    diagnostics = result.content_redundancy_diagnostics
    assert result.final_count == 1
    assert diagnostics.source_count == 3
    assert diagnostics.duplicate_content_groups[0].source_ids == ["A", "B"]
    assert analyze_content_redundancy(canonical).duplicate_content_group_count == 1
    assert analyze_content_redundancy(canonical, selected_ids=set()).source_count == 0
    assert analyze_content_redundancy([]).overlap_check_complete
    with pytest.raises(IndexDataError, match="未知"):
        analyze_content_redundancy(canonical, selected_ids={"unknown"})
    with pytest.raises(IndexDataError, match="重复"):
        analyze_content_redundancy([canonical[0], canonical[0]])
    with pytest.raises(TypeError, match="selected_ids"):
        analyze_content_redundancy(canonical, selected_ids="A")


def test_dedup_demo_exports_provenance_and_unchanged_inputs(tmp_path, monkeypatch, capsys):
    import json
    from examples.day09_dedup import main

    monkeypatch.setattr("sys.argv", ["day09_dedup.py", "--output-root", str(tmp_path)])
    main()
    assert "Inputs unchanged: True" in capsys.readouterr().out
    payload = json.loads(next(tmp_path.glob("*/dedup.json")).read_text(encoding="utf-8"))
    assert payload["inputs_unchanged"]
    result = payload["result"]
    assert [source["source_id"] for source in result["sources"]] == ["B", "A", "D", "C"]
    assert result["id_dedup_diagnostics"]["within_branch_duplicate_count"] == 1
    content = result["content_redundancy_diagnostics"]
    assert content["duplicate_content_groups"][0]["source_ids"] == ["A", "C", "D"]
    assert content["overlap_pairs"][0]["overlap_chars"] == 2
