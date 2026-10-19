"""Migration 29: recoverable timed practice and evidence references."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS interview_runtime (
    interview_id TEXT PRIMARY KEY REFERENCES interview_sessions(interview_id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK(status IN ('prepared','running','interrupted','finished','expired')),
    revision INTEGER NOT NULL DEFAULT 0,
    version_token TEXT NOT NULL,
    seed TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL CHECK(duration_seconds BETWEEN 60 AND 3600),
    started_at TEXT,
    deadline TEXT,
    ended_at TEXT,
    current_task INTEGER NOT NULL DEFAULT 0,
    audience_count INTEGER NOT NULL DEFAULT 0 CHECK(audience_count BETWEEN 0 AND 30),
    last_audience_at TEXT,
    ai_reserved INTEGER NOT NULL DEFAULT 0 CHECK(ai_reserved BETWEEN 0 AND 12),
    prepare_key TEXT NOT NULL UNIQUE,
    prepare_digest TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS interview_tasks (
    interview_id TEXT NOT NULL REFERENCES interview_sessions(interview_id) ON DELETE CASCADE,
    task_index INTEGER NOT NULL,
    task_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_id TEXT REFERENCES interview_answer_attempts(attempt_id) ON DELETE SET NULL,
    PRIMARY KEY(interview_id, task_index),
    UNIQUE(interview_id, task_id)
);
CREATE TABLE IF NOT EXISTS interview_events (
    interview_id TEXT NOT NULL REFERENCES interview_sessions(interview_id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    event_key TEXT NOT NULL,
    kind TEXT NOT NULL,
    task_index INTEGER,
    text TEXT NOT NULL DEFAULT '',
    attempt_id TEXT REFERENCES interview_answer_attempts(attempt_id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    input_digest TEXT NOT NULL DEFAULT '',
    receipt TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(interview_id, sequence),
    UNIQUE(interview_id, event_key)
);
CREATE INDEX IF NOT EXISTS idx_interview_events_kind ON interview_events(interview_id, kind, sequence);
CREATE INDEX IF NOT EXISTS idx_interview_tasks_attempt ON interview_tasks(attempt_id);
CREATE INDEX IF NOT EXISTS idx_interview_events_attempt ON interview_events(attempt_id);
"""
