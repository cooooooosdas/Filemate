"""Paged navigation and literal search across an entire course snapshot."""

from typing import Any

from filemate.course_graph.models import CourseGraphError
from filemate.course_graph.workspace_models import (
    WorkspaceConceptPage,
    WorkspaceFilter,
    WorkspaceNavigation,
    validate_page,
)
from filemate.course_graph.workspace_snapshot import load_workspace_snapshot, selected_nodes
from filemate.execution.storage import SQLiteStorage


def get_workspace(storage: SQLiteStorage, course_id: str, *, parent_id: str | None = None,
                  group_limit: int = 200, group_offset: int = 0, source_limit: int = 50,
                  source_offset: int = 0) -> WorkspaceNavigation:
    """Page groups and sources without expanding the full concept graph."""
    validate_page(group_limit, group_offset)
    validate_page(source_limit, source_offset)
    snapshot = load_workspace_snapshot(storage, course_id)
    if parent_id is not None and parent_id != "@root" and parent_id not in snapshot.chapters:
        raise CourseGraphError("chapter_not_found", 404)
    groups = sorted(snapshot.groups.values(), key=lambda g: (g["sort_order"], g["id"]))
    if parent_id is not None:
        groups = [g for g in groups if g["parent_id"] == (None if parent_id == "@root" else parent_id)]
    sources = [{"source_id": r["source_id"], "original_name": r["original_name"],
                "chapter_id": r["chapter_id"], "active": bool(r["active"])} for r in snapshot.sources.values()]
    return {"course_id": course_id, "name": snapshot.course["name"], "graph_digest": snapshot.graph_digest,
            "groups": groups[group_offset:group_offset + group_limit], "group_total": len(groups),
            "group_limit": group_limit, "group_offset": group_offset,
            "sources": sources[source_offset:source_offset + source_limit], "source_total": len(sources),
            "source_limit": source_limit, "source_offset": source_offset, "total_concepts": len(snapshot.nodes)}


def get_chapter_path(storage: SQLiteStorage, course_id: str, chapter_id: str) -> dict[str, Any]:
    """Resolve the real ancestor path without guessing unloaded parents."""
    snapshot = load_workspace_snapshot(storage, course_id)
    if chapter_id not in snapshot.ancestors:
        raise CourseGraphError("chapter_not_found", 404)
    return {"course_id": course_id, "graph_digest": snapshot.graph_digest,
            "items": [snapshot.groups[cid] for cid in snapshot.ancestors[chapter_id]]}


def list_workspace_concepts(storage: SQLiteStorage, course_id: str, *, filters: WorkspaceFilter,
                            q: str = "", limit: int = 50, offset: int = 0) -> WorkspaceConceptPage:
    """Search representative and member labels without removing term symbols."""
    validate_page(limit, offset)
    if not isinstance(q, str) or len(q) > 160:
        raise CourseGraphError("invalid_query", 422)
    snapshot = load_workspace_snapshot(storage, course_id)
    selected = selected_nodes(snapshot, filters)
    results = []
    needle = q.casefold()
    for nid in sorted(selected):
        node = snapshot.nodes[nid]
        labels = [node["label"], *(a["label"] for a in node["aliases"])]
        matched = next((label for label in labels if needle in label.casefold()), None)
        if matched is not None:
            results.append({**node, "matched_label": matched})
    return {"course_id": course_id, "graph_digest": snapshot.graph_digest,
            "items": results[offset:offset + limit], "total": len(results), "limit": limit, "offset": offset}
