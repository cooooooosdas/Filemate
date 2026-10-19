"""Versioned interview configuration; preferences never grant permissions."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

TRACKS = {
    "general": {"general": "求职面试", "hr": "HR面"},
    "technical": {"technical": "技术面", "algorithm": "算法面"},
    "project": {"project": "项目面", "competition": "竞赛答辩", "academic": "保研复试"},
    "creator": {"knowledge": None, "commerce": None},
    "learning_expression": {"explain": "知识讲解"},
}


class MediaPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    camera: bool = False
    microphone: bool = False
    transcription: bool = False
    local_recording: bool = False
    post_analysis: bool = False


class InterviewConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    category: Literal["general", "technical", "project", "creator", "learning_expression"] = "general"
    track: str = Field(default="general", max_length=24)
    language: Literal["zh-CN", "en-US"] = "zh-CN"
    difficulty: Literal["入门", "标准", "压力面"] = "标准"
    duration_minutes: int = Field(default=10, ge=1, le=60)
    difficulty_strategy: Literal["standard", "challenge"] = "standard"
    question_strategy: Literal["fixed", "random", "ai", "mixed"] = "fixed"
    media_preferences: MediaPreferences = Field(default_factory=MediaPreferences)

    @model_validator(mode="after")
    def validate_track(self):
        if self.track not in TRACKS[self.category]:
            raise ValueError("训练方向与专项不匹配")
        return self

    def legacy_scenario(self) -> str:
        """Reject capabilities the fixed-question runtime cannot execute."""
        if self.category == "creator" or self.question_strategy != "fixed":
            raise ValueError("该任务模式尚未启用，可保存配置，暂不能开始")
        if self.language == "en-US":
            if (self.category, self.track, self.difficulty_strategy) != ("general", "general", "standard"):
                raise ValueError("英文目前仅支持通用求职；其他英文专项尚未启用")
            return "英语面"
        if self.difficulty_strategy == "challenge":
            if (self.category, self.track) != ("general", "general"):
                raise ValueError("挑战追问目前仅支持通用求职")
            return "压力面"
        return TRACKS[self.category][self.track]


class DraftContent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    configuration: InterviewConfiguration = Field(default_factory=InterviewConfiguration)
    target_role: str = Field(default="", max_length=120)
    source_id: str = Field(default="", max_length=64)
    project_name: str = Field(default="", max_length=120)
    project_details: str = Field(default="", max_length=6000)


class SaveDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    content: DraftContent
    expected_revision: int = Field(ge=0)
    request_key: str = Field(min_length=12, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")


def legacy_projection(scenario: str, difficulty: str) -> dict[str, Any]:
    category, track, language = "legacy", "unknown", None
    for group, tracks in TRACKS.items():
        for item, value in tracks.items():
            if value == scenario:
                category, track, language = group, item, "zh-CN"
    if scenario in {"英语面", "压力面"}:
        category, track, language = "general", "general", "en-US" if scenario == "英语面" else "zh-CN"
    return {"schema_version": 1, "origin": "legacy", "original_scenario": scenario,
            "category": category, "track": track, "language": language, "difficulty": difficulty,
            "duration_minutes": None, "question_strategy": "fixed", "timing_active": False,
            "difficulty_strategy": "challenge" if scenario == "压力面" else "standard"}


def session_configuration(conn, interview_id: str, scenario: str, difficulty: str) -> dict[str, Any]:
    row = conn.execute("SELECT configuration FROM interview_session_config WHERE interview_id=?", (interview_id,)).fetchone()
    if row:
        try:
            config = InterviewConfiguration.model_validate_json(row[0])
            return {**config.model_dump(), "origin": "snapshot", "timing_active": False}
        except (ValueError, ValidationError):
            return {**legacy_projection(scenario, difficulty), "origin": "unavailable",
                    "error": "配置无法读取；原题和回答仍保留，可导出后恢复备份"}
    return legacy_projection(scenario, difficulty)


class ConfigurationRepository:
    def __init__(self, storage):
        self.storage = storage

    def read_draft(self) -> dict[str, Any]:
        row = self.storage._conn().execute("SELECT * FROM interview_configuration_draft WHERE singleton=1").fetchone()
        if not row:
            return {"revision": 0, "content": None, "updated_at": None, "error": None}
        try:
            content = DraftContent.model_validate_json(row["content"]).model_dump()
            error = None
        except (ValueError, ValidationError):
            content, error = None, "草稿无法读取；原记录保留，可重新保存当前配置"
        return {"revision": row["revision"], "content": content, "updated_at": row["updated_at"], "error": error}

    def save_draft(self, content: DraftContent, revision: int, request_key: str) -> dict[str, Any]:
        from filemate.execution.storage import _now_iso

        serialized = json.dumps(content.model_dump(), ensure_ascii=False, sort_keys=True)
        with self.storage._write_lock, self.storage._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM interview_configuration_draft WHERE singleton=1").fetchone()
            if row and row["request_key"] == request_key:
                if row["content"] != serialized:
                    raise ValueError("同一保存请求内容已变化，请重新保存")
                return self.read_draft()
            if (row["revision"] if row else 0) != revision:
                raise ValueError("草稿已在其他页面更新；先读取最新草稿，再决定保留哪一份")
            conn.execute("INSERT INTO interview_configuration_draft VALUES (1,?,?,?,?) "
                         "ON CONFLICT(singleton) DO UPDATE SET revision=excluded.revision,content=excluded.content,"
                         "request_key=excluded.request_key,updated_at=excluded.updated_at",
                         (revision + 1, serialized, request_key, _now_iso()))
        return self.read_draft()
