"""Bounded course canvases and paged details from canonical read snapshots."""

from filemate.course_graph.models import CourseGraphError
from filemate.course_graph.workspace_models import (
    WorkspaceCanvas,
    WorkspaceDetail,
    WorkspaceFilter,
    WorkspaceRelation,
    validate_page,
)
from filemate.course_graph.workspace_snapshot import (
    CourseWorkspaceSnapshot,
    load_workspace_snapshot,
    selected_nodes,
)
from filemate.execution.storage import SQLiteStorage


def supported_relations(snapshot: CourseWorkspaceSnapshot, selected: set[str],
                        filters: WorkspaceFilter) -> list[WorkspaceRelation]:
    """Deduplicate only relations with current evidence and supported endpoints."""
    edges: dict[tuple[str, str, str], WorkspaceRelation] = {}
    for row in snapshot.relations:
        a, b = snapshot.member_to_root.get(row["from_id"]), snapshot.member_to_root.get(row["to_id"])
        if row["status"] != "confirmed" or a == b or a not in selected or b not in selected:
            continue
        if filters.relations is not None and row["type"] not in filters.relations:
            continue
        refs = snapshot.relation_refs.get(row["relation_id"], [])
        if not refs or not snapshot.nodes[a]["source_count"] or not snapshot.nodes[b]["source_count"]:
            continue
        key = (a, b, row["type"])
        if key not in edges:
            edges[key] = {"id": row["relation_id"], "from": a, "to": b, "relation": row["type"],
                          "relation_ids": [], "evidence_count": 0}
        edges[key]["relation_ids"].append(row["relation_id"])
        edges[key]["evidence_count"] += len(refs)
    return [edges[key] for key in sorted(edges)]


def resolve_concept(snapshot: CourseWorkspaceSnapshot, concept_id: str) -> str:
    """Resolve original IDs only within the current confirmed course."""
    resolved = snapshot.member_to_root.get(concept_id)
    if resolved is None:
        raise CourseGraphError("concept_not_found", 404)
    return resolved


def get_workspace_canvas(storage: SQLiteStorage, course_id: str, *, filters: WorkspaceFilter,
                         focus: str | None = None, limit: int = 100, group_limit: int = 20,
                         group_offset: int = 0) -> WorkspaceCanvas:
    """Return a group overview or a bounded concept neighborhood without silent truncation."""
    validate_page(limit, 0, 100)
    validate_page(group_limit, group_offset, 20)
    snapshot = load_workspace_snapshot(storage, course_id)
    selected = selected_nodes(snapshot, filters)
    resolved = resolve_concept(snapshot, focus) if focus is not None else None
    if resolved is not None and resolved not in selected:
        raise CourseGraphError("focus_outside_filter")
    edges = supported_relations(snapshot, selected, filters)
    result: WorkspaceCanvas = {
        "course_id": course_id, "graph_digest": snapshot.graph_digest,
        "mode": "concepts", "nodes": [], "edges": [], "groups": [], "group_edges": [],
        "total_concepts": len(selected), "total_edges": len(edges), "truncated": False,
        "node_has_more": False, "edge_has_more": False, "group_total": 0,
        "group_offset": group_offset, "group_limit": group_limit,
        "requested_id": focus, "resolved_id": resolved,
    }
    if (focus is None and filters.chapter_id is None and filters.source_id is None
            and (len(snapshot.chapters) > 1 or len(selected) > 100)):
        result["mode"] = "groups"
        groups = sorted(snapshot.groups.values(), key=lambda g: (g["sort_order"], g["id"]))
        result["groups"] = groups[group_offset:group_offset + group_limit]
        result["group_total"] = len(groups)
        shown = {g["id"] for g in result["groups"]}
        summary: dict[tuple[str, str], set[str]] = {}
        for edge in edges:
            for a in snapshot.nodes[edge["from"]]["chapter_ids"]:
                for b in snapshot.nodes[edge["to"]]["chapter_ids"]:
                    if a != b and a in shown and b in shown:
                        summary.setdefault((a, b), set()).add(edge["id"])
        result["group_edges"] = [{"from_group": a, "to_group": b, "relation_count": len(ids)}
                                 for (a, b), ids in sorted(summary.items())][:300]
        result["edge_has_more"] = len(summary) > 300
        result["truncated"] = group_offset + group_limit < len(groups) or result["edge_has_more"]
        return result
    candidates = selected
    if resolved is not None:
        candidates = {resolved}
        for edge in edges:
            if resolved == edge["from"]:
                candidates.add(edge["to"])
            elif resolved == edge["to"]:
                candidates.add(edge["from"])
    ordered = ([resolved] if resolved else []) + sorted(candidates - ({resolved} if resolved else set()))
    visible = set(ordered[:limit])
    visible_edges = [e for e in edges if e["from"] in visible and e["to"] in visible]
    result["nodes"] = [snapshot.nodes[nid] for nid in ordered[:limit]]
    result["edges"] = visible_edges[:300]
    result["node_has_more"] = len(candidates) > limit
    result["edge_has_more"] = len(visible_edges) > 300
    result["truncated"] = result["node_has_more"] or result["edge_has_more"]
    return result


def get_workspace_detail(storage: SQLiteStorage, course_id: str, concept_id: str, *,
                         limit: int = 50, offset: int = 0) -> WorkspaceDetail:
    """Page current source references independently of the canvas page."""
    validate_page(limit, offset)
    snapshot = load_workspace_snapshot(storage, course_id)
    resolved = resolve_concept(snapshot, concept_id)
    refs = snapshot.refs.get(resolved, [])
    return {"course_id": course_id, "graph_digest": snapshot.graph_digest, "requested_id": concept_id,
            "resolved_id": resolved, "node": snapshot.nodes[resolved], "total_refs": len(refs),
            "limit": limit, "offset": offset,
            "source_refs": [{"evidence_id": e["evidence_id"], "source_id": e["source_id"],
                             "original_name": snapshot.sources[e["source_id"]]["original_name"],
                             "excerpt": e["excerpt"], "page": e["page"], "chunk_id": e["chunk_id"]}
                            for e in refs[offset:offset + limit]]}
