"""Reviewed within-course fusion and specific-operation history regressions."""

import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from filemate.course_graph.drafts import DraftService
from filemate.execution.storage import SQLiteStorage
from filemate.tests.course_graph.test_review import accept_nodes, draft, publish


def fusion():
    return importlib.import_module("filemate.course_graph.fusion")


@pytest.fixture
def pair(course_context):
    store, repo, cid, _sid = course_context
    publish(course_context, accept_nodes(course_context, draft(course_context), True))
    sid2 = store.save_source(original_name="第二份.txt", source_path="two.txt", raw_text="栈：另一份后进先出定义。")
    repo.attach_sources(cid, [sid2], None, repo.get_course(cid)["revision"])
    svc = DraftService(store, lambda: None, lambda: datetime.now(timezone.utc))
    d = svc.create_group(cid, [sid2], "local", "create_draft_00002")
    d = svc.extract_source(cid, d["draft_id"], sid2, "extract_source_002", False)
    publish(course_context, accept_nodes(course_context, d), "confirm_review_002")
    ids = [r[0] for r in store._conn().execute("SELECT concept_id FROM kg_concepts WHERE label='栈' ORDER BY concept_id")]
    return course_context, ids


def merge(pair):
    context, ids = pair
    store, _, cid, _ = context
    module = fusion()
    preview = module.preview_merge(store, cid, ids, ids[0])
    return module.confirm_merge(store, cid, ids, ids[0], preview["confirmation_token"], "confirm_merge_0001", True)


def change(context, oid, action, key):
    module, store, cid = fusion(), context[0], context[2]
    preview = module.preview_operation(store, cid, oid, action)
    return module.transition_operation(store, cid, oid, action, preview["confirmation_token"], key, True)


def test_same_course_merge_keeps_original_ids_and_quotes(pair):
    context, ids = pair
    store, _, cid, _ = context
    before = [tuple(r) for r in store._conn().execute("SELECT evidence_id,concept_id,excerpt FROM kg_evidence ORDER BY evidence_id")]
    result = merge(pair)
    assert result["affected"]["concepts"] == 2
    graph = fusion().course_graph(store, cid)
    stacks = [n for n in graph["nodes"] if n["label"] == "栈"]
    assert len(stacks) == 1 and set(stacks[0]["member_ids"]) == set(ids)
    assert stacks[0]["source_count"] == 2
    assert [tuple(r) for r in store._conn().execute("SELECT evidence_id,concept_id,excerpt FROM kg_evidence ORDER BY evidence_id")] == before
    assert store._conn().execute("SELECT COUNT(*) FROM kg_concepts WHERE concept_id IN (?,?)", ids).fetchone()[0] == 2
    assert graph["nodes"][0]["learning_status"] == "not_evaluated"


def test_stack_queue_and_cross_course_never_auto_merge(pair):
    context, ids = pair
    store, repo, cid, _ = context
    suggestions = fusion().merge_candidates(store, cid, ids[0])
    assert [s["concept_id"] for s in suggestions] == [ids[1]]
    other = repo.create_course("Python", "create_course_0002")["course_id"]
    with store._conn() as conn:
        conn.execute("INSERT INTO kg_concepts(concept_id,course_id,label) VALUES('foreign',?,'栈')", (other,))
    with pytest.raises(ValueError):
        fusion().preview_merge(store, cid, [ids[0], "foreign"], ids[0])
    assert store._conn().execute("SELECT canonical_id FROM kg_concepts WHERE concept_id=?", (ids[1],)).fetchone()[0] is None


def test_undo_specific_merge_preserves_quiz_and_plan(pair):
    context, ids = pair
    store, repo, _cid, sid = context
    aid = store.save_artifact(artifact_type="questions", source_id=sid, content=[{"question": "栈?", "answer": "后进先出", "knowledge_point": "栈"}])
    store.record_quiz_attempt(artifact_id=aid, question_index=0, user_answer="不会", is_correct=False, score=0, feedback="复习")
    before = {t: [tuple(r) for r in store._conn().execute(f"SELECT * FROM {t}")]
              for t in ("quiz_attempts", "wrong_questions", "study_plans", "artifacts")}
    result = merge(pair)
    # 与本次融合无关的新来源和课程不得妨碍指定撤销。
    repo.create_course("另一门课", "create_course_0003")
    change(context, result["operation_id"], "undo", "undo_merge_000001")
    assert all(r[0] is None for r in store._conn().execute("SELECT canonical_id FROM kg_concepts WHERE concept_id IN (?,?)", ids))
    change(context, result["operation_id"], "restore", "restore_merge_001")
    assert store._conn().execute("SELECT canonical_id FROM kg_concepts WHERE concept_id=?", (ids[1],)).fetchone()[0] == ids[0]
    assert {t: [tuple(r) for r in store._conn().execute(f"SELECT * FROM {t}")] for t in before} == before


def test_dependent_edit_blocks_unsafe_undo(pair):
    context, ids = pair
    result = merge(pair)
    with context[0]._conn() as conn:
        conn.execute("UPDATE kg_concepts SET revision=revision+1,label='用户之后修订' WHERE concept_id=?", (ids[0],))
    with pytest.raises(ValueError, match="operation_conflict"):
        fusion().preview_operation(context[0], context[2], result["operation_id"], "undo")


