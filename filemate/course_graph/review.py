"""Persist human choices and atomically publish only checked source evidence."""

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from filemate.course_graph.drafts import DraftService
from filemate.course_graph.extraction import validate_candidates
from filemate.course_graph.models import CourseGraphError, ItemDecision, digest, request_key_valid
from filemate.course_graph.occurrence import find_occurrence, legacy_hint, occurrence_id
from filemate.course_graph.repository import get_request, record_change, require_course, transaction
from filemate.execution import data_actions
from filemate.execution.storage import SQLiteStorage


def _reader(storage: SQLiteStorage) -> DraftService:
    return DraftService(storage, lambda: None, lambda: datetime.now(timezone.utc))


def _items(source):
    return source["payload"].get("nodes", []) + source["payload"].get("edges", [])


def save_decisions(storage: SQLiteStorage, course_id: str, draft_id: str, expected_digest: str,
                   decisions: list[ItemDecision]) -> dict[str, Any]:
    if not 1 <= len(decisions) <= 2000 or len({d.item_id for d in decisions}) != len(decisions):
        raise CourseGraphError("invalid_decisions", 422)
    with transaction(storage) as conn:
        snap = _reader(storage).read_snapshot(conn, course_id, draft_id)
        if snap["revision_digest"] != expected_digest:
            raise CourseGraphError("revision_conflict")
        indexed = {n["item_id"]: (source, n) for source in snap["sources"] for n in _items(source)}
        touched = set()
        for decision in decisions:
            if decision.item_id not in indexed:
                raise CourseGraphError("candidate_not_found", 404)
            source, item = indexed[decision.item_id]
            if item.get("review_status") in {"confirmed", "revoked"}:
                raise CourseGraphError("candidate_already_published")
            if any(not 1 <= len(a.strip()) <= 120 for a in decision.aliases):
                raise CourseGraphError("invalid_alias", 422)
            item["decision"] = decision.model_dump()
            item["review_status"] = "rejected" if decision.verdict == "reject" else "pending"
            touched.add(source["source_id"])
        for source in snap["sources"]:
            if source["source_id"] in touched:
                conn.execute("UPDATE kg_extractions SET payload=? WHERE extraction_id=?",
                             (json.dumps(source["payload"], ensure_ascii=False), source["extraction_id"]))
        return _reader(storage).read_snapshot(conn, course_id, draft_id)


def _prepare(storage, conn, course_id, draft_id):
    snap = _reader(storage).read_snapshot(conn, course_id, draft_id)
    chosen = []
    selected_terms = set()
    for source in snap["sources"]:
        selected = [n for n in _items(source) if isinstance(n["decision"], dict)
                    and n["decision"]["verdict"] in {"accept", "revise"}
                    and n.get("review_status") not in {"confirmed", "revoked"}]
        if not selected:
            continue
        if source["status"] not in {"ready", "partial"} or not source["source_current"]:
            raise CourseGraphError("source_changed")
        raw = {kind: [dict(n["original"]) for n in source["payload"].get(kind, [])] for kind in ("nodes", "edges")}
        for index, item in enumerate(source["payload"].get("edges", [])):
            choice = item["decision"]
            if isinstance(choice, dict):
                for field, option in (("from", "from_label"), ("to", "to_label"), ("relation", "relation")):
                    if choice.get(option) is not None:
                        raw["edges"][index][field] = choice[option]
        document = storage.get_source(source["source_id"])
        fresh = validate_candidates(raw, document["raw_text"], source["source_id"], storage.list_source_chunks(source["source_id"]))
        for kind in ("nodes", "edges"):
            for old, validated in zip(source["payload"].get(kind, []), fresh[kind], strict=True):
                if old not in selected:
                    continue
                if old["validation"] == "invalid" or validated["validation"] == "invalid":
                    raise CourseGraphError("invalid_candidate", 422)
                choice = old["decision"]
                if validated["validation"] == "needs_semantic_review" and not choice["semantic_checked"]:
                    raise CourseGraphError("semantic_check_required", 422)
                if kind == "nodes":
                    legacy_hint(conn, course_id, source, validated["parsed"], apply_changes=False)
                chosen.append((source, old, validated["parsed"], choice))
                if kind == "nodes":
                    selected_terms.add((source["source_id"], validated["parsed"]["label"]))
    if not chosen:
        raise CourseGraphError("no_selected_candidates", 422)
    for source, item, parsed, _ in chosen:
        if item["kind"] != "edge":
            continue
        for term in (parsed["from"], parsed["to"]):
            if (source["source_id"], term) in selected_terms:
                continue
            node = next((n for n in source["payload"]["nodes"] if n.get("parsed") and n["parsed"]["label"] == term), None)
            existing = find_occurrence(conn, course_id, source, node["parsed"]) if node else None
            concept = conn.execute("SELECT status FROM kg_concepts WHERE concept_id=?",
                                   (existing["concept_id"],)).fetchone() if existing else None
            if not existing or existing["status"] != "confirmed" or not concept or concept[0] != "confirmed":
                raise CourseGraphError("endpoint_not_confirmed", 422)
    return snap, chosen


