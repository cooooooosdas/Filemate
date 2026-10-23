"""Append-only course graph schema."""

SCHEMA = """
CREATE TABLE kg_courses (
    course_id TEXT PRIMARY KEY, name TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0 CHECK(revision>=0),
    archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
    request_key TEXT NOT NULL UNIQUE, input_digest TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE kg_chapters (
    chapter_id TEXT PRIMARY KEY, course_id TEXT NOT NULL,
    title TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0,
    parent_id TEXT, revision INTEGER NOT NULL DEFAULT 1,
    UNIQUE(course_id,chapter_id), CHECK(parent_id IS NULL OR parent_id!=chapter_id),
    FOREIGN KEY(course_id) REFERENCES kg_courses(course_id) ON DELETE CASCADE,
    FOREIGN KEY(course_id,parent_id) REFERENCES kg_chapters(course_id,chapter_id)
);
CREATE INDEX kg_chapters_parent ON kg_chapters(course_id,parent_id,sort_order);
CREATE TABLE kg_course_sources (
    course_id TEXT NOT NULL, source_id TEXT NOT NULL, chapter_id TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    revision INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY(course_id,source_id),
    FOREIGN KEY(course_id) REFERENCES kg_courses(course_id) ON DELETE CASCADE,
    FOREIGN KEY(source_id) REFERENCES sources(source_id) ON DELETE CASCADE,
    FOREIGN KEY(course_id,chapter_id) REFERENCES kg_chapters(course_id,chapter_id)
);
CREATE INDEX kg_course_sources_source ON kg_course_sources(source_id,active);
CREATE TABLE kg_extractions (
    extraction_id TEXT PRIMARY KEY, draft_id TEXT NOT NULL,
    course_id TEXT NOT NULL, source_id TEXT NOT NULL, source_revision TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('local','llm')), extractor_version TEXT NOT NULL,
    request_key TEXT NOT NULL, input_digest TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending','running','ready','partial','failed','interrupted','cancelled')),
    epoch INTEGER NOT NULL DEFAULT 0, lease_until TEXT, payload TEXT NOT NULL DEFAULT '{}',
    error_code TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(draft_id,source_id), UNIQUE(course_id,extraction_id),
    FOREIGN KEY(course_id) REFERENCES kg_courses(course_id) ON DELETE CASCADE,
    FOREIGN KEY(source_id) REFERENCES sources(source_id) ON DELETE CASCADE
);
CREATE INDEX kg_extractions_draft ON kg_extractions(course_id,draft_id,created_at);
CREATE INDEX kg_extractions_reuse ON kg_extractions(course_id,source_id,source_revision,mode,status);
CREATE TABLE kg_concepts (
    concept_id TEXT PRIMARY KEY, course_id TEXT NOT NULL, label TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'confirmed'
        CHECK(status IN ('pending','confirmed','rejected','revoked')),
    revision INTEGER NOT NULL DEFAULT 1, canonical_id TEXT,
    UNIQUE(course_id,concept_id), CHECK(canonical_id IS NULL OR canonical_id!=concept_id),
    FOREIGN KEY(course_id) REFERENCES kg_courses(course_id) ON DELETE CASCADE,
    FOREIGN KEY(course_id,canonical_id) REFERENCES kg_concepts(course_id,concept_id)
);
CREATE INDEX kg_concepts_page ON kg_concepts(course_id,status,concept_id);
CREATE INDEX kg_concepts_canonical ON kg_concepts(course_id,canonical_id);
CREATE TABLE kg_relations (
    relation_id TEXT PRIMARY KEY, course_id TEXT NOT NULL, from_id TEXT NOT NULL, to_id TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('prerequisite','depends_on','part_of','contains','application','related_to')),
    status TEXT NOT NULL DEFAULT 'confirmed' CHECK(status IN ('pending','confirmed','rejected','revoked')),
    revision INTEGER NOT NULL DEFAULT 1, UNIQUE(course_id,relation_id),
    FOREIGN KEY(course_id) REFERENCES kg_courses(course_id) ON DELETE CASCADE,
    FOREIGN KEY(course_id,from_id) REFERENCES kg_concepts(course_id,concept_id),
    FOREIGN KEY(course_id,to_id) REFERENCES kg_concepts(course_id,concept_id)
);
CREATE INDEX kg_relations_from ON kg_relations(course_id,from_id,status);
CREATE INDEX kg_relations_to ON kg_relations(course_id,to_id,status);
CREATE TABLE kg_evidence (
    evidence_id TEXT PRIMARY KEY, course_id TEXT NOT NULL, source_id TEXT NOT NULL,
    source_revision TEXT NOT NULL, concept_id TEXT, relation_id TEXT,
    legacy_node_id TEXT, excerpt TEXT NOT NULL, chunk_id TEXT, page INTEGER,
    char_start INTEGER NOT NULL, char_end INTEGER NOT NULL, extraction_id TEXT,
    status TEXT NOT NULL DEFAULT 'confirmed' CHECK(status IN ('confirmed','revoked')),
    CHECK((concept_id IS NOT NULL AND relation_id IS NULL) OR
          (concept_id IS NULL AND relation_id IS NOT NULL)),
    CHECK(legacy_node_id IS NULL OR concept_id IS NOT NULL),
    UNIQUE(course_id,source_id,source_revision,legacy_node_id),
    FOREIGN KEY(course_id) REFERENCES kg_courses(course_id) ON DELETE CASCADE,
    FOREIGN KEY(source_id) REFERENCES sources(source_id) ON DELETE CASCADE,
    FOREIGN KEY(course_id,concept_id) REFERENCES kg_concepts(course_id,concept_id),
    FOREIGN KEY(course_id,relation_id) REFERENCES kg_relations(course_id,relation_id),
    FOREIGN KEY(course_id,extraction_id) REFERENCES kg_extractions(course_id,extraction_id)
);
CREATE INDEX kg_evidence_source ON kg_evidence(source_id,source_revision);
CREATE INDEX kg_evidence_concept ON kg_evidence(course_id,concept_id,status);
CREATE INDEX kg_evidence_relation ON kg_evidence(course_id,relation_id,status);
CREATE TABLE kg_changes (
    operation_id TEXT PRIMARY KEY, course_id TEXT NOT NULL, kind TEXT NOT NULL,
    request_key TEXT NOT NULL, input_digest TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'applied', metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(course_id,request_key),
    FOREIGN KEY(course_id) REFERENCES kg_courses(course_id) ON DELETE CASCADE
);
CREATE INDEX kg_changes_history ON kg_changes(course_id,created_at,operation_id);
"""
