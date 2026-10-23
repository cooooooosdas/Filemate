# ruff: noqa: F811
"""Synthetic course unlink, purge and personal backup recovery contracts."""

import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event
from types import SimpleNamespace

import pytest

from filemate.course_graph.drafts import DraftService
from filemate.course_graph.fusion import course_graph
from filemate.execution import storage as storage_module
from filemate.operations import personal_backup as backup_module
from filemate.operations.personal_backup import PersonalBackup
from filemate.tests.course_graph.test_fusion import change, merge, pair  # noqa: F401
from filemate.tests.course_graph.test_review import accept_nodes, draft, publish


def privacy():
    return importlib.import_module("filemate.course_graph.privacy")


def unlink(context, sid, key="remove_source_001"):
    module, store, cid = privacy(), context[0], context[2]
    preview = module.preview_remove_source(store, cid, sid)
    return module.remove_source(store, cid, sid, preview["confirmation_token"], key, True)


def purge(store, sid, token=None):
    preview = store.source_deletion_preview(sid) if token is None else {"confirmation_token": token}
    # 合成资料没有托管物理文件，只替换外部文件暂存边界，数据库使用真实事务。
    return store.confirmed_source_delete(sid, preview["confirmation_token"],
        lambda path, shared: SimpleNamespace(status={"managed": False}, finish=lambda: None, rollback=lambda: None))


def test_remove_course_source_preserves_learning_history(course_context):
    store, _, cid, sid = course_context
    publish(course_context, accept_nodes(course_context, draft(course_context), True))
    aid = store.save_artifact(artifact_type="questions", source_id=sid,
        content=[{"question": "栈?", "answer": "后进先出", "knowledge_point": "栈"}])
    store.record_quiz_attempt(artifact_id=aid, question_index=0, user_answer="不会", is_correct=False, score=0, feedback="复习")
    plan = {"title": "栈复习", "daily_minutes": 20, "daily_plan": [{"date": "2026-10-22", "tasks": ["栈"]}]}
    plan_artifact = store.save_artifact(artifact_type="study_plan", source_id=sid, content=plan)
    store.create_study_plan(artifact_id=plan_artifact, source_id=sid, plan=plan)
    before = {t: [tuple(r) for r in store._conn().execute(f"SELECT * FROM {t}")]
              for t in ("sources", "artifacts", "quiz_attempts", "wrong_questions", "study_plans")}
    result = unlink(course_context, sid)
    assert result["changed"] is True and result["retains_learning_history"] is True
    assert {t: [tuple(r) for r in store._conn().execute(f"SELECT * FROM {t}")] for t in before} == before
    graph = course_graph(store, cid)
    assert all(n["source_status"] == "no_valid_source" for n in graph["nodes"])
    assert graph["edges"] == []
    change(course_context, result["operation_id"], "undo", "undo_remove_00001")
    assert all(n["source_count"] == 1 for n in course_graph(store, cid)["nodes"])


def test_other_source_support_survives_purge(pair):
    context, _ = pair
    store, _, cid, sid = context
    merge(pair)
    preview = store.source_deletion_preview(sid)
    assert preview["affected"]["course_graph_evidence"] > 0
    purge(store, sid, preview["confirmation_token"])
    graph = course_graph(store, cid)
    stack = next(n for n in graph["nodes"] if n["label"] == "栈")
    assert stack["source_count"] == 1
    assert store.get_source(sid) is None
    assert store._conn().execute("SELECT COUNT(*) FROM kg_extractions WHERE source_id=?", (sid,)).fetchone()[0] == 0
    assert store._conn().execute("SELECT COUNT(*) FROM kg_evidence WHERE source_id=?", (sid,)).fetchone()[0] == 0
    assert store._conn().execute("PRAGMA foreign_key_check").fetchall() == []
    # 操作日志只保留ID/状态，不残留被删引文。
    assert "后进先出的线性表" not in "".join(r[0] for r in store._conn().execute("SELECT metadata FROM kg_changes"))


def test_last_support_is_unavailable_not_deleted(course_context):
    store, _, cid, sid = course_context
    publish(course_context, accept_nodes(course_context, draft(course_context), True))
    ids = {n["id"] for n in course_graph(store, cid)["nodes"]}
    purge(store, sid)
    graph = course_graph(store, cid)
    assert {n["id"] for n in graph["nodes"]} == ids
    assert all(n["source_status"] == "no_valid_source" for n in graph["nodes"])
    assert graph["edges"] == []


