"""Local-only evaluation shared by first answers and revisions."""

from typing import Any

from filemate.understanding.interview import InterviewEvaluator


def local_evaluation(answer: str, fluency_metrics: dict[str, Any] | None, *,
                     speech_language: str) -> dict[str, Any]:
    return InterviewEvaluator(None).evaluate('', answer, '', fluency_metrics,
                                              speech_language=speech_language)
