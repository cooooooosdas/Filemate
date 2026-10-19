"""Synthetic runtime evidence; clock injection is not real-duration acceptance."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from filemate.execution.storage import SQLiteStorage
from filemate.interview_coach.models import AdvanceCommand, SubmitAnswer
from filemate.interview_coach.repository import CoachError, CoachRepository
from filemate.interview_config import DraftContent, InterviewConfiguration
from filemate.interview_runtime import RuntimeCommand, RuntimeRepository


@pytest.fixture
def runtime(tmp_path):
    store = SQLiteStorage(tmp_path / "runtime.db")
    store.init_schema()
    clock = [datetime(2026, 10, 19, tzinfo=timezone.utc)]
    repo = RuntimeRepository(store, clock=lambda: clock[0])
    yield repo, clock
    store.close()


def prepared(repo, track="knowledge", minutes=10):
    content = DraftContent(
        configuration=InterviewConfiguration(
            execution_mode="timed", category="creator", track=track, duration_minutes=minutes
        ),
        target_role="学生知识主播",
        project_details="主题：C++ RAII；事实：资源与对象生命周期绑定。",
    )
    return repo.prepare(content, uuid4().hex)


def act(repo, snap, kind, **fields):
    return repo.command(
        snap.session["interview_id"],
        RuntimeCommand(
            request_key=uuid4().hex,
            expected_revision=snap.session["runtime"]["revision"],
            task_index=snap.session["runtime"]["current_task"],
            expected_token=snap.session["runtime"]["version_token"],
            kind=kind,
            **fields,
        ),
    )


def test_explicit_start_recover_original_deadline_and_replay(runtime):
    repo, clock = runtime
    p = prepared(repo)
    assert p.session["runtime"]["status"] == "prepared"
    assert p.session["runtime"]["deadline"] is None
    cmd = RuntimeCommand(
        kind="start",
        request_key=uuid4().hex,
        expected_revision=0,
        expected_token=p.session["runtime"]["version_token"],
    )
    s = repo.command(p.session["interview_id"], cmd).snapshot
    assert s.session["runtime"]["remaining_seconds"] == 600
    clock[0] += timedelta(seconds=601)
    replay = repo.command(p.session["interview_id"], cmd)
    assert replay.receipt["request_key"] == cmd.request_key
    assert replay.snapshot.session["runtime"]["status"] == "expired"
    assert replay.snapshot.session["runtime"]["deadline"] == s.session["runtime"]["deadline"]


def test_answer_revision_attempt_and_task_conflicts_preserve_raw(runtime):
    repo, _ = runtime
    s = act(repo, prepared(repo), "start").snapshot
    first = act(repo, s, "submit", answer="事实依据：C++ 对象销毁时释放资源。")
    assert first.snapshot.current_attempt.answer.startswith("事实依据")
    with pytest.raises(CoachError, match="runtime_revision_conflict"):
        act(repo, s, "submit", answer="陈旧窗口")
    with pytest.raises(CoachError, match="attempt_conflict"):
        act(repo, first.snapshot, "submit", answer="缺失版本号")
    s = act(
        repo,
        first.snapshot,
        "advance",
        expected_attempt_id=first.snapshot.current_attempt.attempt_id,
    ).snapshot
    assert s.session["runtime"]["current_task"] == 1
    with pytest.raises(CoachError, match="runtime_task_conflict"):
        repo.command(
            s.session["interview_id"],
            RuntimeCommand(
                kind="submit",
                answer="跨题写入",
                task_index=0,
                expected_token=s.session["runtime"]["version_token"],
                expected_revision=s.session["runtime"]["revision"],
                request_key=uuid4().hex,
            ),
        )
    assert len(s.session["turns"]) == 1


def test_event_cooldown_bound_and_answer_evidence(runtime):
    repo, clock = runtime
    s = act(repo, prepared(repo), "start").snapshot
    for index in range(30):
        s = act(repo, s, "event").snapshot
        if index == 0:
            with pytest.raises(CoachError, match="runtime_event_cooldown"):
                act(repo, s, "event")
        clock[0] += timedelta(seconds=15)
    with pytest.raises(CoachError, match="runtime_event_limit"):
        act(repo, s, "event")
    s = act(repo, s, "submit", answer="我回应模拟观众：请以资料原文为准。").snapshot
    events = [e for e in s.session["runtime"]["events"] if e["kind"] == "audience"]
    assert len(events) == 30
    assert all(e["attempt_id"] == s.current_attempt.attempt_id for e in events)


def test_legacy_routes_cannot_bypass_runtime_and_finish_keeps_answers(runtime):
    repo, _ = runtime
    s = act(repo, prepared(repo), "start").snapshot
    sid = s.session["interview_id"]
    coach = CoachRepository(repo.storage)
    with pytest.raises(CoachError, match="runtime_command_required"):
        coach.submit(
            sid,
            SubmitAnswer(
                request_key=uuid4().hex,
                expected_revision=s.revision,
                question_index=0,
                answer="旧入口",
            ),
        )
    with pytest.raises(CoachError, match="runtime_command_required"):
        coach.advance(
            sid,
            AdvanceCommand(
                request_key=uuid4().hex,
                expected_revision=s.revision,
                from_index=0,
                expected_attempt_id="none",
            ),
        )
    s = act(repo, s, "submit", answer="必须保留的原回答").snapshot
    s = act(repo, s, "finish").snapshot
    assert s.session["runtime"]["status"] == "finished"
    assert s.session["turns"][0]["answer"] == "必须保留的原回答"
    with pytest.raises(CoachError, match="runtime_not_running"):
        act(repo, s, "submit", answer="结束后禁止写入")


def test_prepare_replay_digest_and_separate_commerce_pool(runtime):
    repo, _ = runtime
    c = DraftContent(
        configuration=InterviewConfiguration(
            execution_mode="timed", category="creator", track="commerce"
        ),
        project_details="水杯：容量300ml；其他信息未知。",
    )
    key = uuid4().hex
    a = repo.prepare(c, key)
    b = repo.prepare(c, key)
    assert a.session["interview_id"] == b.session["interview_id"]
    assert a.session["questions"] == b.session["questions"]
    assert "300ml" in a.session["questions"][1]
    assert "不得" in a.session["questions"][1]
    with pytest.raises(CoachError, match="runtime_request_conflict"):
        repo.prepare(c.model_copy(update={"target_role": "changed"}), key)


def test_skip_only_challenge_and_expired_answer_does_not_save(runtime):
    repo, clock = runtime
    s = act(repo, prepared(repo), "start").snapshot
    with pytest.raises(CoachError, match="runtime_task_not_skippable"):
        act(repo, s, "skip")
    for _ in range(2):
        s = act(repo, s, "submit", answer="以给定事实作答").snapshot
        s = act(repo, s, "advance", expected_attempt_id=s.current_attempt.attempt_id).snapshot
    assert s.session["runtime"]["tasks"][2]["kind"] == "challenge"
    s = act(repo, s, "skip").snapshot
    assert s.session["runtime"]["current_task"] == 3
    clock[0] += timedelta(seconds=601)
    with pytest.raises(CoachError, match="runtime_not_running"):
        act(repo, s, "submit", answer="迟到回答")
    end = repo.snapshot(s.session["interview_id"])
    assert end.session["runtime"]["status"] == "expired"
    assert len(end.session["turns"]) == 2


def test_report_delete_and_ai_reservation_cancellation(runtime):
    from filemate.interview_coach.models import ConsentCommand
    from filemate.interview_coach.service import provider_metadata
    from filemate.interview_review.reports import evidence_digest, report_markdown
    from filemate.interview_review.repository import ReviewRepository
    from filemate.interview_runtime import utc_now
    from filemate.tests.test_interview_coach_analysis import Provider, command

    repo, clock = runtime
    clock[0] = utc_now()
    s = act(repo, prepared(repo), "start").snapshot
    s = act(repo, s, "submit", answer="我通过真实测试验证了索引").snapshot
    sid = s.session["interview_id"]
    coach = repo.coach
    provider = Provider()
    state = coach.set_consent(
        sid,
        ConsentCommand(allowed=True, expected_revision=s.revision, request_key=uuid4().hex),
        provider_identity=provider_metadata(provider)[0],
    ).snapshot
    for _ in range(6):
        state = coach.snapshot(sid)
        cmd = command(state, uuid4().hex)
        claim = coach.claim_analysis(
            sid, cmd, provider_identity=state.provider_identity, model="fixture"
        )
        assert (
            coach.claim_analysis(
                sid, cmd, provider_identity=state.provider_identity, model="fixture"
            )["execute"]
            is False
        )
        repo.storage._conn().execute(
            "UPDATE interview_coach_analysis_runs SET status='failed' WHERE run_id=?",
            (claim["run"]["run_id"],),
        )
        repo.storage._conn().commit()
    state = coach.snapshot(sid)
    with pytest.raises(CoachError, match="runtime_ai_budget_exhausted"):
        coach.claim_analysis(
            sid,
            command(state, uuid4().hex),
            provider_identity=state.provider_identity,
            model="fixture",
        )
    before = repo.storage.get_interview(sid)
    clock[0] += timedelta(seconds=1)
    assert evidence_digest(before) == evidence_digest(repo.storage.get_interview(sid))
    s = act(repo, repo.snapshot(sid), "event").snapshot
    assert evidence_digest(before) != evidence_digest(s.session)
    s = act(repo, s, "finish").snapshot
    review = ReviewRepository(repo.storage)
    report = review.generate(sid)
    assert report["runtime"]["events"]
    assert "实战任务与互动" in report_markdown(report)
    preview = review.delete_preview(sid)
    assert preview["runtime_tasks"] == 4 and preview["runtime_events"] > 0
    review.delete(sid, preview["confirmation_token"])
    for table in ("interview_runtime", "interview_tasks", "interview_events"):
        assert repo.storage._conn().execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_model_finishing_after_early_end_cannot_publish(runtime):
    from concurrent.futures import ThreadPoolExecutor

    from filemate.interview_coach.models import ConsentCommand
    from filemate.interview_coach.service import CoachAnalysisService, provider_metadata
    from filemate.interview_runtime import utc_now
    from filemate.tests.test_interview_coach_analysis import Provider, command

    repo, clock = runtime
    clock[0] = utc_now()
    s = act(repo, prepared(repo), "start").snapshot
    s = act(repo, s, "submit", answer="我通过真实测试验证了索引").snapshot
    sid = s.session["interview_id"]
    provider = Provider(block=True)
    state = repo.coach.set_consent(
        sid,
        ConsentCommand(allowed=True, expected_revision=s.revision, request_key=uuid4().hex),
        provider_identity=provider_metadata(provider)[0],
    ).snapshot
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(
            CoachAnalysisService(repo.storage, lambda: provider).analyze, sid, command(state)
        )
        assert provider.entered.wait(timeout=5)
        act(repo, repo.snapshot(sid), "finish")
        provider.release.set()
        result = future.result(timeout=10)
    assert result.snapshot.current_attempt.score is None
    assert result.snapshot.current_attempt.answer == "我通过真实测试验证了索引"
    assert result.snapshot.current_attempt.analysis_status == "cancelled"
