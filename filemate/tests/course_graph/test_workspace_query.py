"""Synthetic reviewed sources exercise the read-only C workspace contract."""

import importlib
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from filemate.course_graph.drafts import DraftService
from filemate.course_graph.models import CourseGraphError
from filemate.execution.storage import SQLiteStorage
from filemate.tests.course_graph.test_fusion import change, merge, pair  # noqa: F401
from filemate.tests.course_graph.test_review import accept_nodes, publish


def query():
    return importlib.import_module("filemate.course_graph.workspace_query")


def filters(**kwargs):
    return importlib.import_module("filemate.course_graph.workspace_models").WorkspaceFilter(**kwargs)


def publish_source(context, text, name="extra.txt"):
    store, repo, cid, _ = context
    sid = store.save_source(original_name=name, source_path="synthetic.txt", raw_text=text)
    repo.attach_sources(cid, [sid], None, repo.get_course(cid)["revision"])
    svc = DraftService(store, lambda: None, lambda: datetime.now(timezone.utc))
    snap = svc.create_group(cid, [sid], "local", uuid4().hex)
    snap = svc.extract_source(cid, snap["draft_id"], sid, uuid4().hex, False)
    publish(context, accept_nodes(context, snap), uuid4().hex)
    return sid


@pytest.fixture
def workspace_case(pair):  # noqa: F811
    context, ids = pair
    store, repo, cid, first_sid = context
    second_sid = store._conn().execute(
        "SELECT source_id FROM kg_course_sources WHERE course_id=? AND source_id!=?", (cid, first_sid)
    ).fetchone()[0]
    parent, child = str(uuid4()), str(uuid4())
    repo.put_chapter(cid, parent, "基础", None, 0, 0)
    repo.put_chapter(cid, child, "深入", parent, 1, 0)
    repo.attach_sources(cid, [first_sid], parent, repo.get_course(cid)["revision"])
    repo.attach_sources(cid, [second_sid], child, repo.get_course(cid)["revision"])
    result = merge(pair)
    return {"context": context, "ids": ids, "parent": parent, "child": child,
            "sid2": second_sid, "merge": result}


def page(case, **kwargs):
    store, _, cid, _ = case["context"]
    return query().list_workspace_concepts(store, cid, filters=filters(), **kwargs)


def test_groups_follow_current_sources_not_label(workspace_case):
    store, _, cid, _ = workspace_case["context"]
    nav = query().get_workspace(store, cid)
    assert nav["total_concepts"] == 3
    nodes = page(workspace_case)["items"]
    assert len({n["id"] for n in nodes}) == 3
    stack = next(n for n in nodes if n["label"] == "栈")
    assert set(stack["chapter_ids"]) == {workspace_case["parent"], workspace_case["child"]}
    assert stack["member_count"] == stack["source_count"] == 2
    assert "source_refs" not in stack and "score" not in stack


def test_parent_count_deduplicates_merged_members(workspace_case):
    store, _, cid, _ = workspace_case["context"]
    nav = query().get_workspace(store, cid)
    groups = {g["id"]: g for g in nav["groups"]}
    assert groups[workspace_case["parent"]]["concept_count"] == 3
    assert groups[workspace_case["child"]]["concept_count"] == 1
    assert groups[workspace_case["parent"]]["child_count"] == 1
    assert query().list_workspace_concepts(store, cid, filters=filters(
        chapter_id=workspace_case["parent"]))["total"] == 3


def test_alias_and_member_name_search_survives_merge(workspace_case):
    store, _, _, _ = workspace_case["context"]
    with store._conn() as conn:
        conn.execute("UPDATE kg_concepts SET label='Stack',aliases=? WHERE concept_id=?",
                     (json.dumps([{"label": "LIFO", "origin": "user"}]), workspace_case["ids"][1]))
    for term in ("Stack", "lifo"):
        result = page(workspace_case, q=term)
        assert result["total"] == 1
        assert result["items"][0]["id"] == workspace_case["ids"][0]
        assert result["items"][0]["matched_label"].casefold() == term.casefold()


def test_symbol_search_and_snapshot_digest(workspace_case):
    context = workspace_case["context"]
    store, _, cid, sid = context
    publish_source(context, "C：lang。C#：lang。C++：lang。A-B：term。AB：term。")
    for term in ("C#", "C++", "A-B", "AB"):
        assert [n["label"] for n in page(workspace_case, q=term)["items"]] == [term]
    before = query().get_workspace(store, cid)["graph_digest"]
    store.save_source(source_id=sid, original_name="changed", source_path="s.txt", raw_text="正文已更新")
    after = query().get_workspace(store, cid)["graph_digest"]
    assert len(after) == 64 and after != before


def test_no_source_and_unassigned_are_distinct(workspace_case):
    context = workspace_case["context"]
    store, _, cid, sid = context
    publish_source(context, "未分组：definition。")
    store.save_source(source_id=sid, original_name="new", source_path="s.txt", raw_text="新版本")
    no_source = query().list_workspace_concepts(store, cid, filters=filters(chapter_id="@no-source"))
    unassigned = query().list_workspace_concepts(store, cid, filters=filters(chapter_id="@unassigned"))
    assert {n["label"] for n in no_source["items"]} == {"队列", "DFS"}
    assert [n["label"] for n in unassigned["items"]] == ["未分组"]
    assert all(n["source_status"] == "no_valid_source" for n in no_source["items"])


