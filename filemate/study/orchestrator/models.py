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
