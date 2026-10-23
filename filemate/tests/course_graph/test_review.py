"""Per-item review, stale confirmations and atomic publication."""

import importlib
import sqlite3
from datetime import datetime, timezone

import pytest

from filemate.course_graph.drafts import DraftService


def review():
    return importlib.import_module("filemate.course_graph.review")


def draft(context, payload=None, text=None):
    store, _, cid, sid = context
    if text:
        store.save_source(source_id=sid, original_name="修订.txt", source_path="synthetic.txt", raw_text=text)

    class Provider:
        def extract(self, text):
            return payload

    service = DraftService(store, lambda: Provider(), lambda: datetime.now(timezone.utc))
    mode = "llm" if payload else "local"
    did = service.create_group(cid, [sid], mode, "create_draft_00001")["draft_id"]
    return service.extract_source(cid, did, sid, "extract_source_001", bool(payload))


def decide(context, snap, choices):
    return review().save_decisions(context[0], context[2], snap["draft_id"], snap["revision_digest"], [
        review().ItemDecision(**choice) for choice in choices
    ])


def items(snap):
    return [item for source in snap["sources"] for kind in ("nodes", "edges")
            for item in source["payload"].get(kind, [])]


def accept_nodes(context, snap, include_edges=False):
    return decide(context, snap, [{"item_id": n["item_id"], "verdict": "accept"}
                                 for n in items(snap) if include_edges or n["kind"] == "node"])


def publish(context, snap, key="confirm_review_001"):
    module, store, cid = review(), context[0], context[2]
    preview = module.preview_review(store, cid, snap["draft_id"])
    return module.confirm_review(store, cid, snap["draft_id"], key, preview["confirmation_token"], True)


def test_only_accepted_items_publish(course_context):
    snap = draft(course_context)
    nodes = {n["parsed"]["label"]: n for n in items(snap) if n["kind"] == "node"}
    saved = decide(course_context, snap, [
        {"item_id": nodes["栈"]["item_id"], "verdict": "accept"},
        {"item_id": nodes["队列"]["item_id"], "verdict": "reject"},
    ])
    result = publish(course_context, saved)
    store = course_context[0]
    assert result["affected"]["concepts"] == 1
    assert [r[0] for r in store._conn().execute("SELECT label FROM kg_concepts")] == ["栈"]
    assert store._conn().execute("SELECT COUNT(*) FROM kg_relations").fetchone()[0] == 0
    assert store.list_graph_batches() == []


def test_invalid_or_unchecked_relation_cannot_publish(course_context):
    text = "栈和队列都是线性结构。"
    payload = {"nodes": [{"label": t, "excerpt": text} for t in ("栈", "队列")],
               "edges": [{"from": "栈", "to": "队列", "relation": "prerequisite", "excerpt": text}]}
    snap = draft(course_context, payload, text)
    saved = accept_nodes(course_context, snap, True)
    with pytest.raises(ValueError, match="invalid_candidate"):
        publish(course_context, saved)
    assert course_context[0]._conn().execute("SELECT COUNT(*) FROM kg_concepts").fetchone()[0] == 0


def test_semantic_review_requires_explicit_check(course_context):
    text = "栈为DFS提供学习基础。"
    payload = {"nodes": [{"label": t, "excerpt": text} for t in ("栈", "DFS")],
               "edges": [{"from": "栈", "to": "DFS", "relation": "prerequisite", "excerpt": text}]}
    snap = draft(course_context, payload, text)
    saved = accept_nodes(course_context, snap, True)
    with pytest.raises(ValueError, match="semantic_check_required"):
        publish(course_context, saved)
    edge = next(n for n in items(saved) if n["kind"] == "edge")
    checked = decide(course_context, saved, [{"item_id": edge["item_id"], "verdict": "accept", "semantic_checked": True}])
    assert publish(course_context, checked)["affected"]["relations"] == 1


@pytest.mark.parametrize("action", ["source", "decision"])
def test_revision_and_token_prevent_stale_confirmation(course_context, action):
    store, _, cid, sid = course_context
    snap = accept_nodes(course_context, draft(course_context))
    module = review()
    preview = module.preview_review(store, cid, snap["draft_id"])
    if action == "source":
        store.save_source(source_id=sid, original_name="新版", source_path="synthetic.txt", raw_text="内容更新")
    else:
        decide(course_context, snap, [{"item_id": items(snap)[0]["item_id"], "verdict": "reject"}])
    with pytest.raises(ValueError):
        module.confirm_review(store, cid, snap["draft_id"], "confirm_review_001", preview["confirmation_token"], True)
    assert store._conn().execute("SELECT COUNT(*) FROM kg_concepts").fetchone()[0] == 0