def test_navigation_paging_and_chapter_path(workspace_case):
    store, _, cid, _ = workspace_case["context"]
    whole = query().get_workspace(store, cid)
    pages = [query().get_workspace(store, cid, group_limit=1, group_offset=i, source_limit=1,
                                  source_offset=i) for i in range(whole["group_total"])]
    assert [g for p in pages for g in p["groups"]] == whole["groups"]
    assert len({p["graph_digest"] for p in pages}) == 1
    path = query().get_chapter_path(store, cid, workspace_case["child"])
    assert [g["id"] for g in path["items"]] == [workspace_case["parent"], workspace_case["child"]]
    children = query().get_workspace(store, cid, parent_id=workspace_case["parent"])
    assert [g["id"] for g in children["groups"]] == [workspace_case["child"]]
    assert page(workspace_case, limit=1, offset=2)["items"] == page(workspace_case)["items"][2:3]


def test_invalid_chapter_cycle_is_bounded(workspace_case):
    store, _, cid, _ = workspace_case["context"]
    with store._conn() as conn:
        conn.execute("UPDATE kg_chapters SET parent_id=? WHERE chapter_id=?",
                     (workspace_case["child"], workspace_case["parent"]))
    with pytest.raises(CourseGraphError, match="chapter_structure_invalid") as caught:
        query().get_chapter_path(store, cid, workspace_case["child"])
    assert caught.value.status_code == 409


def test_digest_changes_on_review_merge_undo_even_without_course_revision(pair):  # noqa: F811
    context, _ = pair
    store, repo, cid, _ = context
    before = query().get_workspace(store, cid)["graph_digest"]
    revision = repo.get_course(cid)["revision"]
    result = merge(pair)
    after = query().get_workspace(store, cid)["graph_digest"]
    assert after != before and repo.get_course(cid)["revision"] == revision
    change(context, result["operation_id"], "undo", "undo_workspace_0001")
    assert query().get_workspace(store, cid)["graph_digest"] != after
    publish_source(context, "新概念：定义。")
    assert query().get_workspace(store, cid)["graph_digest"] != before


def test_reads_are_isolated_bounded_and_do_not_write(workspace_case, tmp_path, monkeypatch):
    store, _, cid, _ = workspace_case["context"]
    before = store._conn().total_changes
    count = []
    original = SQLiteStorage.get_source_revision

    def tracked(self, sid):
        count.append(sid)
        return original(self, sid)

    monkeypatch.setattr(SQLiteStorage, "get_source_revision", tracked)
    query().get_workspace(store, cid)
    assert len(count) == len(set(count)) == 2
    assert store._conn().total_changes == before
    assert store._conn().execute("PRAGMA foreign_key_check").fetchall() == []
    for kwargs in ({"limit": 201}, {"offset": -1}, {"q": "x" * 161}):
        with pytest.raises(CourseGraphError) as caught:
            page(workspace_case, **kwargs)
        assert caught.value.status_code == 422
    with pytest.raises(CourseGraphError, match="chapter_not_found"):
        query().list_workspace_concepts(store, cid, filters=filters(chapter_id="foreign"))
    other = SQLiteStorage(tmp_path / "other.sqlite")
    other.init_schema()
    try:
        with pytest.raises(CourseGraphError, match="course_not_found"):
            query().get_workspace(other, cid)
    finally:
        other.close()



def test_outline_page_carries_bounded_real_chapter_paths(workspace_case):
    _, repo, cid, _ = workspace_case["context"]
    grandchild = str(uuid4())
    repo.put_chapter(cid, grandchild, "深入", workspace_case["child"], 0, 0)
    repo.attach_sources(cid, [workspace_case["sid2"]], grandchild, repo.get_course(cid)["revision"])
    result = page(workspace_case)
    groups = {g["id"]: g for g in result["chapter_groups"]}
    assert groups[grandchild]["parent_id"] == workspace_case["child"]
    assert groups[workspace_case["child"]]["parent_id"] == workspace_case["parent"]
    stack = next(n for n in result["items"] if n["label"] == "栈")
    assert set(stack["chapter_ids"]) == {workspace_case["parent"], grandchild}
    assert result["chapter_groups_truncated"] is False
    assert len(result["chapter_groups"]) <= 200
    assert {g["id"] for g in page(workspace_case, limit=1)["chapter_groups"]} <= set(groups)


def test_outline_chapter_metadata_cap_is_explicit(workspace_case, monkeypatch):
    from dataclasses import replace

    from filemate.course_graph.workspace_snapshot import load_workspace_snapshot

    store, _, cid, _ = workspace_case["context"]
    snapshot = load_workspace_snapshot(store, cid)
    groups = {f"g{i}": {"id": f"g{i}", "parent_id": None, "title": str(i),
                       "sort_order": i, "concept_count": 1, "child_count": 0} for i in range(201)}
    node = {**next(iter(snapshot.nodes.values())), "chapter_ids": list(groups)}
    wide = replace(snapshot, nodes={node["id"]: node}, groups=groups, ancestors={})
    monkeypatch.setattr(query(), "load_workspace_snapshot", lambda *_: wide)
    result = page(workspace_case)
    assert len(result["chapter_groups"]) == 200
    assert result["chapter_groups_truncated"] is True
    assert result["items"][0]["chapter_ids"] == list(groups)
