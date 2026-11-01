"""Strict contracts and safe domain errors for learning decisions."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


class GoalOptionsRequest(StrictRequest):
    q: str = Field(default='', max_length=120)
    offset: int = Field(default=0, ge=0, le=1000000)


class GoalChoice(BaseModel):
    goal_id: str
    title: str
    goal_type: str | None = None
    deadline: str | None = None
    source_id: str | None = None
    valid: bool


class GoalOptionsPage(BaseModel):
    items: list[GoalChoice]
    total: int
    offset: int
    limit: int = 30


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
    dependency_ids: list[str] = Field(default_factory=list)
    dependency_coverage: str = 'not_applicable'


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


class PreviewRequest(StrictRequest):
    scope: ScopeRequest
    expected_evidence_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    options: ScheduleOptions


class Confirmation(StrictRequest):
    confirmation_token: str = Field(pattern=r'^[a-f0-9]{64}$')
    request_key: str = Field(pattern=r'^[a-zA-Z0-9_-]{16,80}$')
    confirmed: bool

    @field_validator('confirmed')
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError('explicit_confirmation_required')
        return value


class ConfirmRequest(PreviewRequest, Confirmation):
    pass


class UndoConfirmRequest(Confirmation):
    pass


class SchedulePreview(ScheduleResult):
    scope: ScopeRequest
    study_date: str
    as_of: datetime
    evidence_revision: str
    day_revision: int
    changes: dict[str, Any]
    confirmation_token: str
    expires_in_seconds: int = 900


class UndoPreview(BaseModel):
    operation_id: str
    study_date: str
    day_revision: int
    confirmation_token: str
    expires_in_seconds: int = 900


class OperationReceipt(BaseModel):
    operation_id: str
    request_key: str
    study_date: str
    revision: int
    status: str
    affected: dict[str, int] = Field(default_factory=lambda: {'daily_schedules': 1})


class DayView(BaseModel):
    study_date: str
    revision: int = 0
    status: str
    scope: ScopeRequest | None = None
    options: ScheduleOptions | None = None
    selected: list[TaskView] = Field(default_factory=list)
    completed: list[TaskView] = Field(default_factory=list)
    stale_refs: list[str] = Field(default_factory=list)
    latest_operation: OperationReceipt | None = None
