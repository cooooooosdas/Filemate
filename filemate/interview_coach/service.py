"""Bounded model transport after a durable answer and atomic claim."""

import os
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from filemate.runtime_governance import BudgetExceeded, GovernanceUnavailable
from filemate.understanding.interview import InterviewEvaluator

from .models import AnalysisCommand, CoachMutationResult
from .repository import CoachError, CoachRepository, digest


def provider_metadata(llm: Any) -> tuple[str, str]:
    config = getattr(llm, "config", None)
    provider = str(getattr(config, "provider", os.getenv("LLM_PROVIDER", "deepseek")))
    model = str(getattr(config, "model", os.getenv("LLM_MODEL", "deepseek-v4-flash")))
    endpoint = urlsplit(
        str(getattr(config, "base_url", os.getenv("LLM_BASE_URL", "https://api.deepseek.com")))
    )
    # Endpoint credentials, query parameters and keys never enter persistent provenance.
    return digest(
        [provider, endpoint.scheme, endpoint.hostname, endpoint.port, endpoint.path, model]
    ), model[:200]


class CoachAnalysisService:
    def __init__(self, storage, llm_factory: Callable[[], Any]) -> None:
        self.repo = CoachRepository(storage)
        self.llm_factory = llm_factory

    def analyze(
        self, interview_id: str, command: AnalysisCommand, *, one_shot_consent: bool = False
    ) -> CoachMutationResult:
        factory_error = None
        try:
            llm = self.llm_factory()
        except Exception as exc:  # noqa: BLE001 - persist only a finite failure code
            llm, factory_error = None, exc
        identity, model = provider_metadata(llm)
        claim = self.repo.claim_analysis(
            interview_id,
            command,
            provider_identity=identity,
            model=model,
            one_shot_consent=one_shot_consent,
        )
        run = claim["run"]
        if claim["execute"]:
            attempt = claim["attempt"]
            session = self.repo.storage.get_interview(interview_id)
            evaluation = None
            error_code = None
            try:
                if factory_error:
                    raise factory_error
                evaluation = InterviewEvaluator(llm).evaluate(
                    attempt["question"],
                    attempt["answer"],
                    session["target_role"],
                    attempt["fluency_metrics"],
                    speech_language="en-US" if session["scenario"] == "英语面" else "zh-CN",
                    analysis_budget_seconds=60.0,
                )
                if evaluation.get("scoring_mode") != "llm":
                    error_code = evaluation.get("analysis_error", {}).get("code", "connection")
                    evaluation = None
            except (BudgetExceeded, GovernanceUnavailable) as exc:
                error_code = (
                    "budget_exceeded"
                    if isinstance(exc, BudgetExceeded)
                    else "governance_unavailable"
                )
            except Exception:  # noqa: BLE001 - no provider details in logs, API or DB
                error_code = "configuration" if factory_error else "connection"
            self.repo.finish_analysis(run["run_id"], evaluation=evaluation, error_code=error_code)
            run = dict(
                self.repo.storage._conn()
                .execute(
                    "SELECT * FROM interview_coach_analysis_runs WHERE run_id=?", (run["run_id"],)
                )
                .fetchone()
            )
        if run["status"] in {"failed", "interrupted"}:
            code = run["error_code"] or "connection"
            error = CoachError(
                code,
                429
                if code == "budget_exceeded"
                else 503
                if code == "governance_unavailable"
                else 502,
            )
            error.run_id, error.attempt_id = run["run_id"], run["attempt_id"]
            raise error
        return self.repo._result(interview_id, claim["receipt"])
