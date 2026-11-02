"""Real SQL transactions protect immutable answers, revisions and retry receipts."""

import importlib
import importlib.util
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from filemate.execution.storage import QuestionRevisionConflict, SQLiteStorage
from filemate.tests.wrongbook.conftest import answer_payload


def repository(fixture, store=None):
    assert importlib.util.find_spec("filemate.wrongbook.repository") is not None
    cls = importlib.import_module("filemate.wrongbook.repository").ReviewRepository
    return cls(store or fixture[0], clock=lambda: fixture[4][0])


def test_sql_time_conversion_reuses_repeated_dates_without_changing_null_or_timezone(review_store, monkeypatch):
    module = importlib.import_module('filemate.wrongbook.repository')
    original = module.parse_time
    values = ['2026-10-29T08:00:00+08:00', '2026-10-29T00:00:00Z', 'invalid', None]
    calls = []

    def measured(value):
        calls.append(value)
        return original(value)

    monkeypatch.setattr(module, 'parse_time', measured)
    connection = repository(review_store).time_connection()
    connection.execute('CREATE TEMP TABLE repeated_review_dates(value)')
    connection.executemany('INSERT INTO repeated_review_dates VALUES (?)', [(v,) for v in values] * 500)
    actual = [row[0] for row in connection.execute('SELECT filemate_review_time(value) FROM repeated_review_dates')]
    assert actual == [1793232000.0, 1793232000.0, None, None] * 500
    assert len(calls) < 16, 'repeated dates must not enter Python datetime parsing once per row'


def test_wrong_then_correction_preserves_original_answer_and_records(review_store):
    repo = repository(review_store)
    wrong = repo.submit(answer_payload(review_store))
    wid = wrong["wrong_id"]
    fixed = repo.submit(answer_payload(review_store, "A", key="synthetic-answer-key-0002"))
    assert wrong["is_correct"] is False and fixed["is_correct"] is True
    assert repo.detail(wid)["eligible_count"] == 0
    assert repo.detail(wid)["review_attempt_count"] == 1
    attempts = repo.history(wid, kind="attempts", limit=30, offset=0)["items"]
    assert [r["user_answer"] for r in attempts] == ["A", "B"]
    assert {r["purpose"] for r in attempts} == {"first_practice", "review"}
    assert repo.history(wid, kind="events", limit=30, offset=0)["total"] == 2
    assert repo.detail(wid)["mastered"] == 0
    assert fixed["after"]["next_review_at"] == "2026-10-27T08:00:00+00:00"


def test_first_correct_does_not_create_a_wrong_question(review_store):
    repo = repository(review_store)
    result = repo.submit(answer_payload(review_store, "A"))
    assert result["is_correct"] is True and result["wrong_id"] is None
    assert repo.summary()["total"] == 0


def test_later_first_error_is_not_mislabeled_the_first_attempt(review_store):
    repo = repository(review_store)
    repo.submit(answer_payload(review_store, "A"))
    wrong = repo.submit(answer_payload(review_store, key="synthetic-answer-key-0002"))
    records = repo.history(wrong["wrong_id"], kind="attempts", limit=30, offset=0)["items"]
    assert [record["purpose"] for record in records] == ["practice", "first_practice"]


def test_legacy_diagnosis_cannot_bypass_review_revision(review_store):
    repo = repository(review_store)
    wrong = repo.submit(answer_payload(review_store))
    with pytest.raises(QuestionRevisionConflict):
        review_store[0].update_wrong_diagnosis(wrong["wrong_id"], error_cause="concept_gap")


def test_subjective_and_self_report_never_fake_an_objective_result(review_store):
    repo = repository(review_store)
    subjective = repo.submit(answer_payload(review_store, "栈后进先出，队列也是后进先出", index=1))
    assert subjective["is_correct"] is None and subjective["score"] is None
    assert subjective["judgement_status"] == "pending"
    assert repo.detail(subjective["wrong_id"])["error_count"] == 0
    declared = repo.submit(answer_payload(review_store, "", action="dont_know", key="synthetic-answer-key-0002"))
    assert declared["judgement_status"] == "self_reported" and declared["is_correct"] is None
    assert repo.detail(declared["wrong_id"])["eligible_count"] == 0


