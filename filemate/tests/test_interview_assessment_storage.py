"""Synthetic assessment persistence and erasure regression tests."""

import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import pytest

from filemate.execution.storage import SQLiteStorage
from filemate.interview_coach.models import SubmitAnswer
from filemate.interview_coach.repository import CoachError, CoachRepository
from filemate.interview_review.repository import ReviewRepository
from filemate.operations.personal_backup import PersonalBackup
from filemate.tests.test_interview_assessment import model_payload


def module():
    return importlib.import_module("filemate.interview_assessment.repository")


@pytest.fixture
def context(tmp_path):
    store = SQLiteStorage(tmp_path / "db.sqlite")
    store.init_schema()
    sid = store.create_interview(
        target_role="开发", scenario="求职面试", difficulty="标准", questions=["说明方案"]
    )["interview_id"]
    coach = CoachRepository(store)
    coach.submit(
        sid,
        SubmitAnswer(
            answer="我用索引减少扫描，并对比执行计划。",
            question_index=0,
            request_key="assessment_answer1",
            expected_revision=0,
        ),
    )
    yield store, sid, coach, tmp_path
    store.close()


def command(repo, sid, key="assessment_req01", mode="local"):
    return module().AssessmentCommand(
        request_key=key,
        expected_digest=repo.context(sid)["input_digest"],
        mode=mode,
        external_consent=mode == "model",
    )


def test_migration_append_only_reports_idempotency_and_original_legacy_report(context):
    store, sid, _, _ = context
    repo = module().AssessmentRepository(store)
    old = ReviewRepository(store).generate(sid)
    cmd = command(repo, sid)
    first = repo.create_local(sid, cmd)
    again = repo.create_local(sid, cmd)
    second = repo.create_local(sid, command(repo, sid, "assessment_req02"))
    assert first == again and first["assessment_id"] != second["assessment_id"]
    assert first["report"]["result"]["overall_score"] is None
    assert first["report"]["rubric"]["version"] == "1.0.0"
    assert first["report"]["input"]["turns"][0]["version"] == 1
    assert repo.context(sid)["history"][0]["assessment_id"] == second["assessment_id"]
    assert ReviewRepository(store).report(sid) == old
    assert store.get_schema_version() == 30
    store.init_schema()
    assert store._conn().execute("PRAGMA foreign_key_check").fetchall() == []
    assert (
        store._conn().execute("SELECT COUNT(*) FROM interview_assessment_evidence").fetchone()[0]
        == 2
    )
    with pytest.raises(CoachError):
        repo.create_local(sid, cmd.model_copy(update={"mode": "model", "external_consent": True}))


class Provider:
    config = SimpleNamespace(
        provider="fixture", base_url="https://fixture.invalid", model="six-test"
    )

    def __init__(self, context, block=False, invalid=False):
        self.context, self.block, self.invalid = context, block, invalid
        self.entered, self.release, self.calls = Event(), Event(), []

    def call(self, **kwargs):
        self.calls.append(kwargs)
        self.entered.set()
        if self.block:
            assert self.release.wait(10)
        if self.invalid:
            return SimpleNamespace(content='{"overall_score": 100}')
        from filemate.interview_assessment.rules import rubric_for, snapshot

        data = self.context
        return SimpleNamespace(content=json.dumps(model_payload(rubric_for(data), snapshot(data))))


def service(repo, provider):
    return importlib.import_module("filemate.interview_assessment.service").AssessmentService(
        repo, lambda: provider
    )


def test_model_failure_preserves_old_report_and_retry_is_bounded(context):
    store, sid, _, _ = context
    repo = module().AssessmentRepository(store)
    old = repo.create_local(sid, command(repo, sid))
    provider = Provider(store.get_interview(sid), invalid=True)
    result = service(repo, provider).create(sid, command(repo, sid, "assessment_model1", "model"))
    assert result["status"] == "failed" and result["error_code"] == "invalid_evidence"
    assert result["report"] is None and len(provider.calls) == 2
    assert repo.read(sid, old["assessment_id"]) == old
    assert (
        service(repo, provider).create(sid, command(repo, sid, "assessment_model1", "model"))
        == result
    )
    assert len(provider.calls) == 2


