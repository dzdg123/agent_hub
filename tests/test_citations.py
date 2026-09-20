from research_agent.citations import append_references, validate_citations
from research_agent.models import Source


def test_citation_validation_and_references():
    sources = [Source(source_id="doc-123", title="Notes", content="Evidence", file_path="notes.md")]
    report = "Agent 有状态。[doc-123] 未知事实。[web-missing]"
    assert validate_citations(report, sources) == ["web-missing"]
    rendered = append_references(report, sources)
    assert "## 参考资料" in rendered
    assert "notes.md" in rendered