@pytest.mark.parametrize("action", ["text", "chunks"])
def test_updated_text_or_chunks_invalidates_all_course_mappings(course_context, action):
    store, repo, cid, sid = course_context
    publish(course_context, accept_nodes(course_context, draft(course_context), True))
    other = repo.create_course("另一门课", "create_course_0002")["course_id"]
    repo.attach_sources(other, [sid], None, 0)
    svc = DraftService(store, lambda: None, lambda: datetime.now(timezone.utc))
    d = svc.create_group(other, [sid], "local", "create_draft_00002")
    d = svc.extract_source(other, d["draft_id"], sid, "extract_source_002", False)
    other_context = (store, repo, other, sid)
    publish(other_context, accept_nodes(other_context, d), "confirm_review_002")
    if action == "text":
        store.save_source(source_id=sid, original_name="变化", source_path="x.txt", raw_text="正文更新")
    else:
        store.replace_source_chunks(sid, [{"chunk_index": 0, "content": "新分块", "page_number": 3}])
    for course in (cid, other):
        assert all(n["source_status"] == "no_valid_source" for n in course_graph(store, course)["nodes"])


def test_backup_30_and_new_roundtrip(course_context, tmp_path, monkeypatch):
    store, _, cid, sid = course_context
    svc = DraftService(store, lambda: None, lambda: datetime.now(timezone.utc))
    d = svc.create_group(cid, [sid], "local", "create_draft_00001")
    with store._conn() as conn:
        conn.execute("UPDATE kg_extractions SET status='running',epoch=7,lease_until='2099-01-01T00:00:00+00:00'")
    backup = PersonalBackup(store, "local", tmp_path / "inbox", tmp_path / "archive")
    raw = backup.export()
    preview = backup.preview(raw)
    backup.restore(preview["backup_id"], preview["confirmation_token"])
    restored = svc.snapshot(cid, d["draft_id"])["sources"][0]
    assert restored["status"] == "interrupted" and restored["epoch"] != 7
    assert restored["lease_until"] is None
    # 用真实30版表结构导出旧格式签名包，再交给31版恢复。
    old = storage_module.SQLiteStorage(tmp_path / "old.sqlite")
    migrations = storage_module._MIGRATIONS
    with monkeypatch.context() as scope:
        scope.setattr(storage_module, "_MIGRATIONS", tuple(m for m in migrations if m[0] <= 30))
        scope.setattr(backup_module, "_MIGRATIONS", tuple(m for m in migrations if m[0] <= 30))
        old.init_schema()
        old.save_source(original_name="旧数据", source_path="legacy.txt", raw_text="30版原文")
        legacy_backup = PersonalBackup(old, "local", tmp_path / "old-inbox", tmp_path / "old-archive")
        old_raw = legacy_backup.export()
    old.init_schema()
    legacy_preview = legacy_backup.preview(old_raw)
    legacy_backup.restore(legacy_preview["backup_id"], legacy_preview["confirmation_token"])
    assert old.list_sources()[0]["raw_text"] == "30版原文"
    assert old._conn().execute("SELECT COUNT(*) FROM kg_courses").fetchone()[0] == 0
    assert old._conn().execute("PRAGMA foreign_key_check").fetchall() == []
    old.close()


def test_delete_token_covers_graph_changes(course_context):
    store, _, _, sid = course_context
    publish(course_context, accept_nodes(course_context, draft(course_context), True))
    preview = store.source_deletion_preview(sid)
    with store._conn() as conn:
        conn.execute("UPDATE kg_concepts SET label='用户修订',revision=revision+1")
    with pytest.raises(ValueError):
        purge(store, sid, preview["confirmation_token"])
    assert store.get_source(sid) is not None


def test_restore_never_allows_old_claim_to_complete_new_request(course_context, tmp_path):
    store, _, cid, sid = course_context
    svc = DraftService(store, lambda: None, lambda: datetime.now(timezone.utc))
    did = svc.create_group(cid, [sid], "llm", "create_draft_00001")["draft_id"]
    with store._conn() as conn:
        conn.execute("UPDATE kg_extractions SET status='failed',epoch=7")
    backup = PersonalBackup(store, "local", tmp_path / "inbox", tmp_path / "archive")
    raw = backup.export()

    class Blocking:
        def __init__(self, label):
            self.entered, self.release, self.label = Event(), Event(), label

        def extract(self, text):
            self.entered.set()
            assert self.release.wait(10)
            return {"nodes": [{"label": self.label, "excerpt": text}], "edges": []}

    old, new = Blocking("栈"), Blocking("队列")
    old_svc = DraftService(store, lambda: old, lambda: datetime.now(timezone.utc))
    new_svc = DraftService(store, lambda: new, lambda: datetime.now(timezone.utc))
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            stale = pool.submit(old_svc.extract_source, cid, did, sid, "old_extract_00001", True)
            assert old.entered.wait(5)
            preview = backup.preview(raw)
            backup.restore(preview["backup_id"], preview["confirmation_token"])
            fresh = pool.submit(new_svc.extract_source, cid, did, sid, "new_extract_00001", True)
            assert new.entered.wait(5)
            old.release.set()
            stale.result(5)
            assert new_svc.snapshot(cid, did)["sources"][0]["status"] == "running"
            new.release.set()
            result = fresh.result(5)
            assert result["sources"][0]["payload"]["nodes"][0]["parsed"]["label"] == "队列"
    finally:
        old.release.set()
        new.release.set()
