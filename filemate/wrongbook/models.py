"""Shared strict command validation for HTTP and direct review callers."""

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Key = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{16,80}$")]
Identity = Annotated[str, Field(min_length=1, max_length=128)]
Cause = Literal["concept_gap", "memory_gap", "reasoning_break", "expression_gap", "option_confusion",
                "careless", "method_gap", "condition_gap", "calculation_error", "code_error",
                "boundary_gap", "time_pressure", "other"]


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Answer(StrictBody):
    artifact_id: Identity
    question_index: int = Field(ge=0, le=100_000)
    expected_question: dict[str, Any]
    request_key: Key
    user_answer: str = Field(default="", max_length=10_000)
    action: Literal["answer", "dont_know"] = "answer"
    answer_revealed: bool = False
    duration_ms: int | None = Field(default=None, ge=0, le=14_400_000)
    self_reported_result: Literal["correct", "incorrect", "unsure"] | None = None

    @model_validator(mode="after")
    def content_bounds(self):
        if len(json.dumps(self.expected_question, ensure_ascii=False)) > 60_000:
            raise ValueError("题目快照过大")
        if self.action == "answer" and not self.user_answer.strip():
            raise ValueError("请输入回答，或明确选择暂时不会")
        if self.action == "dont_know" and (self.user_answer or self.self_reported_result not in {None, "unsure"}):
            raise ValueError("暂时不会不能同时声明已答对或带有回答")
        return self


class Diagnosis(StrictBody):
    request_key: Key
    expected_revision: int = Field(ge=1)
    error_causes: list[Cause] = Field(max_length=3)
    primary_cause: Cause | None = None
    custom_tags: list[Annotated[str, Field(min_length=1, max_length=30)]] = Field(default_factory=list, max_length=5)
    note: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def distinct_causes(self):
        if len(set(self.error_causes)) != len(self.error_causes):
            raise ValueError("错因不能重复")
        if self.primary_cause is not None and self.primary_cause not in self.error_causes:
            raise ValueError("主因必须在所选错因中")
        if any(not tag.strip() or tag != tag.strip() for tag in self.custom_tags) or len(set(self.custom_tags)) != len(self.custom_tags):
            raise ValueError("自定义标签不能为空、重复或带首尾空格")
        return self
