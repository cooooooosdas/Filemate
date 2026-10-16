"""Synthetic migration and atomic-write tests for interview answer versions."""

import json
import sqlite3

import pytest

from filemate.execution.storage import _MIGRATIONS, SQLiteStorage


def legacy_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, name TEXT)")
    for version, name, script in _MIGRATIONS:
        if version <= 26:
            conn.executescript(script)
            conn.execute("INSERT INTO schema_migrations VALUES (?,?)", (version, name))
    conn.execute(
        "INSERT INTO interview_sessions(interview_id,target_role,scenario,difficulty,questions,"
        "current_index,status) VALUES ('old','开发','求职面试','标准',?,1,'completed')",
        (json.dumps(["Explain\n线程安全"]),),
    )
    conn.execute(
        "INSERT INTO interview_turns(turn_id,interview_id,question_index,question,answer,score,"
        "dimensions,fluency_metrics,content_analysis,created_at) "
        "VALUES ('original','old',0,'Explain\n线程安全',?,0,'{}','{}',?,'2025-01-02T03:04:05')",
        ("  原文\nwith whitespace  ", "{broken"),
    )
    conn.commit()
    conn.close()


def test_upgrade_backfills_once_without_rewriting_raw_turn(tmp_path):
    path = tmp_path / "old.db"
    legacy_db(path)
    store = SQLiteStorage(path)
    try:
        raw = dict(store._conn().execute("SELECT * FROM interview_turns").fetchone())
        store.init_schema()
        attempt = dict(store._conn().execute("SELECT * FROM interview_answer_attempts").fetchone())
        assert (attempt["version"], attempt["answer"], attempt["created_at"]) == (
            1,
            "  原文\nwith whitespace  ",
            "2025-01-02T03:04:05",
        )
        assert attempt["turn_id"] == "original"
        assert attempt["origin"] == "migrated"
        assert dict(store._conn().execute("SELECT * FROM interview_turns").fetchone()) == raw
        store.init_schema()
        assert (
            store._conn().execute("SELECT COUNT(*) FROM interview_answer_attempts").fetchone()[0]
            == 1
        )
        assert (
            store._conn()
            .execute("SELECT COUNT(*) FROM interview_coach_analysis_runs")
            .fetchone()[0]
            == 0
        )
        state = store._conn().execute("SELECT * FROM interview_coach_state").fetchone()
        assert state["external_consent"] == 0
        assert state["phase"] == "summary"
    finally:
        store.close()


def test_backfill_failure_rolls_back_all_and_restart_recovers(tmp_path, monkeypatch):
    from filemate.interview_coach import repository

    path = tmp_path / "old.db"
    legacy_db(path)
    original = repository.record_attempt_from_turn

    def fail_after_capture(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(repository, "record_attempt_from_turn", fail_after_capture)
    store = SQLiteStorage(path)
    try:
        with pytest.raises(RuntimeError, match="synthetic failure"):
            store.init_schema()
        assert (
            store._conn().execute("SELECT COUNT(*) FROM interview_answer_attempts").fetchone()[0]
            == 0
        )
        assert (
            store._conn().execute("SELECT answer FROM interview_turns").fetchone()[0]
            == "  原文\nwith whitespace  "
        )
        monkeypatch.setattr(repository, "record_attempt_from_turn", original)
        store.init_schema()
        assert (
            store._conn().execute("SELECT COUNT(*) FROM interview_answer_attempts").fetchone()[0]
            == 1
        )
    finally:
        store.close()


def test_legacy_save_is_atomic_with_version_capture(tmp_path, monkeypatch):
    from filemate.interview_coach import repository

    store = SQLiteStorage(tmp_path / "new.db")
    store.init_schema()
    session = store.create_interview(
        target_role="开发", scenario="求职面试", difficulty="标准", questions=["第一题", "第二题"]
    )
    payload = {
        "interview_id": session["interview_id"],
        "question_index": 0,
        "question": "第一题",
        "answer": "我的回答",
        "score": None,
        "dimensions": {},
        "feedback": "待分析",
    }
    original = repository.record_attempt_from_turn

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic capture failure")

    try:
        monkeypatch.setattr(repository, "record_attempt_from_turn", fail)
        with pytest.raises(RuntimeError, match="capture failure"):
            store.save_interview_turn(**payload)
        assert store.get_interview(session["interview_id"])["current_index"] == 0
        assert store._conn().execute("SELECT COUNT(*) FROM interview_turns").fetchone()[0] == 0
        monkeypatch.setattr(repository, "record_attempt_from_turn", original)
        saved = store.save_interview_turn(**payload)
        attempt = store._conn().execute("SELECT * FROM interview_answer_attempts").fetchone()
        assert (attempt["version"], attempt["answer"], attempt["origin"]) == (
            1,
            "我的回答",
            "legacy_write",
        )
        assert saved["current_index"] == 1
        state = store._conn().execute("SELECT * FROM interview_coach_state").fetchone()
        assert (state["displayed_index"], state["phase"]) == (1, "question")
        assert (
            store._conn().execute("SELECT COUNT(*) FROM interview_coach_questions").fetchone()[0]
            == 2
        )
    finally:
        store.close()


def test_valid_legacy_score_keeps_unknown_provenance_without_invented_finish_time(tmp_path):
    from filemate.interview_coach.repository import attempt_view
    from filemate.interview_review.models import CONTENT_AREAS

    store = SQLiteStorage(tmp_path / "legacy-score.db")
    store.init_schema()
    session = store.create_interview(
        target_role="开发", scenario="求职面试", difficulty="标准", questions=["项目"]
    )
    content = {
        "source": "llm_reference",
        "dimension_evidence": dict.fromkeys(["内容", "结构", "表达", "岗位匹配"], "真实原文"),
        "keywords": [],
        "areas": {
            k: {"status": "partial", "evidence": "真实原文", "suggestion": "补充依据"}
            for k in CONTENT_AREAS
        },
    }
    try:
        store.save_interview_turn(
            interview_id=session["interview_id"],
            question_index=0,
            question="项目",
            answer="真实原文",
            score=0,
            dimensions={},
            feedback="补充依据",
            scoring_mode="llm",
            content_analysis=content,
        )
        row = store._conn().execute("SELECT * FROM interview_answer_attempts").fetchone()
        view = attempt_view(store._conn(), row)
        assert view.score == 0
        run = store._conn().execute("SELECT * FROM interview_coach_analysis_runs").fetchone()
        assert (run["model"], run["prompt_version"], run["rubric_version"]) == (
            "legacy_unknown",
        ) * 3
        assert run["finished_at"] is None
    finally:
        store.close()
