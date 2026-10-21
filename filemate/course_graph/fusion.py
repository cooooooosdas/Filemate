"""Explicit course-local fusion and revision-bound operation reversal."""

import copy
import json
from collections import deque
from typing import Any
from uuid import uuid4

from filemate.course_graph.models import (
    CourseGraphError,
    digest,
    normalize_term,
    now_iso,
    request_key_valid,
)
from filemate.course_graph.projection import (  # noqa: F401 -- public service interface
    course_graph,
    valid_evidence,
)
from filemate.course_graph.repository import get_request, record_change, require_course, transaction
from filemate.course_graph.review import object_states
from filemate.execution import data_actions


def merge_candidates(storage, course_id: str, concept_id: str, limit: int = 20) -> list[dict[str, Any]]:
    if not 1 <= limit <= 20:
        raise CourseGraphError("invalid_limit", 422)
    conn = storage._conn()
    require_course(conn, course_id)
    rows = [dict(r) for r in conn.execute("""SELECT * FROM kg_concepts WHERE course_id=? AND status='confirmed'
                                           AND canonical_id IS NULL ORDER BY concept_id""", (course_id,))]
    current = next((r for r in rows if r["concept_id"] == concept_id), None)
    if current is None:
        raise CourseGraphError("concept_not_found", 404)

    def terms(row):
        return {normalize_term(row["label"]), *(normalize_term(a["label"]) for a in json.loads(row["aliases"]))}

    normalized = terms(current)
    return [{"concept_id": r["concept_id"], "label": r["label"], "reason": "same_term_or_reviewed_alias"}
            for r in rows if r["concept_id"] != concept_id and normalized & terms(r)][:limit]


def dependency_check(storage, conn, course_id: str, mapping: dict[str, str] | None = None) -> int:
    """Reject cycles on the bounded supported prerequisite graph."""
    concepts = conn.execute("SELECT concept_id,canonical_id FROM kg_concepts WHERE course_id=? AND status='confirmed' LIMIT 10001",
                            (course_id,)).fetchall()
    relations = conn.execute("SELECT * FROM kg_relations WHERE course_id=? AND status='confirmed' AND type IN ('prerequisite','depends_on') LIMIT 30001",
                             (course_id,)).fetchall()
    if len(concepts) > 10_000 or len(relations) > 30_000:
        raise CourseGraphError("dependency_check_limit")
    canonical = {r["concept_id"]: r["canonical_id"] or r["concept_id"] for r in concepts}
    canonical.update(mapping or {})
    graph: dict[str, set[str]] = {}
    degree: dict[str, int] = {}
    cache, self_edges = {}, 0
    for edge in relations:
        if not any(valid_evidence(storage, conn, course_id, e, cache) for e in conn.execute(
                "SELECT * FROM kg_evidence WHERE course_id=? AND relation_id=?", (course_id, edge["relation_id"]))):
            continue
        a, b = canonical.get(edge["from_id"]), canonical.get(edge["to_id"])
        if not a or not b:
            continue
        if a == b:
            self_edges += 1
            continue
        if edge["type"] == "depends_on":
            a, b = b, a
        graph.setdefault(a, set())
        degree.setdefault(a, 0)
        degree.setdefault(b, 0)
        if b not in graph[a]:
            graph[a].add(b)
            degree[b] += 1
    queue = deque(n for n, value in degree.items() if value == 0)
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for target in graph.get(current, ()):
            degree[target] -= 1
            if degree[target] == 0:
                queue.append(target)
    if visited != len(degree):
        raise CourseGraphError("dependency_cycle")
    return self_edges


def _selection(concept_ids, target_id):
    if not 2 <= len(concept_ids) <= 20 or len(set(concept_ids)) != len(concept_ids) or target_id not in concept_ids:
        raise CourseGraphError("invalid_merge_selection", 422)
    return digest({"concept_ids": sorted(concept_ids), "target_id": target_id})


def _merge_context(storage, conn, course_id, concept_ids, target_id):
    selection = _selection(concept_ids, target_id)
    require_course(conn, course_id)
    expanded, labels = set(), []
    for identity in concept_ids:
        row = conn.execute("SELECT * FROM kg_concepts WHERE concept_id=?", (identity,)).fetchone()
        if row is None:
            raise CourseGraphError("concept_not_found", 404)
        if row["course_id"] != course_id:
            raise CourseGraphError("cross_course_merge")
        if row["status"] != "confirmed" or row["canonical_id"] is not None:
            raise CourseGraphError("merge_selection_changed")
        labels.append({"concept_id": identity, "label": row["label"]})
        expanded.add(identity)
        expanded.update(r[0] for r in conn.execute("SELECT concept_id FROM kg_concepts WHERE course_id=? AND canonical_id=?",
                                                   (course_id, identity)))
    if len(expanded) > 10_000:
        raise CourseGraphError("dependency_check_limit")
    ids = {"concepts": sorted(expanded), "relations": [], "evidence": []}
    states = object_states(conn, course_id, ids)
    self_edges = dependency_check(storage, conn, course_id, {identity: target_id for identity in expanded})
    support = [(r["source_id"], r["revision"], r["active"], storage.get_source_revision(r["source_id"]))
               for r in conn.execute("SELECT * FROM kg_course_sources WHERE course_id=? ORDER BY source_id", (course_id,))]
    return {"selection_digest": selection, "ids": ids, "before": states, "self_edge_count": self_edges,
            "concepts": labels, "revision_digest": digest({"states": states, "selection": selection, "support": support})}


