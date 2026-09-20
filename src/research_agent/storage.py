from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from .models import ResearchTask, TaskStatus, utc_now


class TaskStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_tasks (
                    task_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    cancelled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def save(self, task: ResearchTask) -> None:
        task.updated_at = utc_now()
        payload = task.model_dump_json()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO research_tasks(task_id, payload, cancelled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    payload=excluded.payload,
                    cancelled=excluded.cancelled,
                    updated_at=excluded.updated_at
                """,
                (
                    task.task_id,
                    payload,
                    int(task.status == TaskStatus.CANCELLED),
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                ),
            )

    def get(self, task_id: str) -> ResearchTask | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM research_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        return ResearchTask.model_validate_json(row["payload"]) if row else None

    def cancel(self, task_id: str) -> ResearchTask | None:
        task = self.get(task_id)
        if task is None:
            return None
        if task.status not in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            task.status = TaskStatus.CANCELLED
            self.save(task)
        return task

    def is_cancelled(self, task_id: str) -> bool:
        task = self.get(task_id)
        return task is not None and task.status == TaskStatus.CANCELLED

    def list_recent(self, limit: int = 20) -> list[ResearchTask]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM research_tasks ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [ResearchTask.model_validate_json(row["payload"]) for row in rows]

