"""SQLite 持久化。

Schema 与《项目总纲 v1.0》§3.6 对齐。
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from filemate.execution import data_actions

logger = logging.getLogger(__name__)


class QuestionRevisionConflict(ValueError):
    """拒绝把过期题目上的判题结果写入新题目。"""

# ──────────────────────────────────────────────
#  Schema（与 项目总纲 §3.6 保持一致）
# ──────────────────────────────────────────────

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS sessions (
    session_id       TEXT PRIMARY KEY,
    source_path      TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending'
                     CHECK(status IN ('pending','processing','done','confirmed','skipped','expired','failed')),
    category         TEXT,
    confidence       REAL,
    suggested_name   TEXT,
    entities         TEXT,   -- JSON
    milestones       TEXT,   -- JSON
    error            TEXT,
    user_modified    INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE TABLE IF NOT EXISTS processed_files (
    file_hash         TEXT PRIMARY KEY,
    session_id        TEXT NOT NULL REFERENCES sessions(session_id),
    first_seen_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    last_processed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    process_count     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS operation_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT NOT NULL REFERENCES sessions(session_id),
    action            TEXT NOT NULL,
    detail            TEXT DEFAULT '',
    input_snapshot    TEXT,
    user_override     TEXT,
    latency_ms        INTEGER,
    model_used        TEXT,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE TABLE IF NOT EXISTS user_rules (
    rule_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_type   TEXT NOT NULL,
    pattern     TEXT NOT NULL,
    replacement TEXT NOT NULL,
    priority    INTEGER NOT NULL DEFAULT 0,
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE INDEX IF NOT EXISTS idx_sessions_status    ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_created   ON sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_operation_log_sid  ON operation_log(session_id);
CREATE INDEX IF NOT EXISTS idx_operation_log_ts   ON operation_log(created_at);
"""

_KNOWLEDGE_SCHEMA = """\
CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

INSERT OR IGNORE INTO workspaces (workspace_id, name) VALUES ('local', '本地工作区');

CREATE TABLE IF NOT EXISTS sources (
    source_id     TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL DEFAULT 'local'
                  REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    original_name TEXT NOT NULL,
    source_path   TEXT NOT NULL,
    media_type    TEXT NOT NULL DEFAULT '',
    file_hash     TEXT,
    raw_text      TEXT NOT NULL DEFAULT '',
    metadata      TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id   TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL DEFAULT 'local'
                  REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    source_id     TEXT REFERENCES sources(source_id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    title         TEXT NOT NULL DEFAULT '',
    content       TEXT NOT NULL,
    metadata      TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE TABLE IF NOT EXISTS document_contexts (
    ctx_id        TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL DEFAULT 'local'
                  REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    source_id     TEXT REFERENCES sources(source_id) ON DELETE CASCADE,
    artifact_id   TEXT REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
    context_text  TEXT NOT NULL,
    chat_history  TEXT NOT NULL DEFAULT '[]',
    metadata      TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    expires_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_sources_workspace ON sources(workspace_id, created_at);
CREATE INDEX IF NOT EXISTS idx_sources_hash ON sources(workspace_id, file_hash);
CREATE INDEX IF NOT EXISTS idx_artifacts_source ON artifacts(source_id, created_at);
CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts(workspace_id, artifact_type);
CREATE INDEX IF NOT EXISTS idx_contexts_source ON document_contexts(source_id, created_at);
"""

_EXECUTION_SCHEMA = """\
CREATE TABLE IF NOT EXISTS execution_records (
    execution_id   TEXT PRIMARY KEY,
    session_id     TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK(status IN ('pending','applied','undone','failed')),
    source_path    TEXT NOT NULL,
    dest_path      TEXT NOT NULL,
    ics_path       TEXT,
    input_snapshot TEXT NOT NULL DEFAULT '{}',
    output_snapshot TEXT NOT NULL DEFAULT '{}',
    error          TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    applied_at     TEXT,
    undone_at      TEXT,
    updated_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE INDEX IF NOT EXISTS idx_execution_session
    ON execution_records(session_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_open
    ON execution_records(session_id)
    WHERE status IN ('pending','applied');
"""

_LEARNING_SCHEMA = """\
CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id     TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    chunk_index  INTEGER NOT NULL,
    page_number  INTEGER,
    content      TEXT NOT NULL,
    metadata     TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    UNIQUE(source_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    attempt_id      TEXT PRIMARY KEY,
    artifact_id     TEXT NOT NULL REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    source_id       TEXT REFERENCES sources(source_id) ON DELETE CASCADE,
    question_index  INTEGER NOT NULL,
    user_answer     TEXT NOT NULL,
    is_correct      INTEGER NOT NULL,
    score           REAL NOT NULL,
    feedback        TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE TABLE IF NOT EXISTS wrong_questions (
    wrong_id         TEXT PRIMARY KEY,
    artifact_id      TEXT NOT NULL REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    source_id        TEXT REFERENCES sources(source_id) ON DELETE CASCADE,
    question_index   INTEGER NOT NULL,
    question         TEXT NOT NULL,
    latest_answer    TEXT NOT NULL DEFAULT '',
    error_count      INTEGER NOT NULL DEFAULT 1,
    correct_streak   INTEGER NOT NULL DEFAULT 0,
    mastered         INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    UNIQUE(artifact_id, question_index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_source ON document_chunks(source_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_attempts_artifact ON quiz_attempts(artifact_id, created_at);
CREATE INDEX IF NOT EXISTS idx_wrong_mastered ON wrong_questions(mastered, updated_at);
"""

_INTERVIEW_SCHEMA = """\
CREATE TABLE IF NOT EXISTS interview_sessions (
    interview_id  TEXT PRIMARY KEY,
    target_role   TEXT NOT NULL,
    scenario      TEXT NOT NULL,
    difficulty    TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active',
    questions     TEXT NOT NULL,
    current_index INTEGER NOT NULL DEFAULT 0,
    overall_score REAL NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE TABLE IF NOT EXISTS interview_turns (
    turn_id        TEXT PRIMARY KEY,
    interview_id   TEXT NOT NULL REFERENCES interview_sessions(interview_id) ON DELETE CASCADE,
    question_index INTEGER NOT NULL,
    question       TEXT NOT NULL,
    answer         TEXT NOT NULL,
    score          REAL NOT NULL,
    dimensions     TEXT NOT NULL DEFAULT '{}',
    feedback       TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    UNIQUE(interview_id, question_index)
);

CREATE INDEX IF NOT EXISTS idx_interview_turns ON interview_turns(interview_id, question_index);
"""

_STUDY_PLAN_SCHEMA = """\
CREATE TABLE IF NOT EXISTS study_plans (
    plan_id         TEXT PRIMARY KEY,
    artifact_id     TEXT NOT NULL UNIQUE REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    source_id       TEXT REFERENCES sources(source_id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    exam_date       TEXT NOT NULL,
    daily_minutes   INTEGER NOT NULL,
    goal            TEXT NOT NULL DEFAULT '',
    plan_data       TEXT NOT NULL,
    completed_days  TEXT NOT NULL DEFAULT '[]',
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK(status IN ('active','completed','archived')),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE INDEX IF NOT EXISTS idx_study_plans_status
    ON study_plans(status, updated_at);
"""

_PRODUCT_FEEDBACK_SCHEMA = """\
CREATE TABLE IF NOT EXISTS product_feedback (
    feedback_id  TEXT PRIMARY KEY,
    area         TEXT NOT NULL
                 CHECK(area IN ('retrieval','tutor','interview','study_plan')),
    target_hash  TEXT NOT NULL,
    rating       INTEGER NOT NULL CHECK(rating IN (-1, 1)),
    context      TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    UNIQUE(area, target_hash)
);

CREATE INDEX IF NOT EXISTS idx_product_feedback_area
    ON product_feedback(area, updated_at);
"""

_SPACED_REPETITION_SCHEMA = """\
ALTER TABLE wrong_questions
    ADD COLUMN next_review_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00+00:00';
ALTER TABLE wrong_questions
    ADD COLUMN interval_days INTEGER NOT NULL DEFAULT 0;
ALTER TABLE wrong_questions
    ADD COLUMN ease_factor REAL NOT NULL DEFAULT 2.5;
ALTER TABLE wrong_questions
    ADD COLUMN review_count INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_wrong_next_review
    ON wrong_questions(mastered, next_review_at);
"""

_INTERVIEW_BANK_SCHEMA = """\
CREATE TABLE IF NOT EXISTS interview_questions (
    id          TEXT PRIMARY KEY,
    scenario    TEXT NOT NULL
                CHECK(scenario IN ('求职面试','竞赛答辩','保研复试')),
    difficulty  TEXT NOT NULL
                CHECK(difficulty IN ('入门','标准','压力面')),
    text        TEXT NOT NULL CHECK(length(trim(text)) BETWEEN 1 AND 1000),
    enabled     INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    UNIQUE(scenario, difficulty, text)
);

CREATE INDEX IF NOT EXISTS idx_interview_questions_filter
    ON interview_questions(scenario, difficulty, enabled);

ALTER TABLE interview_sessions
    ADD COLUMN question_ids TEXT NOT NULL DEFAULT '[]';
"""

# v9 曾在未合并的开发分支中被 AI 学习实验占用，部分本地数据库还保留
# v9-v11 的实验迁移记录。v12 只补齐现役题库表；question_ids 由初始化时
# 的列检查幂等修复，避免重复 ALTER TABLE。
_INTERVIEW_BANK_REPAIR_SCHEMA = """\
CREATE TABLE IF NOT EXISTS interview_questions (
    id          TEXT PRIMARY KEY,
    scenario    TEXT NOT NULL
                CHECK(scenario IN ('求职面试','竞赛答辩','保研复试')),
    difficulty  TEXT NOT NULL
                CHECK(difficulty IN ('入门','标准','压力面')),
    text        TEXT NOT NULL CHECK(length(trim(text)) BETWEEN 1 AND 1000),
    enabled     INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    UNIQUE(scenario, difficulty, text)
);

CREATE INDEX IF NOT EXISTS idx_interview_questions_filter
    ON interview_questions(scenario, difficulty, enabled);
"""

_INTERVIEW_FLUENCY_SCHEMA = """\
ALTER TABLE interview_turns
    ADD COLUMN fluency_metrics TEXT NOT NULL DEFAULT '{}';
"""

_TRUSTED_AGENT_SCHEMA = """\
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id          TEXT PRIMARY KEY,
    task_type       TEXT NOT NULL,
    goal            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'running'
                    CHECK(status IN ('running','completed','failed')),
    selected_agents TEXT NOT NULL DEFAULT '[]',
    context_refs    TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE TABLE IF NOT EXISTS agent_steps (
    step_id        TEXT PRIMARY KEY,
    run_id         TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    sequence       INTEGER NOT NULL,
    agent_name     TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'completed'
                   CHECK(status IN ('completed','failed','blocked')),
    input_refs     TEXT NOT NULL DEFAULT '{}',
    output_summary TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    UNIQUE(run_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_recent
    ON agent_runs(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_steps_run
    ON agent_steps(run_id, sequence);

CREATE TABLE IF NOT EXISTS agent_memories (
    memory_id      TEXT PRIMARY KEY,
    memory_type    TEXT NOT NULL
                   CHECK(memory_type IN ('session','knowledge','growth','operation')),
    scope_id       TEXT NOT NULL,
    source_type    TEXT NOT NULL,
    source_id      TEXT NOT NULL,
    summary        TEXT NOT NULL,
    allowed_agents TEXT NOT NULL DEFAULT '[]',
    expires_at     TEXT,
    deleted_at     TEXT,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE INDEX IF NOT EXISTS idx_agent_memories_scope
    ON agent_memories(scope_id, memory_type, deleted_at);

CREATE TABLE IF NOT EXISTS source_rights (
    source_id      TEXT PRIMARY KEY REFERENCES sources(source_id) ON DELETE CASCADE,
    rights_status  TEXT NOT NULL DEFAULT 'unconfirmed'
                   CHECK(rights_status IN ('unconfirmed','self_owned','authorized','public')),
    sharing_scope  TEXT NOT NULL DEFAULT 'private'
                   CHECK(sharing_scope IN ('private','restricted','shareable')),
    note           TEXT NOT NULL DEFAULT '',
    confirmed_at   TEXT,
    updated_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

ALTER TABLE interview_sessions
    ADD COLUMN agent_run_id TEXT REFERENCES agent_runs(run_id);
"""

_INTERVIEW_SCORING_SCHEMA = """\
ALTER TABLE interview_turns ADD COLUMN scoring_mode TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE interview_turns ADD COLUMN scoring_version TEXT NOT NULL DEFAULT 'legacy';
"""

_WRONG_DIAGNOSIS_SCHEMA = """\
ALTER TABLE wrong_questions ADD COLUMN knowledge_key TEXT NOT NULL DEFAULT '';
ALTER TABLE wrong_questions ADD COLUMN knowledge_label TEXT NOT NULL DEFAULT '';
ALTER TABLE wrong_questions ADD COLUMN error_cause TEXT NOT NULL DEFAULT 'unconfirmed';
ALTER TABLE wrong_questions ADD COLUMN error_cause_source TEXT NOT NULL DEFAULT 'unconfirmed';
ALTER TABLE wrong_questions ADD COLUMN error_cause_confidence REAL NOT NULL DEFAULT 0;
ALTER TABLE wrong_questions ADD COLUMN error_cause_note TEXT NOT NULL DEFAULT '';
ALTER TABLE wrong_questions ADD COLUMN diagnosed_at TEXT;

CREATE INDEX IF NOT EXISTS idx_wrong_knowledge
    ON wrong_questions(source_id, knowledge_key, mastered);
"""

_DIGITAL_HUMAN_SCHEMA = """\
CREATE TABLE IF NOT EXISTS digital_human_playbacks (
    playback_id TEXT PRIMARY KEY,
    context_id TEXT,
    message_index INTEGER,
    text_length INTEGER NOT NULL CHECK(text_length BETWEEN 1 AND 5000),
    avatar_id TEXT NOT NULL,
    voice_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    module_version TEXT NOT NULL DEFAULT '2.1',
    status TEXT NOT NULL CHECK(status IN ('started','completed','stopped','failed')),
    error_code TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_digital_human_playbacks_time
    ON digital_human_playbacks(created_at DESC);
"""

_KNOWLEDGE_GRAPH_SCHEMA = """\
CREATE TABLE IF NOT EXISTS knowledge_graph_batches (
    batch_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    source_revision TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('local','llm')),
    status TEXT NOT NULL CHECK(status IN ('draft','confirmed','undone','failed')),
    payload TEXT NOT NULL,
    error_code TEXT NOT NULL DEFAULT '',
    module_version TEXT NOT NULL DEFAULT '2.2',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_graph_batches_source
    ON knowledge_graph_batches(source_id, created_at DESC);
"""

_DAILY_COACH_SCHEMA = """\
CREATE TABLE IF NOT EXISTS daily_coach_preferences (
    study_date TEXT PRIMARY KEY,
    available_minutes INTEGER NOT NULL CHECK(available_minutes BETWEEN 10 AND 240),
    item_order TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL
);
"""

_EXPRESSION_CYCLE_SCHEMA = """\
ALTER TABLE interview_sessions
    ADD COLUMN expression_review TEXT NOT NULL DEFAULT '{}';
"""

_GRAPH_EVENTS_SCHEMA = """\
CREATE TABLE IF NOT EXISTS knowledge_graph_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    target_id TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}',
    module_version TEXT NOT NULL DEFAULT '2.2',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_graph_events_source
    ON knowledge_graph_events(source_id, event_id DESC);
"""

