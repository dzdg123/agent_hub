from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, TypedDict

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(StrEnum):
    PLANNING = "planning"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Source(BaseModel):
    source_id: str
    title: str
    content: str
    url: str | None = None
    file_path: str | None = None
    page: int | None = None
    score: float = 0.0
    fetched_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    claim: str
    excerpt: str
    source_id: str
    relevance: float = Field(default=0.0, ge=0.0, le=1.0)


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    estimated_cost: float = 0.0
    elapsed_seconds: float = 0.0

    def add(self, other: "Usage") -> None:
        for field in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "model_calls",
            "tool_calls",
            "estimated_cost",
            "elapsed_seconds",
        ):
            setattr(self, field, getattr(self, field) + getattr(other, field))


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ModelReply(BaseModel):
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    request_id: str | None = None


class RunEvent(BaseModel):
    run_id: str
    kind: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class ResearchState(TypedDict, total=False):
    task_id: str
    query: str
    plan: list[str]
    sources: list[Source]
    evidence: list[Evidence]
    report: str | None
    iteration: int
    status: str
    errors: list[str]
    usage: Usage


class ResearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    use_web: bool = True
    use_documents: bool = True


class ResearchTask(BaseModel):
    task_id: str
    query: str
    plan: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PLANNING
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    report: str | None = None
    errors: list[str] = Field(default_factory=list)
    use_web: bool = True
    use_documents: bool = True
    usage: Usage = Field(default_factory=Usage)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MiniAgentStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STOPPED = "stopped"


class MiniAgentResult(BaseModel):
    run_id: str
    status: MiniAgentStatus = MiniAgentStatus.RUNNING
    answer: str = ""
    stop_reason: str | None = None
    steps: int = 0
    messages: list[dict[str, Any]] = Field(default_factory=list)
    events: list[RunEvent] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    elapsed_seconds: float = 0.0
