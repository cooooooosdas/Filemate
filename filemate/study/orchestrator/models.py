"""Strict contracts and safe domain errors for learning decisions."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

Clock = Callable[[], datetime]
LOCAL_ZONE = timezone(timedelta(hours=8))
Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r'^[^\x00-\x1f]+$')]


class OrchestratorError(ValueError):
    def __init__(self, code: str, status_code: int = 409):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ScopeRequest(StrictRequest):
    goal_id: Identifier
    course_id: Identifier | None = None
    source_ids: list[Identifier] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def unique_sources(self):
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError('duplicate_source_ids')
        self.source_ids = sorted(self.source_ids)
        return self


class EvidenceSnapshot(BaseModel):
    scope: ScopeRequest
    as_of: datetime
    study_date: str
    evidence_revision: str
    facts: dict[str, Any]
    evidence_refs: list[dict[str, Any]]
    coverage: dict[str, Any]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError('clock_must_be_aware')
    return value.astimezone(timezone.utc)


class TaskView(BaseModel):
    task_id: str
    kind: str
    title: str
    source_id: str | None = None
    goal_id: str
    course_id: str | None = None
    due_date: str | None = None
    estimated_minutes: int | None = None
    estimate_source: str | None = None
    status: str = 'pending'
    reason: str
    priority: int = 0
    rule_version: str = 'learning-orchestrator-rules-v1'
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    origin_refs: list[dict[str, Any]] = Field(default_factory=list)
    completion_ref: dict[str, Any] | None = None
    action_key: str | None = None
    route: str
    eligibility: str = 'eligible'
    recorded_errors: int = 0


class TaskProjection(BaseModel):
    tasks: list[TaskView]
    completed: list[TaskView]
    unavailable: list[dict[str, Any]]
    overlaps: list[dict[str, Any]]
    coverage: dict[str, Any]


TaskId = Annotated[str, Field(min_length=1, max_length=512)]
Minutes = Annotated[int, Field(strict=True, ge=1, le=240)]


class ScheduleOptions(StrictRequest):
    available_minutes: int = Field(ge=0, le=1440)
    item_order: list[TaskId] = Field(default_factory=list, max_length=200)
    pinned_ids: list[TaskId] = Field(default_factory=list, max_length=20)
    excluded_ids: list[TaskId] = Field(default_factory=list, max_length=200)
    minute_overrides: dict[TaskId, Minutes] = Field(default_factory=dict, max_length=200)

    @model_validator(mode='after')
    def valid_order(self):
        for items in (self.item_order, self.pinned_ids, self.excluded_ids):
            if len(items) != len(set(items)):
                raise ValueError('duplicate_task_ids')
        if not set(self.pinned_ids) <= set(self.item_order) or set(self.pinned_ids) & set(self.excluded_ids):
            raise ValueError('invalid_pinned_order')
        return self


class ScheduleResult(BaseModel):
    rule_version: str
    selected: list[TaskView]
    deferred: list[dict[str, Any]]
    deferred_count: int
    deferred_counts: dict[str, int]
    deferred_truncated: bool
    completed: list[TaskView]
    coverage: dict[str, Any]
    estimated_minutes: int
