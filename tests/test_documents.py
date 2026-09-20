from pathlib import Path

import pytest

from research_agent.documents import DocumentLoadError, load_document, safe_document_path


def test_load_text_document_keeps_source_metadata(tmp_path: Path):
    path = tmp_path / "notes.md"
    path.write_text("Agent 负责组织模型、工具和状态。" * 80, encoding="utf-8")
    sources = load_document(path, tmp_path)
    assert sources
    assert all(source.file_path == str(path.resolve()) for source in sources)
    assert len({source.source_id for source in sources}) == len(sources)


def test_empty_document_has_clear_error(tmp_path: Path):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    with pytest.raises(DocumentLoadError, match="没有可用文本"):
        load_document(path, tmp_path)


def test_path_cannot_escape_root(tmp_path: Path):
    outside = tmp_path.parent / "secret.txt"
    with pytest.raises(DocumentLoadError, match="不在允许"):
        safe_document_path(tmp_path, outside)

