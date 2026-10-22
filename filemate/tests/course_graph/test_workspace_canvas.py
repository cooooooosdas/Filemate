"""Bounded canvas behavior, including explicitly constructed scale fixtures."""

import importlib
from uuid import uuid4

import pytest

from filemate.course_graph.models import CourseGraphError
from filemate.course_graph.repository import CourseGraphRepository
from filemate.tests.course_graph.test_workspace_query import (
    filters,
    pair,  # noqa: F401
    query,
    workspace_case,  # noqa: F401
)


def canvas():
    return importlib.import_module("filemate.course_graph.workspace_canvas")


def seed_scale(store, size=10000):
    """Construct synthetic graph shape, without claiming extraction quality."""
    repo = CourseGraphRepository(store)
    cid = repo.create_course("合成性能构造", uuid4().hex)["course_id"]
    sid = store.save_source(original_name="synthetic.txt", source_path="synthetic.txt", raw_text="合成引文")
    repo.attach_sources(cid, [sid], None, 0)
    revision = store.get_source_revision(sid)
    with store._conn() as conn:
        conn.executemany("INSERT INTO kg_concepts(concept_id,course_id,label) VALUES(?,?,?)",
                         [(f"n{i:05}", cid, f"concept {i}") for i in range(size)])
        conn.executemany("""INSERT INTO kg_evidence(evidence_id,course_id,source_id,source_revision,
                         concept_id,excerpt,char_start,char_end) VALUES(?,?,?,?,?,'合成引文',0,4)""",
                         [(f"e{i:05}", cid, sid, revision, f"n{i:05}") for i in range(size)])
        # 最后一页节点连接151个跨页邻居，验证focus不能被首屏分页限制。
        edges = [(f"r{i:05}", cid, f"n{size-1:05}", f"n{i:05}", "related_to") for i in range(min(size-1, 151))]
        conn.executemany("INSERT INTO kg_relations(relation_id,course_id,from_id,to_id,type) VALUES(?,?,?,?,?)", edges)
        conn.executemany("""INSERT INTO kg_evidence(evidence_id,course_id,source_id,source_revision,
                         relation_id,excerpt,char_start,char_end) VALUES(?,?,?,?,?,'合成引文',0,4)""",
                         [(f"re{i:05}", cid, sid, revision, row[0]) for i, row in enumerate(edges)])
    return repo, cid, sid


@pytest.fixture
def large_workspace(course_store):
    repo, cid, sid = seed_scale(course_store)
    return course_store, repo, cid, sid


def test_focus_outside_first_page_is_kept(large_workspace):
    store, _, cid, _ = large_workspace
    result = canvas().get_workspace_canvas(store, cid, filters=filters(), focus="n09999")
    assert result["resolved_id"] == "n09999"
    assert "n09999" in {n["id"] for n in result["nodes"]}
    assert len(result["nodes"]) == 100 and len(result["edges"]) <= 300
    assert result["truncated"] is True and result["node_has_more"] is True
    last = query().list_workspace_concepts(store, cid, filters=filters(), offset=9950)
    assert last["total"] == 10000 and len(last["items"]) == 50


def test_groups_are_not_semantic_nodes(workspace_case):  # noqa: F811
    store, _, cid, _ = workspace_case["context"]
    result = canvas().get_workspace_canvas(store, cid, filters=filters())
    assert result["mode"] == "groups" and result["nodes"] == [] and result["edges"] == []
    assert result["total_concepts"] == 3
    assert workspace_case["parent"] in {g["id"] for g in result["groups"]}


def test_cross_group_summary_requires_valid_evidence(workspace_case):  # noqa: F811
    store, _, cid, sid = workspace_case["context"]
    result = canvas().get_workspace_canvas(store, cid, filters=filters())
    assert any(e["from_group"] == workspace_case["child"] and e["to_group"] == workspace_case["parent"]
               for e in result["group_edges"])
    store.save_source(source_id=sid, original_name="new", source_path="s.txt", raw_text="新正文")
    assert canvas().get_workspace_canvas(store, cid, filters=filters())["group_edges"] == []


@pytest.mark.parametrize("relations", [(), ("application",)])
def test_relation_filter_retains_isolated_nodes(workspace_case, relations):  # noqa: F811
    store, _, cid, _ = workspace_case["context"]
    result = canvas().get_workspace_canvas(store, cid, filters=filters(
        chapter_id=workspace_case["parent"], relations=relations))
    assert len(result["nodes"]) == 3 and result["edges"] == []