def preview_merge(storage, course_id: str, concept_ids: list[str], target_id: str) -> dict[str, Any]:
    with transaction(storage) as conn:
        context = _merge_context(storage, conn, course_id, concept_ids, target_id)
        context["confirmation_token"] = data_actions.issue(conn, "course_graph_merge", course_id, context["revision_digest"])
        return context


def _used_receipt(conn, action, resource, token):
    try:
        return data_actions.check(conn, action, resource, token, None)
    except ValueError:
        return None


def _check_preview(conn, action, resource, token, revision):
    try:
        return data_actions.check(conn, action, resource, token, revision)
    except ValueError:
        raise CourseGraphError("preview_expired_or_changed") from None


def confirm_merge(storage, course_id: str, concept_ids: list[str], target_id: str,
                  confirmation_token: str, request_key: str, confirmed: bool) -> dict[str, Any]:
    request_key_valid(request_key)
    if confirmed is not True:
        raise CourseGraphError("confirmation_required", 422)
    selection = _selection(concept_ids, target_id)
    command = digest({"selection": selection, "token": confirmation_token})
    with transaction(storage) as conn:
        require_course(conn, course_id)
        previous = get_request(conn, course_id, request_key, "merge", command)
        if previous:
            return previous["metadata"]["receipt"]
        used = _used_receipt(conn, "course_graph_merge", course_id, confirmation_token)
        if used:
            if used.get("selection_digest") != selection:
                raise CourseGraphError("preview_selection_changed")
            record_change(conn, course_id, request_key, "merge", command, {"receipt": used, "alias_of": used["operation_id"]})
            return used
        context = _merge_context(storage, conn, course_id, concept_ids, target_id)
        _check_preview(conn, "course_graph_merge", course_id, confirmation_token, context["revision_digest"])
        for identity in context["ids"]["concepts"]:
            conn.execute("UPDATE kg_concepts SET canonical_id=?,revision=revision+1 WHERE course_id=? AND concept_id=?",
                         (None if identity == target_id else target_id, course_id, identity))
        states = object_states(conn, course_id, context["ids"])
        oid = str(uuid4())
        receipt = {"operation_id": oid, "selection_digest": selection,
                   "affected": {"concepts": len(context["ids"]["concepts"])}, "self_edge_count": context["self_edge_count"]}
        record_change(conn, course_id, request_key, "merge", command,
                      {"receipt": receipt, "ids": context["ids"], "before": context["before"], "after": states,
                       "expected": digest(states)}, oid)
        data_actions.finish(conn, "course_graph_merge", course_id, confirmation_token, receipt)
        return receipt


def _operation(conn, course_id, operation_id):
    require_course(conn, course_id)
    row = conn.execute("SELECT rowid AS sequence,* FROM kg_changes WHERE course_id=? AND operation_id=?",
                       (course_id, operation_id)).fetchone()
    if row is None:
        raise CourseGraphError("operation_not_found", 404)
    op = dict(row)
    op["metadata"] = json.loads(op["metadata"])
    if op["kind"] not in {"merge", "review", "remove_source"} or "ids" not in op["metadata"]:
        raise CourseGraphError("operation_not_reversible", 422)
    return op


def _operation_context(storage, conn, course_id, operation_id, action):
    if action not in {"undo", "restore"}:
        raise CourseGraphError("invalid_action", 422)
    op = _operation(conn, course_id, operation_id)
    meta = op["metadata"]
    states = object_states(conn, course_id, meta["ids"])
    if digest(states) != meta["expected"]:
        raise CourseGraphError("operation_conflict")
    affected_ids = {identity for values in meta["ids"].values() for identity in values}
    for later in conn.execute("""SELECT operation_id,metadata FROM kg_changes WHERE course_id=? AND rowid>?
                                 AND kind IN ('merge','review','remove_source') AND status='applied'""",
                              (course_id, op["sequence"])):
        later_meta = json.loads(later["metadata"])
        later_ids = {identity for values in later_meta.get("ids", {}).values() for identity in values}
        later_ids.update(later_meta.get("dependencies", []))
        if not later_meta.get("alias_of") and affected_ids & later_ids:
            raise CourseGraphError("operation_conflict", details={"blocking_operation_id": later["operation_id"]})
    if action == "restore" and op["kind"] == "review":
        cache = {}
        for row in states["evidence"]:
            current = dict(row)
            current["status"] = "confirmed"
            if not valid_evidence(storage, conn, course_id, current, cache):
                raise CourseGraphError("operation_source_unavailable")
    return op, digest({"state": states, "status": op["status"], "action": action, "operation_id": operation_id})