@pytest.mark.parametrize(
    "action", ["reanswer", "clear", "cancel", "delete", "lease", "restore_epoch"]
)
def test_late_result_cannot_publish_after_evidence_or_permission_changes(context, action):
    store, sid, coach, _ = context
    repo = module().AssessmentRepository(store)
    p = Provider(store.get_interview(sid), block=True)
    cmd = command(repo, sid, mode="model")
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(service(repo, p).create, sid, cmd)
        assert p.entered.wait(5)
        with pytest.raises(CoachError):
            repo.create_local(sid, command(repo, sid, "assessment_busy1"))
        if action == "reanswer":
            state = coach.snapshot(sid)
            coach.submit(
                sid,
                SubmitAnswer(
                    answer="改用覆盖索引，提供实测依据。",
                    question_index=0,
                    expected_revision=state.revision,
                    expected_attempt_id=state.current_attempt.attempt_id,
                    request_key="assessment_answer2",
                ),
            )
        elif action == "clear":
            ReviewRepository(store).clear(sid)
            with pytest.raises(CoachError):
                repo.create_local(sid, command(repo, sid, "assessment_cancel_wait"))
        elif action == "cancel":
            ReviewRepository(store).cancel(sid)
            with pytest.raises(CoachError):
                repo.create_local(sid, command(repo, sid, "assessment_cancel_wait"))
        elif action == "delete":
            review = ReviewRepository(store)
            review.delete(sid, review.delete_preview(sid)["confirmation_token"])
        elif action == "lease":
            store._conn().execute(
                "UPDATE interview_assessments SET deadline_at='2000-01-01T00:00:00+00:00'"
            )
            store._conn().commit()
        else:
            module().normalize_restored_assessments(store._conn())
            store._conn().commit()
        p.release.set()
        try:
            result = future.result(timeout=10)
            assert result["status"] != "succeeded" and result["report"] is None
        except CoachError:
            assert action in {"delete", "clear"}
    assert (
        store._conn()
        .execute("SELECT COUNT(*) FROM artifacts WHERE artifact_type='interview_report'")
        .fetchone()[0]
        == 0
    )


def test_clear_delete_and_backup_include_every_version(context):
    store, sid, _, root = context
    repo = module().AssessmentRepository(store)
    first = repo.create_local(sid, command(repo, sid))
    provider = Provider(store.get_interview(sid))
    scored = service(repo, provider).create(sid, command(repo, sid, "assessment_model1", "model"))
    assert scored["status"] == "succeeded" and scored["report"]["result"]["overall_score"] == 80
    backup = PersonalBackup(store, "local", root / "inbox", root / "archive")
    raw = backup.export()
    preview = backup.preview(raw)
    backup.restore(preview["backup_id"], preview["confirmation_token"])
    assert repo.read(sid, first["assessment_id"]) == first
    assert repo.read(sid, scored["assessment_id"]) == scored
    review = ReviewRepository(store)
    deletion = review.delete_preview(sid)
    assert deletion["assessments"] == 2 and deletion["reports"] == 2
    review.clear(sid)
    assert repo.context(sid)["history"] == []
    assert repo.create_local(sid, command(repo, sid, "assessment_req01"))["status"] == "cancelled"
    assert repo.context(sid)["model_requests_remaining"] == 5
    again = repo.create_local(sid, command(repo, sid, "assessment_again"))
    review.delete(sid, review.delete_preview(sid)["confirmation_token"])
    assert (
        again["report"]
        and store._conn().execute("SELECT COUNT(*) FROM interview_assessments").fetchone()[0] == 0
    )
    assert (
        store._conn().execute("SELECT COUNT(*) FROM interview_assessment_evidence").fetchone()[0]
        == 0
    )