def test_confirm_retry_is_idempotent(course_context):
    store, _, cid, _ = course_context
    snap = accept_nodes(course_context, draft(course_context), True)
    module = review()
    preview = module.preview_review(store, cid, snap["draft_id"])
    args = (store, cid, snap["draft_id"], "confirm_review_001", preview["confirmation_token"], True)
    first = module.confirm_review(*args)
    assert module.confirm_review(*args) == first
    assert store._conn().execute("SELECT COUNT(*) FROM kg_changes WHERE kind='review'").fetchone()[0] == 1
    assert store._conn().execute("SELECT COUNT(*) FROM data_action_audit WHERE action='course_graph_review'").fetchone()[0] == 1
    assert store._conn().execute("PRAGMA foreign_key_check").fetchall() == []


def test_edge_with_unaccepted_endpoint_is_blocked(course_context):
    snap = draft(course_context)
    edge = next(n for n in items(snap) if n["kind"] == "edge")
    saved = decide(course_context, snap, [{"item_id": edge["item_id"], "verdict": "accept"}])
    with pytest.raises(ValueError, match="endpoint_not_confirmed"):
        publish(course_context, saved)


def test_label_revision_preserves_quote_and_marks_user_alias(course_context):
    store, _, _, _ = course_context
    snap = draft(course_context)
    node = next(n for n in items(snap) if n["kind"] == "node" and n["parsed"]["label"] == "栈")
    saved = decide(course_context, snap, [{"item_id": node["item_id"], "verdict": "revise", "label": "栈结构", "aliases": ["自定义栈名"]}])
    publish(course_context, saved)
    concept = dict(store._conn().execute("SELECT * FROM kg_concepts").fetchone())
    assert concept["label"] == "栈结构"
    assert '"origin": "user"' in concept["aliases"]
    evidence = dict(store._conn().execute("SELECT * FROM kg_evidence").fetchone())
    assert evidence["legacy_node_id"] == node["parsed"]["legacy_node_id"]
    assert evidence["excerpt"] == node["parsed"]["excerpt"]


def test_atomic_failure_has_no_graph_or_receipt(course_context):
    store, _, _, _ = course_context
    snap = accept_nodes(course_context, draft(course_context))
    with store._conn() as conn:
        conn.execute("CREATE TRIGGER reject_evidence BEFORE INSERT ON kg_evidence BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
    with pytest.raises(sqlite3.Error):
        publish(course_context, snap)
    assert store._conn().execute("SELECT COUNT(*) FROM kg_concepts").fetchone()[0] == 0
    assert store._conn().execute("SELECT COUNT(*) FROM kg_changes WHERE kind='review'").fetchone()[0] == 0


def test_blank_display_name_is_rejected():
    with pytest.raises(ValueError):
        review().ItemDecision(item_id="candidate", verdict="revise", label="   ")


def test_cached_source_requires_fresh_review_without_duplicate_concepts(course_context):
    store, repo, cid, sid = course_context
    first = accept_nodes(course_context, draft(course_context), True)
    publish(course_context, first)
    before = store._conn().execute("SELECT COUNT(*) FROM kg_concepts").fetchone()[0]
    sid2 = store.save_source(original_name="第二份.txt", source_path="second.txt", raw_text="栈：后进先出的结构。")
    repo.attach_sources(cid, [sid2], None, repo.get_course(cid)["revision"])
    svc = DraftService(store, lambda: None, lambda: datetime.now(timezone.utc))
    other = svc.create_group(cid, [sid, sid2], "local", "create_draft_00002")
    svc.extract_source(cid, other["draft_id"], sid, "extract_source_002", False)
    other = svc.extract_source(cid, other["draft_id"], sid2, "extract_source_003", False)
    cached = next(s for s in other["sources"] if s["source_id"] == sid)
    assert all(n.get("review_status", "pending") == "pending" for n in cached["payload"]["nodes"])
    publish(course_context, accept_nodes(course_context, other), "confirm_review_002")
    assert store._conn().execute("SELECT COUNT(*) FROM kg_concepts").fetchone()[0] == before + 1
