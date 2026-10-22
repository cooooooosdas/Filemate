"""Saved literal ranges, not fuzzy quote guesses, authorize source context."""

import importlib
from uuid import uuid4

import pytest

from filemate.course_graph.models import CourseGraphError
from filemate.tests.course_graph.test_workspace_query import (
    pair,  # noqa: F401
    publish_source,
    workspace_case,  # noqa: F401
)


def citation(store, cid, nid, eid):
    return importlib.import_module("filemate.course_graph.workspace_source").get_workspace_citation(store, cid, nid, eid)


@pytest.fixture
def citation_case(workspace_case):  # noqa: F811
    store, _, cid, _ = workspace_case["context"]
    sid = publish_source(workspace_case["context"], "😀" * 2100 + "重复：原句。中间😀。重复：原句。" + "尾" * 2100)
    ref = dict(store._conn().execute("SELECT * FROM kg_evidence WHERE source_id=? AND concept_id IS NOT NULL LIMIT 1", (sid,)).fetchone())
    # 在同一有效资料里设置另一条人工核对过的重复原句，验证保存位置的语义。
    text = store.get_source(sid)["raw_text"]
    quote = "重复：原句"
    start = text.rfind(quote)
    eid = str(uuid4())
    with store._conn() as conn:
        conn.execute("""INSERT INTO kg_evidence(evidence_id,course_id,source_id,source_revision,
                     concept_id,excerpt,char_start,char_end) VALUES(?,?,?,?,?,?,?,?)""",
                     (eid, cid, sid, ref["source_revision"], ref["concept_id"], quote, start, start + len(quote)))
    return workspace_case, sid, ref["concept_id"], eid, quote


def test_unicode_duplicate_quote_uses_saved_range(citation_case):
    case, _, nid, eid, quote = citation_case
    store, _, cid, _ = case["context"]
    result = citation(store, cid, nid, eid)
    assert result["quote"] == quote
    assert result["before"].endswith("中间😀。")
    assert len(result["before"]) <= 2000 and len(result["after"]) <= 2000
    assert result["original_name"] == "extra.txt" and result["page"] is None


def test_source_revision_change_is_not_fuzzy_repaired(citation_case):
    case, sid, nid, eid, _ = citation_case
    store, _, cid, _ = case["context"]
    text = store.get_source(sid)["raw_text"]
    store.save_source(source_id=sid, original_name="updated", source_path="s", raw_text="前缀" + text)
    with pytest.raises(CourseGraphError, match="citation_unavailable") as caught:
        citation(store, cid, nid, eid)
    assert caught.value.status_code == 409


def test_removed_source_is_unavailable(citation_case):
    case, sid, nid, eid, _ = citation_case
    store, _, cid, _ = case["context"]
    with store._conn() as conn:
        conn.execute("UPDATE kg_course_sources SET active=0 WHERE course_id=? AND source_id=?", (cid, sid))
    with pytest.raises(CourseGraphError, match="citation_unavailable"):
        citation(store, cid, nid, eid)


def test_deleted_or_foreign_evidence_is_404(citation_case):
    case, _, nid, eid, _ = citation_case
    store, _, cid, _ = case["context"]
    wrong_node = case["ids"][0]
    with pytest.raises(CourseGraphError) as caught:
        citation(store, cid, wrong_node, eid)
    assert caught.value.status_code == 404
    with store._conn() as conn:
        conn.execute("DELETE FROM kg_evidence WHERE evidence_id=?", (eid,))
    with pytest.raises(CourseGraphError) as caught:
        citation(store, cid, nid, eid)
    assert caught.value.status_code == 404


def test_merged_member_reference_is_valid(workspace_case):  # noqa: F811
    store, _, cid, _ = workspace_case["context"]
    nid = workspace_case["ids"][1]
    eid = store._conn().execute("SELECT evidence_id FROM kg_evidence WHERE concept_id=?", (nid,)).fetchone()[0]
    result = citation(store, cid, nid, eid)
    assert result["requested_id"] == nid and result["resolved_id"] == workspace_case["ids"][0]
    assert result["quote"]


def test_bad_saved_range_is_not_repaired(citation_case):
    case, _, nid, eid, _ = citation_case
    store, _, cid, _ = case["context"]
    with store._conn() as conn:
        conn.execute("UPDATE kg_evidence SET char_start=0 WHERE evidence_id=?", (eid,))
    with pytest.raises(CourseGraphError, match="citation_unavailable"):
        citation(store, cid, nid, eid)
