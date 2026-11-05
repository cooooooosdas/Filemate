"""Small semantic gate for the same benchmark used for large capacity runs."""

import importlib.util


def test_capacity_uses_real_reads_and_http_with_stable_ids(tmp_path, monkeypatch):
    assert importlib.util.find_spec("scripts.acceptance.learning_coach_performance")
    from scripts.acceptance.learning_coach_performance import benchmark

    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_ORCHESTRATOR", "1")
    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_COACH", "1")
    result = benchmark(
        tmp_path / "capacity", wrong_count=3, node_count=6, force_no_json1=True, samples=4
    )
    assert result["scope_wrong_count"] == 3
    assert result["scope_node_count"] == 6
    assert result["semantic_ids_stable"] is True
    assert result["context"]["samples"] == 4
    assert result["http_four_concurrent"]["samples"] == 4
    assert result["json1_rejections"] > 0
    assert result["json1_probe_rejected"] is True
    assert result["workload_json1_rejections"] == result["json1_rejections"] - 1
    assert result["scope_relation_count"] == 5
    assert result["supplier_calls"] == 0
