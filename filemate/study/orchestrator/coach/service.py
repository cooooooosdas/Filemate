"""Single-owner requests; model work is always outside the business transaction."""

import json
import time
from dataclasses import replace

from filemate.execution.storage import SQLiteStorage
from filemate.llm_client import LLMConfig
from filemate.llm_client.bounded_call import BoundedLLMRunner
from filemate.llm_client.exceptions import LLMConfigError
from filemate.runtime_governance import BudgetExceeded, GovernanceUnavailable, default_scope
from filemate.task_resources import admit_learning

from ..models import Clock
from .context import CoachContextReader
from .models import CoachRequest, CoachRunView, OrchestratorError
from .output import CoachModelOutput, validate_enhancement
from .prompts import build_model_messages
from .repository import CoachRepository, request_digest
from .rules import build_rule_proposal
from .settings import HARD_TIMEOUT_SECONDS, QUOTA_BUCKET, enabled


class CoachService:
    def __init__(
        self,
        storage: SQLiteStorage,
        *,
        clock: Clock | None = None,
        config_factory=None,
        runner=None,
    ) -> None:
        self.storage = storage
        self.repo = CoachRepository(storage, clock=clock)
        self.reader = CoachContextReader(storage, clock=clock)
        self.config_factory = config_factory or LLMConfig.from_env
        self.runner = runner or BoundedLLMRunner()

    def get(self, request_key: str) -> CoachRunView:
        result = self.repo.find(request_key)
        if result is None:
            raise OrchestratorError("coach_request_not_found", 404)
        return result

    def cancel(self, request_key: str) -> CoachRunView:
        return self.repo.cancel(request_key)

    def request(self, body: CoachRequest) -> CoachRunView:
        body = CoachRequest.model_validate(body)
        fingerprint = request_digest(body)
        old = self.repo.find(body.request_key, fingerprint)
        if old:
            return old
        if not enabled():
            raise OrchestratorError("learning_coach_disabled", 503)
        context = self.reader.read(body.input)
        if context.context_revision != body.expected_context_revision:
            raise OrchestratorError("context_changed")
        if body.mode == "llm" and body.consent_digest != context.external_digest:
            raise OrchestratorError("model_consent_changed", 422)
        claim = self.repo.claim(body, context)
        if not claim.claimed:
            return claim.view
        identifier, epoch = claim.view.work_id, claim.claim_epoch
        deadline = time.monotonic() + HARD_TIMEOUT_SECONDS
        try:
            admitted = admit_learning(
                self.storage.db_path,
                QUOTA_BUCKET,
                body.request_key,
                fingerprint,
                now=self.repo._now().timestamp(),
            )
        except BudgetExceeded:
            self.repo.reject(identifier, epoch, "quota_exceeded")
            raise OrchestratorError("coach_quota_exceeded", 429) from None
        except ValueError:
            self.repo.reject(identifier, epoch, "admission_conflict")
            raise OrchestratorError("request_conflict") from None
        except (GovernanceUnavailable, OSError):
            self.repo.reject(identifier, epoch, "governance_unavailable")
            raise OrchestratorError("coach_governance_unavailable", 503) from None
        if not self.repo.authorize_claim(identifier, epoch, admitted=admitted):
            return self.get(body.request_key)
        baseline = build_rule_proposal(context)
        if body.mode == "rule":
            self.repo.finish(identifier, epoch, baseline, model_status="not_requested")
            return self.get(body.request_key)
        proposal, error, status = baseline, None, "succeeded"
        try:
            config = self.config_factory()
            if not config.api_key:
                error = "credentials_missing"
            else:
                self.repo.set_provider(identifier, epoch, config.provider, config.model)
                messages = build_model_messages(context)
                schema = CoachModelOutput.model_json_schema()
                instruction = "请仅返回符合以下 JSON Schema 的内容，不要额外解释：\n" + json.dumps(
                    schema, ensure_ascii=False
                )
                if (
                    len(
                        json.dumps(
                            [{"role": "system", "content": instruction}, *messages],
                            ensure_ascii=False,
                        ).encode("utf-8")
                    )
                    > 65536
                ):
                    raise OrchestratorError("model_message_too_large", 422)
                scope = replace(default_scope(), operation="learning.coach")
                result = self.runner.run(
                    config,
                    scope,
                    prompt="",
                    messages=messages,
                    schema=schema,
                    deadline=deadline,
                    cancelled=lambda: not self.repo.active(identifier, epoch),
                )
                error = result.get("error_code")
                if not error:
                    proposal = validate_enhancement(context, baseline, result.get("output"))
        except LLMConfigError:
            error = "credentials_missing"
        except (OrchestratorError, ValueError, TypeError):
            error = "invalid_output"
        except Exception:  # noqa: BLE001 -- Provider/config failures must never persist their potentially secret text.
            error = "provider_unavailable"
        if error:
            status = "failed"
        self.repo.finish(identifier, epoch, proposal, model_status=status, safe_error_code=error)
        return self.get(body.request_key)
