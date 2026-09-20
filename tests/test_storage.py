from pathlib import Path

from research_agent.models import ResearchTask, TaskStatus
from research_agent.storage import TaskStore


def test_task_round_trip_and_cancel(tmp_path: Path):
    store = TaskStore(tmp_path / "tasks.db")
    task = ResearchTask(task_id="task-1", query="研究 Agent 工作流")
    store.save(task)
    assert store.get("task-1").query == task.query
    cancelled = store.cancel("task-1")
    assert cancelled.status == TaskStatus.CANCELLED
    assert store.is_cancelled("task-1")

