"""Source unlinking, purge impact and non-replaying backup recovery."""

import secrets
from typing import Any
from uuid import uuid4

from filemate.course_graph.fusion import _check_preview, _used_receipt
from filemate.course_graph.models import CourseGraphError, digest, now_iso, request_key_valid
from filemate.course_graph.projection import valid_evidence
from filemate.course_graph.repository import get_request, record_change, require_course, transaction
from filemate.course_graph.review import object_states
from filemate.execution import data_actions


def _has_tables(conn) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='kg_courses'").fetchone() is not None


def source_impact(storage, source_id: str, course_id: str | None = None) -> dict[str, Any]:
    """Count graph rows and current support lost without this source."""
    conn = storage._conn()
    if not _has_tables(conn):
        return {"counts": {}, "concept_ids": [], "relation_ids": [], "preserved_concepts": 0,
                "losing_support_concepts": 0, "already_unavailable": 0}
    clause = "source_id=?" + (" AND course_id=?" if course_id else "")
    args = (source_id, course_id) if course_id else (source_id,)
    counts = {name: conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {clause}", args).fetchone()[0]
              for name, table in (("course_graph_memberships", "kg_course_sources"),
                                  ("course_graph_extractions", "kg_extractions"), ("course_graph_evidence", "kg_evidence"))}
    roots, relations = set(), set()
    for row in conn.execute(f"SELECT course_id,concept_id,relation_id FROM kg_evidence WHERE {clause}", args):
        candidates = [row["concept_id"]] if row["concept_id"] else []
        if row["relation_id"]:
            relations.add(row["relation_id"])
            edge = conn.execute("SELECT from_id,to_id FROM kg_relations WHERE relation_id=?", (row["relation_id"],)).fetchone()
            if edge:
                candidates.extend(edge)
        for identity in candidates:
            node = conn.execute("SELECT canonical_id FROM kg_concepts WHERE course_id=? AND concept_id=?",
                                (row["course_id"], identity)).fetchone()
            if node:
                roots.add((row["course_id"], node[0] or identity))
    preserved = losing = unavailable = 0
    for cid, root in roots:
        cache, supported, other = {}, False, False
        for evidence in conn.execute("""SELECT e.* FROM kg_evidence e JOIN kg_concepts c USING(concept_id)
                                        WHERE c.course_id=? AND c.status='confirmed'
                                        AND (c.concept_id=? OR c.canonical_id=?)""", (cid, root, root)):
            if valid_evidence(storage, conn, cid, evidence, cache):
                supported = True
                other = other or evidence["source_id"] != source_id
        preserved += int(other)
        losing += int(supported and not other)
        unavailable += int(not supported)
    return {"counts": counts, "concept_ids": sorted(root for _, root in roots), "relation_ids": sorted(relations),
            "preserved_concepts": preserved, "losing_support_concepts": losing, "already_unavailable": unavailable}


def source_revision_fragment(storage, source_id: str) -> dict[str, Any]:
    """Bind deletion previews to candidates, mappings and surviving support."""
    conn = storage._conn()
    if not _has_tables(conn):
        return {}
    result: dict[str, Any] = {}
    for table in ("kg_course_sources", "kg_extractions", "kg_evidence"):
        result[table] = [digest(dict(row)) for row in conn.execute(
            f"SELECT * FROM {table} WHERE source_id=? ORDER BY rowid", (source_id,))]
    impact = source_impact(storage, source_id)
    supporting_sources = set()
    result["concepts"], result["relations"], result["support"] = [], [], []
    for root in impact["concept_ids"]:
        for node in conn.execute("SELECT * FROM kg_concepts WHERE concept_id=? OR canonical_id=? ORDER BY concept_id", (root, root)):
            result["concepts"].append(digest(dict(node)))
            for evidence in conn.execute("SELECT * FROM kg_evidence WHERE concept_id=? ORDER BY evidence_id", (node["concept_id"],)):
                result["support"].append(digest(dict(evidence)))
                supporting_sources.add((evidence["course_id"], evidence["source_id"]))
    for rid in impact["relation_ids"]:
        row = conn.execute("SELECT * FROM kg_relations WHERE relation_id=?", (rid,)).fetchone()
        if row:
            result["relations"].append(digest(dict(row)))
    result["source_versions"] = []
    for cid, sid in sorted(supporting_sources):
        member = conn.execute("SELECT active,revision FROM kg_course_sources WHERE course_id=? AND source_id=?", (cid, sid)).fetchone()
        result["source_versions"].append((cid, sid, tuple(member) if member else None, storage.get_source_revision(sid)))
    return result


