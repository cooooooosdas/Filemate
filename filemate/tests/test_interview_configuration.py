"""Synthetic configuration persistence and compatibility contracts."""

import json

import pytest
from pydantic import ValidationError

from filemate.execution.storage import SQLiteStorage
from filemate.interview_config import (
    ConfigurationRepository,
    DraftContent,
    InterviewConfiguration,
    legacy_projection,
)


@pytest.fixture
def store(tmp_path):
    storage = SQLiteStorage(tmp_path / "config.db")
    storage.init_schema()
    yield storage
    storage.close()


@pytest.mark.parametrize(("scenario", "category", "track", "language"), [
    ("技术面", "technical", "technical", "zh-CN"),
    ("英语面", "general", "general", "en-US"),
    ("知识讲解", "learning_expression", "explain", "zh-CN"),
    ("保研复试", "project", "academic", "zh-CN"),
    ("未知旧模式", "legacy", "unknown", None),
])
def test_legacy_projection_does_not_invent_duration(scenario, category, track, language):
    data = legacy_projection(scenario, "标准")
    assert (data["category"], data["track"], data["language"]) == (category, track, language)
    assert data["duration_minutes"] is None
    assert data["original_scenario"] == scenario


def test_unsupported_choices_are_valid_drafts_but_not_launchable():
    for values in [{"category": "creator", "track": "commerce"},
                   {"category": "technical", "track": "algorithm", "language": "en-US"},
                   {"question_strategy": "mixed"}]:
        config = InterviewConfiguration(**values)
        with pytest.raises(ValueError):
            config.legacy_scenario()
    with pytest.raises(ValidationError):
        InterviewConfiguration(category="technical", track="hr")
    with pytest.raises(ValidationError):
        InterviewConfiguration(duration_minutes=999)


def test_draft_revision_prevents_silent_overwrite_and_survives_reopen(store):
    repo = ConfigurationRepository(store)
    assert repo.read_draft()["revision"] == 0
    content = DraftContent(target_role="合成岗位", project_details="合成项目事实")
    saved = repo.save_draft(content, 0, "draft-command-001")
    assert saved["revision"] == 1
    assert repo.save_draft(content, 0, "draft-command-001") == saved
    with pytest.raises(ValueError):
        repo.save_draft(DraftContent(target_role="其他"), 0, "draft-command-002")
    store.close()
    assert ConfigurationRepository(store).read_draft()["content"]["project_details"] == "合成项目事实"
    with pytest.raises(ValidationError):
        DraftContent(external_consent=True)


def test_snapshot_immutable_draft_independent_and_fk_cascades(store):
    session = store.create_interview(target_role="测试", scenario="技术面", difficulty="标准",
                                     questions=["真实项目？"],
                                     configuration=InterviewConfiguration(category="technical", track="technical").model_dump())
    sid = session["interview_id"]
    ConfigurationRepository(store).save_draft(DraftContent(target_role="新草稿"), 0, "draft-command-003")
    assert store.get_interview(sid)["configuration"]["category"] == "technical"
    assert store.get_interview(sid)["configuration"]["timing_active"] is False
    store._conn().execute("DELETE FROM interview_sessions WHERE interview_id=?", (sid,))
    store._conn().commit()
    assert store._conn().execute("SELECT COUNT(*) FROM interview_session_config").fetchone()[0] == 0
    assert not store._conn().execute("PRAGMA foreign_key_check").fetchall()


def test_old_sessions_and_corrupt_config_remain_readable(store):
    old = store.create_interview(target_role="历史", scenario="未知旧模式", difficulty="标准", questions=["原题"])
    sid = old["interview_id"]
    store.init_schema()
    assert store.get_interview(sid)["questions"] == ["原题"]
    assert store.get_interview(sid)["configuration"]["origin"] == "legacy"
    store._conn().execute("INSERT INTO interview_session_config VALUES (?, ?, ?)", (sid, "{bad", "2026-10-19"))
    store._conn().commit()
    assert store.get_interview(sid)["configuration"]["origin"] == "unavailable"
    assert store.get_interview(sid)["questions"] == ["原题"]


def test_draft_corruption_is_visible_without_destroying_saved_record(store):
    repo = ConfigurationRepository(store)
    repo.save_draft(DraftContent(target_role="测试"), 0, "draft-command-004")
    store._conn().execute("UPDATE interview_configuration_draft SET content=?", (json.dumps({"external_consent": True}),))
    store._conn().commit()
    assert repo.read_draft()["content"] is None
    assert repo.read_draft()["error"]


def test_custom_duration_and_device_preferences_never_grant_permissions(store):
    config = InterviewConfiguration(duration_minutes=3, media_preferences={"camera": True, "post_analysis": True})
    assert InterviewConfiguration(duration_minutes=27).duration_minutes == 27
    session = store.create_interview(target_role="测试", scenario="求职面试", difficulty="标准",
                                     questions=["介绍经历"], configuration=config.model_dump())
    assert session["configuration"]["media_preferences"]["camera"] is True
    state = store._conn().execute('SELECT external_consent FROM interview_coach_state').fetchone()
    assert state[0] == 0
    with pytest.raises(ValidationError):
        InterviewConfiguration(duration_minutes=0)