def test_zero_relation_selection_hides_edges_only(workspace_case):  # noqa: F811
    store, _, cid, _ = workspace_case["context"]
    a = canvas().get_workspace_canvas(store, cid, filters=filters(chapter_id=workspace_case["parent"]))
    b = canvas().get_workspace_canvas(store, cid, filters=filters(
        chapter_id=workspace_case["parent"], relations=()))
    assert a["nodes"] == b["nodes"] and a["edges"] and not b["edges"]


def test_group_canvas_pages_twenty_at_a_time(large_workspace):
    store, repo, cid, _ = large_workspace
    for i in range(45):
        repo.put_chapter(cid, str(uuid4()), f"章{i}", None, i, 0)
    a = canvas().get_workspace_canvas(store, cid, filters=filters())
    b = canvas().get_workspace_canvas(store, cid, filters=filters(), group_offset=20)
    assert len(a["groups"]) == len(b["groups"]) == 20
    assert a["group_total"] == 47
    assert not ({g["id"] for g in a["groups"]} & {g["id"] for g in b["groups"]})
    assert a["truncated"] is True


def test_merged_original_id_resolves_representative(workspace_case):  # noqa: F811
    store, _, cid, _ = workspace_case["context"]
    original, root = workspace_case["ids"][1], workspace_case["ids"][0]
    result = canvas().get_workspace_canvas(store, cid, filters=filters(), focus=original)
    detail = canvas().get_workspace_detail(store, cid, original)
    assert result["requested_id"] == detail["requested_id"] == original
    assert result["resolved_id"] == detail["resolved_id"] == root
    assert detail["node"]["source_count"] == 2
    assert detail["graph_digest"] == result["graph_digest"]


def test_focus_outside_filter_returns_conflict(workspace_case):  # noqa: F811
    store, _, cid, _ = workspace_case["context"]
    queue = next(n["id"] for n in query().list_workspace_concepts(store, cid, filters=filters())["items"]
                 if n["label"] == "队列")
    with pytest.raises(CourseGraphError, match="focus_outside_filter") as caught:
        canvas().get_workspace_canvas(store, cid, filters=filters(chapter_id=workspace_case["child"]), focus=queue)
    assert caught.value.status_code == 409


def test_no_source_relations_are_suppressed(workspace_case):  # noqa: F811
    store, _, cid, sid = workspace_case["context"]
    store.save_source(source_id=sid, original_name="new", source_path="s", raw_text="changed")
    result = canvas().get_workspace_canvas(store, cid, filters=filters(chapter_id="@no-source"))
    assert len(result["nodes"]) == 2 and result["edges"] == []


def test_detail_refs_are_paged(workspace_case):  # noqa: F811
    store, _, cid, _ = workspace_case["context"]
    nid = workspace_case["ids"][0]
    a = canvas().get_workspace_detail(store, cid, nid, limit=1)
    b = canvas().get_workspace_detail(store, cid, nid, limit=1, offset=1)
    assert a["total_refs"] == b["total_refs"] == 2
    assert a["source_refs"] != b["source_refs"]
    assert all(r["original_name"] and r["excerpt"] for r in a["source_refs"] + b["source_refs"])
    assert "merge_candidates" not in a


def test_edge_budget_applies_after_deduplication(course_store):
    _, cid, sid = seed_scale(course_store, 100)
    revision = course_store.get_source_revision(sid)
    with course_store._conn() as conn:
        for i in range(20):
            for j in range(20, 40):
                rid = f"dense-{i}-{j}"
                conn.execute("INSERT INTO kg_relations(relation_id,course_id,from_id,to_id,type) VALUES(?,?,?,?,?)",
                             (rid, cid, f"n{i:05}", f"n{j:05}", "related_to"))
                conn.execute("""INSERT INTO kg_evidence(evidence_id,course_id,source_id,source_revision,
                             relation_id,excerpt,char_start,char_end) VALUES(?,?,?,?,?,'合成引文',0,4)""",
                             (f"e-{rid}", cid, sid, revision, rid))
    result = canvas().get_workspace_canvas(course_store, cid, filters=filters(chapter_id="@unassigned"))
    assert len(result["edges"]) == 300 and result["edge_has_more"] is True
    assert result["total_edges"] > 300