_PROGRAMMING_SCHEMA = """\
CREATE TABLE IF NOT EXISTS coding_submissions (
    submission_id TEXT PRIMARY KEY,
    request_key TEXT NOT NULL UNIQUE,
    problem_id TEXT NOT NULL,
    problem_version INTEGER NOT NULL,
    artifact_id TEXT NOT NULL UNIQUE REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK(status IN ('queued','running','completed','cancelled','failed')),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_coding_problem ON coding_submissions(problem_id, created_at);
CREATE TABLE IF NOT EXISTS coding_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id TEXT REFERENCES coding_submissions(submission_id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
"""


_INTERVIEW_REVIEW_SCHEMA = """\
ALTER TABLE interview_turns ADD COLUMN visual_metrics TEXT NOT NULL DEFAULT '{}';
ALTER TABLE interview_turns ADD COLUMN content_analysis TEXT NOT NULL DEFAULT '{}';
ALTER TABLE interview_turns ADD COLUMN answer_key TEXT;
ALTER TABLE interview_turns ADD COLUMN answer_digest TEXT;
CREATE UNIQUE INDEX idx_interview_answer_key
    ON interview_turns(interview_id, answer_key) WHERE answer_key IS NOT NULL;
CREATE TABLE interview_review_state (
    interview_id TEXT PRIMARY KEY REFERENCES interview_sessions(interview_id) ON DELETE CASCADE,
    revision INTEGER NOT NULL DEFAULT 0,
    artifact_id TEXT REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
    input_digest TEXT NOT NULL DEFAULT ''
);
CREATE TABLE interview_review_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    interview_id TEXT,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX idx_interview_review_events ON interview_review_events(interview_id, event_id DESC);
"""

_CAREER_SCHEMA = """\
CREATE TABLE career_positions (
    position_id TEXT PRIMARY KEY,
    request_key TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE career_trainings (
    training_id TEXT PRIMARY KEY,
    position_id TEXT NOT NULL REFERENCES career_positions(position_id) ON DELETE CASCADE,
    request_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    interview_id TEXT REFERENCES interview_sessions(interview_id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE career_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id TEXT,
    training_id TEXT,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX idx_career_trainings ON career_trainings(position_id, created_at DESC);
CREATE INDEX idx_career_events ON career_events(position_id, event_id DESC);
"""

_ACCOUNT_SCHEMA = """\
CREATE TABLE accounts (
    account_id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    recovery_hash TEXT NOT NULL,
    workspace_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);
CREATE TABLE account_sessions (
    token_hash TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX idx_account_sessions_owner ON account_sessions(account_id);
CREATE INDEX idx_account_sessions_expiry ON account_sessions(expires_at);
CREATE TABLE account_attempts (
    attempt_key TEXT PRIMARY KEY,
    window_start INTEGER NOT NULL,
    attempts INTEGER NOT NULL
);
"""

_MIGRATIONS = (
    (1, "initial_execution_schema", _SCHEMA),
    (2, "knowledge_persistence", _KNOWLEDGE_SCHEMA),
    (3, "reversible_execution", _EXECUTION_SCHEMA),
    (4, "retrieval_and_wrongbook", _LEARNING_SCHEMA),
    (5, "mock_interview", _INTERVIEW_SCHEMA),
    (6, "persistent_study_plans", _STUDY_PLAN_SCHEMA),
    (7, "anonymous_product_feedback", _PRODUCT_FEEDBACK_SCHEMA),
    (8, "spaced_repetition", _SPACED_REPETITION_SCHEMA),
    (9, "interview_question_bank", _INTERVIEW_BANK_SCHEMA),
    (12, "interview_question_bank_compatibility", _INTERVIEW_BANK_REPAIR_SCHEMA),
    (13, "interview_fluency_metrics", _INTERVIEW_FLUENCY_SCHEMA),
    (14, "trusted_agent_memory_and_rights", _TRUSTED_AGENT_SCHEMA),
    (15, "interview_scoring_provenance", _INTERVIEW_SCORING_SCHEMA),
    (16, "wrong_question_knowledge_and_diagnosis", _WRONG_DIAGNOSIS_SCHEMA),
    (17, "digital_human_playback_metadata", _DIGITAL_HUMAN_SCHEMA),
    (18, "personal_knowledge_graph_batches", _KNOWLEDGE_GRAPH_SCHEMA),
    (19, "daily_coach_preferences", _DAILY_COACH_SCHEMA),
    (20, "interview_expression_review", _EXPRESSION_CYCLE_SCHEMA),
    (21, "knowledge_graph_operation_events", _GRAPH_EVENTS_SCHEMA),
    (22, "isolated_programming_submissions", _PROGRAMMING_SCHEMA),
    (23, "interview_observation_and_review", _INTERVIEW_REVIEW_SCHEMA),
    (24, "career_training_center", _CAREER_SCHEMA),
    (25, "accounts_and_revocable_sessions", _ACCOUNT_SCHEMA),
    (26, "confirmed_data_actions", data_actions.SCHEMA),
)


# update_session / update_rule 允许更新的列（防止拼写错误；SQL 注入已由参数化查询防御）
_ALLOWED_SESSION_COLS = {
    "status", "category", "confidence", "suggested_name",
    "entities", "milestones", "error", "user_modified",
}
_ALLOWED_RULE_COLS = {"pattern", "replacement", "priority", "enabled"}
_ALLOWED_EXECUTION_COLS = {
    "status",
    "dest_path",
    "ics_path",
    "output_snapshot",
    "error",
    "applied_at",
    "undone_at",
}
_ALLOWED_INTERVIEW_QUESTION_COLS = {"scenario", "difficulty", "text", "enabled"}
_INTERVIEW_SCENARIOS = {"求职面试", "竞赛答辩", "保研复试"}
_INTERVIEW_DIFFICULTIES = {"入门", "标准", "压力面"}


def _now_iso() -> str:
    """生成带时区的 UTC 时间。"""
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


_ERROR_CAUSES = {
    "unconfirmed",
    "concept_gap",
    "memory_gap",
    "reasoning_break",
    "expression_gap",
    "option_confusion",
    "careless",
}


def _knowledge_identity(
    question: dict[str, Any],
    *,
    source_id: str | None,
    artifact_id: str,
) -> tuple[str, str]:
    """从持久化题目生成资料范围内稳定的知识点标识。"""
    label = str(
        question.get("knowledge_point")
        or question.get("subject")
        or question.get("stem")
        or question.get("question")
        or "未标注知识点"
    ).strip()[:120]
    normalized = "".join(
        character.lower()
        for character in label
        if character.isalnum() or character in {"+", "#"}
    )
    identity_scope = source_id or artifact_id
    key = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"filemate:{identity_scope}:knowledge:{normalized or 'unlabeled'}",
    ).hex
    return key, label


def _suggest_error_cause(
    question: dict[str, Any], user_answer: str,
) -> tuple[str, float]:
    """用保守本地规则给出可被用户修正的错因建议。"""
    answer = user_answer.strip().lower()
    if not answer or answer in {"不知道", "不会", "不清楚", "忘了", "不确定"}:
        return "concept_gap", 0.55
    question_type = str(
        question.get("question_type") or question.get("type") or ""
    ).lower()
    if question_type in {"choice", "选择题", "单选题", "多选题"}:
        return "option_confusion", 0.45
    if question_type in {"fill", "填空题"}:
        return "memory_gap", 0.4
    if question_type in {"short_answer", "简答题", "计算题", "论述题"}:
        return "reasoning_break", 0.35
    return "unconfirmed", 0.0


