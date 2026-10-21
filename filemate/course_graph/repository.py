"""Tenant-local course persistence with short write transactions."""

import json
import sqlite3
from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

from filemate.course_graph.models import (
    CourseGraphError,
    bounded_text,
    digest,
    now_iso,
    request_key_valid,
)
from filemate.execution.storage import SQLiteStorage


@contextmanager
def transaction(storage: SQLiteStorage):
    """Serialize mutations across connections without holding locks over models."""
    with storage._write_lock:
        conn = storage._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def require_course(conn: sqlite3.Connection, course_id: str) -> dict[str, Any]:
    """Resolve a course within this tenant only."""
    row = conn.execute("SELECT * FROM kg_courses WHERE course_id=? AND archived=0", (course_id,)).fetchone()
    if row is None:
        raise CourseGraphError("course_not_found", 404)
    return dict(row)


def get_request(conn: sqlite3.Connection, course_id: str, request_key: str,
                kind: str, input_digest: str) -> dict[str, Any] | None:
    """Bind every idempotency key to one command and normalized body."""
    row = conn.execute("SELECT * FROM kg_changes WHERE course_id=? AND request_key=?",
                       (course_id, request_key)).fetchone()
    if row is None:
        return None
    if row["kind"] != kind or row["input_digest"] != input_digest:
        raise CourseGraphError("request_key_conflict")
    result = dict(row)
    result["metadata"] = json.loads(result["metadata"])
    return result


def record_change(conn: sqlite3.Connection, course_id: str, request_key: str, kind: str,
                  input_digest: str, metadata: dict[str, Any], operation_id: str | None = None) -> str:
    """Persist only command identities and inverse metadata in operation history."""
    oid, stamp = operation_id or str(uuid4()), now_iso()
    conn.execute("""INSERT INTO kg_changes(operation_id,course_id,kind,request_key,input_digest,
                    metadata,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)""",
                 (oid, course_id, kind, request_key, input_digest,
                  json.dumps(metadata, ensure_ascii=False), stamp, stamp))
    return oid