def preview_operation(storage, course_id: str, operation_id: str, action: str) -> dict[str, Any]:
    with transaction(storage) as conn:
        op, revision = _operation_context(storage, conn, course_id, operation_id, action)
        token = data_actions.issue(conn, f"course_graph_{action}", f"{course_id}:{operation_id}", revision)
        return {"operation_id": operation_id, "action": action, "status": op["status"],
                "affected": {k: len(v) for k, v in op["metadata"]["ids"].items()}, "confirmation_token": token}


def transition_operation(storage, course_id: str, operation_id: str, action: str,
                         confirmation_token: str, request_key: str, confirmed: bool) -> dict[str, Any]:
    request_key_valid(request_key)
    if confirmed is not True:
        raise CourseGraphError("confirmation_required", 422)
    command = digest({"operation_id": operation_id, "action": action, "token": confirmation_token})
    with transaction(storage) as conn:
        require_course(conn, course_id)
        previous = get_request(conn, course_id, request_key, "transition", command)
        if previous:
            return previous["metadata"]["receipt"]
        resource, token_action = f"{course_id}:{operation_id}", f"course_graph_{action}"
        used = _used_receipt(conn, token_action, resource, confirmation_token)
        if used:
            record_change(conn, course_id, request_key, "transition", command, {"receipt": used, "target_operation_id": operation_id})
            return used
        op, revision = _operation_context(storage, conn, course_id, operation_id, action)
        _check_preview(conn, token_action, resource, confirmation_token, revision)
        meta = op["metadata"]
        wanted_status = "undone" if action == "undo" else "applied"
        changed = op["status"] != wanted_status
        if changed:
            desired = copy.deepcopy(meta.get("before") if action == "undo" else meta["after"])
            if desired is None:  # review新增对象保留ID，以revoked表达撤销。
                desired = copy.deepcopy(meta["after"])
                for values in desired.values():
                    for state in values:
                        state["status"] = "revoked"
            for state in desired["concepts"]:
                conn.execute("UPDATE kg_concepts SET canonical_id=?,status=?,revision=revision+1 WHERE course_id=? AND concept_id=?",
                             (state["canonical_id"], state["status"], course_id, state["id"]))
            for state in desired["relations"]:
                conn.execute("UPDATE kg_relations SET status=?,revision=revision+1 WHERE course_id=? AND relation_id=?",
                             (state["status"], course_id, state["id"]))
            for state in desired["evidence"]:
                conn.execute("UPDATE kg_evidence SET status=? WHERE course_id=? AND evidence_id=?",
                             (state["status"], course_id, state["id"]))
            for state in desired.get("memberships", []):
                conn.execute("UPDATE kg_course_sources SET active=?,chapter_id=?,revision=revision+1 WHERE course_id=? AND source_id=?",
                             (state["active"], state["chapter_id"], course_id, state["id"]))
                conn.execute("UPDATE kg_courses SET revision=revision+1,updated_at=? WHERE course_id=?", (now_iso(), course_id))
            if op["kind"] == "review":
                for row in conn.execute("SELECT extraction_id,payload FROM kg_extractions WHERE course_id=? AND draft_id=?",
                                        (course_id, meta["draft_id"])):
                    payload = json.loads(row["payload"])
                    for item in payload.get("nodes", []) + payload.get("edges", []):
                        if item["item_id"] in meta["item_ids"]:
                            item["review_status"] = "revoked" if action == "undo" else "confirmed"
                    conn.execute("UPDATE kg_extractions SET payload=? WHERE extraction_id=?",
                                 (json.dumps(payload, ensure_ascii=False), row["extraction_id"]))
            dependency_check(storage, conn, course_id)
            meta["expected"] = digest(object_states(conn, course_id, meta["ids"]))
            conn.execute("UPDATE kg_changes SET status=?,metadata=?,updated_at=? WHERE operation_id=?",
                         (wanted_status, json.dumps(meta, ensure_ascii=False), now_iso(), operation_id))
        receipt = {"operation_id": operation_id, "action": action, "changed": changed,
                   "affected": {k: len(v) if changed else 0 for k, v in meta["ids"].items()}}
        record_change(conn, course_id, request_key, "transition", command, {"receipt": receipt, "target_operation_id": operation_id})
        data_actions.finish(conn, token_action, resource, confirmation_token, receipt)
        return receipt