def test_merge_cycle_and_self_edge_are_explicit(pair):
    context, ids = pair
    store, _, cid, _ = context
    dfs = store._conn().execute("SELECT concept_id FROM kg_concepts WHERE label='DFS'").fetchone()[0]
    # 原关系为栈1→DFS，新增DFS→栈2，合并两个栈将引入有向环。
    with store._conn() as conn:
        conn.execute("INSERT INTO kg_relations(relation_id,course_id,from_id,to_id,type) VALUES('cycle',?,?,?,'prerequisite')", (cid, dfs, ids[1]))
        original = conn.execute("SELECT * FROM kg_evidence WHERE relation_id IS NOT NULL LIMIT 1").fetchone()
        conn.execute("""INSERT INTO kg_evidence(evidence_id,course_id,source_id,source_revision,relation_id,excerpt,char_start,char_end)
                        VALUES('cycle-evidence',?,?,?,'cycle',?,0,1)""", (cid, original["source_id"], original["source_revision"], "合成环测试"))
    with pytest.raises(ValueError, match="dependency_cycle"):
        fusion().preview_merge(store, cid, ids, ids[0])
    with store._conn() as conn:
        conn.execute("DELETE FROM kg_evidence WHERE evidence_id='cycle-evidence'")
        conn.execute("DELETE FROM kg_relations WHERE relation_id='cycle'")
        conn.execute("UPDATE kg_relations SET to_id=? WHERE from_id IN (?,?)", (ids[1], *ids))
    preview = fusion().preview_merge(store, cid, ids, ids[0])
    assert preview["self_edge_count"] == 1
    merge(pair)
    assert all(e["from"] != e["to"] for e in fusion().course_graph(store, cid)["edges"])


def test_replayed_merge_is_idempotent_and_bound_to_selection(pair):
    context, ids = pair
    module, store, cid = fusion(), context[0], context[2]
    preview = module.preview_merge(store, cid, ids, ids[0])
    args = (store, cid, ids, ids[0], preview["confirmation_token"], "confirm_merge_0001", True)
    first = module.confirm_merge(*args)
    assert module.confirm_merge(*args) == first
    with pytest.raises(ValueError):
        module.confirm_merge(store, cid, ids, ids[1], preview["confirmation_token"], "confirm_merge_0002", True)


def test_review_undo_restore_and_stale_sources(pair):
    context, _ = pair
    store, _, cid, sid = context
    oid = store._conn().execute("SELECT operation_id FROM kg_changes WHERE kind='review' ORDER BY rowid LIMIT 1").fetchone()[0]
    # 先撤销一个没有后续依赖的新来源审核。
    oid = store._conn().execute("SELECT operation_id FROM kg_changes WHERE kind='review' ORDER BY rowid DESC LIMIT 1").fetchone()[0]
    change(context, oid, "undo", "undo_review_00001")
    change(context, oid, "restore", "restore_review_01")
    assert store._conn().execute("PRAGMA foreign_key_check").fetchall() == []
    graph = fusion().course_graph(store, cid, limit=1, offset=0, q="栈")
    assert graph["total"] == 2 and len(graph["nodes"]) == 1
    store.save_source(source_id=sid, original_name="变化", source_path="x.txt", raw_text="正文已更新")
    graph = fusion().course_graph(store, cid, q="DFS")
    assert graph["nodes"][0]["source_status"] == "no_valid_source"


def test_two_connections_same_merge_commits_once(pair):
    context, ids = pair
    store, _, cid, _ = context
    module = fusion()
    preview = module.preview_merge(store, cid, ids, ids[0])
    other = SQLiteStorage(store.db_path)
    try:
        def confirm(db):
            return module.confirm_merge(db, cid, ids, ids[0], preview["confirmation_token"], "confirm_merge_0001", True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(confirm, [store, other]))
        assert results[0] == results[1]
        assert store._conn().execute("SELECT COUNT(*) FROM kg_changes WHERE kind='merge'").fetchone()[0] == 1
    finally:
        other.close()


def test_later_review_dependency_blocks_merge_undo(pair):
    context, _ids = pair
    store, _, cid, _ = context
    result = merge(pair)
    # 后续审核引用已存在的概念；不创建新概念也必须登记依赖。
    old = store._conn().execute("SELECT * FROM kg_changes WHERE kind='review' ORDER BY rowid DESC LIMIT 1").fetchone()
    import json
    meta = json.loads(old["metadata"])
    source = store._conn().execute("SELECT source_id FROM kg_extractions WHERE draft_id=?", (meta["draft_id"],)).fetchone()[0]
    sid = source
    # 用一个新的候选分组复用原节点，并确认节点本身；它依赖既有映射。
    svc = DraftService(store, lambda: None, lambda: datetime.now(timezone.utc))
    # 加入另一份来源使分组身份不同。
    extra = store.save_source(original_name="第三份", source_path="three.txt", raw_text="队列：先进先出。")
    context[1].attach_sources(cid, [extra], None, context[1].get_course(cid)["revision"])
    fresh = svc.create_group(cid, [sid, extra], "local", "create_draft_00003")
    fresh = svc.extract_source(cid, fresh["draft_id"], sid, "extract_source_003", False)
    fresh = accept_nodes(context, fresh)
    publish(context, fresh, "confirm_review_003")
    with pytest.raises(ValueError, match="operation_conflict") as caught:
        fusion().preview_operation(store, cid, result["operation_id"], "undo")
    later = store._conn().execute("SELECT operation_id FROM kg_changes WHERE kind='review' ORDER BY rowid DESC LIMIT 1").fetchone()[0]
    assert caught.value.details["blocking_operation_id"] == later


def test_review_cannot_publish_a_prerequisite_cycle(course_context):
    snap = draft(course_context, text="栈是DFS的前置知识。DFS是栈的前置知识。")
    saved = accept_nodes(course_context, snap, True)
    with pytest.raises(ValueError, match="dependency_cycle"):
        publish(course_context, saved)
    assert course_context[0]._conn().execute("SELECT COUNT(*) FROM kg_concepts").fetchone()[0] == 0
