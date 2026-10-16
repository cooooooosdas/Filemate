"""Controlled-provider tests; no external requests or real user evidence."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from types import SimpleNamespace

import pytest

from filemate.execution.storage import SQLiteStorage
from filemate.interview_coach.models import AnalysisCommand, ConsentCommand, SubmitAnswer
from filemate.interview_coach.repository import CoachError, CoachRepository
from filemate.interview_coach.service import CoachAnalysisService, provider_metadata
from filemate.interview_review.models import CONTENT_AREAS

ANSWER = "我通过真实测试验证了索引"


def payload():
    return {
        "score": 80,
        "dimensions": dict.fromkeys(["内容", "结构", "表达", "岗位匹配"], 80),
        "dimension_evidence": dict.fromkeys(["内容", "结构", "表达", "岗位匹配"], "E1"),
        "feedback": "请补充测试条件。",
        "keywords": [],
        "content_analysis": {
            k: {"status": "partial", "evidence": "E1", "suggestion": "补充测试条件"}
            for k in CONTENT_AREAS
        },
    }


class Provider:
    def __init__(self, *, failure=None, block=False):
        self.config = SimpleNamespace(
            provider="test", base_url="https://example.invalid", model="fixture"
        )
        self.calls = []
        self.failure = failure
        self.entered, self.release = Event(), Event()
        self.block = block

    def call(self, **kwargs):
        self.calls.append(kwargs)
        self.entered.set()
        if self.block:
            assert self.release.wait(timeout=10)
        if self.failure:
            raise self.failure
        return json.dumps(payload(), ensure_ascii=False)


@pytest.fixture
def setup(tmp_path):
    store = SQLiteStorage(tmp_path / "coach.db")
    store.init_schema()
    sid = store.create_interview(
        target_role="开发", scenario="求职面试", difficulty="标准", questions=["介绍项目"]
    )["interview_id"]
    repo = CoachRepository(store)
    repo.submit(
        sid,
        SubmitAnswer(
            answer=ANSWER, question_index=0, request_key="first_answer_001", expected_revision=0
        ),
    )
    yield store, repo, sid
    store.close()


def authorize(repo, sid, provider):
    return repo.set_consent(
        sid,
        ConsentCommand(
            allowed=True,
            expected_revision=repo.snapshot(sid).revision,
            request_key="authorize_first1",
        ),
        provider_identity=provider_metadata(provider)[0],
    ).snapshot


def command(state, key="analysis_first_01"):
    return AnalysisCommand(
        attempt_id=state.current_attempt.attempt_id,
        request_key=key,
        expected_revision=state.revision,
        consent_revision=state.consent_revision,
    )


def test_analysis_claim_is_unique_across_connections(setup):
    store, repo, sid = setup
    provider = Provider(block=True)
    state = authorize(repo, sid, provider)
    cmd = command(state)

    def analyze():
        other = SQLiteStorage(store.db_path)
        try:
            return CoachAnalysisService(other, lambda: provider).analyze(sid, cmd)
        finally:
            other.close()

    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(analyze)
        assert provider.entered.wait(timeout=5)
        duplicate = CoachAnalysisService(store, lambda: provider).analyze(sid, cmd)
        assert duplicate.snapshot.current_attempt.analysis_status == "running"
        with pytest.raises(CoachError) as exc:
            CoachAnalysisService(store, lambda: provider).analyze(
                sid, command(repo.snapshot(sid), "analysis_second02")
            )
        assert exc.value.status_code == 409
        assert repo.snapshot(sid).current_attempt.answer == ANSWER
        provider.release.set()
        completed = future.result(timeout=10)
    assert len(provider.calls) == 1
    assert completed.snapshot.current_attempt.score == 80
    assert duplicate.receipt == completed.receipt


@pytest.mark.parametrize("action", ["reanswer", "revoke", "cancel", "clear"])
def test_late_success_never_projects(setup, action):
    store, repo, sid = setup
    provider = Provider(block=True)
    cmd = command(authorize(repo, sid, provider))
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(CoachAnalysisService(store, lambda: provider).analyze, sid, cmd)
        assert provider.entered.wait(timeout=5)
        state = repo.snapshot(sid)
        if action == "reanswer":
            repo.submit(
                sid,
                SubmitAnswer(
                    answer="最新回答",
                    question_index=0,
                    request_key="reanswer_second2",
                    expected_revision=state.revision,
                    expected_attempt_id=state.current_attempt.attempt_id,
                ),
            )
        elif action == "revoke":
            repo.set_consent(
                sid,
                ConsentCommand(
                    allowed=False, request_key="revoke_consent_1", expected_revision=state.revision
                ),
                provider_identity=provider_metadata(provider)[0],
            )
        else:
            from filemate.interview_review.repository import ReviewRepository

            getattr(ReviewRepository(store), action)(sid)
        assert repo.snapshot(sid).active_run_id is not None
        provider.release.set()
        result = future.result(timeout=10)
    assert result.snapshot.current_attempt.score is None
    assert result.snapshot.active_run_id is None
    if action == "reanswer":
        assert result.snapshot.current_attempt.answer == "最新回答"
        assert result.snapshot.current_attempt.attempt_id != cmd.attempt_id


def test_repeated_failed_key_is_not_reexecuted_and_error_is_safe(setup):
    store, repo, sid = setup
    provider = Provider(failure=RuntimeError("secret_key_and_private_answer"))
    cmd = command(authorize(repo, sid, provider))
    service = CoachAnalysisService(store, lambda: provider)
    for _ in range(2):
        with pytest.raises(CoachError) as exc:
            service.analyze(sid, cmd)
        assert exc.value.status_code == 502
        assert "secret_key" not in str(exc.value)
    assert len(provider.calls) == 1
    assert repo.snapshot(sid).current_attempt.analysis_status == "failed"
    assert repo.snapshot(sid).current_attempt.score is None
    stored = str(
        [tuple(r) for r in store._conn().execute("SELECT * FROM interview_coach_analysis_runs")]
    )
    assert "secret_key" not in stored


def test_provider_change_requires_new_consent_and_expired_run_does_not_replay(setup):
    store, repo, sid = setup
    first = Provider()
    state = authorize(repo, sid, first)
    second = Provider()
    second.config.model = "changed"
    with pytest.raises(CoachError) as exc:
        CoachAnalysisService(store, lambda: second).analyze(sid, command(state))
    assert exc.value.code == "consent_required"
    assert second.calls == []
    claim = repo.claim_analysis(
        sid, command(state), provider_identity=provider_metadata(first)[0], model="fixture"
    )
    assert claim["execute"] is True
    assert repo.interrupt_expired(sid, now=datetime.now(timezone.utc) + timedelta(seconds=70)) == 1
    assert repo.snapshot(sid).current_attempt.analysis_status == "interrupted"
    assert first.calls == []


def test_only_format_error_gets_second_call_with_bounded_timeout(setup):
    store, repo, sid = setup
    provider = Provider()
    original = provider.call

    def malformed_first(**kwargs):
        if not provider.calls:
            provider.calls.append(kwargs)
            return "{}"
        return original(**kwargs)

    provider.call = malformed_first
    result = CoachAnalysisService(store, lambda: provider).analyze(
        sid, command(authorize(repo, sid, provider))
    )
    assert result.snapshot.current_attempt.score == 80
    assert len(provider.calls) == 2
    assert all(0 < c["timeout"] <= 30 and c["retry"] == 1 for c in provider.calls)


@pytest.mark.parametrize(
    "kind,expected", [("budget", 429), ("governance", 503), ("timeout", 502), ("rate", 502)]
)
def test_budget_and_transport_failures_do_not_retry_or_discard_answer(
    setup, kind, expected, caplog
):
    from filemate.llm_client.exceptions import LLMRateLimitError, LLMTimeoutError
    from filemate.runtime_governance import BudgetExceeded, GovernanceUnavailable

    errors = {
        "budget": BudgetExceeded,
        "governance": GovernanceUnavailable,
        "timeout": LLMTimeoutError,
        "rate": LLMRateLimitError,
    }
    store, repo, sid = setup
    provider = Provider(failure=errors[kind]("secret_key_and_private_answer"))
    state = authorize(repo, sid, provider)
    with pytest.raises(CoachError) as exc:
        CoachAnalysisService(store, lambda: provider).analyze(sid, command(state))
    assert exc.value.status_code == expected
    assert len(provider.calls) == 1
    assert repo.snapshot(sid).current_attempt.answer == ANSWER
    assert repo.snapshot(sid).current_attempt.score is None
    assert "secret_key" not in caplog.text


def test_explicit_retry_new_key_keeps_old_run_and_clears_current_score(setup):
    store, repo, sid = setup
    provider = Provider()
    service = CoachAnalysisService(store, lambda: provider)
    first = service.analyze(sid, command(authorize(repo, sid, provider)))
    assert first.snapshot.current_attempt.score == 80
    provider.failure = RuntimeError("private error")
    with pytest.raises(CoachError):
        service.analyze(sid, command(first.snapshot, "explicit_retry_02"))
    assert len(provider.calls) == 2
    assert repo.snapshot(sid).current_attempt.score is None
    assert [
        r[0]
        for r in store._conn().execute(
            "SELECT status FROM interview_coach_analysis_runs ORDER BY attempt_seq"
        )
    ] == ["succeeded", "failed"]


def test_one_shot_new_provider_does_not_grant_later_automatic_analysis(setup):
    store, repo, sid = setup
    provider = Provider()
    state = authorize(repo, sid, provider)
    provider.config.model = 'new-provider-model'
    result = CoachAnalysisService(store, lambda: provider).analyze(sid, command(state), one_shot_consent=True)
    assert result.snapshot.current_attempt.score == 80
    assert result.snapshot.external_consent is False
    with pytest.raises(CoachError) as exc:
        CoachAnalysisService(store, lambda: provider).analyze(sid, command(result.snapshot, 'another_analysis1'))
    assert exc.value.code == 'consent_required'
    assert len(provider.calls) == 1
