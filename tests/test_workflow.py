from pathlib import Path

import pytest

from research_agent.config import Settings
from research_agent.demo_model import DemoModel
from research_agent.events import EventBroker
from research_agent.models import Source
from research_agent.retrieval import HybridIndex
from research_agent.web import SearchProvider
from research_agent.workflow import ResearchServices, ResearchWorkflow


class NoWeb(SearchProvider):
    async def search(self, query: str, max_results: int = 5):
        return []


@pytest.mark.asyncio
async def test_workflow_generates_report_with_real_source(tmp_path: Path):
    index = HybridIndex()
    index.add(
        [
            Source(
                source_id="doc-agent",
                title="Agent Notes",
                content="Agent 由模型、工具、状态和控制流程组成。",
                file_path="agent.md",
            )
        ]
    )
    settings = Settings(
        document_root=tmp_path / "docs",
        database_path=tmp_path / "db.sqlite",
        max_research_iterations=0,
    )
    workflow = ResearchWorkflow(
        ResearchServices(
            model=DemoModel(),
            index=index,
            search_provider=NoWeb(),
            settings=settings,
            events=EventBroker(),
        )
    )
    state = await workflow.run(
        task_id="run-1",
        query="Agent 由什么组成？",
        plan=["Agent 由什么组成？"],
        use_web=False,
    )
    assert state["status"] == "completed"
    assert "doc-agent" in state["report"]
    assert "## 参考资料" in state["report"]

