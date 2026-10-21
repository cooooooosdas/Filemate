"""Read-only bounded course projections with current-source evidence."""

import json
from typing import Any

from filemate.course_graph.models import CourseGraphError
from filemate.course_graph.repository import require_course


def valid_evidence(storage, conn, course_id, evidence, cache) -> bool:
    """Require active course membership and the original source fingerprint."""
    sid = evidence["source_id"]
    if sid not in cache:
        member = conn.execute("SELECT active FROM kg_course_sources WHERE course_id=? AND source_id=?",
                              (course_id, sid)).fetchone()
        cache[sid] = storage.get_source_revision(sid) if member and member[0] else None
    return evidence["status"] == "confirmed" and cache[sid] is not None and cache[sid] == evidence["source_revision"]


def _nodes(storage, conn, course_id, roots):
    result, cache = [], {}
    for root in roots:
        members = [dict(r) for r in conn.execute("""SELECT * FROM kg_concepts WHERE course_id=?
                      AND status='confirmed' AND (concept_id=? OR canonical_id=?) ORDER BY concept_id""",
                                                (course_id, root["concept_id"], root["concept_id"]))]
        evidence, aliases = [], []
        for member in members:
            aliases.extend(json.loads(member["aliases"]))
            for row in conn.execute("SELECT * FROM kg_evidence WHERE course_id=? AND concept_id=?",
                                    (course_id, member["concept_id"])):
                if valid_evidence(storage, conn, course_id, row, cache):
                    evidence.append(dict(row))
        result.append({"id": root["concept_id"], "concept_id": root["concept_id"], "label": root["label"],
                       "aliases": aliases, "member_ids": [m["concept_id"] for m in members],
                       "source_count": len({e["source_id"] for e in evidence}), "source_refs": evidence,
                       "source_status": "available" if evidence else "no_valid_source",
                       "learning_status": "not_evaluated", "revision": root["revision"]})
    return result


def course_graph(storage, course_id: str, limit: int = 50, offset: int = 0, q: str = "") -> dict[str, Any]:
    """Page representative concepts and include only supported in-page relations."""
    if not 1 <= limit <= 200 or not 0 <= offset <= 1_000_000 or len(q) > 160:
        raise CourseGraphError("invalid_pagination", 422)
    with storage.read_snapshot() as snapshot:
        conn = snapshot._conn()
        require_course(conn, course_id)
        where = """course_id=? AND status='confirmed' AND canonical_id IS NULL AND
                   (instr(lower(label),lower(?))>0 OR EXISTS(SELECT 1 FROM json_each(kg_concepts.aliases)
                   WHERE instr(lower(json_extract(value,'$.label')),lower(?))>0))"""
        args = (course_id, q, q)
        total = conn.execute(f"SELECT COUNT(*) FROM kg_concepts WHERE {where}", args).fetchone()[0]
        roots = conn.execute(f"SELECT * FROM kg_concepts WHERE {where} ORDER BY concept_id LIMIT ? OFFSET ?",
                             (*args, limit, offset)).fetchall()
        nodes = _nodes(snapshot, conn, course_id, roots)
        member_to_root = {mid: n["id"] for n in nodes for mid in n["member_ids"]}
        supported = {n["id"] for n in nodes if n["source_count"]}
        edges, cache, self_edges, omitted = {}, {}, 0, 0
        # B保持分页画布；C再引入专门的邻域索引查询与布局。
        for row in conn.execute("SELECT * FROM kg_relations WHERE course_id=? AND status='confirmed'", (course_id,)):
            a, b = member_to_root.get(row["from_id"]), member_to_root.get(row["to_id"])
            if not a and not b:
                continue
            refs = [dict(e) for e in conn.execute("SELECT * FROM kg_evidence WHERE course_id=? AND relation_id=?",
                                                 (course_id, row["relation_id"]))
                    if valid_evidence(snapshot, conn, course_id, e, cache)]
            if not refs:
                continue
            if a == b and a is not None:
                self_edges += 1
                continue
            if a not in supported or b not in supported:
                omitted += 1
                continue
            key = (a, b, row["type"])
            if key not in edges:
                edges[key] = {"id": row["relation_id"], "from": a, "to": b, "relation": row["type"],
                              "relation_ids": [], "source_refs": []}
            edges[key]["relation_ids"].append(row["relation_id"])
            edges[key]["source_refs"].extend(refs)
        return {"course_id": course_id, "nodes": nodes, "edges": list(edges.values()), "total": total,
                "limit": limit, "offset": offset, "self_edge_count": self_edges, "omitted_edge_count": omitted}


def concept_detail(storage, course_id: str, concept_id: str) -> dict[str, Any]:
    """Resolve either an original ID or its representative without scanning pages."""
    with storage.read_snapshot() as snapshot:
        conn = snapshot._conn()
        require_course(conn, course_id)
        row = conn.execute("SELECT * FROM kg_concepts WHERE course_id=? AND concept_id=? AND status='confirmed'",
                           (course_id, concept_id)).fetchone()
        if row is None:
            raise CourseGraphError("concept_not_found", 404)
        if row["canonical_id"]:
            row = conn.execute("SELECT * FROM kg_concepts WHERE course_id=? AND concept_id=?",
                               (course_id, row["canonical_id"])).fetchone()
        return _nodes(snapshot, conn, course_id, [row])[0]
