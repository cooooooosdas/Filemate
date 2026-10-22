"""Reproduce important findings from the independent B review."""

import json
from datetime import datetime, timezone
from uuid import uuid4

from filemate.course_graph import review as review_module
from filemate.course_graph.drafts import DraftService
from filemate.course_graph.extraction import extract_local_course, validate_candidates
from filemate.course_graph.fusion import course_graph, merge_candidates, preview_merge
from filemate.course_graph.review import preview_review
from filemate.tests.course_graph.test_fusion import change, merge, pair  # noqa: F401
from filemate.tests.course_graph.test_review import accept_nodes, decide, draft, items, publish


def test_cancelled_group_alias_never_becomes_new_group(course_context):
    store, _, cid, sid = course_context
    svc = DraftService(store, lambda: None, lambda: datetime.now(timezone.utc))
    a = svc.create_group(cid, [sid], "local", "create_original_0001")
    assert svc.create_group(cid, [sid], "local", "reuse_original_0001")["draft_id"] == a["draft_id"]
    svc.cancel(cid, a["draft_id"], "cancel_original_001")
    b = svc.create_group(cid, [sid], "local", "new_after_cancel_001")
    assert b["sources"][0]["status"] == "pending"
    assert store._conn().execute("SELECT COUNT(*) FROM kg_extractions WHERE draft_id=?", (b["draft_id"],)).fetchone()[0] == 1
    assert svc.extract_source(cid, b["draft_id"], sid, "extract_after_cancel", False)["sources"][0]["status"] == "ready"


def test_revoked_items_do_not_block_remaining_review(course_context):
    store, _, cid, _ = course_context
    snap = draft(course_context, text="AA：first。BB：second。")
    a, b = items(snap)
    saved = decide(course_context, snap, [{"item_id": a["item_id"], "verdict": "accept"}])
    receipt = publish(course_context, saved)
    change(course_context, receipt["operation_id"], "undo", "undo_only_first_001")
    svc = DraftService(store, lambda: None, lambda: datetime.now(timezone.utc))
    current = svc.snapshot(cid, snap["draft_id"])
    saved = decide(course_context, current, [{"item_id": b["item_id"], "verdict": "accept"}])
    assert preview_review(store, cid, snap["draft_id"])["nodes"] == 1
    assert publish(course_context, saved, "publish_remaining_01")["affected"]["concepts"] == 1
    assert [n["label"] for n in course_graph(store, cid)["nodes"]] == ["BB"]


def test_revoked_relation_is_not_selected_when_publishing_remaining_node(course_context):
    store, _, cid, _ = course_context
    snap = draft(course_context, text="AA：first。BB：second。CC：third。AA是BB的前置知识。")
    choices = [{"item_id": i["item_id"], "verdict": "accept"} for i in items(snap)
               if i["kind"] == "node" and i["original"]["label"] in {"AA", "BB"}]
    publish(course_context, decide(course_context, snap, choices))
    svc = DraftService(store, lambda: None, lambda: datetime.now(timezone.utc))
    current = svc.snapshot(cid, snap["draft_id"])
    edge = next(i for i in items(current) if i["kind"] == "edge")
    op = publish(course_context, decide(course_context, current, [{"item_id": edge["item_id"], "verdict": "accept"}]), "publish_edge_00001")
    change(course_context, op["operation_id"], "undo", "undo_only_edge_0001")
    current = svc.snapshot(cid, snap["draft_id"])
    cc = next(i for i in items(current) if i["original"].get("label") == "CC")
    saved = decide(course_context, current, [{"item_id": cc["item_id"], "verdict": "accept"}])
    preview = preview_review(store, cid, snap["draft_id"])
    assert (preview["nodes"], preview["relations"]) == (1, 0)
    publish(course_context, saved, "publish_cc_0000001")
    assert course_graph(store, cid)["edges"] == []


def test_local_symbol_terms_and_same_payload_remain_distinct():
    text = "C#：a language。C：another language。A-B：one term。AB：another term。"
    payload = extract_local_course(text)
    assert {n["label"] for n in payload["nodes"]} == {"C#", "C", "A-B", "AB"}
    validated = validate_candidates(payload, text, "source", [])
    assert all(n["validation"] == "valid" for n in validated["nodes"])


