"""Bounded weekly review records and explicit user-written feedback."""

from typing import Literal

from pydantic import BaseModel, Field

from filemate.study.orchestrator.models import ScopeRequest, TaskView

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
