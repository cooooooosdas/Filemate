"""Build one detached course read snapshot without per-concept queries."""

import json
from dataclasses import dataclass
from typing import Any

from filemate.course_graph.models import CourseGraphError, digest
from filemate.course_graph.repository import require_course
from filemate.course_graph.workspace_models import (
    SYSTEM_GROUPS,
    WorkspaceFilter,
    WorkspaceGroup,
    WorkspaceNode,
)
from filemate.execution.storage import SQLiteStorage


@dataclass(frozen=True)
class CourseWorkspaceSnapshot:
    """Keep request-local normalized rows after closing the read transaction."""

    course: dict[str, Any]
    graph_digest: str
    chapters: dict[str, dict[str, Any]]
    ancestors: dict[str, tuple[str, ...]]
    sources: dict[str, dict[str, Any]]
    fingerprints: dict[str, str | None]
    concepts: dict[str, dict[str, Any]]
    member_to_root: dict[str, str]
    nodes: dict[str, WorkspaceNode]
    refs: dict[str, list[dict[str, Any]]]
    relations: tuple[dict[str, Any], ...]
    relation_refs: dict[str, list[dict[str, Any]]]
    groups: dict[str, WorkspaceGroup]
    group_members: dict[str, set[str]]


def _chapter_ancestors(chapters: dict[str, dict[str, Any]]) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for cid in chapters:
        trail, seen, current = [], set(), cid
        while current and current not in result:
            if current in seen or current not in chapters:
                raise CourseGraphError("chapter_structure_invalid")
            seen.add(current)
            trail.append(current)
            current = chapters[current]["parent_id"]
        prefix = result.get(current, ())
        for item in reversed(trail):
            prefix = (*prefix, item)
            result[item] = prefix
    return result


