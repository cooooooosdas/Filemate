"""Append durable review work without changing published migrations."""

SCHEMA = """
CREATE TABLE wrong_review_analyses (
    analysis_id TEXT PRIMARY KEY,
    wrong_id TEXT NOT NULL REFERENCES wrong_questions(wrong_id) ON DELETE CASCADE,
    attempt_id TEXT NOT NULL REFERENCES quiz_attempts(attempt_id) ON DELETE CASCADE,
    question_digest TEXT NOT NULL, input_digest TEXT NOT NULL, context_revision TEXT NOT NULL,
    provider_identity TEXT NOT NULL, model TEXT NOT NULL, prompt_version TEXT NOT NULL,
    input_snapshot TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('running','ready','failed','cancelling','cancelled','interrupted')),
    epoch TEXT NOT NULL, deadline REAL NOT NULL, lease_until REAL NOT NULL,
    result_artifact_id TEXT REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
    error_code TEXT, created_at TEXT NOT NULL, finished_at TEXT,
    cancel_request_key TEXT UNIQUE
);
CREATE UNIQUE INDEX wrong_review_analysis_active ON wrong_review_analyses(wrong_id)
    WHERE status IN ('running','cancelling');
CREATE INDEX wrong_review_analysis_history ON wrong_review_analyses(wrong_id,created_at,analysis_id);
CREATE INDEX wrong_review_analysis_attempt ON wrong_review_analyses(attempt_id);
CREATE INDEX wrong_review_analysis_artifact ON wrong_review_analyses(result_artifact_id);
CREATE INDEX wrong_review_analysis_cache ON wrong_review_analyses(wrong_id,input_digest,status);
CREATE TABLE wrong_review_analysis_sources (
    analysis_id TEXT NOT NULL REFERENCES wrong_review_analyses(analysis_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    PRIMARY KEY(analysis_id,source_id)
);
CREATE INDEX wrong_review_analysis_source ON wrong_review_analysis_sources(source_id,analysis_id);
CREATE TABLE wrong_review_analysis_requests (
    request_key TEXT PRIMARY KEY, request_digest TEXT NOT NULL,
    analysis_id TEXT REFERENCES wrong_review_analyses(analysis_id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX wrong_review_analysis_request_run ON wrong_review_analysis_requests(analysis_id);
CREATE TRIGGER wrong_review_analysis_source_purge BEFORE DELETE ON sources
BEGIN
    DELETE FROM wrong_review_analyses WHERE analysis_id IN
        (SELECT analysis_id FROM wrong_review_analysis_sources WHERE source_id=OLD.source_id);
END;
CREATE TRIGGER wrong_review_analysis_body_purge BEFORE DELETE ON wrong_review_analyses
BEGIN
    DELETE FROM artifacts WHERE artifact_id=OLD.result_artifact_id;
END;
"""
