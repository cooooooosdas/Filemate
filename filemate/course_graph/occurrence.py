"""Symbol-preserving source occurrences, separate from legacy graph hints."""

import json
from uuid import NAMESPACE_URL, uuid5

from filemate.course_graph.models import CourseGraphError, digest, normalize_term
from filemate.execution.storage import _knowledge_identity


def occurrence_id(course_id, source_id, source_revision, original_label):
    """Keep immutable original terms distinct regardless of editable display labels."""
    return uuid5(NAMESPACE_URL, "course-occurrence:" + digest(
        [course_id, source_id, source_revision, normalize_term(original_label)])).hex


def original_term(conn, evidence):
    """Read original candidate identity for both current and B1 random evidence IDs."""
    row = conn.execute("SELECT payload FROM kg_extractions WHERE extraction_id=? AND course_id=?",
                       (evidence["extraction_id"], evidence["course_id"])).fetchone()
    if row is None:
        return None
    for item in json.loads(row[0]).get("nodes", []):
        term = item.get("original", {}).get("label")
        if not isinstance(term, str):
            continue
        expected = occurrence_id(evidence["course_id"], evidence["source_id"], evidence["source_revision"], term)
        if item.get("published_id") == evidence["concept_id"] or expected == evidence["evidence_id"]:
            return term
    return None


def find_occurrence(conn, course_id, source, parsed):
    """Reuse only an exact original occurrence, never a lossy legacy key alone."""
    eid = occurrence_id(course_id, source["source_id"], source["source_revision"], parsed["label"])
    row = conn.execute("SELECT * FROM kg_evidence WHERE evidence_id=? AND course_id=?", (eid, course_id)).fetchone()
    if row:
        return row
    for row in conn.execute("""SELECT * FROM kg_evidence WHERE course_id=? AND source_id=?
                               AND source_revision=? AND concept_id IS NOT NULL""",
                            (course_id, source["source_id"], source["source_revision"])):
        term = original_term(conn, row)
        if term is not None and normalize_term(term) == normalize_term(parsed["label"]):
            return row
        if term is None and row["legacy_node_id"] == parsed["legacy_node_id"]:
            raise CourseGraphError("legacy_mapping_unverified")
    return None


def legacy_hint(conn, course_id, source, parsed, *, apply_changes=True):
    """Mark ambiguous hints explicitly without changing old graph identities."""
    key = parsed["legacy_node_id"]
    ambiguous = parsed.get("legacy_mapping_ambiguous", False)
    for row in conn.execute("""SELECT * FROM kg_evidence WHERE course_id=? AND source_id=?
                               AND source_revision=? AND concept_id IS NOT NULL""",
                            (course_id, source["source_id"], source["source_revision"])).fetchall():
        term = original_term(conn, row)
        old_key = _knowledge_identity({"knowledge_point": term}, source_id=source["source_id"], artifact_id="")[0] if term else row["legacy_node_id"]
        if term is None or (old_key == key and normalize_term(term) != normalize_term(parsed["label"])):
            ambiguous = True
            if apply_changes:
                conn.execute("UPDATE kg_evidence SET legacy_node_id=NULL WHERE evidence_id=?", (row["evidence_id"],))
    parsed["legacy_mapping_ambiguous"] = ambiguous
    return None if ambiguous else key
