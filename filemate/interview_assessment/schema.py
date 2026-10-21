"""Migration 30: immutable rubric snapshots and append-only assessment reports."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS interview_rubrics (
    rubric_id TEXT NOT NULL,
    version TEXT NOT NULL,
    content TEXT NOT NULL CHECK(json_valid(content)),
    content_digest TEXT NOT NULL,
    PRIMARY KEY(rubric_id,version)
);
CREATE TABLE IF NOT EXISTS interview_assessment_limits (
    interview_id TEXT PRIMARY KEY REFERENCES interview_sessions(interview_id) ON DELETE CASCADE,
    model_reserved INTEGER NOT NULL DEFAULT 0 CHECK(model_reserved BETWEEN 0 AND 12)
);
CREATE TABLE IF NOT EXISTS interview_assessments (
    assessment_id TEXT PRIMARY KEY,
    interview_id TEXT NOT NULL REFERENCES interview_sessions(interview_id) ON DELETE CASCADE,
    request_key TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    input_digest TEXT NOT NULL,
    input_snapshot TEXT NOT NULL CHECK(json_valid(input_snapshot)),
    rubric_id TEXT NOT NULL,
    rubric_version TEXT NOT NULL,
    rubric_snapshot TEXT NOT NULL CHECK(json_valid(rubric_snapshot)),
    mode TEXT NOT NULL CHECK(mode IN ('local','model')),
    status TEXT NOT NULL CHECK(status IN ('running','cancelling','succeeded','failed','cancelled','interrupted')),
    epoch TEXT NOT NULL,
    consent_revision INTEGER NOT NULL,
    review_revision INTEGER NOT NULL,
    provenance TEXT NOT NULL CHECK(json_valid(provenance)),
    artifact_id TEXT REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
    error_code TEXT,
    created_at TEXT NOT NULL,
    deadline_at TEXT NOT NULL,
    finished_at TEXT,
    UNIQUE(interview_id,request_key),
    FOREIGN KEY(rubric_id,rubric_version) REFERENCES interview_rubrics(rubric_id,version)
);
CREATE INDEX IF NOT EXISTS idx_interview_assessments_history ON interview_assessments(interview_id,created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_interview_assessments_active ON interview_assessments(interview_id) WHERE status IN ('running','cancelling');
CREATE TABLE IF NOT EXISTS interview_assessment_evidence (
    assessment_id TEXT NOT NULL REFERENCES interview_assessments(assessment_id) ON DELETE CASCADE,
    attempt_id TEXT NOT NULL REFERENCES interview_answer_attempts(attempt_id) ON DELETE CASCADE,
    source_run_id TEXT REFERENCES interview_coach_analysis_runs(run_id) ON DELETE SET NULL,
    PRIMARY KEY(assessment_id,attempt_id)
);
CREATE INDEX IF NOT EXISTS idx_interview_assessment_attempt ON interview_assessment_evidence(attempt_id);
CREATE INDEX IF NOT EXISTS idx_interview_assessment_source_run ON interview_assessment_evidence(source_run_id);
"""
