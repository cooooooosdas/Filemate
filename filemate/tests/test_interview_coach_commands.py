"""Atomic synthetic interview coach command behavior."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from filemate.execution.storage import SQLiteStorage
from filemate.interview_coach.models import AdvanceCommand, SubmitAnswer
from filemate.interview_coach.repository import CoachError, CoachRepository


@pytest.fixture
def store(tmp_path):
    value = SQLiteStorage(tmp_path / "coach.db")
    value.init_schema()
    yield value
    value.close()


def start(store):
    return store.create_interview(
        target_role="开发", scenario="求职面试", difficulty="标准", questions=["第一题", "第二题"]
    )["interview_id"]


def submit(repo, sid, text="第一段回答", key="submit_first_0001", index=0):
    state = repo.snapshot(sid)
    previous = next((t for t in state.session["turns"] if t["question_index"] == index), None)
    return repo.submit(
        sid,
        SubmitAnswer(
            answer=text,
            question_index=index,
            request_key=key,
            expected_revision=state.revision,
            expected_attempt_id=previous.get("attempt_id") if previous else None,
        ),
    )


def test_submit_then_reanswer_keeps_turn_and_reading_position(store):
    repo = CoachRepository(store)
    sid = start(store)
    first = submit(repo, sid)
    second = submit(repo, sid, "修改后的回答", "submit_second_0002")
    a, b = first.snapshot.current_attempt, second.snapshot.current_attempt
    assert a.turn_id == b.turn_id
    assert (a.version, b.version) == (1, 2)
    assert a.created_at != b.created_at
    assert (
        second.snapshot.session["current_index"],
        second.snapshot.displayed_index,
        second.snapshot.phase,
    ) == (1, 0, "feedback")
    assert second.snapshot.current_attempt.score is None
    history = repo.list_attempts(sid, a.turn_id, limit=1)
    assert [v["answer"] for v in history["items"]] == ["修改后的回答"]
    assert (
        repo.list_attempts(sid, a.turn_id, before_version=history["next_before_version"])["items"][
            0
        ]["answer"]
        == "第一段回答"
    )


def test_two_connections_same_key_commit_once(store):
    sid = start(store)
    barrier = Barrier(2)
    command = SubmitAnswer(
        answer="并发相同回答",
        question_index=0,
        request_key="shared_submit_0001",
        expected_revision=0,
    )

    def run(_):
        other = SQLiteStorage(store.db_path)
        try:
            barrier.wait(timeout=5)
            return CoachRepository(other).submit(sid, command).receipt
        finally:
            other.close()

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(run, range(2)))
    assert results[0] == results[1]
    assert (
        store._conn().execute("SELECT COUNT(*) FROM interview_answer_attempts").fetchone()[0] == 1
    )
    assert store._conn().execute("SELECT COUNT(*) FROM interview_coach_actions").fetchone()[0] == 1
    with pytest.raises(CoachError) as exc:
        CoachRepository(store).submit(sid, command.model_copy(update={"answer": "另一段"}))
    assert exc.value.status_code == 409


def test_explicit_advance_freezes_question_and_does_not_resubmit(store):
    repo = CoachRepository(store)
    sid = start(store)
    state = submit(repo, sid).snapshot
    command = AdvanceCommand(
        from_index=0,
        expected_attempt_id=state.current_attempt.attempt_id,
        expected_revision=state.revision,
        request_key="advance_first_01",
    )
    result = repo.advance(sid, command)
    repeated = repo.advance(sid, command)
    assert result.receipt == repeated.receipt
    assert (result.snapshot.displayed_index, result.snapshot.phase) == (1, "question")
    assert len(result.snapshot.session["turns"]) == 1
    frozen = (
        store._conn()
        .execute("SELECT question_digest FROM interview_coach_questions WHERE question_index=1")
        .fetchone()[0]
    )
    submit(repo, sid, "第一题再次修改", "submit_third_0003")
    assert (
        store._conn()
        .execute("SELECT question_digest FROM interview_coach_questions WHERE question_index=1")
        .fetchone()[0]
        == frozen
    )


def test_stale_revision_preserves_answer_and_cross_session_history_is_hidden(store):
    repo = CoachRepository(store)
    sid = start(store)
    first = submit(repo, sid).snapshot
    with pytest.raises(CoachError) as exc:
        repo.submit(
            sid,
            SubmitAnswer(
                answer="冲突草稿",
                question_index=0,
                request_key="conflicting_0001",
                expected_revision=0,
            ),
        )
    assert exc.value.status_code == 409
    assert repo.snapshot(sid).current_attempt.answer == "第一段回答"
    with pytest.raises(CoachError) as exc:
        repo.list_attempts(start(store), first.current_attempt.turn_id)
    assert exc.value.status_code == 404


def test_completed_reanswer_does_not_rewind_submitted_progress(store):
    repo = CoachRepository(store)
    sid = start(store)
    submit(repo, sid)
    state = repo.snapshot(sid)
    repo.advance(
        sid,
        AdvanceCommand(
            from_index=0,
            expected_attempt_id=state.current_attempt.attempt_id,
            expected_revision=state.revision,
            request_key="advance_first_01",
        ),
    )
    submit(repo, sid, "第二题回答", "submit_fourth_004", index=1)
    latest = submit(repo, sid, "回看后修改第一题", "submit_fifth_005").snapshot
    assert latest.session["current_index"] == 2
    assert latest.session["status"] == "completed"
    assert (latest.displayed_index, latest.phase) == (0, "feedback")


def test_advance_uses_latest_answer_only_before_question_is_entered(store):
    repo = CoachRepository(store)
    sid = start(store)
    submit(repo, sid)
    latest = submit(repo, sid, "修改后新的证据", "submit_revised_01").snapshot
    result = repo.advance(
        sid,
        AdvanceCommand(
            from_index=0,
            expected_attempt_id=latest.current_attempt.attempt_id,
            expected_revision=latest.revision,
            request_key="advance_revised1",
        ),
    )
    assert "修改后新的证据" in result.snapshot.session["questions"][1]
    assert "第一段回答" not in result.snapshot.session["questions"][1]
    frozen = result.snapshot.session["questions"][1]
    submit(repo, sid, "再改也不改变已进入问题", "submit_revised_02")
    assert repo.snapshot(sid).session["questions"][1] == frozen


def test_same_key_different_action_is_conflict(store):
    repo = CoachRepository(store)
    sid = start(store)
    result = submit(repo, sid)
    with pytest.raises(CoachError) as exc:
        repo.advance(
            sid,
            AdvanceCommand(
                from_index=0,
                expected_attempt_id=result.snapshot.current_attempt.attempt_id,
                expected_revision=result.snapshot.revision,
                request_key="submit_first_0001",
            ),
        )
    assert exc.value.code == "request_key_conflict"


@pytest.mark.parametrize(
    "metrics",
    [
        {"duration_seconds": float("nan")},
        {"duration_seconds": 10, "markers": [{"second": -1, "kind": "filler", "label": "停顿"}]},
        {"duration_seconds": 10, "private_camera_frame": "not allowed"},
    ],
)
def test_invalid_metrics_rejected_before_local_evaluation(metrics):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SubmitAnswer(
            answer="回答",
            question_index=0,
            request_key="metrics_test_001",
            expected_revision=0,
            fluency_metrics=metrics,
        )