def _representatives(concepts: dict[str, dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for mid, member in concepts.items():
        if member["status"] != "confirmed":
            continue
        trail, seen, current = [], set(), mid
        while current not in result:
            row = concepts.get(current)
            if current in seen or row is None or row["status"] != "confirmed":
                raise CourseGraphError("concept_structure_invalid")
            trail.append(current)
            seen.add(current)
            if row["canonical_id"] is None:
                break
            current = row["canonical_id"]
        root = result.get(current, current)
        result.update((item, root) for item in trail)
    return result


def _build_nodes(concepts, member_to_root, evidence, sources):
    members: dict[str, list[str]] = {}
    refs: dict[str, list[dict[str, Any]]] = {}
    relation_refs: dict[str, list[dict[str, Any]]] = {}
    for mid, rid in member_to_root.items():
        members.setdefault(rid, []).append(mid)
    for e in evidence:
        rid = member_to_root.get(e["concept_id"])
        if rid:
            refs.setdefault(rid, []).append(e)
        elif e["relation_id"]:
            relation_refs.setdefault(e["relation_id"], []).append(e)
    nodes: dict[str, WorkspaceNode] = {}
    for rid in sorted(members):
        aliases, seen = [], set()
        for mid in sorted(members[rid]):
            row = concepts[mid]
            candidates = json.loads(row["aliases"])
            if mid != rid:
                candidates = [{"label": row["label"], "origin": "merged"}, *candidates]
            for alias in candidates:
                label, origin = alias.get("label"), alias.get("origin", "user")
                if isinstance(label, str) and label not in seen:
                    seen.add(label)
                    aliases.append({"label": label, "origin": str(origin)})
        source_ids = {e["source_id"] for e in refs.get(rid, [])}
        chapters = {sources[sid]["chapter_id"] or "@unassigned" for sid in source_ids}
        nodes[rid] = {"id": rid, "label": concepts[rid]["label"], "aliases": aliases,
                      "chapter_ids": sorted(chapters) if source_ids else ["@no-source"],
                      "source_count": len(source_ids),
                      "source_status": "available" if source_ids else "no_valid_source",
                      "member_count": len(members[rid])}
    return nodes, refs, relation_refs


def _build_groups(chapters, ancestors, nodes):
    groups: dict[str, WorkspaceGroup] = {
        cid: {"id": cid, "parent_id": row["parent_id"], "title": row["title"],
              "sort_order": row["sort_order"], "concept_count": 0, "child_count": 0}
        for cid, row in chapters.items()
    }
    for i, title in zip(SYSTEM_GROUPS, ("未分组", "无有效来源"), strict=True):
        groups[i] = {"id": i, "parent_id": None, "title": title, "sort_order": 100001,
                     "concept_count": 0, "child_count": 0}
    members: dict[str, set[str]] = {cid: set() for cid in groups}
    for nid, node in nodes.items():
        for cid in node["chapter_ids"]:
            for ancestor in ancestors.get(cid, (cid,)):
                members[ancestor].add(nid)
    for cid, row in chapters.items():
        if row["parent_id"]:
            groups[row["parent_id"]]["child_count"] += 1
    for cid, group in groups.items():
        group["concept_count"] = len(members[cid])
    return groups, members


def load_workspace_snapshot(storage: SQLiteStorage, course_id: str) -> CourseWorkspaceSnapshot:
    """Read graph state and current fingerprints inside a single SQLite snapshot."""
    with storage.read_snapshot() as snapshot:
        return read_workspace_snapshot(snapshot, course_id)


def read_workspace_snapshot(snapshot: SQLiteStorage, course_id: str) -> CourseWorkspaceSnapshot:
    """Share an already-open read transaction with citation range verification."""
    conn = snapshot._conn()
    course = require_course(conn, course_id)
    rows = {}
    for table, key in (("kg_chapters", "chapter_id"), ("kg_concepts", "concept_id"),
                       ("kg_relations", "relation_id"), ("kg_evidence", "evidence_id")):
        rows[table] = [dict(r) for r in conn.execute(
            f"SELECT * FROM {table} WHERE course_id=? ORDER BY {key}", (course_id,))]
    sources = {r["source_id"]: dict(r) for r in conn.execute(
        """SELECT m.*,s.original_name FROM kg_course_sources m JOIN sources s USING(source_id)
           WHERE m.course_id=? ORDER BY m.source_id""", (course_id,))}
    fingerprints = {sid: snapshot.get_source_revision(sid) if row["active"] else None
                    for sid, row in sources.items()}
    graph_digest = digest({"course": course, "rows": rows, "sources": sources, "fingerprints": fingerprints})
    chapters = {r["chapter_id"]: r for r in rows["kg_chapters"]}
    ancestors = _chapter_ancestors(chapters)
    concepts = {r["concept_id"]: r for r in rows["kg_concepts"]}
    member_to_root = _representatives(concepts)
    valid_refs = [e for e in rows["kg_evidence"] if e["status"] == "confirmed"
                  and fingerprints.get(e["source_id"]) is not None
                  and fingerprints[e["source_id"]] == e["source_revision"]]
    nodes, refs, relation_refs = _build_nodes(concepts, member_to_root, valid_refs, sources)
    groups, group_members = _build_groups(chapters, ancestors, nodes)
    return CourseWorkspaceSnapshot(course, graph_digest, chapters, ancestors, sources, fingerprints,
                                   concepts, member_to_root, nodes, refs,
                                   tuple(rows["kg_relations"]), relation_refs, groups, group_members)


def selected_nodes(snapshot: CourseWorkspaceSnapshot, filters: WorkspaceFilter) -> set[str]:
    """Apply chapter descendants and active source membership as an intersection."""
    selected = set(snapshot.nodes)
    if filters.chapter_id is not None:
        if filters.chapter_id not in snapshot.groups:
            raise CourseGraphError("chapter_not_found", 404)
        selected &= snapshot.group_members[filters.chapter_id]
    if filters.source_id is not None:
        source = snapshot.sources.get(filters.source_id)
        if source is None or not source["active"]:
            raise CourseGraphError("source_not_found", 404)
        selected &= {nid for nid, refs in snapshot.refs.items()
                     if any(e["source_id"] == filters.source_id for e in refs)}
    return selected
