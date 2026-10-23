"""Durability, concurrent claims, cancellation and governance regressions."""

import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Event

import pytest

from filemate.execution.storage import SQLiteStorage


class Provider:
    def __init__(self, block=False):
        self.calls = []
        self.entered, self.release = Event(), Event()
        self.block = block

    def extract(self, text):
        self.calls.append(text)
        self.entered.set()
        if self.block:
            assert self.release.wait(10)
        if "坏资料" in text:
            raise RuntimeError("synthetic-secret private provider error")
        label = "栈" if "栈" in text else "队列"
        return {"nodes": [{"label": label, "excerpt": text[:100]}], "edges": []}


def service(store, provider=None, clock=None):
    cls = importlib.import_module("filemate.course_graph.drafts").DraftService
    return cls(store, lambda: provider or Provider(), clock or (lambda: datetime.now(timezone.utc)))


def add_source(store, repo, cid, text):
    sid = store.save_source(original_name="合成.txt", source_path="synthetic.txt", raw_text=text)
    repo.attach_sources(cid, [sid], None, repo.get_course(cid)["revision"])
    return sid


def test_one_failed_source_does_not_drop_others(course_context):
    store, repo, cid, sid = course_context
    bad = add_source(store, repo, cid, "坏资料：失败测试。")
    third = add_source(store, repo, cid, "队列：先进先出。")
    provider = Provider()
    svc = service(store, provider)
    did = svc.create_group(cid, [sid, bad, third], "llm", "create_draft_00001")["draft_id"]
    assert not provider.calls
    svc.extract_source(cid, did, sid, "extract_source_001", True)
    result = svc.extract_source(cid, did, bad, "extract_source_002", True)
    assert {s["source_id"]: s["status"] for s in result["sources"]} == {sid: "ready", bad: "failed", third: "pending"}
    assert "synthetic-secret" not in json.dumps(result)
    reopened = SQLiteStorage(store.db_path)
    try:
        saved = service(reopened, provider).snapshot(cid, did)
        first = next(s for s in saved["sources"] if s["source_id"] == sid)
        assert first["payload"]["nodes"][0]["parsed"]["label"] == "栈"
    finally:
        reopened.close()


def test_two_connections_claim_once(course_context):
    store, _, cid, sid = course_context
    provider = Provider(block=True)
    svc = service(store, provider)
    did = svc.create_group(cid, [sid], "llm", "create_draft_00001")["draft_id"]
    other = SQLiteStorage(store.db_path)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = pool.submit(svc.extract_source, cid, did, sid, "extract_source_001", True)
            assert provider.entered.wait(5)
            repeated = service(other, provider).extract_source(cid, did, sid, "extract_source_001", True)
            assert repeated["sources"][0]["status"] == "running"
            # 与模型无关的持久写入可在模型阻塞期间完成。
            store.save_artifact(artifact_type="notes", content={"text": "并发保留"})
            provider.release.set()
            assert pending.result(5)["sources"][0]["status"] == "ready"
        assert len(provider.calls) == 1
        assert svc.extract_source(cid, did, sid, "extract_source_001", True)["sources"][0]["status"] == "ready"
        assert len(provider.calls) == 1
    finally:
        provider.release.set()
        other.close()


@pytest.mark.parametrize("action", ["cancel", "update", "detach"])
def test_stale_or_cancelled_result_never_commits(course_context, action):
    store, _, cid, sid = course_context
    provider = Provider(block=True)
    svc = service(store, provider)
    did = svc.create_group(cid, [sid], "llm", "create_draft_00001")["draft_id"]
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(svc.extract_source, cid, did, sid, "extract_source_001", True)
        assert provider.entered.wait(5)
        if action == "cancel":
            svc.cancel(cid, did, "cancel_draft_00001")
        elif action == "update":
            store.save_source(source_id=sid, original_name="修订.txt", source_path="synthetic.txt", raw_text="栈：新版。")
        else:
            with store._write_lock, store._conn() as conn:
                conn.execute("UPDATE kg_course_sources SET active=0,revision=revision+1 WHERE course_id=?", (cid,))
        provider.release.set()
        result = pending.result(5)
    source = result["sources"][0]
    assert source["status"] in {"cancelled", "interrupted"}
    assert source["payload"] == {}
    assert store._conn().execute("SELECT COUNT(*) FROM kg_concepts").fetchone()[0] == 0


