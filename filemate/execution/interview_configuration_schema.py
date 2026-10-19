"""Append-only interview configuration migration; statically readable by deploy tooling."""

SCHEMA = """
CREATE TABLE interview_session_config (
 interview_id TEXT PRIMARY KEY REFERENCES interview_sessions(interview_id) ON DELETE CASCADE,
 configuration TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE interview_configuration_draft (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision INTEGER NOT NULL,
 content TEXT NOT NULL, request_key TEXT NOT NULL, updated_at TEXT NOT NULL
);
"""