def preview_review(storage: SQLiteStorage, course_id: str, draft_id: str) -> dict[str, Any]:
    with transaction(storage) as conn:
        snap, selected = _prepare(storage, conn, course_id, draft_id)
        token = data_actions.issue(conn, "course_graph_review", f"{course_id}:{draft_id}", snap["revision_digest"])
        return {"confirmation_token": token, "revision_digest": snap["revision_digest"],
                "nodes": sum(item["kind"] == "node" for _, item, _, _ in selected),
                "relations": sum(item["kind"] == "edge" for _, item, _, _ in selected),
                "items": [{"source_id": s["source_id"], "item_id": n["item_id"], "kind": n["kind"],
                           "parsed": p, "decision": d} for s, n, p, d in selected]}


def object_states(conn, course_id: str, ids: dict[str, list[str]]) -> dict[str, list[dict[str, Any]]]:
    """Read only inverse metadata, never labels, quotations or learning records."""
    tables = {"concepts": ("kg_concepts", "concept_id", "status,revision,canonical_id"),
              "relations": ("kg_relations", "relation_id", "status,revision"),
              "evidence": ("kg_evidence", "evidence_id", "status,source_id,source_revision")}
    if "memberships" in ids:
        tables["memberships"] = ("kg_course_sources", "source_id", "active,revision,chapter_id")
    result = {}
    for kind, (table, pk, columns) in tables.items():
        result[kind] = []
        for identity in sorted(ids.get(kind, [])):
            row = conn.execute(f"SELECT {pk} AS id,{columns} FROM {table} WHERE course_id=? AND {pk}=?",
                               (course_id, identity)).fetchone()
            if row is None:
                raise CourseGraphError("operation_target_unavailable")
            result[kind].append(dict(row))
    return result


