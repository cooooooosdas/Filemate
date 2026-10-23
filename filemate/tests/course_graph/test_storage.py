"""Course migration, idempotency and isolation regressions."""

import importlib
import sqlite3
from uuid import uuid4

import pytest

from filemate.execution import storage as storage_module
from filemate.execution.storage import SQLiteStorage
from filemate.study.knowledge_graph import extract_local, validate_graph


def repository(store):
    return importlib.import_module("filemate.course_graph.repository").CourseGraphRepository(store)


def test_30_upgrade_preserves_legacy_ids_and_history(tmp_path, monkeypatch):
    migrations = storage_module._MIGRATIONS
    monkeypatch.setattr(storage_module, "_MIGRATIONS", tuple(m for m in migrations if m[0] <= 30))
    store = SQLiteStorage(tmp_path / "upgrade.sqlite")
    store.init_schema()
    assert store.get_schema_version() == 30
    text = "栈：后进先出的线性表。"
    sid = store.save_source(original_name="旧课.txt", source_path="old.txt", raw_text=text)
    batch = store.save_graph_batch(sid, store.get_source_revision(sid), "local",
                                   validate_graph(extract_local(text), text, sid, []))
    store.transition_graph_batch(batch["batch_id"], "confirm")
    aid = store.save_artifact(artifact_type="questions", source_id=sid,
                              content=[{"knowledge_point": "栈", "question": "顺序？", "answer": "后进先出"}])
    store.record_quiz_attempt(artifact_id=aid, question_index=0, user_answer="先进先出",
                             is_correct=False, score=0, feedback="需复习")
    tables = ("sources", "artifacts", "knowledge_graph_batches", "quiz_attempts",
              "wrong_questions", "study_plans")
    before = {t: [dict(r) for r in store._conn().execute(f"SELECT * FROM {t}")] for t in tables}
    monkeypatch.setattr(storage_module, "_MIGRATIONS", migrations)
    store.init_schema()
    assert store.get_schema_version() == 34
    assert {t: [dict(r) for r in store._conn().execute(f"SELECT * FROM {t}")] for t in tables} == before
    assert repository(store).list_courses()["total"] == 0
    assert store._conn().execute("PRAGMA foreign_key_check").fetchall() == []
    assert store._conn().execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    store.close()


def test_reopen_is_idempotent(course_store):
    repo = repository(course_store)
    first = repo.create_course("数据结构", "create_course_0001")
    again = repo.create_course("数据结构", "create_course_0001")
    assert again == first
    course_store.init_schema()
    other = SQLiteStorage(course_store.db_path)
    other.init_schema()
    try:
        assert repository(other).list_courses()["items"] == [first]
        assert len([m for m in other.list_migrations() if m["version"] == 31]) == 1
        with pytest.raises(ValueError, match="request_key_conflict"):
            repository(other).create_course("Python", "create_course_0001")
    finally:
        other.close()


def test_cross_course_fk_and_chapter_cycle_rejected(course_store):
    repo = repository(course_store)
    a = repo.create_course("数据结构", "create_course_0001")["course_id"]
    b = repo.create_course("Python", "create_course_0002")["course_id"]
    parent, child = str(uuid4()), str(uuid4())
    repo.put_chapter(a, parent, "线性表", None, 0, 0)
    repo.put_chapter(a, child, "栈", parent, 1, 0)
    with pytest.raises(ValueError, match="chapter_cycle"):
        repo.put_chapter(a, parent, "线性表", child, 0, 1)
    with pytest.raises(ValueError, match="chapter_not_found"):
        repo.put_chapter(b, str(uuid4()), "跨课", parent, 0, 0)
    conn = course_store._conn()
    with pytest.raises(sqlite3.IntegrityError), conn:
        conn.execute("INSERT INTO kg_chapters(chapter_id,course_id,title,parent_id) VALUES(?,?,?,?)",
                     (str(uuid4()), b, "跨课", parent))
    for cid, nid in [(a, "node-a"), (b, "node-b")]:
        with conn:
            conn.execute("INSERT INTO kg_concepts(concept_id,course_id,label) VALUES(?,?,?)", (nid, cid, "栈"))
    with pytest.raises(sqlite3.IntegrityError), conn:
        conn.execute("INSERT INTO kg_relations(relation_id,course_id,from_id,to_id,type) VALUES(?,?,?,?,?)",
                     ("edge", a, "node-a", "node-b", "related_to"))
    with pytest.raises(sqlite3.IntegrityError), conn:
        conn.execute("UPDATE kg_concepts SET canonical_id='node-b' WHERE concept_id='node-a'")


def test_symbol_labels_not_collapsed():
    normalize = importlib.import_module("filemate.course_graph.models").normalize_term
    assert normalize(" C++ ") == "c++"
    assert normalize(" C++ ") != normalize("C")
    assert normalize(" A\t B  ") == "a b"
    assert normalize("e\u0301") == "é"
    assert normalize("C#") != normalize("C")


def test_attach_checks_all_sources_and_optimistic_revision(course_context):
    store, repo, cid, sid = course_context
    with pytest.raises(ValueError, match="revision_conflict"):
        repo.attach_sources(cid, [sid], None, 0)
    with pytest.raises(ValueError, match="source_not_found"):
        repo.attach_sources(cid, [sid, "missing"], None, 1)
    assert len(repo.get_course(cid)["sources"]) == 1
    assert repo.get_course(cid)["revision"] == 1
    assert repo.attach_sources(cid, [sid], None, 1)["revision"] == 1
    assert store._conn().execute("PRAGMA foreign_key_check").fetchall() == []


def test_failed_migration_does_not_register_or_damage_legacy(tmp_path, monkeypatch):
    original = storage_module._MIGRATIONS
    store = SQLiteStorage(tmp_path / "failure.sqlite")
    monkeypatch.setattr(storage_module, "_MIGRATIONS", tuple(m for m in original if m[0] <= 30))
    store.init_schema()
    sid = store.save_source(original_name="旧课.txt", source_path="legacy.txt", raw_text="原文保留")
    bad_version = max(m[0] for m in original) + 1
    monkeypatch.setattr(storage_module, "_MIGRATIONS", original + ((bad_version, "bad_fixture", "CREATE TABLE bad(a); INVALID SQL;"),))
    with pytest.raises(sqlite3.Error):
        store.init_schema()
    assert bad_version not in [m["version"] for m in store.list_migrations()]
    assert store.get_source(sid)["raw_text"] == "原文保留"
    assert not store._conn().execute("SELECT name FROM sqlite_master WHERE name='bad'").fetchone()
    store.close()