class CourseGraphRepository:
    """Manage stable course, chapter and source membership identities."""

    def __init__(self, storage: SQLiteStorage):
        self.storage = storage

    def create_course(self, name: str, request_key: str) -> dict[str, Any]:
        name = bounded_text(name, 80)
        request_key_valid(request_key)
        hashed = digest({"name": name})
        with transaction(self.storage) as conn:
            existing = conn.execute("SELECT * FROM kg_courses WHERE request_key=?", (request_key,)).fetchone()
            if existing:
                if existing["input_digest"] != hashed:
                    raise CourseGraphError("request_key_conflict")
                return dict(existing)
            cid, stamp = str(uuid4()), now_iso()
            conn.execute("""INSERT INTO kg_courses(course_id,name,request_key,input_digest,created_at,updated_at)
                            VALUES(?,?,?,?,?,?)""", (cid, name, request_key, hashed, stamp, stamp))
            return require_course(conn, cid)

    def list_courses(self, limit: int = 50, offset: int = 0, q: str = "") -> dict[str, Any]:
        if not 1 <= limit <= 200 or not 0 <= offset <= 1_000_000 or len(q) > 160:
            raise CourseGraphError("invalid_pagination", 422)
        conn = self.storage._conn()
        params = (q,)
        where = "archived=0 AND instr(lower(name),lower(?))>0"
        total = conn.execute(f"SELECT COUNT(*) FROM kg_courses WHERE {where}", params).fetchone()[0]
        rows = conn.execute(f"SELECT * FROM kg_courses WHERE {where} ORDER BY course_id LIMIT ? OFFSET ?",
                            (*params, limit, offset)).fetchall()
        return {"items": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}

    def get_course(self, course_id: str) -> dict[str, Any]:
        conn = self.storage._conn()
        result = require_course(conn, course_id)
        result["chapters"] = [dict(r) for r in conn.execute(
            "SELECT * FROM kg_chapters WHERE course_id=? ORDER BY sort_order,chapter_id", (course_id,))]
        result["sources"] = [dict(r) for r in conn.execute(
            """SELECT m.*,s.original_name FROM kg_course_sources m JOIN sources s USING(source_id)
               WHERE m.course_id=? ORDER BY m.source_id""", (course_id,))]
        return result

    def put_chapter(self, course_id: str, chapter_id: str, title: str, parent_id: str | None,
                    sort_order: int, expected_revision: int) -> dict[str, Any]:
        title = bounded_text(title, 120)
        try:
            UUID(chapter_id)
        except (ValueError, TypeError, AttributeError):
            raise CourseGraphError("invalid_chapter_id", 422) from None
        if type(sort_order) is not int or not 0 <= sort_order <= 100_000:
            raise CourseGraphError("invalid_sort_order", 422)
        with transaction(self.storage) as conn:
            require_course(conn, course_id)
            existing = conn.execute("SELECT * FROM kg_chapters WHERE course_id=? AND chapter_id=?",
                                    (course_id, chapter_id)).fetchone()
            if (existing["revision"] if existing else 0) != expected_revision:
                raise CourseGraphError("revision_conflict")
            if conn.execute("SELECT 1 FROM kg_chapters WHERE chapter_id=? AND course_id!=?",
                            (chapter_id, course_id)).fetchone():
                raise CourseGraphError("chapter_not_found", 404)
            ancestors, current = {chapter_id}, parent_id
            while current:
                if current in ancestors:
                    raise CourseGraphError("chapter_cycle")
                ancestors.add(current)
                row = conn.execute("SELECT parent_id FROM kg_chapters WHERE course_id=? AND chapter_id=?",
                                   (course_id, current)).fetchone()
                if row is None:
                    raise CourseGraphError("chapter_not_found", 404)
                current = row["parent_id"]
            conn.execute("""INSERT INTO kg_chapters(chapter_id,course_id,title,parent_id,sort_order,revision)
                            VALUES(?,?,?,?,?,1) ON CONFLICT(chapter_id) DO UPDATE SET
                            title=excluded.title,parent_id=excluded.parent_id,sort_order=excluded.sort_order,
                            revision=kg_chapters.revision+1""", (chapter_id, course_id, title, parent_id, sort_order))
            return dict(conn.execute("SELECT * FROM kg_chapters WHERE chapter_id=?", (chapter_id,)).fetchone())

    def attach_sources(self, course_id: str, source_ids: list[str], chapter_id: str | None,
                       expected_revision: int) -> dict[str, Any]:
        if not 1 <= len(source_ids) <= 10 or len(set(source_ids)) != len(source_ids):
            raise CourseGraphError("invalid_sources", 422)
        with transaction(self.storage) as conn:
            course = require_course(conn, course_id)
            if course["revision"] != expected_revision:
                raise CourseGraphError("revision_conflict")
            if chapter_id and not conn.execute("SELECT 1 FROM kg_chapters WHERE course_id=? AND chapter_id=?",
                                               (course_id, chapter_id)).fetchone():
                raise CourseGraphError("chapter_not_found", 404)
            changed = False
            for sid in source_ids:
                if not conn.execute("SELECT 1 FROM sources WHERE source_id=?", (sid,)).fetchone():
                    raise CourseGraphError("source_not_found", 404)
                row = conn.execute("SELECT * FROM kg_course_sources WHERE course_id=? AND source_id=?",
                                   (course_id, sid)).fetchone()
                if row and row["active"] and row["chapter_id"] == chapter_id:
                    continue
                changed = True
                conn.execute("""INSERT INTO kg_course_sources(course_id,source_id,chapter_id) VALUES(?,?,?)
                                ON CONFLICT(course_id,source_id) DO UPDATE SET active=1,
                                chapter_id=excluded.chapter_id,revision=kg_course_sources.revision+1""",
                             (course_id, sid, chapter_id))
            if changed:
                conn.execute("UPDATE kg_courses SET revision=revision+1,updated_at=? WHERE course_id=?",
                             (now_iso(), course_id))
        return self.get_course(course_id)