def test_per_session_model_limit_and_consent_prevent_unbounded_calls(context):
    store, sid, _, _ = context
    repo = module().AssessmentRepository(store)
    provider = Provider(store.get_interview(sid))
    svc = service(repo, provider)
    with pytest.raises(CoachError):
        svc.create(
            sid, command(repo, sid, mode="model").model_copy(update={"external_consent": False})
        )
    assert provider.calls == []
    for i in range(6):
        assert (
            svc.create(sid, command(repo, sid, f"assessment_model{i}", "model"))["status"]
            == "succeeded"
        )
    with pytest.raises(CoachError):
        svc.create(sid, command(repo, sid, "assessment_model6", "model"))
    assert len(provider.calls) == 6


def test_coach_analysis_cannot_run_in_parallel_with_six_assessment(context):
    from filemate.interview_coach.models import AnalysisCommand

    store, sid, coach, _ = context
    repo = module().AssessmentRepository(store)
    claim = repo.claim(sid, command(repo, sid, mode="model"), {"model": "test"})
    state = coach.snapshot(sid)
    with pytest.raises(CoachError, match="analysis_in_progress"):
        coach.claim_analysis(
            sid,
            AnalysisCommand(
                attempt_id=state.current_attempt.attempt_id,
                request_key="assessment_old_block",
                expected_revision=state.revision,
                consent_revision=state.consent_revision,
            ),
            provider_identity="test",
            model="test",
            one_shot_consent=True,
        )
    repo.finish(claim, error_code="test_failure")


def test_real_runtime_interaction_and_timing_are_linked_to_current_answer(tmp_path):
    from filemate.interview_assessment.rules import catalog, snapshot
    from filemate.interview_runtime import RuntimeRepository, utc_now
    from filemate.tests.test_interview_runtime import act, prepared

    store = SQLiteStorage(tmp_path / "runtime.db")
    store.init_schema()
    runtime = RuntimeRepository(store, clock=utc_now)
    state = act(runtime, prepared(runtime), "start").snapshot
    state = act(runtime, state, "event").snapshot
    state = act(
        runtime, state, "submit", answer="大家好，今天讲解 RAII，资源绑定对象生命周期。"
    ).snapshot
    data = snapshot(store.get_interview(state.session["interview_id"]))
    sources = catalog(data)
    assert {e["kind"] for e in sources.values()} == {"answer", "interaction", "timing"}
    assert all(e["attempt_id"] == data["turns"][0]["attempt_id"] for e in sources.values())
    repo = module().AssessmentRepository(store)
    act(runtime, state, "finish")
    provider = Provider(store.get_interview(state.session["interview_id"]))
    result = service(repo, provider).create(
        state.session["interview_id"], command(repo, state.session["interview_id"], mode="model")
    )
    assert result["status"] == "succeeded"
    store.close()


def test_restore_with_live_assessment_is_rejected_and_expired_claim_recovers(context):
    store, sid, _, root = context
    repo = module().AssessmentRepository(store)
    backup = PersonalBackup(store, "local", root / "inbox", root / "archive")
    claim = repo.claim(sid, command(repo, sid, mode="model"), {"model": "test"})
    raw = backup.export()
    preview = backup.preview(raw)
    with pytest.raises(ValueError, match="六维"):
        backup.restore(preview["backup_id"], preview["confirmation_token"])
    store._conn().execute(
        "UPDATE interview_assessments SET deadline_at='2000-01-01T00:00:00+00:00'"
    )
    store._conn().commit()
    assert repo.context(sid)["history"][0]["status"] == "interrupted"
    preview = backup.preview(raw)
    backup.restore(preview["backup_id"], preview["confirmation_token"])
    assert repo.read(sid, claim["assessment_id"])["status"] == "interrupted"


def test_markdown_export_keeps_untrusted_fields_as_literal_text(context):
    from filemate.interview_assessment.reports import markdown

    store, sid, _, _ = context
    repo = module().AssessmentRepository(store)
    report = repo.create_local(sid, command(repo, sid))["report"]
    payload = '<img src="https://attacker.invalid/pixel">\n\n# forged\n![remote](https://attacker.invalid/x)'
    report["input"]["target_role"] = payload
    report["input"]["turns"][0]["answer"] = payload
    report["result"]["dimensions"][0]["reason"] = payload
    report["result"]["dimensions"][0]["suggestion"] = payload
    report["result"]["dimensions"][0]["evidence"] = [
        {"kind": "answer", "attempt_id": "a", "quote": payload}
    ]
    output = markdown(report)
    assert "<img" not in output and "![remote]" not in output and "\n# forged" not in output
    assert "&lt;img" in output and "# FileMate 六维面试训练报告" in output


