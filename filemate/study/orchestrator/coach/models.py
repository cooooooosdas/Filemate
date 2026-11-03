"""Strict bounded inputs and typed evidence for the learning coach."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ..models import (  # noqa: F401 -- Public shared domain error.
    EvidenceSnapshot,
    Identifier,
    OrchestratorError,
    ScheduleOptions,
    ScheduleResult,
    ScopeRequest,
    StrictRequest,
    TaskProjection,
)


class FeedbackRef(StrictRequest):
    interview_id: Identifier
    attempt_id: Identifier
    feedback_item_id: Identifier
    expected_revision: Identifier


class CoachSelection(StrictRequest):
    interview_ids: list[Identifier] = Field(default_factory=list, max_length=3)
    submission_ids: list[Identifier] = Field(default_factory=list, max_length=10)
    concept_ids: list[Identifier] = Field(default_factory=list, max_length=5)
    wrong_ids: list[Identifier] = Field(default_factory=list, max_length=3)
    feedback_refs: list[FeedbackRef] = Field(default_factory=list, max_length=3)
    position_id: Identifier | None = None
    requirement_indices: list[int] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def unique_selection(self):
        for field in (
            "interview_ids",
            "submission_ids",
            "concept_ids",
            "wrong_ids",
            "requirement_indices",
        ):
            values = getattr(self, field)
            if len(values) != len(set(values)):
                raise ValueError("duplicate_evidence_ids")
            setattr(self, field, sorted(values))
        keys = [(r.interview_id, r.attempt_id, r.feedback_item_id) for r in self.feedback_refs]
        if len(keys) != len(set(keys)) or any(
            r.interview_id not in self.interview_ids for r in self.feedback_refs
        ):
            raise ValueError("feedback_selection_required")
        if (
            any(not 0 <= i <= 29 for i in self.requirement_indices)
            or self.requirement_indices
            and not self.position_id
        ):
            raise ValueError("invalid_requirement_selection")
        self.feedback_refs.sort(key=lambda r: (r.interview_id, r.attempt_id, r.feedback_item_id))
        return self


class CoachDayInput(StrictRequest):
    study_date: str
    options: ScheduleOptions

    @model_validator(mode="after")
    def canonical_date(self):
        if (
            len(self.study_date) != 10
            or date.fromisoformat(self.study_date).isoformat() != self.study_date
        ):
            raise ValueError("invalid_study_date")
        return self


class CoachInput(StrictRequest):
    scope: ScopeRequest
    selection: CoachSelection = Field(default_factory=CoachSelection)
    intent: Literal["budget", "exam", "error_cause", "tomorrow", "next_step"]
    question: str = Field(min_length=1, max_length=2000)
    days: list[CoachDayInput] = Field(min_length=1, max_length=7)

    @model_validator(mode="after")
    def ordered_days(self):
        days = [item.study_date for item in self.days]
        if days != sorted(set(days)):
            raise ValueError("duplicate_or_unordered_days")
        return self


class GoalData(StrictRequest):
    title: str
    goal_type: str | None
    deadline: str | None


class SourceData(StrictRequest):
    title: str


class AttemptData(StrictRequest):
    artifact_id: str
    question_index: int
    question_excerpt: str = Field(max_length=500)
    answer_excerpt: str = Field(max_length=500)
    purpose: str
    judgement_status: str


class ReviewData(StrictRequest):
    artifact_id: str
    question_index: int
    next_review_at: str
    schedule_status: str


class CauseData(StrictRequest):
    cause: str
    note: str = Field(max_length=300)
    origin: Literal["user"] = "user"


class FeedbackData(StrictRequest):
    interview_id: str
    attempt_id: str
    feedback_item_id: str
    quote: str = Field(max_length=500)
    suggestion: str = Field(max_length=500)
    origin: Literal["model_feedback"] = "model_feedback"


class CompilerData(StrictRequest):
    problem_id: str
    problem_version: int
    verdict: str
    origin: Literal["compiler_judge"] = "compiler_judge"


class RequirementData(StrictRequest):
    position_id: str
    requirement_index: int
    label: str
    quote: str = Field(max_length=400)
    origin: Literal["saved_position"] = "saved_position"


class ConceptData(StrictRequest):
    course_id: str
    label: str
    source_ids: list[str]


class RelationData(StrictRequest):
    course_id: str
    from_id: str
    to_id: str
    relation_type: str
    source_ids: list[str]


class PlanData(StrictRequest):
    day_count: int
    completed_day_count: int
    origin: Literal["self_reported_plan_progress"] = "self_reported_plan_progress"


FACT_TYPES = {
    "goal": GoalData,
    "source": SourceData,
    "attempt": AttemptData,
    "review": ReviewData,
    "cause": CauseData,
    "interview_feedback": FeedbackData,
    "compiler_result": CompilerData,
    "position_requirement": RequirementData,
    "concept": ConceptData,
    "relation": RelationData,
    "plan": PlanData,
}


class CoachFact(StrictRequest):
    fact_id: str
    kind: Literal[
        "goal",
        "source",
        "attempt",
        "review",
        "cause",
        "interview_feedback",
        "compiler_result",
        "position_requirement",
        "concept",
        "relation",
        "plan",
    ]
    record_id: str
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    observed_at: str | None
    display_text: str = Field(max_length=500)
    data: (
        GoalData
        | SourceData
        | AttemptData
        | ReviewData
        | CauseData
        | FeedbackData
        | CompilerData
        | RequirementData
        | ConceptData
        | RelationData
        | PlanData
    )

    @model_validator(mode="after")
    def matching_payload(self):
        if not isinstance(self.data, FACT_TYPES[self.kind]):
            raise TypeError("fact_payload_kind_mismatch")
        return self


class CoachContext(BaseModel):
    input: CoachInput
    as_of: datetime
    context_revision: str
    restore_epoch: str
    snapshot: EvidenceSnapshot
    projection: TaskProjection
    facts: list[CoachFact]
    coverage: dict
    external_payload: dict
    external_digest: str


class CoachCatalogRequest(StrictRequest):
    scope: ScopeRequest
    kind: Literal["interview", "submission", "concept", "wrong", "position"]
    q: str = Field(default="", max_length=120)
    offset: int = Field(default=0, ge=0, le=1000000)


class CoachCatalogItem(BaseModel):
    id: str
    label: str
    updated_at: str | None
    revision: str
    valid: bool
    source_id: str | None = None


class CoachCatalogPage(BaseModel):
    items: list[CoachCatalogItem]
    total: int
    offset: int
    limit: int = 30


CoachReason = Literal[
    "due_review",
    "confirmed_cause",
    "confirmed_dependency",
    "selected_feedback",
    "compiler_result",
    "selected_requirement",
    "goal_step",
]
CoachMethod = Literal[
    "reread", "trace_error", "compare_cases", "retry_independently", "rehearse", "practice"
]
ActionKind = Literal[
    "read_source", "review_question", "train_concept", "rehearse_interview", "practice_problem"
]


class CoachTarget(StrictRequest):
    kind: Literal["source", "question", "concept", "interview", "problem"]
    id: Identifier
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifact_id: Identifier | None = None
    question_index: int | None = Field(default=None, ge=0, le=1000000)
    course_id: Identifier | None = None
    attempt_id: Identifier | None = None
    problem_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def exact_target_shape(self):
        extras = {"artifact_id", "question_index", "course_id", "attempt_id", "problem_version"}
        required = {
            "source": set(),
            "question": {"artifact_id", "question_index"},
            "concept": {"course_id"},
            "interview": {"attempt_id"},
            "problem": {"problem_version"},
        }[self.kind]
        if {name for name in extras if getattr(self, name) is not None} != required:
            raise ValueError("invalid_target_shape")
        return self


class CoachActionSpec(StrictRequest):
    action: ActionKind
    target_ref: CoachTarget
    method_code: CoachMethod
    study_date: str
    minutes: int = Field(ge=1, le=240)
    fact_ids: list[str] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def valid_action(self):
        kinds = {
            "read_source": "source",
            "review_question": "question",
            "train_concept": "concept",
            "rehearse_interview": "interview",
            "practice_problem": "problem",
        }
        if kinds[self.action] != self.target_ref.kind:
            raise ValueError("action_target_mismatch")
        if (
            len(self.study_date) != 10
            or date.fromisoformat(self.study_date).isoformat() != self.study_date
        ):
            raise ValueError("invalid_study_date")
        if len(self.fact_ids) != len(set(self.fact_ids)):
            raise ValueError("duplicate_fact_ids")
        return self


class CoachAction(CoachActionSpec):
    action_key: str = Field(min_length=1, max_length=512, pattern=r"^[^\x00-\x1f]+$")


class CoachExplanationSpec(StrictRequest):
    task_id: str | None = None
    fact_ids: list[str] = Field(min_length=1, max_length=8)
    reason_code: CoachReason
    method_code: CoachMethod

    @model_validator(mode="after")
    def unique_facts(self):
        if len(set(self.fact_ids)) != len(self.fact_ids):
            raise ValueError("duplicate_fact_ids")
        return self


class CoachExplanation(CoachExplanationSpec):
    text: str


class CoachProposalDay(CoachDayInput):
    schedule: ScheduleResult


class CoachProposal(BaseModel):
    rule_version: str
    prompt_version: str
    facts: list[CoachFact]
    explanations: list[CoachExplanation]
    days: list[CoachProposalDay] = Field(min_length=1, max_length=7)
    new_actions: list[CoachAction] = Field(max_length=7)
    coverage: dict
    overlaps: list[dict]
    limitations: list[str]


class CoachRequest(StrictRequest):
    input: CoachInput
    expected_context_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    request_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,80}$")
    mode: Literal["rule", "llm"] = "rule"
    allow_external_model: bool = False
    consent_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def single_request_consent(self):
        if self.mode == "llm" and (not self.allow_external_model or self.consent_digest is None):
            raise ValueError("model_consent_required")
        if self.mode == "rule" and (self.allow_external_model or self.consent_digest is not None):
            raise ValueError("rule_request_has_no_model_consent")
        return self


class CoachRunView(BaseModel):
    work_id: str
    request_key: str
    status: Literal["running", "ready", "failed", "cancelled", "interrupted", "stale"]
    requested_mode: Literal["rule", "llm"]
    effective_mode: Literal["rule", "model", "rule_fallback"]
    model_status: Literal[
        "not_requested", "running", "succeeded", "failed", "cancelled", "interrupted"
    ]
    safe_error_code: str | None = None
    context_revision: str
    proposal: CoachProposal | None = None
    rule_version: str = "learning-coach-rules-v1"
    prompt_version: str = "learning-coach-v1"
    provider: str | None = None
    model: str | None = None
    quota_window: Literal["rolling_24h"] = "rolling_24h"