class SQLiteStorage:
    """SQLite 存储封装（版本迁移 + 线程安全）。

    每张表提供最小完备的 CRUD 接口，调用方通过方法字段参数与表列交互。
    """

    def __init__(self, db_path: str | Path = "filemate.db") -> None:
        self.db_path = Path(db_path)
        self._local = threading.local()
        self._write_lock = threading.RLock()
        self._connections: set[sqlite3.Connection] = set()

    # ------------------------------------------------------------------
    # 内部：每个线程持有一条连接
    # ------------------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                detect_types=sqlite3.PARSE_DECLTYPES,
                timeout=10.0,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=10000")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
            with self._write_lock:
                self._connections.add(conn)
        return conn

    def close(self) -> None:
        """关闭该存储实例创建的全部线程连接。"""
        with self._write_lock:
            for conn in tuple(self._connections):
                conn.close()
            self._connections.clear()
            self._local.conn = None

    @contextmanager
    def read_snapshot(self) -> Iterator[SQLiteStorage]:
        """以独立只读事务聚合大图谱，不占用当前工作区写锁。"""
        snapshot = SQLiteStorage(self.db_path)
        conn = sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True,
                               check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        snapshot._local.conn = conn
        snapshot._connections.add(conn)
        try:
            yield snapshot
        finally:
            conn.rollback()
            snapshot.close()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def init_schema(self) -> None:
        """按版本执行数据库迁移。幂等，可重复调用。"""
        conn = self._conn()
        with self._write_lock:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                       version    INTEGER PRIMARY KEY,
                       name       TEXT NOT NULL,
                       applied_at TEXT NOT NULL DEFAULT
                                  (strftime('%Y-%m-%dT%H:%M:%S','now'))
                   )"""
            )
            conn.commit()
            applied = {
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations")
            }
            for version, name, script in _MIGRATIONS:
                if version in applied:
                    continue
                safe_name = name.replace("'", "''")
                try:
                    conn.executescript(
                        "BEGIN IMMEDIATE;\n"
                        f"{script}\n"
                        "INSERT INTO schema_migrations (version, name) "
                        f"VALUES ({version}, '{safe_name}');\n"
                        "COMMIT;"
                    )
                except Exception:
                    if conn.in_transaction:
                        conn.rollback()
                    raise

            interview_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(interview_sessions)")
            }
            if "question_ids" not in interview_columns:
                conn.execute(
                    "ALTER TABLE interview_sessions "
                    "ADD COLUMN question_ids TEXT NOT NULL DEFAULT '[]'"
                )
                conn.commit()

    def get_schema_version(self) -> int:
        """返回已应用的最高数据库版本。"""
        row = self._conn().execute(
            "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
        ).fetchone()
        return int(row["version"] if row else 0)

    def list_migrations(self) -> list[dict[str, Any]]:
        """按版本列出迁移记录。"""
        rows = self._conn().execute(
            "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # sessions 表
    # ------------------------------------------------------------------

    def create_session(self, session_id: str, source_path: str) -> None:
        with self._write_lock:
            conn = self._conn()
            conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id, source_path) VALUES (?, ?)",
                (session_id, str(source_path)),
            )
            conn.commit()

    def update_session(self, session_id: str, **kwargs: Any) -> None:
        """按字段名更新 session。自动刷新 updated_at。

        支持的字段：status, category, confidence, suggested_name,
        entities, milestones, error, user_modified。
        """
        if not kwargs:
            return
        invalid = set(kwargs) - _ALLOWED_SESSION_COLS
        if invalid:
            raise ValueError(
                f"无效字段: {sorted(invalid)}，允许: {sorted(_ALLOWED_SESSION_COLS)}"
            )
        set_clause = ", ".join(f"{k}=?" for k in kwargs)
        values = list(kwargs.values()) + [_now_iso(), session_id]
        with self._write_lock:
            conn = self._conn()
            conn.execute(
                f"UPDATE sessions SET {set_clause}, updated_at=? WHERE session_id=?",
                values,
            )
            conn.commit()

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_sessions(
        self, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        conn = self._conn()
        if status:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_session(self, session_id: str) -> bool:
        """删除 session 及其关联的操作日志与去重记录。返回是否实际删除了行。"""
        with self._write_lock:
            conn = self._conn()
            conn.execute("DELETE FROM operation_log WHERE session_id=?", (session_id,))
            conn.execute("DELETE FROM processed_files WHERE session_id=?", (session_id,))
            cur = conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
            conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # processed_files 表
    # ------------------------------------------------------------------

    def is_duplicate(self, file_hash: str) -> bool:
        conn = self._conn()
        row = conn.execute(
            "SELECT 1 FROM processed_files WHERE file_hash=?", (file_hash,)
        ).fetchone()
        return row is not None

    def record_hash(self, file_hash: str, session_id: str) -> None:
        """记录文件哈希（新建或更新处理时间+计数）。

        调用方应在调用本方法前先通过 create_session() 创建 session。
        若 session 尚不存在，自动创建占位记录以保证 FK 不报错
        （source_path 为 __auto_created__ 前缀，方便排查调用顺序问题）。
        """
        with self._write_lock:
            conn = self._conn()
            conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id, source_path) VALUES (?, ?)",
                (session_id, f"__auto_created__/{session_id}"),
            )
            conn.execute(
                """INSERT INTO processed_files (file_hash, session_id)
                   VALUES (?, ?)
                   ON CONFLICT(file_hash) DO UPDATE SET
                       last_processed_at = strftime('%Y-%m-%dT%H:%M:%S','now'),
                       process_count = process_count + 1""",
                (file_hash, session_id),
            )
            conn.commit()

    def get_file_info(self, file_hash: str) -> dict[str, Any] | None:
        """查询某个哈希的历史处理信息。"""
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM processed_files WHERE file_hash=?", (file_hash,)
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # operation_log 表
    # ------------------------------------------------------------------

    def log_operation(
        self,
        session_id: str,
        action: str,
        detail: str = "",
        *,
        input_snapshot: str | None = None,
        user_override: str | None = None,
        latency_ms: int | None = None,
        model_used: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
    ) -> int:
        """写入操作日志。返回自增 id。

        新增的 keyword-only 字段对齐项目总纲 §3.6，用于 Prompt 迭代分析。
        """
        with self._write_lock:
            conn = self._conn()
            cur = conn.execute(
                """INSERT INTO operation_log
                   (session_id, action, detail, input_snapshot, user_override,
                    latency_ms, model_used, prompt_tokens, completion_tokens)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id, action, detail, input_snapshot, user_override,
                    latency_ms, model_used, prompt_tokens, completion_tokens,
                ),
            )
            conn.commit()
        return cur.lastrowid

    def get_operations(self, session_id: str) -> list[dict[str, Any]]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM operation_log WHERE session_id=? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # user_rules 表
    # ------------------------------------------------------------------

    def add_rule(
        self,
        rule_type: str,
        pattern: str,
        replacement: str,
        priority: int = 0,
    ) -> int:
        """添加用户自定义规则。返回 rule_id。"""
        with self._write_lock:
            conn = self._conn()
            cur = conn.execute(
                """INSERT INTO user_rules (rule_type, pattern, replacement, priority)
                   VALUES (?, ?, ?, ?)""",
                (rule_type, pattern, replacement, priority),
            )
            conn.commit()
        return cur.lastrowid

    def update_rule(self, rule_id: int, **kwargs: Any) -> bool:
        """更新规则字段（pattern, replacement, priority, enabled 等）。"""
        if not kwargs:
            return False
        invalid = set(kwargs) - _ALLOWED_RULE_COLS
        if invalid:
            raise ValueError(
                f"无效字段: {sorted(invalid)}，允许: {sorted(_ALLOWED_RULE_COLS)}"
            )
        set_clause = ", ".join(f"{k}=?" for k in kwargs)
        values = list(kwargs.values()) + [rule_id]
        with self._write_lock:
            conn = self._conn()
            cur = conn.execute(
                f"UPDATE user_rules SET {set_clause} WHERE rule_id=?",
                values,
            )
            conn.commit()
        return cur.rowcount > 0

    def delete_rule(self, rule_id: int) -> bool:
        """删除规则。返回是否实际删除了行。"""
        with self._write_lock:
            conn = self._conn()
            cur = conn.execute("DELETE FROM user_rules WHERE rule_id=?", (rule_id,))
            conn.commit()
        return cur.rowcount > 0

    def list_rules(
        self, rule_type: str | None = None, enabled_only: bool = True
    ) -> list[dict[str, Any]]:
        conn = self._conn()
        clauses = []
        params: list[Any] = []
        if enabled_only:
            clauses.append("enabled=1")
        if rule_type:
            clauses.append("rule_type=?")
            params.append(rule_type)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM user_rules{where} ORDER BY priority DESC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # workspaces / sources / artifacts / document_contexts
    # ------------------------------------------------------------------

    @staticmethod
    def _dump_json(value: Any) -> str:
        """稳定序列化 JSON 数据。"""
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _decode_row(
        row: sqlite3.Row | None,
        json_fields: tuple[str, ...],
    ) -> dict[str, Any] | None:
        """把 SQLite 行转换为字典并还原 JSON 字段。"""
        if row is None:
            return None
        result = dict(row)
        for field in json_fields:
            raw = result.get(field)
            if raw is None:
                continue
            try:
                result[field] = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                result[field] = {} if field == "metadata" else []
        return result

    def create_workspace(self, workspace_id: str, name: str) -> None:
        """创建或更新工作区。"""
        if not workspace_id.strip() or not name.strip():
            raise ValueError("workspace_id 和 name 不能为空")
        now = _now_iso()
        with self._write_lock:
            self._conn().execute(
                """INSERT INTO workspaces (workspace_id, name)
                   VALUES (?, ?)
                   ON CONFLICT(workspace_id) DO UPDATE SET
                       name=excluded.name, updated_at=?""",
                (workspace_id, name, now),
            )
            self._conn().commit()

    def get_workspace(self, workspace_id: str) -> dict[str, Any] | None:
        """读取单个工作区。"""
        row = self._conn().execute(
            "SELECT * FROM workspaces WHERE workspace_id=?",
            (workspace_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_workspaces(self) -> list[dict[str, Any]]:
        """列出工作区。"""
        rows = self._conn().execute(
            "SELECT * FROM workspaces ORDER BY created_at"
        ).fetchall()
        return [dict(row) for row in rows]

    def save_source(
        self,
        *,
        original_name: str,
        source_path: str,
        raw_text: str = "",
        workspace_id: str = "local",
        media_type: str = "",
        file_hash: str | None = None,
        metadata: dict[str, Any] | None = None,
        source_id: str | None = None,
    ) -> str:
        """新增或更新统一资料源，并返回 source_id。"""
        if not original_name.strip() or not source_path.strip():
            raise ValueError("original_name 和 source_path 不能为空")
        if self.get_workspace(workspace_id) is None:
            raise ValueError(f"工作区不存在: {workspace_id}")

        if source_id is None:
            if file_hash:
                source_id = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"filemate:{workspace_id}:{file_hash}",
                ).hex
            else:
                source_id = uuid.uuid4().hex

        now = _now_iso()
        with self._write_lock:
            self._conn().execute(
                """INSERT INTO sources
                   (source_id, workspace_id, original_name, source_path,
                    media_type, file_hash, raw_text, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_id) DO UPDATE SET
                       original_name=excluded.original_name,
                       source_path=excluded.source_path,
                       media_type=excluded.media_type,
                       file_hash=excluded.file_hash,
                       raw_text=excluded.raw_text,
                       metadata=excluded.metadata,
                       updated_at=?""",
                (
                    source_id,
                    workspace_id,
                    original_name,
                    source_path,
                    media_type,
                    file_hash,
                    raw_text,
                    self._dump_json(metadata or {}),
                    now,
                ),
            )
            self._conn().commit()
        return source_id

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        """按 ID 读取资料源。"""
        row = self._conn().execute(
            "SELECT * FROM sources WHERE source_id=?",
            (source_id,),
        ).fetchone()
        return self._decode_row(row, ("metadata",))

    def get_source_lineage(self, source_id: str) -> dict[str, Any] | None:
        """汇总一份资料已形成的学习资产链，不复制用户原文。"""
        source = self.get_source(source_id)
        if source is None:
            return None
        connection = self._conn()
        artifacts = self.list_artifacts(source_id=source_id, limit=200)
        artifact_counts: dict[str, int] = {}
        for artifact in artifacts:
            artifact_type = str(artifact["artifact_type"])
            artifact_counts[artifact_type] = artifact_counts.get(artifact_type, 0) + 1

        chunk_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM document_chunks WHERE source_id=?",
                (source_id,),
            ).fetchone()[0]
        )
        attempt_row = connection.execute(
            """SELECT COUNT(*) AS total, COALESCE(SUM(is_correct), 0) AS correct
               FROM quiz_attempts WHERE source_id=?""",
            (source_id,),
        ).fetchone()
        wrong_row = connection.execute(
            """SELECT COUNT(*) AS total,
                      COALESCE(SUM(CASE WHEN mastered=0 THEN 1 ELSE 0 END), 0) AS pending,
                      COALESCE(SUM(CASE WHEN mastered=1 THEN 1 ELSE 0 END), 0) AS mastered
               FROM wrong_questions WHERE source_id=?""",
            (source_id,),
        ).fetchone()
        plan_rows = connection.execute(
            "SELECT plan_data, completed_days FROM study_plans WHERE source_id=?",
            (source_id,),
        ).fetchall()
        total_plan_days = 0
        completed_plan_days = 0
        for row in plan_rows:
            try:
                total_plan_days += len(
                    json.loads(row["plan_data"]).get("daily_plan", [])
                )
                completed_plan_days += len(json.loads(row["completed_days"]))
            except (TypeError, json.JSONDecodeError):
                continue

        linked_run_ids = []
        run_rows = connection.execute(
            "SELECT run_id, context_refs FROM agent_runs "
            "WHERE task_type='interview_session'"
        ).fetchall()
        for row in run_rows:
            try:
                refs = json.loads(row["context_refs"])
            except (TypeError, json.JSONDecodeError):
                continue
            if refs.get("source_id") == source_id:
                linked_run_ids.append(str(row["run_id"]))
        interview_count = 0
        interview_turn_count = 0
        interview_average: float | None = None
        if linked_run_ids:
            placeholders = ",".join("?" for _ in linked_run_ids)
            interview_row = connection.execute(
                f"""SELECT COUNT(*) AS sessions,
                           AVG(CASE WHEN current_index > 0
                               THEN overall_score END) AS average
                    FROM interview_sessions
                    WHERE agent_run_id IN ({placeholders})""",
                linked_run_ids,
            ).fetchone()
            turn_row = connection.execute(
                f"""SELECT COUNT(*) AS turns FROM interview_turns
                    WHERE interview_id IN (
                        SELECT interview_id FROM interview_sessions
                        WHERE agent_run_id IN ({placeholders})
                    )""",
                linked_run_ids,
            ).fetchone()
            interview_count = int(interview_row["sessions"] or 0)
            interview_turn_count = int(turn_row["turns"] or 0)
            if interview_row["average"] is not None:
                interview_average = round(float(interview_row["average"]), 2)

        attempt_count = int(attempt_row["total"] or 0)
        correct_count = int(attempt_row["correct"] or 0)
        wrong_total = int(wrong_row["total"] or 0)
        stages = [
            {
                "key": "source",
                "label": "原始资料",
                "state": "ready",
                "primary": "1 份已入库资料",
                "secondary": f"{chunk_count} 个可引用片段",
            },
            {
                "key": "understanding",
                "label": "理解产物",
                "state": "ready" if artifacts else "empty",
                "primary": f"{len(artifacts)} 个学习产物",
                "secondary": " · ".join(
                    f"{name} {count}"
                    for name, count in sorted(artifact_counts.items())
                ) or "尚未生成摘要或知识卡",
            },
            {
                "key": "practice",
                "label": "练习证据",
                "state": "ready" if attempt_count else "empty",
                "primary": f"{attempt_count} 次真实作答",
                "secondary": (
                    f"其中答对 {correct_count} 次"
                    if attempt_count
                    else "尚未开始练习"
                ),
            },
            {
                "key": "review",
                "label": "错题复习",
                "state": "ready" if wrong_total else "empty",
                "primary": f"{wrong_total} 道错题进入闭环",
                "secondary": (
                    f"待复习 {int(wrong_row['pending'] or 0)} · "
                    f"已掌握 {int(wrong_row['mastered'] or 0)}"
                ),
            },
            {
                "key": "plan",
                "label": "行动计划",
                "state": "ready" if plan_rows else "empty",
                "primary": f"{len(plan_rows)} 份学习计划",
                "secondary": (
                    f"已完成 {completed_plan_days}/{total_plan_days} 个学习日"
                    if plan_rows
                    else "尚未生成学习计划"
                ),
            },
            {
                "key": "interview",
                "label": "表达验证",
                "state": "ready" if interview_count else "empty",
                "primary": f"{interview_count} 场资料关联面试",
                "secondary": (
                    f"{interview_turn_count} 次回答 · 均分 {interview_average:.0f}"
                    if interview_average is not None
                    else "尚无资料关联面试"
                ),
            },
        ]
        return {
            "source_id": source_id,
            "source_name": source["original_name"],
            "rights": self.get_source_rights(source_id),
            "artifact_counts": artifact_counts,
            "stages": stages,
            "completed_stage_count": sum(
                item["state"] == "ready" for item in stages
            ),
            "total_stage_count": len(stages),
        }

    def list_sources(
        self,
        workspace_id: str = "local",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """按工作区列出最近资料源。"""
        rows = self._conn().execute(
            """SELECT * FROM sources WHERE workspace_id=?
               ORDER BY created_at DESC LIMIT ?""",
            (workspace_id, limit),
        ).fetchall()
        return [self._decode_row(row, ("metadata",)) for row in rows]

    def preview_source_deletion(self, source_id: str) -> dict[str, Any] | None:
        """预览删除一个资料源会级联影响的派生数据，不执行删除。

        返回资料源基本信息与各级联表的受影响行数。source 不存在时返回 None。
        仅统计数据层影响；托管文件是否随删除清理由调用方（server 层）判断。
        """
        source = self.get_source(source_id)
        if source is None:
            return None
        conn = self._conn()
        counts = {
            "artifacts": conn.execute(
                "SELECT COUNT(*) FROM artifacts WHERE source_id=?", (source_id,)
            ).fetchone()[0],
            "chunks": conn.execute(
                "SELECT COUNT(*) FROM document_chunks WHERE source_id=?", (source_id,)
            ).fetchone()[0],
            "contexts": conn.execute(
                "SELECT COUNT(*) FROM document_contexts WHERE source_id=?", (source_id,)
            ).fetchone()[0],
            "quiz_attempts": conn.execute(
                "SELECT COUNT(*) FROM quiz_attempts WHERE source_id=?", (source_id,)
            ).fetchone()[0],
            "wrong_questions": conn.execute(
                "SELECT COUNT(*) FROM wrong_questions WHERE source_id=?", (source_id,)
            ).fetchone()[0],
            "study_plans": conn.execute(
                "SELECT COUNT(*) FROM study_plans WHERE source_id=?", (source_id,)
            ).fetchone()[0],
            "knowledge_graph_batches": conn.execute(
                "SELECT COUNT(*) FROM knowledge_graph_batches WHERE source_id=?",
                (source_id,),
            ).fetchone()[0],
            "knowledge_graph_events": conn.execute(
                "SELECT COUNT(*) FROM knowledge_graph_events WHERE source_id=?", (source_id,),
            ).fetchone()[0],
        }
        return {
            "source_id": source_id,
            "original_name": source.get("original_name"),
            "source_path": source.get("source_path"),
            "media_type": source.get("media_type"),
            "affected": {key: int(value) for key, value in counts.items()},
        }

    def delete_source(self, source_id: str) -> dict[str, Any] | None:
        """删除资料源及其全部派生数据，依赖外键级联。

        删除前先统计受影响数量用于日志与返回。source 不存在时返回 None，
        由调用方决定是否视为幂等删除。
        """
        preview = self.preview_source_deletion(source_id)
        if preview is None:
            return None
        with self._write_lock:
            conn = self._conn()
            cur = conn.execute("DELETE FROM sources WHERE source_id=?", (source_id,))
            conn.commit()
        if cur.rowcount == 0:
            return None
        logger.info(
            "删除资料源 source_id=%s original_name=%r affected=%s",
            source_id,
            preview["original_name"],
            preview["affected"],
        )
        return preview

    def _source_deletion_revision(self, source_id: str) -> str | None:
        """覆盖原文及级联行的变化，不能只依据删除数量。"""
        conn = self._conn()
        source = conn.execute("SELECT * FROM sources WHERE source_id=?", (source_id,)).fetchone()
        if source is None:
            return None
        snapshot: dict[str, Any] = {"source": dict(source)}
        for table in ("artifacts", "document_chunks", "document_contexts", "quiz_attempts",
                      "wrong_questions", "study_plans", "knowledge_graph_batches",
                      "knowledge_graph_events", "source_rights"):
            rows = conn.execute(f"SELECT * FROM {table} WHERE source_id=? ORDER BY rowid",
                                (source_id,)).fetchall()
            snapshot[table] = [dict(row) for row in rows]
        return data_actions.digest(snapshot)

    def source_deletion_preview(self, source_id: str) -> dict[str, Any] | None:
        """在写锁内生成修订绑定的删除预览。"""
        with self._write_lock, self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            preview = self.preview_source_deletion(source_id)
            if preview is None:
                return None
            preview["confirmation_token"] = data_actions.issue(
                conn, "source_delete", source_id, self._source_deletion_revision(source_id),
            )
            return preview

    def confirmed_source_delete(self, source_id: str, token: str,
                                stage_file: Any) -> dict[str, Any]:
        """先暂存托管文件，事务失败时还原，提交后再清理暂存副本。"""
        with self._write_lock:
            conn = self._conn()
            staged = None
            try:
                conn.execute("BEGIN IMMEDIATE")
                revision = self._source_deletion_revision(source_id)
                if revision is None and conn.execute(
                    "SELECT 1 FROM data_action_previews WHERE token_hash=? AND action='source_delete' AND resource_id=? AND result IS NOT NULL",
                    (data_actions.digest(token), source_id),
                ).fetchone() is None:
                    raise LookupError("Source not found")
                receipt = data_actions.check(conn, "source_delete", source_id, token,
                                             revision)
                if receipt is not None:
                    conn.rollback()
                    return receipt
                preview = self.preview_source_deletion(source_id)
                shared = conn.execute("SELECT COUNT(*) FROM sources WHERE source_path=? AND source_id!=?",
                                      (preview["source_path"], source_id)).fetchone()[0]
                staged = stage_file(preview["source_path"], bool(shared))
                result = {"source_id": source_id, "affected": preview["affected"],
                          "managed_file": staged.status,
                          "external_files_untouched": not staged.status["managed"]}
                conn.execute("DELETE FROM sources WHERE source_id=?", (source_id,))
                data_actions.finish(conn, "source_delete", source_id, token, result)
                staged.finish()
                conn.commit()
            except Exception:
                conn.rollback()
                if staged is not None:
                    staged.rollback()
                raise
            return result

    def save_artifact(
        self,
        *,
        artifact_type: str,
        content: Any,
        source_id: str | None = None,
        workspace_id: str = "local",
        title: str = "",
        metadata: dict[str, Any] | None = None,
        artifact_id: str | None = None,
    ) -> str:
        """保存由资料派生的 AI 产物。"""
        if not artifact_type.strip():
            raise ValueError("artifact_type 不能为空")
        artifact_id = artifact_id or uuid.uuid4().hex
        now = _now_iso()
        with self._write_lock:
            existing = self.get_artifact(artifact_id)
            if existing and isinstance(existing.get("metadata"), dict) and existing["metadata"].get("read_only_snapshot"):
                raise ValueError("历史题集是只读证据，不能修改")
            if existing and existing["artifact_type"] == "questions" and (
                artifact_type != "questions" or existing["content"] != content
            ):
                raise ValueError("题集正文请通过 update_artifact 修订以保留学习历史")
            self._conn().execute(
                """INSERT INTO artifacts
                   (artifact_id, workspace_id, source_id, artifact_type,
                    title, content, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(artifact_id) DO UPDATE SET
                       artifact_type=excluded.artifact_type,
                       title=excluded.title,
                       content=excluded.content,
                       metadata=excluded.metadata,
                       updated_at=?""",
                (
                    artifact_id,
                    workspace_id,
                    source_id,
                    artifact_type,
                    title,
                    self._dump_json(content),
                    self._dump_json(metadata or {}),
                    now,
                ),
            )
            self._conn().commit()
        return artifact_id

    def save_source_artifact(
        self, *, source_id: str, artifact_type: str, content: Any,
        title: str, metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """与资料删除互斥，避免长时间生成结束后重新写入孤立产物。"""
        with self._write_lock:
            if self.get_source(source_id) is None:
                return None
            artifact_id = self.save_artifact(
                source_id=source_id, artifact_type=artifact_type, content=content,
                title=title, metadata=metadata,
            )
            return self.get_artifact(artifact_id)

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        """读取单个 AI 产物。"""
        row = self._conn().execute(
            "SELECT * FROM artifacts WHERE artifact_id=?",
            (artifact_id,),
        ).fetchone()
        return self._decode_row(row, ("content", "metadata"))

    def update_artifact(
        self,
        artifact_id: str,
        *,
        title: str,
        content: Any,
    ) -> dict[str, Any] | None:
        """更新用户可编辑的学习产物标题与内容。"""
        with self._write_lock:
            connection = self._conn()
            try:
                connection.execute("BEGIN IMMEDIATE")
                artifact = self.get_artifact(artifact_id)
                if artifact is None:
                    connection.rollback()
                    return None
                metadata = artifact.get("metadata")
                metadata = dict(metadata) if isinstance(metadata, dict) else {}
                if metadata.get("read_only_snapshot"):
                    raise ValueError("历史题集是只读证据，不能修改")
                if artifact["artifact_type"] == "questions":
                    # 历史库没有正文修订记录时，冻结原边界，避免标题更新时间改变证据归属。
                    if "graph_attempt_cutoff" not in metadata and "question_evidence_since" not in metadata:
                        if artifact["created_at"] == artifact["updated_at"]:
                            metadata["graph_attempt_cutoff"] = 0
                        else:
                            metadata["question_evidence_since"] = artifact["updated_at"]
                    if artifact["content"] != content:
                        has_history = connection.execute(
                            """SELECT EXISTS(SELECT 1 FROM quiz_attempts WHERE artifact_id=?)
                               OR EXISTS(SELECT 1 FROM wrong_questions WHERE artifact_id=?)""",
                            (artifact_id, artifact_id),
                        ).fetchone()[0]
                        if has_history:
                            snapshot_id = uuid.uuid4().hex
                            snapshot_metadata = metadata | {
                                "read_only_snapshot": True,
                                "question_revision_parent": artifact_id,
                                "question_revision_saved_at": _now_iso(),
                            }
                            connection.execute(
                                """INSERT INTO artifacts
                                   (artifact_id, workspace_id, source_id, artifact_type, title,
                                    content, metadata, created_at, updated_at)
                                   VALUES (?, ?, ?, 'questions', ?, ?, ?, ?, ?)""",
                                (snapshot_id, artifact["workspace_id"], artifact["source_id"],
                                 f"[历史题集] {artifact['title']}", self._dump_json(artifact["content"]),
                                 self._dump_json(snapshot_metadata), artifact["created_at"], artifact["updated_at"]),
                            )
                            for table in ("quiz_attempts", "wrong_questions"):
                                connection.execute(
                                    f"UPDATE {table} SET artifact_id=? WHERE artifact_id=?",
                                    (snapshot_id, artifact_id),
                                )
                        metadata["graph_attempt_cutoff"] = 0
                        metadata["question_revision"] = uuid.uuid4().hex
                        metadata.pop("question_evidence_since", None)
                connection.execute(
                    """UPDATE artifacts SET title=?, content=?, metadata=?, updated_at=?
                       WHERE artifact_id=?""",
                    (title.strip(), self._dump_json(content), self._dump_json(metadata), _now_iso(), artifact_id),
                )
                result = self.get_artifact(artifact_id)
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def list_artifacts(
        self,
        *,
        workspace_id: str = "local",
        source_id: str | None = None,
        artifact_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """按资料源或类型筛选 AI 产物。"""
        clauses = ["workspace_id=?"]
        params: list[Any] = [workspace_id]
        if source_id:
            clauses.append("source_id=?")
            params.append(source_id)
        if artifact_type:
            clauses.append("artifact_type=?")
            params.append(artifact_type)
        params.append(limit)
        rows = self._conn().execute(
            f"""SELECT * FROM artifacts WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC LIMIT ?""",
            params,
        ).fetchall()
        return [
            self._decode_row(row, ("content", "metadata"))
            for row in rows
        ]

    def save_document_context(
        self,
        *,
        ctx_id: str,
        context_text: str,
        source_id: str | None = None,
        artifact_id: str | None = None,
        workspace_id: str = "local",
        chat_history: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        expires_at: str | None = None,
    ) -> None:
        """新增或更新可恢复的文档问答上下文。"""
        if not ctx_id.strip() or not context_text.strip():
            raise ValueError("ctx_id 和 context_text 不能为空")
        now = _now_iso()
        with self._write_lock:
            self._conn().execute(
                """INSERT INTO document_contexts
                   (ctx_id, workspace_id, source_id, artifact_id, context_text,
                    chat_history, metadata, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(ctx_id) DO UPDATE SET
                       artifact_id=excluded.artifact_id,
                       context_text=excluded.context_text,
                       chat_history=excluded.chat_history,
                       metadata=excluded.metadata,
                       expires_at=excluded.expires_at,
                       updated_at=?""",
                (
                    ctx_id,
                    workspace_id,
                    source_id,
                    artifact_id,
                    context_text,
                    self._dump_json(chat_history or []),
                    self._dump_json(metadata or {}),
                    expires_at,
                    now,
                ),
            )
            self._conn().commit()

    def get_document_context(self, ctx_id: str) -> dict[str, Any] | None:
        """读取文档问答上下文。"""
        row = self._conn().execute(
            "SELECT * FROM document_contexts WHERE ctx_id=?",
            (ctx_id,),
        ).fetchone()
        return self._decode_row(row, ("chat_history", "metadata"))

    def append_context_messages(
        self,
        ctx_id: str,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """原子追加上下文对话消息并返回完整历史。"""
        if not messages:
            context = self.get_document_context(ctx_id)
            return context["chat_history"] if context else []
        with self._write_lock:
            context = self.get_document_context(ctx_id)
            if context is None:
                raise ValueError(f"文档上下文不存在: {ctx_id}")
            history = list(context.get("chat_history") or [])
            history.extend(messages)
            self._conn().execute(
                """UPDATE document_contexts
                   SET chat_history=?, updated_at=? WHERE ctx_id=?""",
                (
                    self._dump_json(history),
                    _now_iso(),
                    ctx_id,
                ),
            )
            self._conn().commit()
            return history

    def delete_document_context(self, ctx_id: str) -> bool:
        """删除文档上下文。"""
        with self._write_lock:
            cur = self._conn().execute(
                "DELETE FROM document_contexts WHERE ctx_id=?",
                (ctx_id,),
            )
            self._conn().commit()
            return cur.rowcount > 0

    def list_document_contexts(
        self,
        *,
        source_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """列出文档问答上下文会话摘要。"""
        bounded_limit = min(max(int(limit), 1), 200)
        summary_fields = """ctx_id, source_id, artifact_id,
                          substr(context_text, 1, 60) AS context_preview,
                          json_extract(chat_history, '$[0].content') AS first_message,
                          COALESCE(json_array_length(chat_history), 0) AS message_count,
                          metadata, created_at, updated_at"""
        if source_id:
            rows = self._conn().execute(
                f"""SELECT {summary_fields}
                    FROM document_contexts
                    WHERE source_id=?
                    ORDER BY updated_at DESC
                    LIMIT ?""",
                (source_id, bounded_limit),
            ).fetchall()
        else:
            rows = self._conn().execute(
                f"""SELECT {summary_fields}
                    FROM document_contexts
                    ORDER BY updated_at DESC
                    LIMIT ?""",
                (bounded_limit,),
            ).fetchall()
        results = []
        for row in rows:
            ctx = self._decode_row(row, ("metadata",))
            first_message = ctx.get("first_message")
            title = (
                first_message[:60]
                if isinstance(first_message, str) and first_message.strip()
                else ctx.get("context_preview", "")
            )
            results.append(
                {
                    "ctx_id": ctx["ctx_id"],
                    "source_id": ctx.get("source_id"),
                    "artifact_id": ctx.get("artifact_id"),
                    "title": title,
                    "message_count": int(ctx.get("message_count") or 0),
                    "created_at": ctx.get("created_at"),
                    "updated_at": ctx.get("updated_at"),
                    "metadata": ctx.get("metadata"),
                }
            )
        return results

    def replace_source_chunks(
        self,
        source_id: str,
        chunks: list[dict[str, Any]],
    ) -> None:
        """原子替换资料源的检索分块。"""
        if self.get_source(source_id) is None:
            raise ValueError(f"资料源不存在: {source_id}")
        with self._write_lock:
            connection = self._conn()
            connection.execute("DELETE FROM document_chunks WHERE source_id=?", (source_id,))
            connection.executemany(
                """INSERT INTO document_chunks
                   (chunk_id, source_id, chunk_index, page_number, content, metadata)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"filemate:{source_id}:chunk:{chunk['chunk_index']}",
                        ).hex,
                        source_id,
                        int(chunk["chunk_index"]),
                        chunk.get("page_number"),
                        str(chunk["content"]),
                        self._dump_json(chunk.get("metadata") or {}),
                    )
                    for chunk in chunks
                ],
            )
            connection.commit()

    def list_source_chunks(self, source_id: str) -> list[dict[str, Any]]:
        """按原始顺序读取资料分块。"""
        rows = self._conn().execute(
            "SELECT * FROM document_chunks WHERE source_id=? ORDER BY chunk_index",
            (source_id,),
        ).fetchall()
        return [self._decode_row(row, ("metadata",)) for row in rows]

    def get_source_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        """按稳定 ID 读取单个资料分块。"""
        row = self._conn().execute(
            "SELECT * FROM document_chunks WHERE chunk_id=?",
            (chunk_id,),
        ).fetchone()
        return self._decode_row(row, ("metadata",)) if row else None

    def get_source_revision(self, source_id: str) -> str | None:
        """返回资料正文与检索分块的稳定内容指纹。"""
        source = self.get_source(source_id)
        if source is None:
            return None
        import hashlib

        digest = hashlib.sha256()
        digest.update(str(source.get("raw_text") or "").encode("utf-8"))
        for chunk in self.list_source_chunks(source_id):
            digest.update(b"\x00")
            digest.update(str(chunk["chunk_index"]).encode("utf-8"))
            digest.update(b"\x00")
            digest.update(str(chunk.get("page_number") or "").encode("utf-8"))
            digest.update(b"\x00")
            digest.update(str(chunk["content"]).encode("utf-8"))
        return digest.hexdigest()

    def record_quiz_attempt(
        self,
        *,
        artifact_id: str,
        question_index: int,
        user_answer: str,
        is_correct: bool,
        score: float,
        feedback: str,
        expected_question: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """记录一次作答，并同步更新错题掌握状态。"""
        with self._write_lock:
            connection = self._conn()
            try:
                connection.execute("BEGIN IMMEDIATE")
                result = self._record_quiz_attempt(
                    artifact_id=artifact_id, question_index=question_index,
                    user_answer=user_answer, is_correct=is_correct, score=score,
                    feedback=feedback, expected_question=expected_question,
                )
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def _record_quiz_attempt(
        self, *, artifact_id: str, question_index: int, user_answer: str,
        is_correct: bool, score: float, feedback: str,
        expected_question: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """在写事务内核对题目快照并保存作答与错题。"""
        artifact = self.get_artifact(artifact_id)
        if artifact is None:
            raise ValueError(f"AI 产物不存在: {artifact_id}")
        if artifact["artifact_type"] != "questions":
            raise ValueError("该产物不是题目集")
        questions = artifact.get("content")
        if not isinstance(questions, list) or not 0 <= question_index < len(questions):
            if expected_question is not None:
                raise QuestionRevisionConflict("题目已更新，请刷新题集后重新作答")
            raise ValueError("题目序号无效")
        question = questions[question_index]
        if expected_question is not None and question != expected_question:
            raise QuestionRevisionConflict("题目已更新，请刷新题集后重新作答")
        attempt_id = uuid.uuid4().hex
        now = _now_iso()
        question_dict = question if isinstance(question, dict) else {}
        knowledge_key, knowledge_label = _knowledge_identity(
            question_dict,
            source_id=artifact.get("source_id"),
            artifact_id=artifact_id,
        )
        error_cause, error_cause_confidence = _suggest_error_cause(
            question_dict, user_answer,
        )
        existing_wrong = self._conn().execute(
            """SELECT correct_streak, interval_days, ease_factor, review_count
               FROM wrong_questions WHERE artifact_id=? AND question_index=?""",
            (artifact_id, question_index),
        ).fetchone()
        with self._write_lock:
            connection = self._conn()
            connection.execute(
                """INSERT INTO quiz_attempts
                   (attempt_id, artifact_id, source_id, question_index,
                    user_answer, is_correct, score, feedback)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    attempt_id,
                    artifact_id,
                    artifact.get("source_id"),
                    question_index,
                    user_answer,
                    int(is_correct),
                    score,
                    feedback,
                ),
            )
            if is_correct:
                current_interval = int(existing_wrong["interval_days"]) if existing_wrong else 0
                current_ease = float(existing_wrong["ease_factor"]) if existing_wrong else 2.5
                quality = 5 if score >= 0.95 else 4 if score >= 0.85 else 3
                ease = max(
                    1.3,
                    current_ease
                    + 0.1
                    - (5 - quality) * (0.08 + (5 - quality) * 0.02),
                )
                interval_days = (
                    1
                    if current_interval <= 0
                    else max(3, round(current_interval * ease))
                )
                next_review_at = (
                    datetime.now(tz=timezone.utc) + timedelta(days=interval_days)
                ).isoformat(timespec="seconds")
                connection.execute(
                    """UPDATE wrong_questions SET
                       latest_answer=?, correct_streak=correct_streak + 1,
                       mastered=CASE WHEN correct_streak + 1 >= 2 THEN 1 ELSE 0 END,
                       interval_days=?, ease_factor=?,
                       review_count=review_count + 1, next_review_at=?,
                       updated_at=?
                       WHERE artifact_id=? AND question_index=?""",
                    (
                        user_answer,
                        interval_days,
                        round(ease, 3),
                        next_review_at,
                        now,
                        artifact_id,
                        question_index,
                    ),
                )
            else:
                # 历史错题保留原 ID；新版本首次答错必须拥有新的记录 ID。
                wrong_id = uuid.uuid4().hex
                connection.execute(
                    """INSERT INTO wrong_questions
                       (wrong_id, artifact_id, source_id, question_index,
                        question, latest_answer, next_review_at,
                        interval_days, ease_factor, review_count,
                        knowledge_key, knowledge_label, error_cause,
                        error_cause_source, error_cause_confidence, diagnosed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 0, 2.3, 1, ?, ?, ?, 'rule', ?, ?)
                       ON CONFLICT(artifact_id, question_index) DO UPDATE SET
                           latest_answer=excluded.latest_answer,
                           error_count=wrong_questions.error_count + 1,
                           correct_streak=0, mastered=0, interval_days=0,
                           ease_factor=MAX(1.3, wrong_questions.ease_factor - 0.2),
                           review_count=wrong_questions.review_count + 1,
                           next_review_at=excluded.next_review_at,
                           knowledge_key=CASE WHEN wrong_questions.knowledge_key=''
                               THEN excluded.knowledge_key ELSE wrong_questions.knowledge_key END,
                           knowledge_label=CASE WHEN wrong_questions.knowledge_label=''
                               THEN excluded.knowledge_label ELSE wrong_questions.knowledge_label END,
                           error_cause=CASE WHEN wrong_questions.error_cause_source='user'
                               THEN wrong_questions.error_cause ELSE excluded.error_cause END,
                           error_cause_source=CASE WHEN wrong_questions.error_cause_source='user'
                               THEN 'user' ELSE 'rule' END,
                           error_cause_confidence=CASE WHEN wrong_questions.error_cause_source='user'
                               THEN wrong_questions.error_cause_confidence
                               ELSE excluded.error_cause_confidence END,
                           diagnosed_at=CASE WHEN wrong_questions.error_cause_source='user'
                               THEN wrong_questions.diagnosed_at ELSE excluded.diagnosed_at END,
                           updated_at=?""",
                    (
                        wrong_id,
                        artifact_id,
                        artifact.get("source_id"),
                        question_index,
                        self._dump_json(question),
                        user_answer,
                        now,
                        knowledge_key,
                        knowledge_label,
                        error_cause,
                        error_cause_confidence,
                        now,
                        now,
                    ),
                )
        return {
            "attempt_id": attempt_id,
            "is_correct": is_correct,
            "score": score,
            "feedback": feedback,
            "reference_answer": question.get("answer", "") if isinstance(question, dict) else "",
        }

    def list_wrong_questions(
        self,
        *,
        mastered: bool | None = None,
        due_only: bool = False,
        source_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """列出待复习或已掌握错题。"""
        query = "SELECT * FROM wrong_questions"
        params: list[Any] = []
        clauses: list[str] = []
        if mastered is not None:
            clauses.append("mastered=?")
            params.append(int(mastered))
        if source_id is not None:
            clauses.append("source_id=?")
            params.append(source_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY next_review_at, updated_at DESC LIMIT ?"
        params.append(max(1, min(limit, 1000)))
        rows = self._conn().execute(query, params).fetchall()
        decoded = [
            self._enrich_wrong_question(self._decode_row(row, ("question",)))
            for row in rows
        ]
        if not due_only:
            return decoded
        now = datetime.now(tz=timezone.utc)
        due: list[dict[str, Any]] = []
        for item in decoded:
            try:
                next_review = datetime.fromisoformat(str(item["next_review_at"]))
                if next_review.tzinfo is None:
                    next_review = next_review.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                next_review = datetime.min.replace(tzinfo=timezone.utc)
            if next_review <= now:
                due.append(item)
        return due

    def get_wrong_question(self, wrong_id: str) -> dict[str, Any] | None:
        """按记录 ID 读取一条带来源的错题。"""
        row = self._conn().execute(
            "SELECT * FROM wrong_questions WHERE wrong_id=?",
            (wrong_id,),
        ).fetchone()
        return self._enrich_wrong_question(
            self._decode_row(row, ("question",)) if row else None
        )

    def wrong_question_page(self, *, mastered: bool | None = False, limit: int = 50,
                            offset: int = 0, q: str = "", source_id: str | None = None,
                            error_cause: str | None = None, due_only: bool = False) -> dict[str, Any]:
        """在全量记录中筛选再分页，稳定排序避免同时间记录丢失。"""
        clauses: list[str] = []
        params: list[Any] = []
        for field, value in (("mastered", int(mastered) if mastered is not None else None),
                             ("source_id", source_id), ("error_cause", error_cause)):
            if value is not None:
                clauses.append(f"w.{field}=?")
                params.append(value)
        if q.strip():
            clauses.append("(lower(w.question) LIKE ? ESCAPE '\\' OR lower(w.knowledge_label) LIKE ? ESCAPE '\\' OR lower(s.original_name) LIKE ? ESCAPE '\\')")
            pattern = "%" + q.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            params.extend([pattern] * 3)
        if due_only:
            clauses.append("(julianday(w.next_review_at) IS NULL OR julianday(w.next_review_at)<=julianday('now'))")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        base = " FROM wrong_questions w LEFT JOIN sources s ON s.source_id=w.source_id" + where
        conn = self._conn()
        total = conn.execute("SELECT COUNT(*)" + base, params).fetchone()[0]
        rows = conn.execute("SELECT w.*, s.original_name AS source_name" + base +
                            " ORDER BY w.next_review_at, w.updated_at DESC, w.wrong_id LIMIT ? OFFSET ?",
                            [*params, limit, offset]).fetchall()
        return {"items": [self._enrich_wrong_question(self._decode_row(row, ("question",))) for row in rows],
                "total": total, "offset": offset, "limit": limit, "has_more": offset + len(rows) < total}

    @staticmethod
    def _enrich_wrong_question(
        wrong: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """为旧错题补充只读知识点和未确认诊断默认值。"""
        if wrong is None:
            return None
        if not wrong.get("knowledge_key") or not wrong.get("knowledge_label"):
            question = wrong.get("question")
            knowledge_key, knowledge_label = _knowledge_identity(
                question if isinstance(question, dict) else {},
                source_id=wrong.get("source_id"),
                artifact_id=str(wrong["artifact_id"]),
            )
            wrong["knowledge_key"] = knowledge_key
            wrong["knowledge_label"] = knowledge_label
        wrong.setdefault("error_cause", "unconfirmed")
        wrong.setdefault("error_cause_source", "unconfirmed")
        wrong.setdefault("error_cause_confidence", 0.0)
        wrong.setdefault("error_cause_note", "")
        wrong.setdefault("diagnosed_at", None)
        return wrong

    def update_wrong_diagnosis(
        self,
        wrong_id: str,
        *,
        error_cause: str,
        note: str = "",
    ) -> dict[str, Any]:
        """保存用户确认的错因，并保留同一知识点标识。"""
        if error_cause not in _ERROR_CAUSES:
            raise ValueError("错因类型无效")
        wrong = self.get_wrong_question(wrong_id)
        if wrong is None:
            raise ValueError("错题不存在")
        clean_note = note.strip()
        if len(clean_note) > 300:
            raise ValueError("错因备注不能超过 300 字")
        now = _now_iso()
        with self._write_lock:
            self._conn().execute(
                """UPDATE wrong_questions SET
                   knowledge_key=?, knowledge_label=?, error_cause=?,
                   error_cause_source='user', error_cause_confidence=1,
                   error_cause_note=?, diagnosed_at=?, updated_at=?
                   WHERE wrong_id=?""",
                (
                    wrong["knowledge_key"],
                    wrong["knowledge_label"],
                    error_cause,
                    clean_note,
                    now,
                    now,
                    wrong_id,
                ),
            )
            self._conn().commit()
        updated = self.get_wrong_question(wrong_id)
        if updated is None:
            raise ValueError("错题不存在")
        return updated

    def get_latest_wrong_attempt(self, wrong_id: str) -> dict[str, Any] | None:
        """读取一条错题最近一次失败作答的标识和时间。"""
        wrong = self.get_wrong_question(wrong_id)
        if wrong is None:
            return None
        row = self._conn().execute(
            """SELECT attempt_id, artifact_id, source_id, question_index, created_at
               FROM quiz_attempts
               WHERE artifact_id=? AND question_index=? AND is_correct=0
               ORDER BY created_at DESC, rowid DESC LIMIT 1""",
            (wrong["artifact_id"], wrong["question_index"]),
        ).fetchone()
        if row is None:
            return None
        attempt = dict(row)
        created_at = str(attempt.get("created_at") or "")
        if created_at and "+" not in created_at and not created_at.endswith("Z"):
            attempt["created_at"] = f"{created_at}+00:00"
        return attempt

    def create_interview(
        self,
        *,
        target_role: str,
        scenario: str,
        difficulty: str,
        questions: list[str],
        question_ids: list[str | None] | None = None,
        agent_run_id: str | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        """创建模拟面试。"""
        if question_ids is not None and len(question_ids) != len(questions):
            raise ValueError("题目 ID 必须与题目逐项对应")
        interview_id = uuid.uuid4().hex[:16]
        with self._write_lock:
            self._conn().execute(
                """INSERT INTO interview_sessions
                   (interview_id, target_role, scenario, difficulty, questions,
                    question_ids, agent_run_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    interview_id,
                    target_role,
                    scenario,
                    difficulty,
                    self._dump_json(questions),
                    self._dump_json(question_ids or [None] * len(questions)),
                    agent_run_id,
                ),
            )
            self._conn().execute(
                "INSERT INTO interview_review_events(interview_id,action,created_at) VALUES (?, 'created', ?)",
                (interview_id, _now_iso()),
            )
            if commit:
                self._conn().commit()
        return self.get_interview(interview_id)

    def get_interview(self, interview_id: str) -> dict[str, Any] | None:
        """读取模拟面试及作答记录。"""
        row = self._conn().execute(
            "SELECT * FROM interview_sessions WHERE interview_id=?",
            (interview_id,),
        ).fetchone()
        interview = self._decode_row(
            row, ("questions", "question_ids", "expression_review")
        )
        if interview is None:
            return None
        question_ids = interview.get("question_ids")
        if not isinstance(question_ids, list) or len(question_ids) != len(
            interview["questions"]
        ):
            interview["question_ids"] = [None] * len(interview["questions"])
        turns = self._conn().execute(
            "SELECT * FROM interview_turns WHERE interview_id=? ORDER BY question_index",
            (interview_id,),
        ).fetchall()
        interview["turns"] = [
            self._decode_row(turn, ("dimensions", "fluency_metrics"))
            for turn in turns
        ]
        for turn in interview["turns"]:
            content_invalid = False
            for key in ("visual_metrics", "content_analysis"):
                try:
                    decoded = json.loads(turn[key])
                    if not isinstance(decoded, dict):
                        raise TypeError("invalid analysis")
                    if decoded:
                        from filemate.interview_review.models import (
                            VisualMetrics,
                            validate_saved_analysis,
                        )

                        if key == "visual_metrics":
                            decoded = VisualMetrics.model_validate(decoded).model_dump()
                        else:
                            decoded = validate_saved_analysis(decoded, turn["answer"])
                    turn[key] = decoded
                except (ValueError, TypeError):
                    turn[key] = {}
                    turn["analysis_data_error"] = True
                    content_invalid = content_invalid or key == "content_analysis"
            if content_invalid:
                turn["feedback"] = "部分内容分析数据异常，内容质量待评估；原回答与有效采集证据保留。"
            if turn["scoring_mode"] != "llm" or content_invalid:
                turn["score"] = None
                turn["dimensions"] = {
                    key: value for key, value in turn["dimensions"].items()
                    if key == "流畅性" and turn["scoring_mode"] == "local_fallback" and not content_invalid
                }
        assessed = [t["score"] for t in interview["turns"] if t["score"] is not None]
        interview["assessed_turn_count"] = len(assessed)
        interview["overall_score"] = round(sum(assessed) / len(assessed), 2) if assessed else None
        return interview

    def save_interview_turn(
        self,
        *,
        interview_id: str,
        question_index: int,
        question: str,
        answer: str,
        score: float | None,
        dimensions: dict[str, float],
        feedback: str,
        fluency_metrics: dict[str, Any] | None = None,
        scoring_mode: str = "unknown",
        scoring_version: str = "v2",
        next_question: str | None = None,
        expression_review: dict[str, Any] | None = None,
        visual_metrics: dict[str, Any] | None = None,
        content_analysis: dict[str, Any] | None = None,
        answer_key: str | None = None,
        answer_digest: str | None = None,
    ) -> dict[str, Any]:
        """保存单轮面试评分并推进进度。"""
        if scoring_mode not in {"llm", "local_fallback", "unknown"}:
            raise ValueError("未知评分来源")
        if scoring_mode == "llm" and score is None:
            raise ValueError("模型评分不能为空")
        with self._write_lock:
            connection = self._conn()
            if answer_key:
                previous = connection.execute(
                    "SELECT answer_digest FROM interview_turns WHERE interview_id=? AND answer_key=?",
                    (interview_id, answer_key),
                ).fetchone()
                if previous:
                    if previous["answer_digest"] != answer_digest:
                        raise ValueError("重复请求键的回答内容不同")
                    return self.get_interview(interview_id)
            interview = self.get_interview(interview_id)
            if interview is None:
                raise ValueError("模拟面试不存在")
            if interview["status"] == "completed":
                raise ValueError("模拟面试已完成")
            if int(interview["current_index"]) != question_index:
                raise ValueError("面试进度已更新，请刷新后继续")
            next_index = question_index + 1
            completed = next_index >= len(interview["questions"])
            if next_question is not None and completed:
                raise ValueError("面试已到最后一题")
            if expression_review is not None and not completed:
                raise ValueError("只能在最后一题保存表达回看")
            questions = list(interview["questions"])
            if next_question is not None:
                questions[next_index] = next_question
            scores = [
                float(turn["score"])
                for turn in interview["turns"]
                if turn["score"] is not None
            ]
            if scoring_mode == "llm" and score is not None:
                scores.append(score)
            turn_id = uuid.uuid4().hex
            connection.execute(
                """INSERT INTO interview_turns
                   (turn_id, interview_id, question_index, question, answer,
                    score, dimensions, feedback, fluency_metrics, scoring_mode, scoring_version,
                    visual_metrics, content_analysis, answer_key, answer_digest)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    turn_id, interview_id, question_index, question, answer,
                    score if scoring_mode == "llm" else 0, self._dump_json(dimensions), feedback,
                    self._dump_json(fluency_metrics or {}),
                    scoring_mode, scoring_version,
                    self._dump_json(visual_metrics or {}),
                    self._dump_json(content_analysis or {}), answer_key, answer_digest,
                ),
            )
            connection.execute(
                """UPDATE interview_sessions SET current_index=?, status=?,
                   overall_score=?, questions=?, expression_review=?,
                   updated_at=? WHERE interview_id=?""",
                (
                    next_index,
                    "completed" if completed else "active",
                    round(sum(scores) / len(scores), 2) if scores else 0,
                    self._dump_json(questions),
                    self._dump_json(expression_review or interview["expression_review"]),
                    _now_iso(),
                    interview_id,
                ),
            )
            connection.execute(
                "INSERT INTO interview_review_state (interview_id, revision) VALUES (?, 1) "
                "ON CONFLICT(interview_id) DO UPDATE SET revision=revision+1, input_digest=''",
                (interview_id,),
            )
            connection.execute(
                "INSERT INTO interview_review_events (interview_id,action,detail,created_at) "
                "VALUES (?, 'answer', ?, ?)",
                (interview_id, self._dump_json({"question_index": question_index}), _now_iso()),
            )
            connection.commit()
        return self.get_interview(interview_id)

    # ------------------------------------------------------------------
    # 面试题库
    # ------------------------------------------------------------------

    def list_interview_questions(
        self,
        *,
        scenario: str | None = None,
        difficulty: str | None = None,
        enabled: bool | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if scenario:
            clauses.append("scenario=?")
            params.append(scenario)
        if difficulty:
            clauses.append("difficulty=?")
            params.append(difficulty)
        if enabled is not None:
            clauses.append("enabled=?")
            params.append(int(enabled))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._conn().execute(
            f"SELECT * FROM interview_questions{where} "
            "ORDER BY scenario, difficulty, created_at LIMIT ?",
            params + [max(1, min(int(limit), 500))],
        ).fetchall()
        return [dict(row) for row in rows]

    def get_interview_question(self, question_id: str) -> dict[str, Any] | None:
        row = self._conn().execute(
            "SELECT * FROM interview_questions WHERE id=?", (question_id,)
        ).fetchone()
        return dict(row) if row else None

    def create_interview_question(
        self,
        *,
        scenario: str,
        difficulty: str,
        text: str,
        enabled: int = 1,
        question_id: str | None = None,
        ignore_duplicate: bool = False,
    ) -> str:
        scenario = scenario.strip()
        difficulty = difficulty.strip()
        text = text.strip()
        enabled = int(enabled)
        if not scenario or not difficulty or not text:
            raise ValueError("场景、难度和题目内容不能为空")
        if scenario not in _INTERVIEW_SCENARIOS:
            raise ValueError("不支持的面试场景")
        if difficulty not in _INTERVIEW_DIFFICULTIES:
            raise ValueError("不支持的面试难度")
        if len(text) > 1000:
            raise ValueError("题目内容不能超过 1000 字")
        if enabled not in {0, 1}:
            raise ValueError("启用状态只能是 0 或 1")
        question_id = question_id or uuid.uuid4().hex
        with self._write_lock:
            conn = self._conn()
            try:
                conn.execute(
                    """INSERT INTO interview_questions
                       (id, scenario, difficulty, text, enabled)
                       VALUES (?, ?, ?, ?, ?)""",
                    (question_id, scenario, difficulty, text, enabled),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                if not ignore_duplicate:
                    raise ValueError("同场景、同难度、同内容的题目已存在") from exc
                row = conn.execute(
                    """SELECT id FROM interview_questions
                       WHERE scenario=? AND difficulty=? AND text=?""",
                    (scenario, difficulty, text),
                ).fetchone()
                if row is None:
                    raise ValueError("题目 ID 已存在") from exc
                question_id = row["id"]
        return question_id

    def ensure_interview_questions(
        self, rows: list[dict[str, Any]]
    ) -> list[str]:
        """幂等写入种子题目，重复执行不会产生重复数据。"""
        ids: list[str] = []
        for row in rows:
            ids.append(
                self.create_interview_question(
                    scenario=str(row["scenario"]),
                    difficulty=str(row["difficulty"]),
                    text=str(row["text"]),
                    enabled=int(row.get("enabled", 1)),
                    ignore_duplicate=True,
                )
            )
        return ids

    def update_interview_question(
        self, question_id: str, **kwargs: Any
    ) -> bool:
        if not kwargs:
            return False
        invalid = set(kwargs) - _ALLOWED_INTERVIEW_QUESTION_COLS
        if invalid:
            raise ValueError(
                f"无效字段: {sorted(invalid)}，允许: {sorted(_ALLOWED_INTERVIEW_QUESTION_COLS)}"
            )
        normalized = dict(kwargs)
        for key in ("scenario", "difficulty", "text"):
            if key in normalized:
                normalized[key] = str(normalized[key]).strip()
                if not normalized[key]:
                    raise ValueError("场景、难度和题目内容不能为空")
        if (
            "scenario" in normalized
            and normalized["scenario"] not in _INTERVIEW_SCENARIOS
        ):
            raise ValueError("不支持的面试场景")
        if (
            "difficulty" in normalized
            and normalized["difficulty"] not in _INTERVIEW_DIFFICULTIES
        ):
            raise ValueError("不支持的面试难度")
        if len(str(normalized.get("text", ""))) > 1000:
            raise ValueError("题目内容不能超过 1000 字")
        if "enabled" in normalized:
            normalized["enabled"] = int(normalized["enabled"])
            if normalized["enabled"] not in {0, 1}:
                raise ValueError("启用状态只能是 0 或 1")
        set_clause = ", ".join(f"{key}=?" for key in normalized) + ", updated_at=?"
        values = list(normalized.values()) + [_now_iso(), question_id]
        with self._write_lock:
            conn = self._conn()
            try:
                cur = conn.execute(
                    f"UPDATE interview_questions SET {set_clause} WHERE id=?",
                    values,
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                raise ValueError("同场景、同难度、同内容的题目已存在") from exc
        return cur.rowcount > 0

    def delete_interview_question(self, question_id: str) -> bool:
        with self._write_lock:
            conn = self._conn()
            cur = conn.execute(
                "DELETE FROM interview_questions WHERE id=?", (question_id,)
            )
            conn.commit()
        return cur.rowcount > 0

    def select_interview_questions(
        self,
        *,
        scenario: str,
        difficulty: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        rows = self._conn().execute(
            """SELECT * FROM interview_questions
               WHERE scenario=? AND difficulty=? AND enabled=1
               ORDER BY updated_at DESC, rowid DESC LIMIT ?""",
            (scenario, difficulty, max(1, min(int(limit), 50))),
        ).fetchall()
        return [dict(row) for row in rows]

    def create_study_plan(
        self,
        *,
        artifact_id: str,
        source_id: str | None,
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        """保存学习计划，并为每日完成状态建立持久化记录。"""
        with self._write_lock:
            connection = self._conn()
            existing = connection.execute(
                "SELECT plan_id FROM study_plans WHERE artifact_id=?",
                (artifact_id,),
            ).fetchone()
            if existing is not None:
                saved = self.get_study_plan(existing["plan_id"])
                if saved is not None:
                    return saved

            plan_id = uuid.uuid4().hex
            connection.execute(
                """INSERT INTO study_plans
                   (plan_id, artifact_id, source_id, title, exam_date,
                    daily_minutes, goal, plan_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    plan_id,
                    artifact_id,
                    source_id,
                    str(plan.get("title", "学习计划")),
                    str(plan.get("exam_date", "")),
                    int(plan.get("daily_minutes", 60)),
                    str(plan.get("goal", "")),
                    self._dump_json(plan),
                ),
            )
            self._conn().commit()
        saved = self.get_study_plan(plan_id)
        if saved is None:
            raise RuntimeError("学习计划保存失败")
        return saved

    def get_study_plan(self, plan_id: str) -> dict[str, Any] | None:
        """读取一份学习计划及已完成日期序号。"""
        row = self._conn().execute(
            "SELECT * FROM study_plans WHERE plan_id=?",
            (plan_id,),
        ).fetchone()
        if row is None:
            return None
        return self._decode_row(row, ("plan_data", "completed_days"))

    def list_study_plans(
        self,
        *,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """按最近更新顺序列出学习计划。"""
        if status is not None and status not in {"active", "completed", "archived"}:
            raise ValueError("无效的学习计划状态")
        query = "SELECT * FROM study_plans"
        params: list[Any] = []
        if status is not None:
            query += " WHERE status=?"
            params.append(status)
        query += " ORDER BY updated_at DESC, rowid DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        rows = self._conn().execute(query, params).fetchall()
        return [
            self._decode_row(row, ("plan_data", "completed_days"))
            for row in rows
        ]

    def get_daily_coach_preferences(self, study_date: str) -> dict[str, Any]:
        """读取某日的时间预算与用户排序。"""
        row = self._conn().execute(
            "SELECT * FROM daily_coach_preferences WHERE study_date=?",
            (study_date,),
        ).fetchone()
        if row is None:
            return {
                "study_date": study_date,
                "available_minutes": 60,
                "item_order": [],
                "updated_at": None,
            }
        return self._decode_row(row, ("item_order",))

    def set_daily_coach_preferences(
        self,
        study_date: str,
        *,
        available_minutes: int,
        item_order: list[str],
    ) -> dict[str, Any]:
        """保存某日的时间预算与用户排序。"""
        if not 10 <= available_minutes <= 240:
            raise ValueError("每日可用时长须在 10 至 240 分钟之间")
        if len(item_order) > 50 or len(set(item_order)) != len(item_order):
            raise ValueError("任务顺序无效")
        with self._write_lock:
            self._conn().execute(
                """INSERT INTO daily_coach_preferences
                   (study_date, available_minutes, item_order, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(study_date) DO UPDATE SET
                       available_minutes=excluded.available_minutes,
                       item_order=excluded.item_order,
                       updated_at=excluded.updated_at""",
                (study_date, available_minutes, self._dump_json(item_order), _now_iso()),
            )
            self._conn().commit()
        return self.get_daily_coach_preferences(study_date)

    def set_study_plan_day(
        self,
        plan_id: str,
        day_index: int,
        completed: bool,
    ) -> dict[str, Any]:
        """更新单个学习日状态，并自动维护计划状态。"""
        with self._write_lock:
            plan = self.get_study_plan(plan_id)
            if plan is None:
                raise ValueError("学习计划不存在")
            if plan["status"] == "archived":
                raise ValueError("学习计划已撤销，请先恢复后再更新进度")
            days = plan["plan_data"].get("daily_plan", [])
            if not 0 <= day_index < len(days):
                raise ValueError("学习日序号无效")

            completed_days = {int(item) for item in plan["completed_days"]}
            if completed:
                completed_days.add(day_index)
            else:
                completed_days.discard(day_index)
            normalized = sorted(completed_days)
            status = (
                "completed" if days and len(normalized) == len(days) else "active"
            )
            connection = self._conn()
            connection.execute(
                """UPDATE study_plans SET completed_days=?, status=?, updated_at=?
                   WHERE plan_id=?""",
                (self._dump_json(normalized), status, _now_iso(), plan_id),
            )
            connection.commit()
        updated = self.get_study_plan(plan_id)
        if updated is None:
            raise RuntimeError("学习计划更新失败")
        return updated

    def record_product_feedback(
        self,
        *,
        area: str,
        target_id: str,
        rating: int,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """保存不含原文和身份信息的匿名产品反馈。"""
        if area not in {"retrieval", "tutor", "interview", "study_plan"}:
            raise ValueError("无效的反馈区域")
        if rating not in {-1, 1}:
            raise ValueError("反馈评分只能为 -1 或 1")
        if not target_id.strip():
            raise ValueError("反馈目标不能为空")
        target_hash = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"filemate:feedback-target:{target_id}",
        ).hex
        feedback_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"filemate:feedback:{area}:{target_hash}",
        ).hex
        now = _now_iso()
        with self._write_lock:
            self._conn().execute(
                """INSERT INTO product_feedback
                   (feedback_id, area, target_hash, rating, context, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(area, target_hash) DO UPDATE SET
                       rating=excluded.rating,
                       context=excluded.context,
                       updated_at=excluded.updated_at""",
                (
                    feedback_id,
                    area,
                    target_hash,
                    rating,
                    self._dump_json(context or {}),
                    now,
                ),
            )
            self._conn().commit()
        row = self._conn().execute(
            "SELECT * FROM product_feedback WHERE feedback_id=?",
            (feedback_id,),
        ).fetchone()
        result = self._decode_row(row, ("context",))
        if result is None:
            raise RuntimeError("产品反馈保存失败")
        return result

    def list_product_feedback(
        self,
        *,
        area: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """读取匿名产品反馈，用于本地统计与导出。"""
        query = "SELECT * FROM product_feedback"
        params: list[Any] = []
        if area is not None:
            if area not in {"retrieval", "tutor", "interview", "study_plan"}:
                raise ValueError("无效的反馈区域")
            query += " WHERE area=?"
            params.append(area)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(limit, 5000)))
        rows = self._conn().execute(query, params).fetchall()
        return [self._decode_row(row, ("context",)) for row in rows]

    def get_product_feedback_summary(self) -> dict[str, Any]:
        """汇总匿名反馈数量和正向率。"""
        rows = self._conn().execute(
            """SELECT area, COUNT(*) AS total,
                      SUM(CASE WHEN rating=1 THEN 1 ELSE 0 END) AS positive
               FROM product_feedback GROUP BY area"""
        ).fetchall()
        by_area = {
            row["area"]: {
                "total": int(row["total"]),
                "positive": int(row["positive"] or 0),
                "positive_rate": round(
                    int(row["positive"] or 0) / int(row["total"]) * 100,
                    2,
                ),
            }
            for row in rows
        }
        total = sum(item["total"] for item in by_area.values())
        positive = sum(item["positive"] for item in by_area.values())
        return {
            "total": total,
            "positive": positive,
            "positive_rate": round(positive / total * 100, 2) if total else 0.0,
            "by_area": by_area,
        }

    # ------------------------------------------------------------------
    # 可信 Agent / 共享记忆 / 资料授权
    # ------------------------------------------------------------------

    def create_agent_run(
        self,
        *,
        task_type: str,
        goal: str,
        selected_agents: list[str],
        context_refs: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        """创建一条可审计的 Agent 协作运行记录。"""
        if not task_type.strip() or not goal.strip():
            raise ValueError("Agent 任务类型和目标不能为空")
        run_id = uuid.uuid4().hex
        with self._write_lock:
            connection = self._conn()
            connection.execute(
                """INSERT INTO agent_runs
                   (run_id, task_type, goal, selected_agents, context_refs)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    run_id,
                    task_type.strip(),
                    goal.strip(),
                    self._dump_json(selected_agents),
                    self._dump_json(context_refs or {}),
                ),
            )
            if commit:
                connection.commit()
        result = self.get_agent_run(run_id)
        if result is None:
            raise RuntimeError("Agent 运行记录创建失败")
        return result

    def get_agent_run(self, run_id: str) -> dict[str, Any] | None:
        """读取一条 Agent 运行及其真实步骤。"""
        row = self._conn().execute(
            "SELECT * FROM agent_runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        result = self._decode_row(row, ("selected_agents", "context_refs"))
        if result is None:
            return None
        steps = self._conn().execute(
            "SELECT * FROM agent_steps WHERE run_id=? ORDER BY sequence",
            (run_id,),
        ).fetchall()
        result["steps"] = [
            self._decode_row(step, ("input_refs",)) for step in steps
        ]
        return result

    def list_agent_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """按更新时间列出最近的 Agent 协作运行。"""
        rows = self._conn().execute(
            "SELECT run_id FROM agent_runs ORDER BY updated_at DESC, rowid DESC LIMIT ?",
            (max(1, min(limit, 200)),),
        ).fetchall()
        return [
            run
            for row in rows
            if (run := self.get_agent_run(str(row["run_id"]))) is not None
        ]

    def append_agent_step(
        self,
        *,
        run_id: str,
        agent_name: str,
        input_refs: dict[str, Any] | None = None,
        output_summary: str,
        status: str = "completed",
    ) -> dict[str, Any]:
        """追加真实执行步骤，不保存输入原文。"""
        if status not in {"completed", "failed", "blocked"}:
            raise ValueError("无效的 Agent 步骤状态")
        if self.get_agent_run(run_id) is None:
            raise ValueError("Agent 运行不存在")
        if not agent_name.strip() or not output_summary.strip():
            raise ValueError("Agent 名称和输出摘要不能为空")
        step_id = uuid.uuid4().hex
        now = _now_iso()
        with self._write_lock:
            connection = self._conn()
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM agent_steps WHERE run_id=?",
                (run_id,),
            ).fetchone()
            sequence = int(row[0])
            connection.execute(
                """INSERT INTO agent_steps
                   (step_id, run_id, sequence, agent_name, status,
                    input_refs, output_summary)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    step_id,
                    run_id,
                    sequence,
                    agent_name.strip(),
                    status,
                    self._dump_json(input_refs or {}),
                    output_summary.strip(),
                ),
            )
            connection.execute(
                "UPDATE agent_runs SET updated_at=? WHERE run_id=?",
                (now, run_id),
            )
            connection.commit()
        row = self._conn().execute(
            "SELECT * FROM agent_steps WHERE step_id=?",
            (step_id,),
        ).fetchone()
        result = self._decode_row(row, ("input_refs",))
        if result is None:
            raise RuntimeError("Agent 步骤保存失败")
        return result

    def finish_agent_run(self, run_id: str, status: str = "completed") -> bool:
        """结束一条 Agent 运行。"""
        if status not in {"completed", "failed"}:
            raise ValueError("无效的 Agent 运行状态")
        with self._write_lock:
            connection = self._conn()
            cursor = connection.execute(
                "UPDATE agent_runs SET status=?, updated_at=? WHERE run_id=?",
                (status, _now_iso(), run_id),
            )
            connection.commit()
        return cursor.rowcount > 0

    def save_agent_memory(
        self,
        *,
        memory_type: str,
        scope_id: str,
        source_type: str,
        source_id: str,
        summary: str,
        allowed_agents: list[str],
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        """保存带来源和使用范围的摘要记忆。"""
        if memory_type not in {"session", "knowledge", "growth", "operation"}:
            raise ValueError("无效的共享记忆类型")
        if not all(
            value.strip() for value in (scope_id, source_type, source_id, summary)
        ):
            raise ValueError("共享记忆字段不能为空")
        memory_id = uuid.uuid4().hex
        with self._write_lock:
            self._conn().execute(
                """INSERT INTO agent_memories
                   (memory_id, memory_type, scope_id, source_type, source_id,
                    summary, allowed_agents, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    memory_id,
                    memory_type,
                    scope_id.strip(),
                    source_type.strip(),
                    source_id.strip(),
                    summary.strip(),
                    self._dump_json(allowed_agents),
                    expires_at,
                ),
            )
            self._conn().commit()
        row = self._conn().execute(
            "SELECT * FROM agent_memories WHERE memory_id=?",
            (memory_id,),
        ).fetchone()
        result = self._decode_row(row, ("allowed_agents",))
        if result is None:
            raise RuntimeError("共享记忆保存失败")
        return result

    def list_agent_memories(
        self,
        *,
        memory_type: str | None = None,
        include_deleted: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """列出共享记忆元数据，默认隐藏已删除记录。"""
        clauses: list[str] = []
        params: list[Any] = []
        if memory_type is not None:
            if memory_type not in {"session", "knowledge", "growth", "operation"}:
                raise ValueError("无效的共享记忆类型")
            clauses.append("memory_type=?")
            params.append(memory_type)
        if not include_deleted:
            clauses.append("deleted_at IS NULL")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, min(limit, 500)))
        rows = self._conn().execute(
            f"SELECT * FROM agent_memories{where} "
            "ORDER BY updated_at DESC, rowid DESC LIMIT ?",
            params,
        ).fetchall()
        return [self._decode_row(row, ("allowed_agents",)) for row in rows]

    def soft_delete_agent_memory(self, memory_id: str) -> bool:
        """软删除共享记忆，使后续 Agent 不再使用。"""
        now = _now_iso()
        with self._write_lock:
            connection = self._conn()
            cursor = connection.execute(
                """UPDATE agent_memories SET deleted_at=?, updated_at=?
                   WHERE memory_id=? AND deleted_at IS NULL""",
                (now, now, memory_id),
            )
            connection.commit()
        return cursor.rowcount > 0

    def set_source_rights(
        self,
        *,
        source_id: str,
        rights_status: str,
        sharing_scope: str = "private",
        note: str = "",
    ) -> dict[str, Any]:
        """保存资料授权与分享范围声明。"""
        if self.get_source(source_id) is None:
            raise ValueError("资料源不存在")
        if rights_status not in {
            "unconfirmed", "self_owned", "authorized", "public"
        }:
            raise ValueError("无效的资料授权状态")
        if sharing_scope not in {"private", "restricted", "shareable"}:
            raise ValueError("无效的分享范围")
        if rights_status == "unconfirmed" and sharing_scope != "private":
            raise ValueError("授权未确认的资料只能保持私有")
        now = _now_iso()
        confirmed_at = None if rights_status == "unconfirmed" else now
        with self._write_lock:
            self._conn().execute(
                """INSERT INTO source_rights
                   (source_id, rights_status, sharing_scope, note,
                    confirmed_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_id) DO UPDATE SET
                       rights_status=excluded.rights_status,
                       sharing_scope=excluded.sharing_scope,
                       note=excluded.note,
                       confirmed_at=excluded.confirmed_at,
                       updated_at=excluded.updated_at""",
                (
                    source_id,
                    rights_status,
                    sharing_scope,
                    note.strip()[:500],
                    confirmed_at,
                    now,
                ),
            )
            self._conn().commit()
        result = self.get_source_rights(source_id)
        if result is None:
            raise RuntimeError("资料授权声明保存失败")
        return result

    def get_source_rights(self, source_id: str) -> dict[str, Any] | None:
        """读取资料授权；未声明时返回私有默认值。"""
        source = self.get_source(source_id)
        if source is None:
            return None
        row = self._conn().execute(
            "SELECT * FROM source_rights WHERE source_id=?",
            (source_id,),
        ).fetchone()
        if row is not None:
            return dict(row)
        return {
            "source_id": source_id,
            "rights_status": "unconfirmed",
            "sharing_scope": "private",
            "note": "",
            "confirmed_at": None,
            "updated_at": source["updated_at"],
        }

    def list_source_rights(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """列出资料名称及其授权状态，不返回资料正文。"""
        rows = self._conn().execute(
            """SELECT s.source_id, s.original_name, s.media_type, s.created_at,
                      COALESCE(r.rights_status, 'unconfirmed') AS rights_status,
                      COALESCE(r.sharing_scope, 'private') AS sharing_scope,
                      COALESCE(r.note, '') AS note,
                      r.confirmed_at,
                      COALESCE(r.updated_at, s.updated_at) AS updated_at
               FROM sources s LEFT JOIN source_rights r ON r.source_id=s.source_id
               ORDER BY s.updated_at DESC, s.rowid DESC LIMIT ?""",
            (max(1, min(limit, 500)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_learning_analytics(self, *, source_id: str | None = None) -> dict[str, Any]:
        """汇总学习资产、错题与模拟面试指标。"""
        connection = self._conn()
        scalar_queries = {
            "source_count": "SELECT COUNT(*) FROM sources",
            "artifact_count": "SELECT COUNT(*) FROM artifacts",
            "pending_wrong_count": "SELECT COUNT(*) FROM wrong_questions WHERE mastered=0",
            "mastered_wrong_count": "SELECT COUNT(*) FROM wrong_questions WHERE mastered=1",
            "quiz_attempt_count": "SELECT COUNT(*) FROM quiz_attempts",
            "interview_count": "SELECT COUNT(*) FROM interview_sessions",
            "study_plan_count": "SELECT COUNT(*) FROM study_plans",
            "completed_study_plan_count": (
                "SELECT COUNT(*) FROM study_plans WHERE status='completed'"
            ),
        }
        params = (source_id,) if source_id else ()
        interview_scope = (
            "agent_run_id IN (SELECT run_id FROM agent_runs "
            "WHERE json_extract(context_refs, '$.source_id')=?)"
        )

        def scoped(query: str, *, interview: bool = False) -> str:
            if not source_id:
                return query
            condition = interview_scope if interview else "source_id=?"
            return query + (" AND " if " WHERE " in query else " WHERE ") + condition

        result = {
            key: int(connection.execute(
                scoped(query, interview=key == "interview_count"), params
            ).fetchone()[0]) for key, query in scalar_queries.items()
        }
        checked_interviews = []
        unreadable_interviews = 0
        for row in connection.execute(
            scoped("SELECT interview_id FROM interview_sessions", interview=True), params
        ):
            try:
                interview = self.get_interview(row["interview_id"])
            except (ValueError, TypeError, AttributeError):
                unreadable_interviews += 1
                continue
            if interview:
                checked_interviews.append(interview)

        def valid_score(value: Any) -> bool:
            return (not isinstance(value, bool) and isinstance(value, (int, float))
                    and math.isfinite(value) and 0 <= value <= 100)

        for interview in checked_interviews:
            for turn in interview["turns"]:
                if not isinstance(turn["dimensions"], dict):
                    turn["analysis_data_error"] = True
                    turn["score"] = None
                    turn["dimensions"] = {}
            scores = [turn["score"] for turn in interview["turns"] if valid_score(turn["score"])]
            interview["overall_score"] = round(sum(scores) / len(scores), 2) if scores else None

        assessed_scores = [
            interview["overall_score"] for interview in checked_interviews
            if valid_score(interview["overall_score"])
        ]
        result["assessed_interview_count"] = len(assessed_scores)
        result["average_interview_score"] = (
            round(sum(assessed_scores) / len(assessed_scores), 2) if assessed_scores else None
        )

        study_rows = connection.execute(
            scoped("SELECT plan_data, completed_days FROM study_plans"), params
        ).fetchall()
        total_study_days = 0
        completed_study_days = 0
        for row in study_rows:
            try:
                plan_data = json.loads(row["plan_data"])
                completed_days = json.loads(row["completed_days"])
            except (TypeError, json.JSONDecodeError):
                continue
            if (isinstance(plan_data, dict) and isinstance(plan_data.get("daily_plan"), list)
                    and isinstance(completed_days, list)):
                total_study_days += len(plan_data["daily_plan"])
                completed_study_days += len(completed_days)
        result["total_study_days"] = total_study_days
        result["completed_study_days"] = completed_study_days
        result["study_completion_rate"] = round(
            completed_study_days / total_study_days * 100,
            2,
        ) if total_study_days else 0.0
        result["product_feedback"] = self.get_product_feedback_summary()

        dimension_totals: dict[str, float] = {}
        dimension_counts: dict[str, int] = {}
        for interview in checked_interviews:
            for turn in interview["turns"]:
                if not valid_score(turn["score"]) or not isinstance(turn["dimensions"], dict):
                    continue
                for name, score in turn["dimensions"].items():
                    if not valid_score(score):
                        continue
                    dimension_totals[name] = dimension_totals.get(name, 0.0) + float(score)
                    dimension_counts[name] = dimension_counts.get(name, 0) + 1
        result["interview_dimensions"] = {
            name: round(total / dimension_counts[name], 2)
            for name, total in dimension_totals.items()
        }

        recent_rows = connection.execute(
            scoped("SELECT interview_id FROM interview_sessions", interview=True)
            + " ORDER BY updated_at DESC LIMIT 5", params
        ).fetchall()
        fields = ("interview_id", "target_role", "scenario", "status", "current_index",
                  "overall_score", "created_at", "assessed_turn_count")
        by_id = {item["interview_id"]: item for item in checked_interviews}
        result["recent_interviews"] = [
            {key: (interview[key] if key != "overall_score" or valid_score(interview[key]) else None)
             for key in fields}
            for row in recent_rows if (interview := by_id.get(row["interview_id"]))
        ]
        from filemate.study.evidence_profile import build_evidence_profile

        result["evidence_profile"] = build_evidence_profile(
            attempts=[dict(row) for row in connection.execute(
                scoped("SELECT attempt_id, artifact_id, source_id, question_index, is_correct, score, created_at FROM quiz_attempts"), params)],
            wrongs=[dict(row) for row in connection.execute(
                scoped("SELECT wrong_id, artifact_id, source_id, question_index, mastered, updated_at FROM wrong_questions"), params)],
            plans=[dict(row) for row in connection.execute(
                scoped("SELECT plan_id, status, plan_data, completed_days, updated_at FROM study_plans"), params)],
            interviews=checked_interviews, source_id=source_id,
        )
        profile = result["evidence_profile"]
        profile["unreadable_interview_sessions"] = unreadable_interviews
        result["total_study_days"] = profile["total_study_days"]
        result["completed_study_days"] = profile["completed_study_days"]
        result["study_completion_rate"] = profile["metrics"]["plan"]["value"] or 0.0
        return result

    # ------------------------------------------------------------------
    # reversible execution
    # ------------------------------------------------------------------

    def start_execution(
        self,
        *,
        session_id: str,
        source_path: str,
        dest_path: str,
        input_snapshot: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        """创建待执行记录；已有未结束记录时原样返回。"""
        with self._write_lock:
            conn = self._conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute(
                    """SELECT * FROM execution_records
                       WHERE session_id=? AND status IN ('pending','applied')
                       ORDER BY rowid DESC LIMIT 1""",
                    (session_id,),
                ).fetchone()
                if existing is not None:
                    conn.commit()
                    decoded = self._decode_row(
                        existing,
                        ("input_snapshot", "output_snapshot"),
                    )
                    return decoded, False

                execution_id = uuid.uuid4().hex
                conn.execute(
                    """INSERT INTO execution_records
                       (execution_id, session_id, source_path, dest_path,
                        input_snapshot)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        execution_id,
                        session_id,
                        source_path,
                        dest_path,
                        self._dump_json(input_snapshot),
                    ),
                )
                conn.commit()
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise
            record = self.get_execution_record(execution_id)
            if record is None:
                raise RuntimeError("执行记录创建失败")
            return record, True

    def update_execution_record(
        self,
        execution_id: str,
        **kwargs: Any,
    ) -> None:
        """更新可撤销执行记录。"""
        if not kwargs:
            return
        invalid = set(kwargs) - _ALLOWED_EXECUTION_COLS
        if invalid:
            raise ValueError(f"无效执行字段: {sorted(invalid)}")
        values_map = dict(kwargs)
        if "output_snapshot" in values_map:
            values_map["output_snapshot"] = self._dump_json(
                values_map["output_snapshot"]
            )
        set_clause = ", ".join(f"{key}=?" for key in values_map)
        values = [*values_map.values(), _now_iso(), execution_id]
        with self._write_lock:
            self._conn().execute(
                f"""UPDATE execution_records SET {set_clause}, updated_at=?
                    WHERE execution_id=?""",
                values,
            )
            self._conn().commit()

    def get_execution_record(
        self,
        execution_id: str,
    ) -> dict[str, Any] | None:
        """读取单条执行记录。"""
        row = self._conn().execute(
            "SELECT * FROM execution_records WHERE execution_id=?",
            (execution_id,),
        ).fetchone()
        return self._decode_row(
            row,
            ("input_snapshot", "output_snapshot"),
        )

    def get_active_execution(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:
        """读取 Session 当前已应用、尚未撤销的执行。"""
        row = self._conn().execute(
            """SELECT * FROM execution_records
               WHERE session_id=? AND status='applied'
               ORDER BY rowid DESC LIMIT 1""",
            (session_id,),
        ).fetchone()
        return self._decode_row(
            row,
            ("input_snapshot", "output_snapshot"),
        )

    def get_latest_execution(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:
        """读取 Session 最近一次执行记录。"""
        row = self._conn().execute(
            """SELECT * FROM execution_records WHERE session_id=?
               ORDER BY rowid DESC LIMIT 1""",
            (session_id,),
        ).fetchone()
        return self._decode_row(
            row,
            ("input_snapshot", "output_snapshot"),
        )

    def list_execution_records(
        self,
        session_id: str,
    ) -> list[dict[str, Any]]:
        """按时间倒序列出 Session 的执行与撤销历史。"""
        rows = self._conn().execute(
            """SELECT * FROM execution_records WHERE session_id=?
               ORDER BY rowid DESC""",
            (session_id,),
        ).fetchall()
        return [
            self._decode_row(
                row,
                ("input_snapshot", "output_snapshot"),
            )
            for row in rows
        ]

    def finalize_execution(
        self,
        *,
        execution_id: str,
        session_id: str,
        entities: dict[str, Any],
        dest_path: str,
        ics_path: str | None,
        output_snapshot: dict[str, Any],
    ) -> None:
        """原子完成执行记录、Session 状态和审计日志。"""
        now = _now_iso()
        with self._write_lock:
            conn = self._conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                updated = conn.execute(
                    """UPDATE execution_records
                       SET status='applied', dest_path=?, ics_path=?,
                           output_snapshot=?, error='', applied_at=?,
                           updated_at=?
                       WHERE execution_id=? AND status='pending'""",
                    (
                        dest_path,
                        ics_path,
                        self._dump_json(output_snapshot),
                        now,
                        now,
                        execution_id,
                    ),
                )
                if updated.rowcount != 1:
                    raise RuntimeError("执行记录状态已变化，无法完成")
                conn.execute(
                    """UPDATE sessions
                       SET status='confirmed', entities=?, error='', updated_at=?
                       WHERE session_id=?""",
                    (self._dump_json(entities), now, session_id),
                )
                conn.execute(
                    """INSERT INTO operation_log
                       (session_id, action, detail, input_snapshot)
                       VALUES (?, 'execute', ?, ?)""",
                    (
                        session_id,
                        dest_path,
                        self._dump_json(output_snapshot),
                    ),
                )
                conn.commit()
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise

    def fail_execution(
        self,
        *,
        execution_id: str,
        session_id: str,
        error: str,
    ) -> None:
        """原子标记执行失败并记录审计信息。"""
        now = _now_iso()
        with self._write_lock:
            conn = self._conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """UPDATE execution_records
                       SET status='failed', error=?, updated_at=?
                       WHERE execution_id=? AND status='pending'""",
                    (error, now, execution_id),
                )
                conn.execute(
                    """UPDATE sessions
                       SET status='failed', error=?, updated_at=?
                       WHERE session_id=?""",
                    (error, now, session_id),
                )
                conn.execute(
                    """INSERT INTO operation_log
                       (session_id, action, detail)
                       VALUES (?, 'execute_failed', ?)""",
                    (session_id, error),
                )
                conn.commit()
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise

    def finalize_undo(
        self,
        *,
        execution_id: str,
        session_id: str,
        entities: dict[str, Any],
    ) -> None:
        """原子完成撤销并将 Session 恢复为待确认状态。"""
        now = _now_iso()
        with self._write_lock:
            conn = self._conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                updated = conn.execute(
                    """UPDATE execution_records
                       SET status='undone', undone_at=?, updated_at=?
                       WHERE execution_id=? AND status='applied'""",
                    (now, now, execution_id),
                )
                if updated.rowcount != 1:
                    raise RuntimeError("执行记录已撤销或状态已变化")
                conn.execute(
                    """UPDATE sessions
                       SET status='done', entities=?, error='', updated_at=?
                       WHERE session_id=?""",
                    (self._dump_json(entities), now, session_id),
                )
                conn.execute(
                    """INSERT INTO operation_log
                       (session_id, action, detail, input_snapshot)
                       VALUES (?, 'undo', ?, ?)""",
                    (
                        session_id,
                        execution_id,
                        self._dump_json(
                            {
                                "execution_id": execution_id,
                                "restored": True,
                            }
                        ),
                    ),
                )
                conn.commit()
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise

    def save_graph_batch(
        self, source_id: str, source_revision: str, mode: str,
        payload: dict[str, Any], error_code: str = "",
    ) -> dict[str, Any]:
        """保存不可变的图谱抽取草稿并校验资料版本。"""
        if mode not in {"local", "llm"}:
            raise ValueError("无效的图谱抽取模式")
        batch_id = uuid.uuid4().hex
        now = _now_iso()
        with self._write_lock:
            conn = self._conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                current = self.get_source_revision(source_id)
                if current is None or current != source_revision:
                    raise ValueError("资料已删除或版本已变化，请重新抽取")
                conn.execute(
                    """INSERT INTO knowledge_graph_batches
                       (batch_id, source_id, source_revision, mode, status, payload,
                        error_code, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (batch_id, source_id, source_revision, mode,
                     "failed" if error_code else "draft", self._dump_json(payload),
                     error_code[:80], now, now),
                )
                self._append_graph_event(conn, source_id, batch_id,
                                         "extract_failed" if error_code else "extract",
                                         {"mode": mode, "error_code": error_code[:80]})
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            result = self.get_graph_batch(batch_id)
            if result is None:
                raise RuntimeError("图谱草稿保存失败")
            return result

    def get_graph_batch(self, batch_id: str) -> dict[str, Any] | None:
        """读取图谱批次及其资料版本是否失效。"""
        row = self._conn().execute(
            "SELECT * FROM knowledge_graph_batches WHERE batch_id=?", (batch_id,),
        ).fetchone()
        result = self._decode_graph_batch(row)
        if result is not None:
            result["stale"] = (
                self.get_source_revision(result["source_id"]) != result["source_revision"]
            )
        return result

    def list_graph_batches(self) -> list[dict[str, Any]]:
        """读取所有图谱批次，避免截断后丢失已确认知识点。"""
        rows = self._conn().execute(
            "SELECT * FROM knowledge_graph_batches ORDER BY created_at DESC, rowid DESC",
        ).fetchall()
        revisions: dict[str, str | None] = {}
        result = []
        for row in rows:
            batch = self._decode_graph_batch(row)
            if batch is None:
                continue
            source_id = batch["source_id"]
            if source_id not in revisions:
                revisions[source_id] = self.get_source_revision(source_id)
            batch["stale"] = revisions[source_id] != batch["source_revision"]
            result.append(batch)
        return result

    def _decode_graph_batch(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        """隔离损坏批次，不让无效持久化数据阻断整个学习空间。"""
        batch = self._decode_row(row, ("payload",))
        if batch is None:
            return None
        payload = batch["payload"]
        valid = (isinstance(payload, dict) and isinstance(payload.get("nodes"), list)
                 and isinstance(payload.get("edges"), list))
        if valid:
            valid = (all(isinstance(node, dict) and isinstance(node.get("id"), str)
                         and isinstance(node.get("label"), str) for node in payload["nodes"])
                     and all(isinstance(edge, dict) and all(isinstance(edge.get(key), str)
                             for key in ("from", "to", "relation", "excerpt")) for edge in payload["edges"]))
        batch["data_error"] = not valid
        if not valid:
            batch["payload"] = {"nodes": [], "edges": []}
            batch["error_code"] = "InvalidStoredPayload"
        return batch

    def transition_graph_batch(self, batch_id: str, action: str) -> dict[str, Any]:
        """原子确认、撤销或恢复图谱批次，重复操作幂等。"""
        targets = {"confirm": "confirmed", "undo": "undone", "restore": "confirmed"}
        allowed = {
            "confirm": {"draft", "confirmed"},
            "undo": {"draft", "confirmed", "undone"},
            "restore": {"undone", "confirmed"},
        }
        if action not in targets:
            raise ValueError("无效的图谱操作")
        with self._write_lock:
            conn = self._conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                batch = self.get_graph_batch(batch_id)
                if batch is None:
                    raise KeyError(batch_id)
                if batch["status"] not in allowed[action]:
                    raise ValueError("当前图谱状态不支持此操作")
                if action in {"confirm", "restore"} and batch["stale"]:
                    raise ValueError("资料版本已变化，请重新抽取")
                if action in {"confirm", "restore"} and batch["data_error"]:
                    raise ValueError("图谱批次数据异常，请重新提取")
                if action in {"confirm", "restore"}:
                    incoming = {node["id"]: node["label"] for node in batch["payload"]["nodes"]}
                    others = conn.execute(
                        """SELECT payload FROM knowledge_graph_batches
                           WHERE source_id=? AND batch_id<>? AND status='confirmed'""",
                        (batch["source_id"], batch_id),
                    ).fetchall()
                    for other in others:
                        for node in json.loads(other["payload"])["nodes"]:
                            if node["id"] in incoming and incoming[node["id"]] != node["label"]:
                                raise ValueError("知识点标识与已确认批次冲突，请撤销旧批次后重试")
                if batch["status"] != targets[action]:
                    conn.execute(
                        "UPDATE knowledge_graph_batches SET status=?, updated_at=? WHERE batch_id=?",
                        (targets[action], _now_iso(), batch_id),
                    )
                    self._append_graph_event(conn, batch["source_id"], batch_id, action,
                                             {"from_status": batch["status"], "to_status": targets[action]})
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            result = self.get_graph_batch(batch_id)
            if result is None:
                raise RuntimeError("图谱状态更新失败")
            return result

    def get_graph_learning_evidence(self, source_id: str) -> dict[str, Any]:
        """完整读取资料的题目、作答与错题证据，不推断掌握程度。"""
        with self._write_lock:
            conn = self._conn()
            artifacts = conn.execute(
                """SELECT * FROM artifacts WHERE source_id=? AND artifact_type='questions'
                   ORDER BY created_at, rowid""", (source_id,),
            ).fetchall()
            attempts = conn.execute(
                "SELECT rowid AS evidence_sequence, * FROM quiz_attempts WHERE source_id=? ORDER BY created_at, rowid",
                (source_id,),
            ).fetchall()
            wrong = conn.execute(
                "SELECT * FROM wrong_questions WHERE source_id=? ORDER BY created_at, rowid",
                (source_id,),
            ).fetchall()
            return {
                "artifacts": [self._decode_row(row, ("content", "metadata")) for row in artifacts],
                "attempts": [dict(row) for row in attempts],
                "wrong_questions": [
                    self._enrich_wrong_question(self._decode_row(row, ("question",)))
                    for row in wrong
                ],
            }

    def _append_graph_event(
        self, conn: sqlite3.Connection, source_id: str, target_id: str,
        action: str, detail: dict[str, Any],
    ) -> None:
        """在业务事务内记录变更元数据，不复制学习正文或供应商错误。"""
        conn.execute(
            """INSERT INTO knowledge_graph_events
               (source_id, target_id, action, detail, created_at) VALUES (?, ?, ?, ?, ?)""",
            (source_id, target_id, action, self._dump_json(detail), _now_iso()),
        )

    def list_graph_events(self, limit: int = 100) -> list[dict[str, Any]]:
        """返回当前身份最近的图谱操作，资料删除时随来源清理。"""
        rows = self._conn().execute(
            "SELECT * FROM knowledge_graph_events ORDER BY event_id DESC LIMIT ?", (limit,),
        ).fetchall()
        return [self._decode_row(row, ("detail",)) for row in rows]

    def save_graph_study_plan(
        self, source_id: str, node_id: str, evidence_revision: str,
        plan: dict[str, Any],
    ) -> dict[str, str]:
        """以知识点和证据版本为幂等键原子创建学习计划与产物。"""
        key = f"filemate:graph-plan:{source_id}:{node_id}:{evidence_revision}"
        artifact_id = uuid.uuid5(uuid.NAMESPACE_URL, key + ":artifact").hex
        plan_id = uuid.uuid5(uuid.NAMESPACE_URL, key + ":plan").hex
        result = {"plan_id": plan_id, "artifact_id": artifact_id}
        title = str(plan.get("title", "知识点学习计划"))
        content = self._dump_json(plan)
        metadata = self._dump_json({
            "origin": "knowledge_graph", "module_version": "2.2",
            "node_id": node_id, "evidence_revision": evidence_revision,
        })
        with self._write_lock:
            conn = self._conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                if self.get_source(source_id) is None:
                    raise ValueError("资料已删除")
                existing = conn.execute(
                    "SELECT plan_id FROM study_plans WHERE plan_id=?", (plan_id,),
                ).fetchone()
                if existing is not None:
                    conn.commit()
                    return result
                conn.execute(
                    """INSERT INTO artifacts
                       (artifact_id, workspace_id, source_id, artifact_type, title, content, metadata)
                       VALUES (?, 'local', ?, 'study_plan', ?, ?, ?)""",
                    (artifact_id, source_id, title, content, metadata),
                )
                conn.execute(
                    """INSERT INTO study_plans
                       (plan_id, artifact_id, source_id, title, exam_date,
                        daily_minutes, goal, plan_data)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (plan_id, artifact_id, source_id, title, str(plan.get("exam_date", "")),
                     int(plan.get("daily_minutes", 30)), str(plan.get("goal", "")), content),
                )
                self._append_graph_event(conn, source_id, plan_id, "plan_create",
                                         {"node_id": node_id, "evidence_revision": evidence_revision})
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return result

    def _transition_graph_study_plan(self, plan_id: str, restore: bool) -> dict[str, Any]:
        """只归档或恢复图谱创建的计划，保留任务完成记录。"""
        with self._write_lock:
            conn = self._conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                plan = self.get_study_plan(plan_id)
                if plan is None:
                    raise KeyError(plan_id)
                artifact = self.get_artifact(plan["artifact_id"])
                if not artifact or artifact["metadata"].get("origin") != "knowledge_graph":
                    raise ValueError("该计划不是由知识图谱创建")
                status = "archived"
                if restore:
                    days = plan["plan_data"].get("daily_plan", [])
                    status = (
                        "completed" if days and len(plan["completed_days"]) == len(days)
                        else "active"
                    )
                if plan["status"] != status:
                    conn.execute(
                        "UPDATE study_plans SET status=?, updated_at=? WHERE plan_id=?",
                        (status, _now_iso(), plan_id),
                    )
                    self._append_graph_event(conn, plan["source_id"], plan_id,
                                             "plan_restore" if restore else "plan_undo",
                                             {"from_status": plan["status"], "to_status": status})
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            result = self.get_study_plan(plan_id)
            if result is None:
                raise RuntimeError("学习计划状态更新失败")
            return result

    def undo_graph_study_plan(self, plan_id: str) -> dict[str, Any]:
        """幂等撤销图谱学习计划，不删除学习证据。"""
        return self._transition_graph_study_plan(plan_id, restore=False)

    def list_graph_study_plans(self) -> list[dict[str, Any]]:
        """列出当前身份由知识图谱生成的计划与归档状态。"""
        rows = self._conn().execute(
            """SELECT p.plan_id, p.source_id, p.title, p.status, p.updated_at, a.metadata
               FROM study_plans p JOIN artifacts a ON a.artifact_id=p.artifact_id
               ORDER BY p.updated_at DESC, p.rowid DESC"""
        ).fetchall()
        result = []
        for row in rows:
            metadata = json.loads(row["metadata"])
            if metadata.get("origin") == "knowledge_graph":
                result.append({key: row[key] for key in (
                    "plan_id", "source_id", "title", "status", "updated_at",
                )})
        return result

    def restore_graph_study_plan(self, plan_id: str) -> dict[str, Any]:
        """恢复图谱学习计划的原有进度。"""
        return self._transition_graph_study_plan(plan_id, restore=True)

    def create_digital_human_playback(
        self,
        *,
        text_length: int,
        avatar_id: str,
        voice_id: str,
        provider: str,
        context_id: str | None = None,
        message_index: int | None = None,
    ) -> dict[str, Any]:
        """只保存播报元数据，不保存学习正文或音频。"""
        playback_id = uuid.uuid4().hex
        now = _now_iso()
        with self._write_lock:
            self._conn().execute(
                """INSERT INTO digital_human_playbacks
                   (playback_id, context_id, message_index, text_length,
                    avatar_id, voice_id, provider, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'started', ?, ?)""",
                (
                    playback_id, context_id, message_index, text_length,
                    avatar_id, voice_id, provider, now, now,
                ),
            )
            self._conn().commit()
        return self.get_digital_human_playback(playback_id)  # type: ignore[return-value]

    def get_digital_human_playback(self, playback_id: str) -> dict[str, Any] | None:
        """读取当前身份的未删除播报记录。"""
        row = self._conn().execute(
            """SELECT * FROM digital_human_playbacks
               WHERE playback_id=? AND deleted_at IS NULL""",
            (playback_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_digital_human_playbacks(self, limit: int = 30) -> list[dict[str, Any]]:
        """按时间倒序列出当前身份的播报元数据。"""
        rows = self._conn().execute(
            """SELECT * FROM digital_human_playbacks
               WHERE deleted_at IS NULL ORDER BY created_at DESC, rowid DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def finish_digital_human_playback(
        self, playback_id: str, status: str, error_code: str = "",
    ) -> dict[str, Any] | None:
        """幂等地结束一次播报；终态不能被晚到的事件覆盖。"""
        if status not in {"completed", "stopped", "failed"}:
            raise ValueError("无效的播报终态")
        with self._write_lock:
            self._conn().execute(
                """UPDATE digital_human_playbacks
                   SET status=?, error_code=?, updated_at=?
                   WHERE playback_id=? AND status='started' AND deleted_at IS NULL""",
                (status, error_code[:80], _now_iso(), playback_id),
            )
            self._conn().commit()
        return self.get_digital_human_playback(playback_id)

    def delete_digital_human_playback(self, playback_id: str) -> bool:
        """软删除一条播报记录，重复删除安全。"""
        with self._write_lock:
            updated = self._conn().execute(
                """UPDATE digital_human_playbacks SET deleted_at=?, updated_at=?
                   WHERE playback_id=? AND deleted_at IS NULL""",
                (_now_iso(), _now_iso(), playback_id),
            )
            self._conn().commit()
        return updated.rowcount == 1

    def restore_digital_human_playback(self, playback_id: str) -> bool:
        """撤销当前身份的一次记录软删除。"""
        with self._write_lock:
            updated = self._conn().execute(
                """UPDATE digital_human_playbacks SET deleted_at=NULL, updated_at=?
                   WHERE playback_id=? AND deleted_at IS NOT NULL""",
                (_now_iso(), playback_id),
            )
            self._conn().commit()
        return updated.rowcount == 1