@pytest.mark.parametrize(
    "corruption", ["shape", "quote", "score", "weight", "input", "rubric", "owner", "provenance"]
)
def test_saved_report_validation_uses_immutable_original_snapshots(context, corruption):
    store, sid, coach, _ = context
    repo = module().AssessmentRepository(store)
    record = service(repo, Provider(store.get_interview(sid))).create(
        sid, command(repo, sid, mode="model")
    )
    report, aid = record["report"], record["assessment_id"]
    state = coach.snapshot(sid)
    coach.submit(
        sid,
        SubmitAnswer(
            answer="第二版回答，不应该影响合法历史。",
            question_index=0,
            request_key="assessment_revision2",
            expected_revision=state.revision,
            expected_attempt_id=state.current_attempt.attempt_id,
        ),
    )
    assert repo.read(sid, aid) == record
    if corruption == "shape":
        changed = {"version": "2.6"}
    else:
        changed = json.loads(json.dumps(report))
        if corruption == "quote":
            changed["result"]["dimensions"][0]["evidence"][0]["quote"] = "不存在的引用"
        elif corruption == "score":
            changed["result"]["overall_score"] = 100
        elif corruption == "weight":
            changed["result"]["dimensions"][0]["weight"] = 100
        elif corruption == "input":
            changed["input"]["turns"][0]["answer"] = "伪造原回答"
        elif corruption == "rubric":
            changed["rubric"]["version"] = "forged"
        elif corruption == "owner":
            changed["assessment_id"] = "foreign"
        else:
            changed["provenance"]["model"] = "forged"
    store._conn().execute(
        "UPDATE artifacts SET content=? WHERE artifact_id=?",
        (json.dumps(changed, ensure_ascii=False), report["artifact_id"]),
    )
    store._conn().commit()
    with pytest.raises(CoachError, match="assessment_evidence_unavailable"):
        repo.read(sid, aid)


def test_runtime_wall_clock_expiry_blocks_late_report_but_allows_new_post_session_consent(
    tmp_path,
):
    from datetime import timedelta

    from filemate.interview_assessment.rules import parse_result
    from filemate.interview_runtime import RuntimeRepository, utc_now
    from filemate.tests.test_interview_runtime import act, prepared

    store = SQLiteStorage(tmp_path / "expiry.db")
    store.init_schema()
    runtime = RuntimeRepository(store, clock=utc_now)
    state = act(runtime, prepared(runtime), "start").snapshot
    state = act(runtime, state, "submit", answer="资源绑定对象生命周期并自动释放。").snapshot
    sid = state.session["interview_id"]
    repo = module().AssessmentRepository(store)
    claim = repo.claim(sid, command(repo, sid, mode="model"), {"model": "test"})
    result = parse_result(
        json.dumps(model_payload(claim["rubric"], claim["input"])), claim["rubric"], claim["input"]
    )
    # Expire only the runtime; the independent assessment lease remains valid.
    store._conn().execute(
        "UPDATE interview_runtime SET deadline=? WHERE interview_id=?",
        ((utc_now() - timedelta(seconds=1)).isoformat(), sid),
    )
    store._conn().commit()
    assert repo.finish(claim, result=result)["status"] == "cancelled"
    # Context must settle expiry even when no client is polling the runtime endpoint.
    context_data = repo.context(sid)
    assert store.get_interview(sid)["runtime"]["status"] == "expired"
    new_command = module().AssessmentCommand(
        request_key="assessment_after_end",
        expected_digest=context_data["input_digest"],
        mode="model",
        external_consent=True,
    )
    assert (
        service(repo, Provider(store.get_interview(sid))).create(sid, new_command)["status"]
        == "succeeded"
    )
    store.close()
