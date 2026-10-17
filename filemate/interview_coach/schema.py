"""Append-only interview answer version schema."""

SCHEMA = """
CREATE TABLE interview_answer_attempts (
 attempt_id TEXT PRIMARY KEY,
 interview_id TEXT NOT NULL REFERENCES interview_sessions(interview_id) ON DELETE CASCADE,
 turn_id TEXT NOT NULL REFERENCES interview_turns(turn_id) ON DELETE CASCADE,
 version INTEGER NOT NULL CHECK(version>=1), question_index INTEGER NOT NULL,
 question TEXT NOT NULL, question_digest TEXT NOT NULL, answer TEXT NOT NULL,
 input_digest TEXT NOT NULL, fluency_metrics TEXT NOT NULL DEFAULT '{}',
 visual_metrics TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
 origin TEXT NOT NULL CHECK(origin IN ('migrated','legacy_write','coach')),
 UNIQUE(turn_id,version)
);
CREATE INDEX interview_attempts_session ON interview_answer_attempts(interview_id,question_index,version);
CREATE TABLE interview_coach_state (
 interview_id TEXT PRIMARY KEY REFERENCES interview_sessions(interview_id) ON DELETE CASCADE,
 revision INTEGER NOT NULL DEFAULT 0, displayed_index INTEGER NOT NULL DEFAULT 0,
 phase TEXT NOT NULL CHECK(phase IN ('question','feedback','summary')),
 entered_indices TEXT NOT NULL DEFAULT '[]', external_consent INTEGER NOT NULL DEFAULT 0,
 consent_revision INTEGER NOT NULL DEFAULT 0, provider_identity TEXT NOT NULL DEFAULT '',
 updated_at TEXT NOT NULL
);
CREATE TABLE interview_coach_questions (
 interview_id TEXT NOT NULL REFERENCES interview_sessions(interview_id) ON DELETE CASCADE,
 question_index INTEGER NOT NULL, question TEXT NOT NULL, question_digest TEXT NOT NULL,
 entered_at TEXT NOT NULL, PRIMARY KEY(interview_id,question_index)
);
CREATE TABLE interview_coach_analysis_runs (
 run_id TEXT PRIMARY KEY,
 interview_id TEXT NOT NULL REFERENCES interview_sessions(interview_id) ON DELETE CASCADE,
 attempt_id TEXT NOT NULL REFERENCES interview_answer_attempts(attempt_id) ON DELETE CASCADE,
 attempt_seq INTEGER NOT NULL, request_key TEXT NOT NULL, input_digest TEXT NOT NULL,
 consent_revision INTEGER NOT NULL, review_revision INTEGER NOT NULL,
 provider_identity TEXT NOT NULL, model TEXT NOT NULL, prompt_version TEXT NOT NULL,
 rubric_version TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('running','cancelling','succeeded','failed','cancelled','interrupted')),
 deadline_at TEXT, lease_until TEXT, evaluation TEXT NOT NULL DEFAULT '{}', error_code TEXT,
 created_at TEXT NOT NULL, finished_at TEXT, UNIQUE(attempt_id,attempt_seq)
);
CREATE UNIQUE INDEX interview_one_active_analysis ON interview_coach_analysis_runs(interview_id)
 WHERE status IN ('running','cancelling');
CREATE TABLE interview_coach_actions (
 interview_id TEXT NOT NULL REFERENCES interview_sessions(interview_id) ON DELETE CASCADE,
 request_key TEXT NOT NULL, kind TEXT NOT NULL, input_digest TEXT NOT NULL,
 result_refs TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(interview_id,request_key)
);
"""
