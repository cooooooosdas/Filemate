"""Tenant-bound metadata pages for explicit evidence selection."""

import sqlite3
from types import SimpleNamespace
from typing import Any

from filemate.execution.data_actions import digest
from filemate.execution.storage import SQLiteStorage

from ..context import resolve_scope
from ..snapshot_queries import object_json
from .evidence import decode, read_wrong_record, selected_concepts, selected_submissions
from .models import (
    CoachCatalogItem,
    CoachCatalogPage,
    CoachCatalogRequest,
    CoachSelection,
    OrchestratorError,
    ScopeRequest,
)


def _object(raw: Any) -> dict[str, Any] | None:
    return (
        object_json(raw) if isinstance(raw, str) and len(raw.encode("utf-8")) <= 1048576 else None
    )


def _interview_source(raw: Any) -> str:
    value = _object(raw or "{}")
    if value is None:
        return "@invalid"
    source = value.get("source_id")
    return "" if source is None else source if isinstance(source, str) else "@invalid"


def _query(
    conn: sqlite3.Connection, request: CoachCatalogRequest, scope: ScopeRequest
) -> tuple[str, str, str, list[Any]]:
    slots = ",".join("?" for _ in scope.source_ids) or "NULL"
    if request.kind == "interview":
        conn.create_function("coach_interview_source", 1, _interview_source)
        base = "interview_sessions i LEFT JOIN agent_runs r ON r.run_id=i.agent_run_id"
        source = "coach_interview_source(COALESCE(r.context_refs,'{}'))"
        select = f"i.interview_id AS id,substr(i.target_role,1,160) AS label,i.updated_at,NULLIF({source},'') AS source_id"
        where = f"({source}='' OR {source} IN ({slots}))"
        args = list(scope.source_ids)
        label = "i.target_role"
    elif request.kind == "submission":
        base = "coding_submissions c JOIN artifacts a ON a.artifact_id=c.artifact_id AND a.artifact_type='coding_submission'"
        select = (
            "c.submission_id AS id,substr(a.title,1,160) AS label,c.updated_at,NULL AS source_id"
        )
        where, args, label = "c.active=1 AND c.status='completed'", [], "a.title"
    elif request.kind == "position":
        base, select = (
            "career_positions p",
            "p.position_id AS id,'岗位' AS label,p.updated_at,NULL AS source_id",
        )
        where, args, label = "p.active=1", [], "p.payload"
    elif request.kind == "wrong":
        base = "wrong_questions w"
        select = (
            "w.wrong_id AS id,substr(w.knowledge_label,1,160) AS label,w.updated_at,w.source_id"
        )
        where, args, label = (
            f"w.source_id IN ({slots})",
            list(scope.source_ids),
            "w.knowledge_label",
        )
    else:
        base = "kg_concepts c"
        select = (
            "c.concept_id AS id,substr(c.label,1,160) AS label,NULL AS updated_at,NULL AS source_id"
        )
        where = f"""c.course_id=? AND c.status='confirmed' AND c.canonical_id IS NULL AND EXISTS(
            SELECT 1 FROM kg_evidence e JOIN kg_concepts member ON member.concept_id=e.concept_id AND member.course_id=e.course_id
            WHERE e.course_id=c.course_id AND (member.concept_id=c.concept_id OR member.canonical_id=c.concept_id)
            AND e.status='confirmed' AND e.source_id IN ({slots}))"""
        args, label = [scope.course_id or "", *scope.source_ids], "c.label"
    if request.q:
        where += f" AND instr(lower(COALESCE({label},'')),lower(?))>0"
        args.append(request.q)
    return base, select, where, args


def _catalog_item(
    read: SQLiteStorage, request: CoachCatalogRequest, scope: ScopeRequest, row: sqlite3.Row
) -> CoachCatalogItem:
    data = dict(row)
    valid = isinstance(data["label"], str) and bool(data["label"].strip())
    revision = digest(data)
    try:
        if request.kind == "position":
            from filemate.career.models import Position

            raw = (
                read._conn()
                .execute(
                    "SELECT CASE WHEN length(CAST(payload AS BLOB))<=1048576 THEN payload END FROM career_positions WHERE position_id=?",
                    (row["id"],),
                )
                .fetchone()[0]
            )
            position = Position.model_validate(decode(raw))
            data["label"] = position.title[:160]
            revision = digest({"metadata": data, "payload": raw})
        elif request.kind == "submission":
            evidence = selected_submissions(read, CoachSelection(submission_ids=[row["id"]]))
            revision = digest({"metadata": data, "evidence": evidence[0].revision})
        elif request.kind == "concept":
            evidence = selected_concepts(
                read,
                scope,
                CoachSelection(concept_ids=[row["id"]]),
                SimpleNamespace(facts={"graph": []}),
            )
            revision = digest({"metadata": data, "evidence": evidence[0].revision})
        elif request.kind == "wrong":
            record, question = read_wrong_record(read, scope, row["id"])
            revision = digest({"metadata": data, "record": record, "question": question})
    except (OrchestratorError, ValueError, TypeError):
        valid = False
    return CoachCatalogItem(**data, revision=revision, valid=valid)


def read_coach_catalog(storage: SQLiteStorage, request: CoachCatalogRequest) -> CoachCatalogPage:
    request = CoachCatalogRequest.model_validate(request)
    with storage.read_snapshot() as read:
        scope, _, _, _, _ = resolve_scope(read, request.scope)
        conn = read._conn()
        base, fields, where, args = _query(conn, request, scope)
        total = conn.execute(f"SELECT count(*) FROM {base} WHERE {where}", args).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM (SELECT {fields} FROM {base} WHERE {where}) ORDER BY updated_at DESC,id LIMIT 30 OFFSET ?",
            [*args, request.offset],
        ).fetchall()
        items = [_catalog_item(read, request, scope, row) for row in rows]
        return CoachCatalogPage(items=items, total=total, offset=request.offset)