def test_reload_expired_claim_is_interrupted(course_context):
    store, _, cid, sid = course_context
    clock = [datetime(2026, 10, 22, tzinfo=timezone.utc)]
    svc = service(store, clock=lambda: clock[0])
    did = svc.create_group(cid, [sid], "local", "create_draft_00001")["draft_id"]
    with store._conn() as conn:
        conn.execute("UPDATE kg_extractions SET status='running',lease_until=? WHERE draft_id=?",
                     ((clock[0] - timedelta(seconds=1)).isoformat(), did))
    snap = svc.snapshot(cid, did)
    assert snap["sources"][0]["status"] == "interrupted"
    result = svc.extract_source(cid, did, sid, "extract_source_001", False)
    assert result["sources"][0]["status"] == "ready"


def test_completed_same_input_reuses_result(course_context):
    store, repo, cid, sid = course_context
    svc, provider = service(store), Provider()
    svc = service(store, provider)
    first = svc.create_group(cid, [sid], "llm", "create_draft_00001")
    svc.extract_source(cid, first["draft_id"], sid, "extract_source_001", True)
    again = svc.create_group(cid, [sid], "llm", "create_draft_00002")
    assert again["draft_id"] == first["draft_id"]
    third = add_source(store, repo, cid, "队列：先进先出。")
    other = svc.create_group(cid, [sid, third], "llm", "create_draft_00003")
    result = svc.extract_source(cid, other["draft_id"], sid, "extract_source_002", True)
    cached = next(s for s in result["sources"] if s["source_id"] == sid)
    assert cached["status"] == "ready" and cached["payload"]["cache_origin"]
    assert len(provider.calls) == 1


def test_request_key_conflicts_and_model_consent_before_provider(course_context):
    store, _, cid, sid = course_context
    provider = Provider()
    svc = service(store, provider)
    did = svc.create_group(cid, [sid], "llm", "create_draft_00001")["draft_id"]
    with pytest.raises(ValueError, match="request_key_conflict"):
        svc.create_group(cid, [sid], "local", "create_draft_00001")
    with pytest.raises(ValueError, match="model_consent_required"):
        svc.extract_source(cid, did, sid, "extract_source_001", False)
    assert provider.calls == []
    assert svc.snapshot(cid, did)["sources"][0]["status"] == "pending"


def test_budget_denial_never_reaches_supplier(course_context, tmp_path, monkeypatch):
    from filemate.course_graph.extraction import CourseGraphProvider
    from filemate.llm_client import LLMClient, LLMConfig
    from filemate.runtime_governance import BudgetStore, Limits, resource_scope

    store, _, cid, sid = course_context
    client = LLMClient(LLMConfig(api_key="synthetic-secret-only"))
    calls = []
    monkeypatch.setattr(client._provider, "chat_with_metadata", lambda *a, **k: calls.append(k))
    budget = BudgetStore(tmp_path / "control.sqlite")
    budget.policy = replace(budget.policy, account=Limits(1, 10, 1))
    svc = service(store, CourseGraphProvider(client))
    did = svc.create_group(cid, [sid], "llm", "create_draft_00001")["draft_id"]
    with resource_scope(budget, "u_" + "a" * 32, "account"):
        result = svc.extract_source(cid, did, sid, "extract_source_001", True)
    assert calls == []
    assert result["sources"][0]["status"] == "failed"
    assert result["sources"][0]["error_code"] == "budget_exceeded"


def test_provider_never_receives_unapproved_suffix(course_context):
    store, repo, cid, _ = course_context
    sid = add_source(store, repo, cid, "栈" * 20_000 + "private-suffix")
    provider = Provider()
    svc = service(store, provider)
    did = svc.create_group(cid, [sid], "llm", "create_draft_00001")["draft_id"]
    result = svc.extract_source(cid, did, sid, "extract_source_001", True)
    assert len(provider.calls[0]) == 20_000
    assert "private-suffix" not in provider.calls[0]
    assert result["sources"][0]["payload"]["coverage"]["source_truncated"] is True