def _remove_context(storage, conn, course_id, source_id):
    require_course(conn, course_id)
    row = conn.execute("SELECT * FROM kg_course_sources WHERE course_id=? AND source_id=?", (course_id, source_id)).fetchone()
    if row is None:
        raise CourseGraphError("source_not_in_course", 404)
    return dict(row), digest({"membership": dict(row), "graph": source_revision_fragment(storage, source_id)})


def preview_remove_source(storage, course_id: str, source_id: str) -> dict[str, Any]:
    with transaction(storage) as conn:
        member, revision = _remove_context(storage, conn, course_id, source_id)
        token = data_actions.issue(conn, "course_graph_remove_source", f"{course_id}:{source_id}", revision)
        return {"source_id": source_id, "confirmation_token": token, "retains_learning_history": True,
                "changed": bool(member["active"]), "support_impact": source_impact(storage, source_id, course_id)}


def remove_source(storage, course_id: str, source_id: str, confirmation_token: str,
                  request_key: str, confirmed: bool) -> dict[str, Any]:
    request_key_valid(request_key)
    if confirmed is not True:
        raise CourseGraphError("confirmation_required", 422)
    command = digest({"source_id": source_id, "token": confirmation_token})
    with transaction(storage) as conn:
        require_course(conn, course_id)
        previous = get_request(conn, course_id, request_key, "remove_source", command)
        if previous:
            return previous["metadata"]["receipt"]
        resource = f"{course_id}:{source_id}"
        used = _used_receipt(conn, "course_graph_remove_source", resource, confirmation_token)
        if used:
            record_change(conn, course_id, request_key, "remove_source", command,
                          {"receipt": used, "alias_of": used["operation_id"]})
            return used
        member, revision = _remove_context(storage, conn, course_id, source_id)
        _check_preview(conn, "course_graph_remove_source", resource, confirmation_token, revision)
        ids = {"concepts": [], "relations": [], "evidence": [], "memberships": [source_id] if member["active"] else []}
        before = object_states(conn, course_id, ids)
        if member["active"]:
            conn.execute("UPDATE kg_course_sources SET active=0,revision=revision+1 WHERE course_id=? AND source_id=?", (course_id, source_id))
            conn.execute("UPDATE kg_courses SET revision=revision+1,updated_at=? WHERE course_id=?", (now_iso(), course_id))
        after = object_states(conn, course_id, ids)
        oid = str(uuid4())
        receipt = {"operation_id": oid, "changed": bool(member["active"]), "retains_learning_history": True,
                   "affected": {"course_graph_memberships": int(bool(member["active"]))}}
        record_change(conn, course_id, request_key, "remove_source", command,
                      {"receipt": receipt, "ids": ids, "before": before, "after": after, "expected": digest(after)}, oid)
        data_actions.finish(conn, "course_graph_remove_source", resource, confirmation_token, receipt)
        return receipt


def normalize_restored_course_graph(conn) -> None:
    """Rotate every execution epoch and never replay restored AI claims."""
    if not _has_tables(conn):
        return
    for row in conn.execute("SELECT extraction_id,status FROM kg_extractions").fetchall():
        interrupted = row["status"] == "running"
        conn.execute("""UPDATE kg_extractions SET epoch=?,lease_until=NULL,
                        status=CASE WHEN status='running' THEN 'interrupted' ELSE status END,
                        error_code=CASE WHEN ? THEN 'backup_restored' ELSE error_code END WHERE extraction_id=?""",
                     (secrets.randbits(60), interrupted, row["extraction_id"]))
    conn.execute("DELETE FROM data_action_previews WHERE action LIKE 'course_graph_%'")
