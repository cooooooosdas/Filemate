"""Verify exact current-source citation context without fuzzy relocation."""

from filemate.course_graph.models import CourseGraphError
from filemate.course_graph.workspace_canvas import resolve_concept
from filemate.course_graph.workspace_models import WorkspaceCitation
from filemate.course_graph.workspace_snapshot import read_workspace_snapshot
from filemate.execution.storage import SQLiteStorage


def get_workspace_citation(storage: SQLiteStorage, course_id: str, concept_id: str,
                           evidence_id: str) -> WorkspaceCitation:
    """Return bounded Unicode context after membership, version and literal checks."""
    with storage.read_snapshot() as reader:
        snapshot = read_workspace_snapshot(reader, course_id)
        resolved = resolve_concept(snapshot, concept_id)
        e = reader._conn().execute("SELECT * FROM kg_evidence WHERE course_id=? AND evidence_id=?",
                                  (course_id, evidence_id)).fetchone()
        if e is None or e["status"] != "confirmed" or snapshot.member_to_root.get(e["concept_id"]) != resolved:
            raise CourseGraphError("evidence_not_found", 404)
        source = reader.get_source(e["source_id"])
        current = snapshot.fingerprints.get(e["source_id"])
        if source is None or current is None or current != e["source_revision"]:
            raise CourseGraphError("citation_unavailable")
        text = source.get("raw_text") or ""
        start, end = e["char_start"], e["char_end"]
        if not 0 <= start < end <= len(text) or text[start:end] != e["excerpt"]:
            raise CourseGraphError("citation_unavailable")
        if e["chunk_id"]:
            chunk = reader.get_source_chunk(e["chunk_id"])
            if chunk is None or chunk["source_id"] != e["source_id"]:
                raise CourseGraphError("citation_unavailable")
        return {"course_id": course_id, "graph_digest": snapshot.graph_digest,
                "requested_id": concept_id, "resolved_id": resolved,
                "evidence_id": evidence_id, "source_id": e["source_id"],
                "original_name": source["original_name"], "page": e["page"], "chunk_id": e["chunk_id"],
                "before": text[max(0, start-2000):start], "quote": text[start:end], "after": text[end:end+2000]}