def test_symbol_collision_across_modes_does_not_reuse_other_concept(course_context):
    store, _, cid, sid = course_context
    snap = draft(course_context, text="A-B：first。AB：second。")
    selected = next(n for n in items(snap) if n["original"]["label"] == "A-B")
    publish(course_context, decide(course_context, snap, [{"item_id": selected["item_id"], "verdict": "revise", "label": "显示名已修改"}]))

    class Provider:
        def extract(self, text):
            return {"nodes": [{"label": "AB", "excerpt": "AB：second"}], "edges": []}

    svc = DraftService(store, Provider, lambda: datetime.now(timezone.utc))
    other = svc.create_group(cid, [sid], "llm", "different_mode_0001")
    other = svc.extract_source(cid, other["draft_id"], sid, "different_extract_1", True)
    receipt = publish(course_context, accept_nodes(course_context, other), "different_publish_1")
    assert receipt["affected"]["concepts"] == 1
    graph = course_graph(store, cid)
    assert {n["label"] for n in graph["nodes"]} == {"显示名已修改", "AB"}
    assert len({n["id"] for n in graph["nodes"]}) == 2
    assert store._conn().execute("SELECT COUNT(*) FROM kg_evidence WHERE concept_id IS NOT NULL AND legacy_node_id IS NOT NULL").fetchone()[0] == 0


def test_b1_random_evidence_reuse_verifies_original_term_after_display_edit(course_context, monkeypatch):
    store, _, cid, sid = course_context
    snap = draft(course_context, text="A-B：first。")
    choice = items(snap)[0]
    saved = decide(course_context, snap, [{"item_id": choice["item_id"], "verdict": "revise", "label": "人工显示名"}])
    with monkeypatch.context() as patch:
        patch.setattr(review_module, "occurrence_id", lambda *args: str(uuid4()))
        publish(course_context, saved)
    original_id = course_graph(store, cid)["nodes"][0]["id"]

    class Provider:
        def extract(self, text):
            return {"nodes": [{"label": "A-B", "excerpt": "A-B：first"}], "edges": []}

    svc = DraftService(store, Provider, lambda: datetime.now(timezone.utc))
    d = svc.create_group(cid, [sid], "llm", "b1_reuse_group_0001")
    d = svc.extract_source(cid, d["draft_id"], sid, "b1_reuse_extract_01", True)
    result = publish(course_context, accept_nodes(course_context, d), "b1_reuse_confirm_01")
    assert result["affected"]["concepts"] == 0
    assert [n["id"] for n in course_graph(store, cid)["nodes"]] == [original_id]


def test_merged_member_names_aliases_remain_searchable_and_suggested(pair):  # noqa: F811
    context, ids = pair
    store, repo, cid, _ = context
    with store._conn() as conn:
        conn.execute("UPDATE kg_concepts SET label='栈' WHERE concept_id=?", (ids[0],))
        conn.execute("UPDATE kg_concepts SET label='Stack',aliases=? WHERE concept_id=?",
                     (json.dumps([{"label": "LIFO", "origin": "user"}]), ids[1]))
    merge(pair)
    assert course_graph(store, cid, q="Stack")["total"] == 1
    assert course_graph(store, cid, q="LIFO")["total"] == 1
    sid = store.save_source(original_name="English.txt", source_path="third.txt", raw_text="Stack：a LIFO structure。")
    repo.attach_sources(cid, [sid], None, repo.get_course(cid)["revision"])
    svc = DraftService(store, lambda: None, lambda: datetime.now(timezone.utc))
    d = svc.create_group(cid, [sid], "local", "third_source_00001")
    d = svc.extract_source(cid, d["draft_id"], sid, "third_extract_0001", False)
    publish((store, repo, cid, sid), accept_nodes((store, repo, cid, sid), d), "third_publish_0001")
    third = next(n for n in course_graph(store, cid)["nodes"] if n["label"] == "Stack")
    assert ids[0] in {n["concept_id"] for n in merge_candidates(store, cid, third["id"])}


def test_merge_preview_displays_selected_source_evidence(pair):  # noqa: F811
    context, ids = pair
    preview = preview_merge(context[0], context[2], ids, ids[0])
    assert all(node["source_refs"] for node in preview["concepts"])
    assert len({ref["source_id"] for node in preview["concepts"] for ref in node["source_refs"]}) == 2
    assert all(ref["excerpt"] and ref["original_name"] for node in preview["concepts"] for ref in node["source_refs"])
