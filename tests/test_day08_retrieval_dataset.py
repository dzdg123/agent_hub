from pathlib import Path

import pytest

from examples.day08_prepare_retrieval_dataset import read_jsonl, resolve_labels, audit_lengths
from research_agent.documents import load_all_documents_detailed, _chunk_sources


ROOT = Path(__file__).resolve().parents[1] / "data/day08/retrieval-v1"


def test_fixed_corpus_and_all_labels_resolve_with_physical_pdf_pages():
    result = load_all_documents_detailed(ROOT / "corpus", chunk_size=400, overlap=60)
    assert not result.errors
    assert result.loaded_files == 12
    assert len(result.sources) >= 12
    questions = read_jsonl(ROOT / "questions.jsonl")
    labels = resolve_labels(result.sources, questions)
    assert len(labels) == 10
    assert all(label["acceptable_source_ids"] for label in labels)
    pdf_sources = [source for source in result.sources if source.metadata["file_type"] == "pdf"]
    assert {source.page for source in pdf_sources} == {1, 3}
    assert all(source.metadata["empty_pages"] == [2] for source in pdf_sources)
    q06 = next(label for label in labels if label["query_id"] == "Q06")
    assert q06["expected_page"] == 3
    assert any(warning.page == 2 for warning in result.warnings)


def test_overlap_accepts_all_full_quote_matches_but_cross_boundary_rejected():
    sources = _chunk_sources(
        "ABCDEFGHIJKLMNO", title="notes", file_path="notes.txt", chunk_size=8,
        overlap=4, base_metadata={"relative_path": "notes.txt"},
    )
    question = {
        "query_id": "Q01", "question": "test", "expected_relative_path": "notes.txt",
        "expected_page": None, "evidence_quote": "EFGH",
    }
    labels = resolve_labels(sources, [question])
    assert len(labels[0]["acceptable_source_ids"]) == 2
    question["evidence_quote"] = "ABCDEFGHI"
    with pytest.raises(ValueError, match="完整包含关键句"):
        resolve_labels(sources, [question])


def test_wrong_pdf_page_cannot_match_evidence():
    sources = load_all_documents_detailed(ROOT / "corpus", chunk_size=400, overlap=60).sources
    q06 = next(row for row in read_jsonl(ROOT / "questions.jsonl") if row["query_id"] == "Q06")
    q06["expected_page"] = 2
    with pytest.raises(ValueError, match="完整包含关键句"):
        resolve_labels(sources, [q06])


def test_probes_are_separate_and_explicitly_excluded():
    probes = read_jsonl(ROOT / "probes.jsonl")
    assert {probe["query_id"] for probe in probes} == {"N01", "N02"}
    assert all(probe["has_evidence"] is False for probe in probes)
    assert all(probe["include_in_positive_hit_rate"] is False for probe in probes)


def test_audit_counts_query_instruction_and_detects_overlength():
    class FakeEmbedder:
        model = type("Model", (), {"max_seq_length": 5})()
        query_instruction = "指令"

        def token_length(self, text):
            return len(text) + 2

    report = audit_lengths(FakeEmbedder(), [], [{"query_id": "Q01", "question": "问题"}])
    assert report["queries"][0]["token_count"] == 6
    assert report["over_limit_query_count"] == 1
