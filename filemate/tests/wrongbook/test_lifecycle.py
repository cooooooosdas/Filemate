"""Signed backup roundtrips retain evidence and invalidate old permissions."""

import json
import sqlite3

import pytest

from filemate.execution.storage import QuestionRevisionConflict
from filemate.operations.personal_backup import PersonalBackup
from filemate.tests.wrongbook.conftest import answer_payload
from filemate.tests.wrongbook.test_schema import legacy_store
from filemate.wrongbook.commands import ReviewCommands
from filemate.wrongbook.repository import ReviewRepository


def backup_for(store, tmp_path):
    return PersonalBackup(store, "synthetic-owner", tmp_path / "inbox", tmp_path / "archive")


def restore(backup, raw):
    preview = backup.preview(raw)
    return backup.restore(preview["backup_id"], preview["confirmation_token"])


def test_new_evidence_roundtrip_and_restore_invalidates_schedule_tokens(review_store, tmp_path):
    store, sid, _, _, clock = review_store
    repo = ReviewRepository(store, clock=lambda: clock[0])
    command = ReviewCommands(repo)
    wid = repo.submit(answer_payload(review_store))["wrong_id"]
    repo.submit(answer_payload(review_store, "解释", index=1, key="synthetic-null-attempt"))
    pause = {"action": "pause", "expected_revision": 1, "request_key": "synthetic-pause-key"}
    token = command.preview(wid, pause)["confirmation_token"]
    backup = backup_for(store, tmp_path)
    raw = backup.export()
    original = json.loads(backup.export(False))
    assert len(original["tables"]["review_events"]) == 2
    assert store.source_deletion_preview(sid)["affected"]["review_events"] == 2
    with store._conn() as conn:
        conn.execute("DELETE FROM sources WHERE source_id=?", (sid,))
    assert store._conn().execute("SELECT COUNT(*) FROM review_events").fetchone()[0] == 0
    assert restore(backup, raw)["restored"]
    current = json.loads(backup.export(False))
    for table in ("quiz_attempts", "wrong_questions", "review_events"):
        assert current["tables"][table] == original["tables"][table]
    assert any(row["is_correct"] is None for row in current["tables"]["quiz_attempts"])
    assert store._conn().execute("PRAGMA foreign_key_check").fetchall() == []
    with pytest.raises(QuestionRevisionConflict):
        command.confirm(wid, pause, token)


def test_v34_signed_backup_restores_legacy_defaults(tmp_path, monkeypatch):
    store, _, _, _ = legacy_store(tmp_path, monkeypatch)
    backup = backup_for(store, tmp_path)
    raw = backup.export()
    original = json.loads(backup.export(False))
    assert original["schema_version"] == 34
    store.init_schema()
    assert restore(backup, raw)["restored"]
    row = dict(store._conn().execute("SELECT * FROM quiz_attempts").fetchone())
    assert row["attempt_id"] == "legacy-attempt" and row["user_answer"] == "先进先出"
    assert row["purpose"] == "legacy_unknown" and row["rule_version"] == "legacy-v1"
    wrong = ReviewRepository(store).detail("legacy-wrong")
    assert wrong["scheduler_version"] == "legacy-v1" and wrong["eligible_count"] == 0
    assert store._conn().execute("PRAGMA foreign_key_check").fetchall() == []
    store.close()


def test_restore_failure_rolls_back_answers_and_events(review_store, tmp_path):
    store = review_store[0]
    repo = ReviewRepository(store, clock=lambda: review_store[4][0])
    wid = repo.submit(answer_payload(review_store))["wrong_id"]
    backup = backup_for(store, tmp_path)
    raw = backup.export()
    repo.diagnose(wid, {"request_key": "synthetic-diagnosis-key", "expected_revision": 1,
                        "error_causes": ["concept_gap"]})
    before = json.loads(backup.export(False))
    preview = backup.preview(raw)
    with store._conn() as conn:
        conn.execute("CREATE TRIGGER fail_event_restore BEFORE INSERT ON review_events BEGIN SELECT RAISE(ABORT,'synthetic-failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        backup.restore(preview["backup_id"], preview["confirmation_token"])
    after = json.loads(backup.export(False))
    for table in ("quiz_attempts", "wrong_questions", "review_events"):
        assert before["tables"][table] == after["tables"][table]
    assert repo.detail(wid)["revision"] == 2


def test_frontend_diagnosis_enum_matches_backend():
    import re
    from pathlib import Path
    from typing import get_args

    from filemate.wrongbook.models import Cause

    content = (Path(__file__).resolve().parents[2] / "web/src/types/wrongbook.ts").read_text(encoding="utf-8")
    assert set(re.findall(r"'([^']+)'", content.splitlines()[1])) == set(get_args(Cause))
