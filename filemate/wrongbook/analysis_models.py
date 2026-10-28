"""Strict model output and explicit per-request review authorization."""

import re
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from filemate.wrongbook.models import Cause, Identity, Key, StrictBody

Text = Annotated[str, Field(min_length=1, max_length=500)]


class Analyze(StrictBody):
    attempt_id: Identity
    course_id: Identity | None = None
    credential_mode: Literal['server', 'browser'] = 'server'
    input_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    request_key: Key
    force_refresh: bool = False
    allow_external_model: Literal[True]

    @field_validator('allow_external_model', mode='before')
    @classmethod
    def explicit_consent(cls, value):
        if value is not True:
            raise ValueError('explicit_consent_required')
        return value


class Cancel(StrictBody):
    request_key: Key


class Adoption(StrictBody):
    selected_causes: list[Cause] = Field(min_length=1, max_length=3)
    expected_revision: int = Field(ge=1)

    @model_validator(mode='after')
    def unique_selection(self):
        if len(set(self.selected_causes)) != len(self.selected_causes):
            raise ValueError('duplicate_causes')
        return self


class AdoptionConfirm(Adoption):
    request_key: Key
    confirmation_token: str = Field(min_length=1, max_length=256)
    confirmed: Literal[True]

    @field_validator('confirmed', mode='before')
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError('explicit_confirmation_required')
        return value


class AnswerReference(StrictBody):
    attempt_id: Identity
    quote: str = Field(min_length=1, max_length=1000)


class PossibleCause(StrictBody):
    cause_code: Cause
    hypothesis: Text
    answer_evidence_refs: list[AnswerReference] = Field(min_length=1, max_length=3)
    source_evidence_refs: list[Annotated[str, Field(min_length=1, max_length=256)]] = Field(min_length=1, max_length=3)


class AnalysisOutput(StrictBody):
    kind: Literal['supported_hypotheses', 'insufficient_evidence']
    possible_causes: list[PossibleCause] = Field(max_length=3)
    uncertainties: list[Text] = Field(max_length=5)
    smallest_action: Text
    targeted_practice_suggestion: Text
    schedule_suggestion: Text
    reasons: list[Text] = Field(max_length=3)

    @model_validator(mode='after')
    def evidence_shape(self):
        if (self.kind == 'supported_hypotheses') != bool(self.possible_causes):
            raise ValueError('invalid_cause_evidence')
        if self.kind == 'insufficient_evidence' and not self.uncertainties:
            raise ValueError('missing_uncertainties')
        codes = [c.cause_code for c in self.possible_causes]
        if len(codes) != len(set(codes)):
            raise ValueError('duplicate_causes')
        # 不允许用带百分比的心理／能力断言冒充已验证的训练事实。
        texts = [self.smallest_action, self.targeted_practice_suggestion, self.schedule_suggestion,
            *self.uncertainties, *self.reasons, *(c.hypothesis for c in self.possible_causes)]
        if any(re.search(r'(掌握率|紧张|焦虑|开心|疑惑|概率|能力评分).{0,16}\d+\s*[%％]', t) for t in texts):
            raise ValueError('unsupported_statistic')
        return self


def validate_output(raw: dict, context: dict) -> dict:
    """Check references against only literal selected inputs, never model identities."""
    result = AnalysisOutput.model_validate(raw)
    answers = {a['attempt_id']: a['user_answer'] for a in [context['attempt'], *context['related_attempts']]}
    sources = {s['evidence_id'] for s in context['source_evidence']}
    for cause in result.possible_causes:
        for ref in cause.answer_evidence_refs:
            if not ref.quote.strip() or ref.attempt_id not in answers or ref.quote not in answers[ref.attempt_id]:
                raise ValueError('invalid_answer_reference')
        if len(cause.source_evidence_refs) != len(set(cause.source_evidence_refs)) or not set(cause.source_evidence_refs) <= sources:
            raise ValueError('invalid_source_reference')
    return result.model_dump()
