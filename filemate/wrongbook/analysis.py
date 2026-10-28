"""Coordinate one authorized model call without allowing automatic repairs."""

import json
import time
from pathlib import Path

from pydantic import ValidationError

from filemate.execution.data_actions import digest
from filemate.execution.storage import QuestionRevisionConflict
from filemate.llm_client import LLMConfig
from filemate.llm_client.bounded_call import BoundedLLMRunner
from filemate.llm_client.exceptions import LLMConfigError
from filemate.runtime_governance import default_scope
from filemate.wrongbook.analysis_models import AnalysisOutput, Analyze, validate_output
from filemate.wrongbook.analysis_repository import ReviewAnalysisRepository, request_fingerprint
from filemate.wrongbook.learning_context import ReviewLearningContext, public_context


class ReviewAnalysisService:
    def __init__(self, storage, config_factory=None, runner=None, clock=None):
        self.storage = storage
        self.repo = ReviewAnalysisRepository(storage, clock)
        self.config_factory = config_factory or LLMConfig.from_env
        self.runner = runner or BoundedLLMRunner()

    def analyze(self, wrong_id, command):
        """Require current preview and explicit consent even when a result may be cached."""
        body = Analyze.model_validate(command)
        fingerprint = request_fingerprint(wrong_id, body.attempt_id, body.input_digest, body.force_refresh,
            body.course_id, body.credential_mode)
        old = self.storage._conn().execute('SELECT request_digest FROM wrong_review_analysis_requests WHERE request_key=?', (body.request_key,)).fetchone()
        if old:
            if old['request_digest'] != fingerprint:
                raise QuestionRevisionConflict('analysis_request_conflict')
            return self.repo.find_request(body.request_key)
        context = ReviewLearningContext(self.storage, self.repo.repo.now).build(wrong_id, body.attempt_id,
            body.course_id, credential_mode=body.credential_mode)
        if body.input_digest != context['input_digest']:
            raise QuestionRevisionConflict('analysis_preview_changed')
        view, claimed, epoch = self.repo.claim(context, body.request_key, body.force_refresh)
        if not claimed:
            return view
        started = time.monotonic()
        row = self.repo._row(view['analysis_id'])
        deadline = started + max(0, row['deadline']-self.repo.repo.now().timestamp())
        aid = view['analysis_id']
        try:
            config = self.config_factory()
            if not config.api_key:
                self.repo.fail(aid, epoch, 'credentials_missing')
                return self.repo.get(wrong_id, aid)
            if digest([config.provider, config.base_url, config.model]) != context['provider_identity']:
                self.repo.fail(aid, epoch, 'input_changed')
                return self.repo.get(wrong_id, aid)
            prompt = (Path(__file__).resolve().parents[1]/'understanding/prompts/wrongbook-analysis-v1.md').read_text(encoding='utf-8')
            result = self.runner.run(config, default_scope(), prompt=prompt,
                messages=[{'role': 'user', 'content': json.dumps(public_context(context), ensure_ascii=False)}],
                schema=AnalysisOutput.model_json_schema(), deadline=deadline,
                cancelled=lambda: not self.repo.active(aid, epoch, check_deadline=False))
            if result.get('error_code'):
                self.repo.fail(aid, epoch, result['error_code'])
            else:
                output = validate_output(result.get('output'), context)
                if not self.repo.finish(aid, epoch, output, {'provider': context['provider'], 'model': context['model'],
                        'prompt_version': context['prompt_version'], 'usage': result.get('usage'),
                        'latency_ms': round((time.monotonic()-started)*1000)}):
                    self.repo.fail(aid, epoch, 'input_changed')
        except (ValidationError, ValueError, TypeError):
            self.repo.fail(aid, epoch, 'invalid_output')
        except LLMConfigError:
            self.repo.fail(aid, epoch, 'credentials_missing')
        except OSError:
            self.repo.fail(aid, epoch, 'provider_unavailable')
        return self.repo.get(wrong_id, aid)
