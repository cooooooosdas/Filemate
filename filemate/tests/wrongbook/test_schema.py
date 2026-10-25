"""Review evidence migrations retain synthetic historical records and row order."""

import json
import sqlite3

import pytest

from filemate.execution import storage as storage_module
from filemate.execution.storage import SQLiteStorage


def legacy_store(tmp_path, monkeypatch):
    store = SQLiteStorage(tmp_path / "legacy.db")
    with monkeypatch.context() as patch:
        patch.setattr(storage_module, "_MIGRATIONS", tuple(
            migration for migration in storage_module._MIGRATIONS if migration[0] <= 34
        ))
        store.init_schema()
    source = store.save_source(original_name="合成教材", source_path="synthetic.txt")
    artifact = store.save_artifact(source_id=source, artifact_type="questions", content=[
        {"type": "fill_blank", "stem": "栈的顺序", "answer": "后进先出"},
    ])
    # 固定v34字段，避免新写入实现替代历史数据库样本。
    store._conn().execute("""INSERT INTO quiz_attempts
        (rowid,attempt_id,artifact_id,source_id,question_index,user_answer,is_correct,score,feedback)
        VALUES (57,'legacy-attempt',?,?,0,'先进先出',0,0,'原始错误')""", (artifact, source))
    store._conn().execute("""INSERT INTO wrong_questions
        (wrong_id,artifact_id,source_id,question_index,question,latest_answer)
        VALUES ('legacy-wrong',?,?,0,?,'先进先出')""",
        (artifact, source, json.dumps({"question": "栈的顺序", "answer": "后进先出"})))
    store._conn().commit()
    return store, source, artifact, "legacy-attempt"


def test_upgrade_keeps_legacy_evidence_identity_and_rowid(tmp_path, monkeypatch):
    store, _, _, attempt_id = legacy_store(tmp_path, monkeypatch)
    before = dict(store._conn().execute("SELECT rowid,* FROM quiz_attempts").fetchone())
    wrong = store.list_wrong_questions()[0]
    store.init_schema()
    assert store.get_schema_version() == 35
    after = dict(store._conn().execute("SELECT rowid,* FROM quiz_attempts").fetchone())
    assert {key: after[key] for key in before} == before
    assert after["attempt_id"] == attempt_id and after["rowid"] == 57
    assert after["purpose"] == "legacy_unknown"
    assert after["judgement_status"] == "legacy"
    assert store.get_wrong_question(wrong["wrong_id"])["scheduler_version"] == "legacy-v1"
    assert store._conn().execute("PRAGMA foreign_key_check").fetchall() == []
    assert store._conn().execute("PRAGMA quick_check").fetchone()[0] == "ok"
    store.init_schema()
    assert store._conn().execute("SELECT COUNT(*) FROM quiz_attempts").fetchone()[0] == 1
    store.close()


def test_unjudged_answers_can_be_saved_without_false_zero(tmp_path):
    store = SQLiteStorage(tmp_path / "pending.db")
    store.init_schema()
    columns = {row["name"]: row for row in store._conn().execute("PRAGMA table_info(quiz_attempts)")}
    assert columns["is_correct"]["notnull"] == 0
    assert columns["score"]["notnull"] == 0
    source = store.save_source(original_name="合成", source_path="synthetic.txt")
    artifact = store.save_artifact(source_id=source, artifact_type="questions", content=[])
    store._conn().execute("""INSERT INTO quiz_attempts
        (attempt_id,artifact_id,question_index,user_answer,is_correct,score,judgement_status)
        VALUES ('pending',?,0,'需要核对',NULL,NULL,'pending')""", (artifact,))
    row = store._conn().execute("SELECT * FROM quiz_attempts WHERE attempt_id='pending'").fetchone()
    assert row["is_correct"] is None and row["score"] is None
    store.close()


def test_failed_migration_restores_original_table_and_version(tmp_path, monkeypatch):
    store, _, _, _ = legacy_store(tmp_path, monkeypatch)
    assert storage_module._MIGRATIONS[-1][0] == 35
    version, name, script = storage_module._MIGRATIONS[-1]
    with monkeypatch.context() as patch:
        patch.setattr(storage_module, "_MIGRATIONS", (
            *storage_module._MIGRATIONS[:-1], (version, name, script + "\nINVALID AUDIT SQL;"),
        ))
        with pytest.raises(sqlite3.OperationalError):
            store.init_schema()
    assert store.get_schema_version() == 34
    assert store._conn().execute("SELECT rowid,user_answer FROM quiz_attempts").fetchone()[:] == (57, "先进先出")
    columns = {r["name"]: r["notnull"] for r in store._conn().execute("PRAGMA table_info(quiz_attempts)")}
    assert columns["is_correct"] == 1
    store.init_schema()
    assert store.get_schema_version() == 35
    store.close()


def test_new_event_foreign_keys_cascade_on_source_delete(tmp_path, monkeypatch):
    store, source, artifact, attempt = legacy_store(tmp_path, monkeypatch)
    store.init_schema()
    assert "review_events" in {r[0] for r in store._conn().execute("SELECT name FROM sqlite_master")}
    wrong = store.list_wrong_questions()[0]
    store._conn().execute("""INSERT INTO review_events
        (event_id,artifact_id,wrong_id,attempt_id,action,request_key,input_digest,before_state,after_state,result,created_at)
        VALUES ('event',?,?,?,'answer','synthetic-request-key','digest','{}','{}','{}','2026-10-26T00:00:00+00:00')""",
        (artifact, wrong["wrong_id"], attempt))
    store._conn().execute("DELETE FROM sources WHERE source_id=?", (source,))
    assert store._conn().execute("SELECT COUNT(*) FROM review_events").fetchone()[0] == 0
    assert store._conn().execute("PRAGMA foreign_key_check").fetchall() == []
    store.close()
