"""Append-only review migration compatible with SQLite 3.26."""

SCHEMA = """
CREATE TABLE quiz_attempts_review_upgrade (
    attempt_id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    source_id TEXT REFERENCES sources(source_id) ON DELETE CASCADE,
    question_index INTEGER NOT NULL,
    user_answer TEXT NOT NULL,
    is_correct INTEGER,
    score REAL,
    feedback TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    purpose TEXT NOT NULL DEFAULT 'legacy_unknown',
    judgement_method TEXT NOT NULL DEFAULT 'legacy_rule',
    judgement_status TEXT NOT NULL DEFAULT 'legacy',
    rule_version TEXT NOT NULL DEFAULT 'legacy-v1',
    question_digest TEXT NOT NULL DEFAULT '',
    answer_revealed INTEGER NOT NULL DEFAULT 0 CHECK(answer_revealed IN (0,1)),
    duration_ms INTEGER,
    duration_source TEXT,
    self_reported_result TEXT
);
INSERT INTO quiz_attempts_review_upgrade
    (rowid,attempt_id,artifact_id,source_id,question_index,user_answer,is_correct,score,feedback,created_at)
SELECT rowid,attempt_id,artifact_id,source_id,question_index,user_answer,is_correct,score,feedback,created_at
FROM quiz_attempts ORDER BY rowid;
DROP TABLE quiz_attempts;
ALTER TABLE quiz_attempts_review_upgrade RENAME TO quiz_attempts;
CREATE INDEX idx_attempts_artifact ON quiz_attempts(artifact_id,created_at);
CREATE INDEX idx_review_attempt_identity ON quiz_attempts(artifact_id,question_index,created_at);

ALTER TABLE wrong_questions ADD COLUMN learning_status TEXT NOT NULL DEFAULT 'legacy';
ALTER TABLE wrong_questions ADD COLUMN scheduler_version TEXT NOT NULL DEFAULT 'legacy-v1';
ALTER TABLE wrong_questions ADD COLUMN schedule_status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE wrong_questions ADD COLUMN revision INTEGER NOT NULL DEFAULT 1;
ALTER TABLE wrong_questions ADD COLUMN review_stage INTEGER NOT NULL DEFAULT 0;
ALTER TABLE wrong_questions ADD COLUMN eligible_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE wrong_questions ADD COLUMN first_verified_at TEXT;
ALTER TABLE wrong_questions ADD COLUMN last_verified_at TEXT;
ALTER TABLE wrong_questions ADD COLUMN review_attempt_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE wrong_questions ADD COLUMN paused_at TEXT;
ALTER TABLE wrong_questions ADD COLUMN error_causes TEXT NOT NULL DEFAULT '[]';
ALTER TABLE wrong_questions ADD COLUMN custom_tags TEXT NOT NULL DEFAULT '[]';
CREATE INDEX idx_review_queue ON wrong_questions(schedule_status,next_review_at,wrong_id);

CREATE TABLE review_events (
    event_id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    wrong_id TEXT REFERENCES wrong_questions(wrong_id) ON DELETE CASCADE,
    attempt_id TEXT REFERENCES quiz_attempts(attempt_id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    request_key TEXT NOT NULL UNIQUE,
    input_digest TEXT NOT NULL,
    before_state TEXT NOT NULL,
    after_state TEXT NOT NULL,
    result TEXT NOT NULL,
    undo_of TEXT REFERENCES review_events(event_id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_review_events_wrong ON review_events(wrong_id,created_at,event_id);
CREATE UNIQUE INDEX idx_review_events_undo ON review_events(undo_of) WHERE undo_of IS NOT NULL;
CREATE INDEX idx_review_events_attempt ON review_events(attempt_id);
"""
