"""Bounded weekly review records and explicit user-written feedback."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from filemate.study.orchestrator.models import ScopeRequest, StrictRequest, TaskView

RULE_VERSION = "weekly-arrangements-v1"


class WeeklySummary(BaseModel):
    planned_days: int = 0
    total_tasks: int = 0
    completed_tasks: int = 0
    pending_tasks: int = 0
    unresolved_tasks: int = 0
    overdue_tasks: int = 0


class WeeklyItem(BaseModel):
    task_id: str
    status: Literal["completed", "pending", "unresolved"]
    dates: list[str]
    task: TaskView | None = None


class WeeklySnapshot(BaseModel):
    rule_version: str = RULE_VERSION
    scope: ScopeRequest
    week_start: str
    week_end: str
    study_date: str
    as_of: str
    revision: str
    summary: WeeklySummary
    items: list[WeeklyItem] = Field(default_factory=list)
    coverage: dict


RecordKind = Literal["reflection", "feedback"]
RecordModule = Literal[
    "home",
    "today",
    "goals",
    "learning",
    "wrongbook",
    "graph",
    "programming",
    "interview",
    "career",
    "privacy",
    "other",
]


class RecordInput(StrictRequest):
    request_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,80}$")
    confirmed: bool

    @field_validator("confirmed")
    @classmethod
    def confirmed_by_user(cls, value):
        if value is not True:
            raise ValueError("explicit_confirmation_required")
        return value


class ReflectionInput(RecordInput):
    scope: ScopeRequest
    expected_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: Literal["time", "difficulty", "unclear", "progress", "other"] = "other"
    notes: str = Field(min_length=1, max_length=2000)

    @field_validator("notes")
    @classmethod
    def meaningful_notes(cls, value):
        if not value.strip():
            raise ValueError("notes_required")
        return value.strip()


class FeedbackInput(RecordInput):
    category: Literal["bug", "suggestion", "other"]
    module: RecordModule
    description: str = Field(min_length=20, max_length=2000)
    steps: str = Field(default="", max_length=2000)
    client_version: str = Field(default="unknown", max_length=100)

    @field_validator("description")
    @classmethod
    def meaningful_description(cls, value):
        if len(value.strip()) < 20:
            raise ValueError("description_too_short")
        return value.strip()


class DeleteRecord(RecordInput):
    confirmation_token: str = Field(pattern=r"^[a-f0-9]{64}$")
