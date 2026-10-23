"""Append-only course learning mappings and bounded work records."""

SCHEMA = """
CREATE TABLE kg_question_links (
    link_id TEXT PRIMARY KEY, course_id TEXT NOT NULL, concept_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL, source_id TEXT NOT NULL,
    question_index INTEGER NOT NULL CHECK(question_index>=0), question_digest TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>0),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(course_id,concept_id,artifact_id,question_index,question_digest),
    FOREIGN KEY(course_id,concept_id) REFERENCES kg_concepts(course_id,concept_id) ON DELETE CASCADE,
    FOREIGN KEY(artifact_id) REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    FOREIGN KEY(course_id,source_id) REFERENCES kg_course_sources(course_id,source_id) ON DELETE CASCADE
);
CREATE INDEX kg_question_links_concept ON kg_question_links(course_id,concept_id,active);
CREATE INDEX kg_question_links_artifact ON kg_question_links(artifact_id,question_index);
CREATE INDEX kg_question_links_source ON kg_question_links(source_id);
CREATE TABLE kg_cross_links (
    link_id TEXT PRIMARY KEY, from_course_id TEXT NOT NULL, from_concept_id TEXT NOT NULL,
    to_course_id TEXT NOT NULL, to_concept_id TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>0),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    CHECK(from_course_id!=to_course_id),
    UNIQUE(from_course_id,from_concept_id,to_course_id,to_concept_id),
    FOREIGN KEY(from_course_id,from_concept_id) REFERENCES kg_concepts(course_id,concept_id) ON DELETE CASCADE,
    FOREIGN KEY(to_course_id,to_concept_id) REFERENCES kg_concepts(course_id,concept_id) ON DELETE CASCADE
);
CREATE INDEX kg_cross_links_from ON kg_cross_links(from_course_id,from_concept_id,active);
CREATE INDEX kg_cross_links_to ON kg_cross_links(to_course_id,to_concept_id,active);
CREATE TABLE kg_course_plan_links (
    plan_id TEXT NOT NULL, course_id TEXT NOT NULL, concept_id TEXT NOT NULL,
    day_index INTEGER NOT NULL CHECK(day_index BETWEEN 0 AND 6),
    PRIMARY KEY(plan_id,course_id,concept_id,day_index),
    FOREIGN KEY(plan_id) REFERENCES study_plans(plan_id) ON DELETE CASCADE,
    FOREIGN KEY(course_id,concept_id) REFERENCES kg_concepts(course_id,concept_id) ON DELETE CASCADE
);
CREATE INDEX kg_course_plan_links_concept ON kg_course_plan_links(course_id,concept_id,plan_id);
CREATE TABLE kg_learning_work (
    work_id TEXT PRIMARY KEY, course_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('practice','answer')),
    request_key TEXT NOT NULL, input_digest TEXT NOT NULL,
    graph_digest TEXT NOT NULL, evidence_digest TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('running','ready','failed','cancelled','interrupted','confirmed')),
    epoch INTEGER NOT NULL, lease_until TEXT,
    payload TEXT NOT NULL DEFAULT '{}', error_code TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(course_id,request_key),
    FOREIGN KEY(course_id) REFERENCES kg_courses(course_id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX kg_learning_work_running ON kg_learning_work(course_id) WHERE status='running';
CREATE INDEX kg_learning_work_history ON kg_learning_work(course_id,created_at,work_id);
CREATE TABLE kg_learning_work_sources (
    work_id TEXT NOT NULL, source_id TEXT NOT NULL,
    PRIMARY KEY(work_id,source_id),
    FOREIGN KEY(work_id) REFERENCES kg_learning_work(work_id) ON DELETE CASCADE,
    FOREIGN KEY(source_id) REFERENCES sources(source_id) ON DELETE CASCADE
);
CREATE INDEX kg_learning_work_sources_source ON kg_learning_work_sources(source_id,work_id);
CREATE TRIGGER kg_learning_work_source_purge BEFORE DELETE ON sources
BEGIN
    DELETE FROM kg_learning_work WHERE work_id IN
        (SELECT work_id FROM kg_learning_work_sources WHERE source_id=OLD.source_id);
END;
"""