@pytest.mark.parametrize("change", [
    {"user_answer": ""}, {"user_answer": " "}, {"user_answer": "x" * 10001},
    {"request_key": "short"}, {"duration_ms": -1}, {"question_index": -1},
])
def test_invalid_submissions_do_not_write(review_store, change):
    repo = repository(review_store)
    with pytest.raises(ValueError):
        repo.submit({**answer_payload(review_store), **change})
    assert review_store[0]._conn().execute("SELECT COUNT(*) FROM quiz_attempts").fetchone()[0] == 0


def test_request_replay_and_payload_conflict(review_store):
    repo = repository(review_store)
    payload = answer_payload(review_store)
    original = repo.submit(payload)
    review_store[4][0] += timedelta(days=1)
    assert repo.submit(payload) == original
    assert repo.history(original["wrong_id"], kind="attempts", limit=30, offset=0)["total"] == 1
    with pytest.raises(QuestionRevisionConflict):
        repo.submit({**payload, "user_answer": "A"})


def test_concurrent_connections_commit_one_answer(review_store):
    other = SQLiteStorage(review_store[0].db_path)
    try:
        repos = [repository(review_store), repository(review_store, other)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda repo: repo.submit(answer_payload(review_store)), repos))
        assert results[0] == results[1]
        assert review_store[0]._conn().execute("SELECT COUNT(*) FROM quiz_attempts").fetchone()[0] == 1
        assert review_store[0]._conn().execute("SELECT COUNT(*) FROM review_events").fetchone()[0] == 1
    finally:
        other.close()


def test_failure_after_answer_insert_rolls_back_all_evidence(review_store):
    repo = repository(review_store)
    conn = review_store[0]._conn()
    conn.execute("CREATE TRIGGER fail_review BEFORE INSERT ON review_events BEGIN SELECT RAISE(ABORT,'synthetic failure'); END;")
    with pytest.raises(sqlite3.IntegrityError):
        repo.submit(answer_payload(review_store))
    assert conn.execute("SELECT COUNT(*) FROM quiz_attempts").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM wrong_questions").fetchone()[0] == 0


def test_diagnosis_multiselect_clear_replay_and_revision(review_store):
    repo = repository(review_store)
    result = repo.submit(answer_payload(review_store))
    wid = result["wrong_id"]
    payload = {"request_key": "synthetic-diagnosis-key-1", "expected_revision": 1,
               "error_causes": ["concept_gap", "boundary_gap"], "primary_cause": "concept_gap",
               "custom_tags": ["易错边界"], "note": "需要核对空栈"}
    saved = repo.diagnose(wid, payload)
    assert saved["error_causes"] == ["concept_gap", "boundary_gap"]
    assert saved["custom_tags"] == ["易错边界"] and saved["revision"] == 2
    assert repo.diagnose(wid, payload) == saved
    with pytest.raises(QuestionRevisionConflict):
        repo.diagnose(wid, {**payload, "request_key": "synthetic-diagnosis-key-2"})
    cleared = repo.diagnose(wid, {"request_key": "synthetic-diagnosis-key-3", "expected_revision": 2,
                                  "error_causes": [], "custom_tags": [], "note": ""})
    assert cleared["error_cause"] == "unconfirmed" and cleared["error_cause_confidence"] == 0
    assert cleared["error_cause_source"] == "unconfirmed"


def test_revision_freezes_events_and_prevents_stale_or_legacy_writes(review_store):
    repo = repository(review_store)
    receipt = repo.submit(answer_payload(review_store))
    store, _, aid, questions, _ = review_store
    with pytest.raises(QuestionRevisionConflict):
        store.record_quiz_attempt(artifact_id=aid, question_index=0, user_answer="A",
                                 is_correct=True, score=1, feedback="legacy")
    store.update_artifact(aid, title="新题", content=[{**questions[0], "answer": "B"}])
    detail = repo.detail(receipt["wrong_id"])
    assert detail["artifact_id"] != aid
    event = repo.history(receipt["wrong_id"], kind="events", limit=30, offset=0)["items"][0]
    assert event["artifact_id"] == detail["artifact_id"]
    assert repo.submit(answer_payload(review_store)) == receipt
    with pytest.raises(QuestionRevisionConflict):
        repo.submit(answer_payload(review_store, key="synthetic-answer-key-0002"))
    assert store._conn().execute("PRAGMA foreign_key_check").fetchall() == []
