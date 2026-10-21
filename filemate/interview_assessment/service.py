"""Bounded model calls outside the database transaction, with explicit consent."""

from filemate.interview_coach.repository import CoachError
from filemate.interview_coach.service import provider_metadata
from filemate.interview_review.content import analysis_failure

from .rules import PROMPT_VERSION, RULES_VERSION, analyze


class AssessmentService:
    def __init__(self, repository, llm_factory, *, enabled=lambda: True):
        self.repo, self.llm_factory, self.enabled = repository, llm_factory, enabled

    def create(self, sid, command):
        if command.mode == "local":
            return self.repo.create_local(sid, command)
        if not command.external_consent:
            raise CoachError("consent_required")
        previous = self.repo.previous(sid, command)
        if previous:
            return previous
        llm, factory_error = None, None
        try:
            llm = self.llm_factory()
        except Exception as exc:  # noqa: BLE001 -- provider failures must not expose credentials or erase answers
            factory_error = exc
        identity, model = provider_metadata(llm)
        claim = self.repo.claim(
            sid,
            command,
            {
                "provider_identity": identity,
                "model": model,
                "prompt_version": PROMPT_VERSION,
                "rules_version": RULES_VERSION,
            },
        )
        if not claim["execute"]:
            return claim["assessment"]
        result, code = None, None
        try:
            if factory_error:
                raise factory_error
            result = analyze(llm, claim["rubric"], claim["input"])
        except Exception as exc:  # noqa: BLE001 -- finite public error codes; provider exception bodies stay private
            code = analysis_failure(exc)["code"]
        return self.repo.finish(claim, result=result, error_code=code, enabled=self.enabled())
