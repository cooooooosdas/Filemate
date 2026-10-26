"""Confirmed schedule changes are reversible without deleting real practice."""

import importlib
import importlib.util

import pytest

from filemate.execution.storage import QuestionRevisionConflict, SQLiteStorage
from filemate.tests.wrongbook.conftest import answer_payload
from filemate.tests.wrongbook.test_repository import repository


def commands(repo):
    assert importlib.util.find_spec("filemate.wrongbook.commands") is not None
    return importlib.import_module("filemate.wrongbook.commands").ReviewCommands(repo)


def setup(review_store):
    repo = repository(review_store)
    wid = repo.submit(answer_payload(review_store))["wrong_id"]
    return repo, commands(repo), wid


def payload(action, revision=1, key="synthetic-schedule-key-1", **extra):
    return {"action": action, "expected_revision": revision, "request_key": key, **extra}


def apply(command, wid, body):
    preview = command.preview(wid, body)
    return command.confirm(wid, body, preview["confirmation_token"])


def test_pause_resume_and_full_summary_are_consistent(review_store):
    repo, command, wid = setup(review_store)
    assert repo.summary()["due_count"] == 1
    paused = apply(command, wid, payload("pause"))
    assert paused["revision"] == 2 and repo.summary()["due_count"] == 0
    assert repo.detail(wid)["schedule_status"] == "paused"
    resumed = apply(command, wid, payload("resume", 2, "synthetic-schedule-key-2"))
    assert resumed["revision"] == 3 and repo.summary()["due_count"] == 1
    assert repo.detail(wid)["eligible_count"] == 0 and repo.detail(wid)["mastered"] == 0


def test_confirmation_and_undo_replay_once_without_deleting_answer(review_store):
    repo, command, wid = setup(review_store)
    body = payload("reschedule", next_review_at="2026-11-01T16:00:00+08:00")
    preview = command.preview(wid, body)
    first = command.confirm(wid, body, preview["confirmation_token"])
    assert command.confirm(wid, body, preview["confirmation_token"]) == first
    assert repo.detail(wid)["next_review_at"] == "2026-11-01T08:00:00+00:00"
    undo_body = payload("undo", 2, "synthetic-schedule-key-2", undo_event_id=first["review_event_id"])
    undo_preview = command.preview(wid, undo_body)
    undone = command.confirm(wid, undo_body, undo_preview["confirmation_token"])
    assert command.confirm(wid, undo_body, undo_preview["confirmation_token"]) == undone
    assert repo.detail(wid)["revision"] == 3
    assert repo.detail(wid)["next_review_at"] == "2026-10-26T08:00:00+00:00"
    assert repo.history(wid, kind="attempts", limit=30, offset=0)["total"] == 1
    with pytest.raises(QuestionRevisionConflict):
        command.preview(wid, {**undo_body, "request_key": "synthetic-schedule-key-3", "expected_revision": 3})


def test_changed_body_or_other_workspace_cannot_reuse_confirmation(review_store, tmp_path):
    repo, command, wid = setup(review_store)
    body = payload("pause")
    preview = command.preview(wid, body)
    with pytest.raises(QuestionRevisionConflict):
        command.confirm(wid, {**body, "action": "resume"}, preview["confirmation_token"])
    applied = command.confirm(wid, body, preview["confirmation_token"])
    with pytest.raises(QuestionRevisionConflict):
        command.confirm(wid, {**body, "action": "resume"}, preview["confirmation_token"])
    assert repo.detail(wid)["revision"] == applied["revision"]
    other = SQLiteStorage(tmp_path / "other.db")
    other.init_schema()
    try:
        with pytest.raises(LookupError):
            commands(repository(review_store, other)).confirm(wid, body, preview["confirmation_token"])
    finally:
        other.close()


def test_new_answer_invalidates_preview_and_undo(review_store):
    repo, command, wid = setup(review_store)
    body = payload("pause")
    preview = command.preview(wid, body)
    repo.submit(answer_payload(review_store, "A", key="synthetic-answer-key-0002"))
    with pytest.raises(QuestionRevisionConflict):
        command.confirm(wid, body, preview["confirmation_token"])
    paused = apply(command, wid, payload("pause", 2, "synthetic-schedule-key-2"))
    repo.diagnose(wid, {"request_key": "synthetic-diagnosis-key-1", "expected_revision": 3, "error_causes": ["concept_gap"]})
    with pytest.raises(QuestionRevisionConflict):
        command.preview(wid, payload("undo", 4, "synthetic-schedule-key-3", undo_event_id=paused["review_event_id"]))


@pytest.mark.parametrize("when", ["2026-11-01T08:00:00", "2026-10-25T08:00:00+00:00", "2028-01-01T00:00:00+00:00", "bad"])
def test_schedule_requires_an_explicit_bounded_timezone(review_store, when):
    repo, command, wid = setup(review_store)
    with pytest.raises(ValueError):
        command.preview(wid, payload("reschedule", next_review_at=when))
    assert repo.detail(wid)["revision"] == 1


def test_legacy_mastered_requires_explicit_activation_and_keeps_its_label(review_store):
    repo = repository(review_store)
    store = review_store[0]
    for answer in ("B", "A", "A"):
        store.record_quiz_attempt(artifact_id=review_store[2], question_index=0,
                                  user_answer=answer, is_correct=answer == "A", score=int(answer == "A"), feedback="legacy")
    wid = store.list_wrong_questions()[0]["wrong_id"]
    with pytest.raises(QuestionRevisionConflict):
        repo.submit(answer_payload(review_store, "A"))
    assert repo.summary()["due_count"] == 0 and repo.detail(wid)["legacy_mastered"]
    command = commands(repo)
    apply(command, wid, payload("activate"))
    current = repo.detail(wid)
    assert current["legacy_mastered"] is True and current["mastered"] == 0
    assert current["eligible_count"] == 0 and repo.summary()["due_count"] == 1
    result = repo.submit(answer_payload(review_store, "A"))
    assert result["reason"] == "initial_correction"
    assert repo.detail(wid)["legacy_mastered"] is True
