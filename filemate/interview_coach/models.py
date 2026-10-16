"""Interview coach commands and immutable answer views."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AttemptView(BaseModel):
    attempt_id: str
    interview_id: str
    turn_id: str
    version: int
    question_index: int
    question: str
    question_digest: str
    answer: str
    input_digest: str
    fluency_metrics: dict[str, Any] = Field(default_factory=dict)
    visual_metrics: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    origin: str
    analysis_status: str = 'unrequested'
    score: float | None = None
    evaluation: dict[str, Any] = Field(default_factory=dict)
    latest_run_id: str | None = None
    data_error: bool = False


class CoachSnapshot(BaseModel):
    session: dict[str, Any]
    revision: int
    displayed_index: int
    phase: Literal['question', 'feedback', 'summary']
    external_consent: bool
    consent_revision: int
    provider_identity: str
    current_attempt: AttemptView | None = None
    active_run_id: str | None = None
    pending_retries: list[str] = Field(default_factory=list)
    data_error: bool = False


class CoachMutationResult(BaseModel):
    snapshot: CoachSnapshot
    receipt: dict[str, Any]


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: str = Field(min_length=16, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    expected_revision: int = Field(ge=0)


class SubmitAnswer(Command):
    answer: str = Field(min_length=1, max_length=12000)
    question_index: int = Field(ge=0, le=100)
    expected_attempt_id: str | None = None
    fluency_metrics: dict[str, Any] | None = None
    visual_metrics: dict[str, Any] | None = None

    @field_validator('answer')
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('回答不能为空白')
        return value


class AnalysisCommand(Command):
    attempt_id: str = Field(min_length=1, max_length=80)
    consent_revision: int = Field(ge=0)


class AdvanceCommand(Command):
    from_index: int = Field(ge=0, le=100)
    expected_attempt_id: str


class ConsentCommand(Command):
    allowed: bool