def _evidence(conn, course_id, source, parsed, target, kind):
    eid = (occurrence_id(course_id, source["source_id"], source["source_revision"], parsed["label"])
           if kind == "node" else str(uuid4()))
    legacy = legacy_hint(conn, course_id, source, parsed) if kind == "node" else None
    conn.execute("""INSERT INTO kg_evidence(evidence_id,course_id,source_id,source_revision,concept_id,relation_id,
                    legacy_node_id,excerpt,chunk_id,page,char_start,char_end,extraction_id)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (eid, course_id, source["source_id"], source["source_revision"],
                  target if kind == "node" else None, target if kind == "edge" else None,
                  legacy, parsed["excerpt"],
                  parsed["chunk_id"], parsed["page"], parsed["char_start"], parsed["char_end"], source["extraction_id"]))
    return eid


def confirm_review(storage: SQLiteStorage, course_id: str, draft_id: str, request_key: str,
                   confirmation_token: str, confirmed: bool) -> dict[str, Any]:
    request_key_valid(request_key)
    if confirmed is not True:
        raise CourseGraphError("confirmation_required", 422)
    command = digest({"draft_id": draft_id, "confirmation_token": confirmation_token})
    with transaction(storage) as conn:
        require_course(conn, course_id)
        previous = get_request(conn, course_id, request_key, "review", command)
        if previous:
            return previous["metadata"]["receipt"]
        # 已完成token的回执可在候选已标记确认之后读取。
        preview_row = conn.execute("SELECT revision FROM data_action_previews WHERE token_hash=?",
                                   (data_actions.digest(confirmation_token),)).fetchone()
        try:
            receipt = data_actions.check(conn, "course_graph_review", f"{course_id}:{draft_id}",
                                         confirmation_token, None)
        except ValueError:
            receipt = None
        if receipt:
            record_change(conn, course_id, request_key, "review", command, {"receipt": receipt, "alias_of": receipt["operation_id"]})
            return receipt
        snap, selected = _prepare(storage, conn, course_id, draft_id)
        if preview_row is None:
            raise CourseGraphError("preview_required")
        try:
            data_actions.check(conn, "course_graph_review", f"{course_id}:{draft_id}", confirmation_token, snap["revision_digest"])
        except ValueError:
            raise CourseGraphError("preview_expired_or_changed") from None
        ids: dict[str, list[str]] = {"concepts": [], "relations": [], "evidence": []}
        published_nodes = {}
        dependencies = set()
        for source, item, parsed, decision in selected:
            if item["kind"] != "node":
                continue
            existing = find_occurrence(conn, course_id, source, parsed)
            if existing:
                if existing["status"] != "confirmed":
                    raise CourseGraphError("occurrence_revoked_use_restore")
                nid = existing["concept_id"]
            else:
                nid = str(uuid4())
                aliases = [{"label": a, "origin": "source", "source_id": source["source_id"]} for a in parsed["aliases"]]
                aliases.extend({"label": a, "origin": "user"} for a in decision["aliases"])
                if len(aliases) > 20:
                    raise CourseGraphError("too_many_aliases", 422)
                conn.execute("INSERT INTO kg_concepts(concept_id,course_id,label,aliases) VALUES(?,?,?,?)",
                             (nid, course_id, decision["label"] or parsed["label"], json.dumps(aliases, ensure_ascii=False)))
                ids["concepts"].append(nid)
                ids["evidence"].append(_evidence(conn, course_id, source, parsed, nid, "node"))
            published_nodes[(source["source_id"], parsed["label"])] = nid
            item["parsed"]["legacy_mapping_ambiguous"] = parsed.get("legacy_mapping_ambiguous", False)
            dependencies.add(nid)
            item["review_status"], item["published_id"] = "confirmed", nid
        for source, item, parsed, _ in selected:
            if item["kind"] != "edge":
                continue
            endpoints = []
            for term in (parsed["from"], parsed["to"]):
                nid = published_nodes.get((source["source_id"], term))
                if nid is None:
                    node = next(n for n in source["payload"]["nodes"] if n.get("parsed") and n["parsed"]["label"] == term)
                    nid = find_occurrence(conn, course_id, source, node["parsed"])["concept_id"]
                endpoints.append(nid)
                dependencies.add(nid)
            old = conn.execute("""SELECT r.relation_id FROM kg_relations r JOIN kg_evidence e USING(relation_id)
                                  WHERE r.course_id=? AND r.from_id=? AND r.to_id=? AND r.type=?
                                  AND e.source_id=? AND e.source_revision=? AND e.excerpt=? AND e.status='confirmed'
                                  AND r.status='confirmed' LIMIT 1""",
                               (course_id, *endpoints, parsed["relation"], source["source_id"], source["source_revision"], parsed["excerpt"])).fetchone()
            rid = old[0] if old else str(uuid4())
            if not old:
                conn.execute("INSERT INTO kg_relations(relation_id,course_id,from_id,to_id,type) VALUES(?,?,?,?,?)",
                             (rid, course_id, *endpoints, parsed["relation"]))
                ids["relations"].append(rid)
                ids["evidence"].append(_evidence(conn, course_id, source, parsed, rid, "edge"))
            item["review_status"], item["published_id"] = "confirmed", rid
        touched = {s["source_id"]: s for s, _, _, _ in selected}
        for source in touched.values():
            conn.execute("UPDATE kg_extractions SET payload=? WHERE extraction_id=?",
                         (json.dumps(source["payload"], ensure_ascii=False), source["extraction_id"]))
        from filemate.course_graph.fusion import dependency_check

        dependency_check(storage, conn, course_id)
        oid = str(uuid4())
        receipt = {"operation_id": oid, "affected": {k: len(v) for k, v in ids.items()}}
        states = object_states(conn, course_id, ids)
        record_change(conn, course_id, request_key, "review", command,
                      {"receipt": receipt, "ids": ids, "after": states, "expected": digest(states),
                       "draft_id": draft_id, "dependencies": sorted(dependencies),
                       "item_ids": [n["item_id"] for _, n, _, _ in selected]}, oid)
        data_actions.finish(conn, "course_graph_review", f"{course_id}:{draft_id}", confirmation_token, receipt)
        return receipt
