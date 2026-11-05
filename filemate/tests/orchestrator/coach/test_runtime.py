"""Actual isolated runtime, transactional rollback and restore authority checks."""

import importlib.util
import sqlite3

import pytest


@pytest.mark.parametrize("force_no_json1", [False, True])
def test_runtime_restore_rollback_and_fault_isolation(tmp_path, monkeypatch, force_no_json1):
    assert importlib.util.find_spec("scripts.acceptance.learning_coach_runtime")
    from scripts.acceptance.learning_coach_runtime import run_runtime

    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_ORCHESTRATOR", "1")
    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_COACH", "1")
    result = run_runtime(tmp_path / "runtime", force_no_json1=force_no_json1)
    assert result["schema"] == 36
    assert all(result["checks"].values())
    assert result["force_no_json1"] is force_no_json1
    if force_no_json1:
        assert result["json1_rejections"] > 0
    assert result["environment"]["sqlite"]


def test_forced_profile_rejects_functions_on_cursor_and_snapshot(tmp_path):
    from filemate.execution.storage import SQLiteStorage
    from scripts.acceptance.learning_coach_runtime import sqlite_profile

    with sqlite_profile(True):
        store = SQLiteStorage(tmp_path / "probe.db")
        store.init_schema()
        try:
            with pytest.raises(sqlite3.OperationalError):
                store._conn().cursor().execute("SELECT json_extract('{}', '$')")
            with store.read_snapshot() as read:
                with pytest.raises(sqlite3.OperationalError):
                    read._conn().execute("SELECT json_extract('{}', '$')")
                assert read._conn().execute("SELECT 1").fetchone()[0] == 1
        finally:
            store.close()


def test_missing_json1_keeps_strict_json_checks_without_migration(tmp_path):
    from filemate.execution.storage import SQLiteStorage
    from scripts.acceptance.learning_coach_runtime import sqlite_profile

    with sqlite_profile(True):
        store = SQLiteStorage(tmp_path / "strict-validation.db")
        try:
            store.init_schema()
            conn = store._conn()
            assert tuple(
                conn.execute(
                    "SELECT json_valid(?),json_valid(?),json_valid(?)", ("{}", "NaN", None)
                ).fetchone()
            ) == (1, 0, 0)
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO interview_rubrics VALUES('synthetic-rubric','v1','{broken','synthetic-hash')"
                )
            assert store.get_schema_version() == 36
        finally:
            store.close()
