"""Reproduce the independent B review findings using actual isolated storage."""

import json
from datetime import datetime, timezone

import pytest

from filemate.execution.storage import QuestionRevisionConflict
from filemate.operations.personal_backup import PersonalBackup
from filemate.study.knowledge_graph import _after_question_revision
from filemate.tests.wrongbook.conftest import answer_payload
from filemate.tests.wrongbook.test_commands import apply, payload
from filemate.tests.wrongbook.test_lifecycle import backup_for, restore
from filemate.tests.wrongbook.test_schema import legacy_store
from filemate.wrongbook.commands import ReviewCommands
from filemate.wrongbook.engine import transition
from filemate.wrongbook.repository import ReviewRepository


def test_backup_preserves_sparse_evidence_sequences_and_revision_boundary(review_store, tmp_path):
    store, _, aid, _, clock = review_store
    repo = ReviewRepository(store, clock=lambda: clock[0])
    repo.submit(answer_payload(review_store))
    repo.submit(answer_payload(review_store, "A", key="synthetic-revision-answer"))
    with store._conn() as conn:
        conn.execute("UPDATE quiz_attempts SET rowid=rowid+100")
        conn.execute("UPDATE artifacts SET metadata=? WHERE artifact_id=?", (json.dumps({"graph_attempt_cutoff": 101}), aid))
    original = [dict(r) for r in store._conn().execute("SELECT rowid AS evidence_sequence,* FROM quiz_attempts ORDER BY rowid")]
    assert [_after_question_revision(row, store.get_artifact(aid)) for row in original] == [False, True]
    backup = backup_for(store, tmp_path)
    assert restore(backup, backup.export())["restored"]
    current = [dict(r) for r in store._conn().execute("SELECT rowid AS evidence_sequence,* FROM quiz_attempts ORDER BY rowid")]
    assert [r["evidence_sequence"] for r in current] == [101, 102]
    assert [_after_question_revision(row, store.get_artifact(aid)) for row in current] == [False, True]


def test_old_backup_without_sequences_conservatively_rebinds_cutoffs(tmp_path, monkeypatch):
    class OldBackup(PersonalBackup):
        def _snapshot(self):
            snapshot = super()._snapshot()
            for row in snapshot["tables"]["quiz_attempts"]:
                row.pop("rowid", None)
            return snapshot

    store, _, aid, _ = legacy_store(tmp_path, monkeypatch)
    with store._conn() as conn:
        question = json.dumps({"question_type": "fill", "stem": "栈的顺序", "answer": "后进先出"})
        conn.execute("UPDATE artifacts SET content=? WHERE artifact_id=?", ("[" + question + "]", aid))
        conn.execute("UPDATE wrong_questions SET question=? WHERE artifact_id=?", (question, aid))
        conn.execute("UPDATE artifacts SET metadata=? WHERE artifact_id=?", (json.dumps({"graph_attempt_cutoff": 56}), aid))
    old = OldBackup(store, "synthetic-owner", tmp_path / "inbox", tmp_path / "archive")
    raw = old.export()
    store.init_schema()
    result = restore(backup_for(store, tmp_path), raw)
    assert result["review_evidence_rebound"] == 1
    row = dict(store._conn().execute("SELECT rowid AS evidence_sequence,* FROM quiz_attempts").fetchone())
    assert not _after_question_revision(row, store.get_artifact(aid))
    repo = ReviewRepository(store)
    repo.submit({"artifact_id": aid, "expected_question": store.get_artifact(aid)["content"][0],
                 "question_index": 0, "user_answer": "后进先出", "request_key": "synthetic-after-restore"})
    row = dict(store._conn().execute("SELECT rowid AS evidence_sequence,* FROM quiz_attempts ORDER BY rowid DESC LIMIT 1").fetchone())
    assert _after_question_revision(row, store.get_artifact(aid))
    store.close()


@pytest.mark.parametrize("operation", ["answer", "diagnose"])
def test_v2_schedule_takes_ownership_of_legacy_record(review_store, operation):
    store = review_store[0]
    store.record_quiz_attempt(artifact_id=review_store[2], question_index=0, user_answer="B", is_correct=False, score=0, feedback="legacy")
    repo = ReviewRepository(store, clock=lambda: review_store[4][0])
    wid = store.list_wrong_questions()[0]["wrong_id"]
    commands = ReviewCommands(repo)
    paused = apply(commands, wid, payload("pause"))
    with pytest.raises(QuestionRevisionConflict):
        if operation == "answer":
            store.record_quiz_attempt(artifact_id=review_store[2], question_index=0, user_answer="A", is_correct=True, score=1, feedback="legacy")
        else:
            store.update_wrong_diagnosis(wid, error_cause="careless")
    assert repo.detail(wid)["revision"] == 2
    undone = apply(commands, wid, payload("undo", 2, "synthetic-undo-key-02", undo_event_id=paused["review_event_id"]))
    assert undone["revision"] == 3
    assert len(repo.history(wid, kind="attempts")["items"]) == 1


@pytest.mark.parametrize("invalid", ["2024-02-30T00:00:00+00:00", "2024-01-01T24:00:00Z", "now", "2451545"])
def test_queue_and_engine_agree_on_strict_invalid_time(review_store, invalid):
    store = review_store[0]
    repo = ReviewRepository(store, clock=lambda: review_store[4][0])
    wid = repo.submit(answer_payload(review_store))["wrong_id"]
    with store._conn() as conn:
        conn.execute("UPDATE wrong_questions SET next_review_at=? WHERE wrong_id=?", (invalid, wid))
    assert repo.summary()["invalid_time_count"] == 1
    assert repo.summary()["due_count"] == 0
    assert repo.due_page() == []


def test_assisted_incorrect_cannot_reset_qualified_state_or_enter_wrong_metrics(review_store):
    now = datetime(2026, 10, 26, tzinfo=timezone.utc)
    state = {"learning_status": "criterion_met", "scheduler_version": "review-interval-v2",
             "mastered": 1, "eligible_count": 3, "correct_streak": 4,
             "next_review_at": "2026-11-01T00:00:00+00:00", "interval_days": 15}
    after = transition(state, correct=False, independent=False, now=now)
    for key, value in state.items():
        assert after[key] == value
    store = review_store[0]
    repo = ReviewRepository(store, clock=lambda: review_store[4][0])
    result = repo.submit(answer_payload(review_store, answer_revealed=True))
    wrong = repo.detail(result["wrong_id"])
    assert wrong["error_count"] == 0 and wrong["learning_status"] == "pending_check"
    analytics = store.get_learning_analytics()
    assert analytics["pending_wrong_count"] == analytics["quiz_attempt_count"] == 0
    assert analytics["evidence_profile"]["metrics"]["wrong"]["sample_count"] == 0


def test_unverified_practice_preserves_legacy_qualification_fields():
    state = {"scheduler_version": "legacy-v1", "learning_status": "legacy", "correct_streak": 1,
             "mastered": 0, "next_review_at": "2026-11-01T00:00:00+00:00"}
    for correct, independent in ((False, False), (None, True)):
        after = transition(state, correct=correct, independent=independent,
                           now=datetime(2026, 10, 26, tzinfo=timezone.utc))
        for key, value in state.items():
            assert after[key] == value


def test_unverified_transition_cannot_repeat_a_previous_eligible_marker():
    after = transition({"eligible": True, "scheduler_version": "review-interval-v2"},
                       correct=None, independent=True, now=datetime(2026, 10, 26, tzinfo=timezone.utc))
    assert after["eligible"] is False
