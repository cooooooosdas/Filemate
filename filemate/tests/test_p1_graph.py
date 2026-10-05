# ruff: noqa: F811
"""图谱聚合复杂度、只读快照和有界 API 的回归。"""

import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from filemate.execution.storage import SQLiteStorage
from filemate.study.knowledge_graph import build_graph, extract_local, validate_graph
from filemate.tests.test_server_persistence import server_module  # noqa: F401


def seed(store):
    text = "\n".join(f"Concept{i:05d}：明确合成定义。" for i in range(60))
    sid = store.save_source(original_name="合成图谱", source_path="synthetic", raw_text=text)
    payload = validate_graph(extract_local(text), text, sid, [])
    batch = store.save_graph_batch(sid, store.get_source_revision(sid), "local", payload)
    store.transition_graph_batch(batch["batch_id"], "confirm")
    return sid, batch


def test_graph_reads_source_and_evidence_once_per_source(tmp_path, monkeypatch):
    store = SQLiteStorage(tmp_path / "test.db")
    store.init_schema()
    seed(store)
    source = Mock(wraps=store.get_source)
    evidence = Mock(wraps=store.get_graph_learning_evidence)
    monkeypatch.setattr(store, "get_source", source)
    monkeypatch.setattr(store, "get_graph_learning_evidence", evidence)
    graph = build_graph(store)
    assert len(graph["nodes"]) == 60
    assert source.call_count <= 3 and evidence.call_count == 1
    store.close()


def test_snapshot_is_read_only_consistent_and_does_not_block_writer(tmp_path):
    store = SQLiteStorage(tmp_path / "snapshot.db")
    store.init_schema()
    store.save_source(original_name="first", source_path="synthetic-first")
    with store.read_snapshot() as snapshot:
        assert len(snapshot.list_sources()) == 1
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(store.save_source, original_name="second", source_path="synthetic-second").result(timeout=2)
        assert len(snapshot.list_sources()) == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            snapshot.save_source(original_name="forbidden", source_path="never")
    assert len(store.list_sources()) == 2
    store.close()


def test_graph_page_and_lazy_details_preserve_complete_data(server_module):
    module, store = server_module
    _, batch = seed(store)
    with TestClient(module.app) as client:
        page = client.get("/api/knowledge-graph?limit=20&offset=20").json()["data"]
        assert page["pagination"]["total"] == 60 and len(page["nodes"]) == 20
        assert page["profile"]["unassessed_node_count"] == 60
        assert page["batches"][0]["payload_loaded"] is False
        assert page["batches"][0]["payload"]["nodes"] == []
        detail = client.get("/api/knowledge-graph/batches/" + batch["batch_id"]).json()["data"]
        assert len(detail["payload"]["nodes"]) == 60
        found = client.get("/api/knowledge-graph?q=Concept00059").json()["data"]
        assert len(found["nodes"]) == 1
        node = client.get("/api/knowledge-graph/nodes/" + found["nodes"][0]["id"]).json()["data"]
        assert node["label"] == "Concept00059" and node["metrics"]["correct_rate"] is None
        assert client.get("/api/knowledge-graph?limit=201").status_code == 422
        assert client.get("/api/knowledge-graph/nodes/missing").status_code == 404
    assert len(build_graph(store)["nodes"]) == 60


def test_graph_aggregation_is_bounded_per_workspace_without_blocking_writes(server_module, monkeypatch):
    module, store = server_module
    seed(store)
    import filemate.study.knowledge_graph as implementation
    original = implementation.build_graph
    lock = threading.Lock()
    active = peak = 0
    def observed(snapshot):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            with ThreadPoolExecutor(max_workers=1) as writer:
                writer.submit(store.save_source, original_name='concurrent synthetic', source_path='owned').result(timeout=2)
            time.sleep(0.02)
            return original(snapshot)
        finally:
            with lock:
                active -= 1
    monkeypatch.setattr(implementation, 'build_graph', observed)
    with TestClient(module.app) as client, ThreadPoolExecutor(max_workers=4) as readers:
        statuses = list(readers.map(lambda _: client.get('/api/knowledge-graph').status_code, range(4)))
    assert statuses == [200] * 4 and peak == 1
