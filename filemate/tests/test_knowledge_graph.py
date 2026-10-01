"""个人知识图谱的提取、证据和确认边界。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from filemate.study.knowledge_graph import (
    RELATIONS,
    extract_local,
    learning_profile,
    mastery_metrics,
    recommend_plan,
    validate_graph,
)


def test_local_extraction_is_grounded_and_supports_relations():
    text = "数据结构包含树。树包含二叉树。二叉树是堆的前置知识。堆应用于堆排序。\n栈：后进先出的线性表。"
    graph = validate_graph(extract_local(text), text, "source", [])
    assert {n["label"] for n in graph["nodes"]} >= {"树", "二叉树", "堆", "堆排序", "栈"}
    assert {e["relation"] for e in graph["edges"]} >= {"contains", "prerequisite", "applies_to"}
    assert all(n["excerpt"] in text for n in graph["nodes"])


def test_hallucinated_or_invalid_graph_is_rejected():
    for payload in (
        {"nodes": [{"label": "不存在", "excerpt": "不存在"}], "edges": []},
        {"nodes": [{"label": "树", "excerpt": "树"}], "edges": [
            {"from": "树", "to": "堆", "relation": "contains", "excerpt": "树"}]},
        {"nodes": "not a list", "edges": []},
    ):
        with pytest.raises((ValueError, TypeError)):
            validate_graph(payload, "树包含二叉树。", "source", [])


def test_distinct_labels_cannot_share_a_graph_node_id():
    text = "A-B是AB的前置知识。"
    with pytest.raises(ValueError, match="相同标识"):
        validate_graph(extract_local(text), text, "source", [])


def test_local_extraction_recognizes_plain_language_study_notes():
    text = "TCP 是面向连接的可靠传输协议。UDP 是无连接协议。"
    graph = validate_graph(extract_local(text), text, "course", [])
    assert [node["label"] for node in graph["nodes"]] == ["TCP", "UDP"]


def test_metrics_use_only_observed_attempts_and_recency():
    now = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
    empty = mastery_metrics([], now=now)
    assert empty["correct_rate"] is None and empty["confidence"] == "待评测"
    assert empty["study_time"] is None
    attempts = [{"is_correct": 0, "created_at": "2026-09-29T01:00:00"}] * 3
    assert mastery_metrics(attempts, now=now)["status"] == "高频错误"
    correct = [{"is_correct": 1, "created_at": "2026-09-29T01:00:00"}] * 5
    assert mastery_metrics(correct, now=now)["status"] == "基本掌握"
    old = [{"is_correct": 1, "created_at": "2026-07-01T01:00:00"}] * 5
    assert mastery_metrics(old, now=now)["status"] == "长期遗忘风险"


def test_all_relations_limits_and_no_speculative_links():
    text = ("甲是乙的前置知识\n甲包含乙\n甲属于乙\n甲依赖乙\n"
            "甲相似于乙\n甲容易混淆于乙\n甲应用于乙\n甲对应题型乙")
    graph = validate_graph(extract_local(text), text, "course", [])
    assert {edge["relation"] for edge in graph["edges"]} == set(RELATIONS)
    limited = extract_local("\n".join(f"# 概念{i}" for i in range(100)))
    assert len(limited["nodes"]) == 80
    assert extract_local("甲可能依赖乙。甲不属于乙。") == {"nodes": [], "edges": []}
    with pytest.raises(ValueError):
        validate_graph(extract_local(""), "", "empty", [])


def test_explicit_natural_language_relations_keep_the_full_quote():
    text = "堆作为完全二叉树的一个特例，具有以下特性。实际上，堆通常用于实现优先队列，大顶堆相当于元素按从大到小的顺序出队的优先队列。"
    graph = validate_graph(extract_local(text), text, "course", [])
    assert {n["label"] for n in graph["nodes"]} == {"堆", "完全二叉树", "优先队列"}
    assert {e["relation"] for e in graph["edges"]} == {"belongs_to", "applies_to"}
    assert all(edge["excerpt"] in text for edge in graph["edges"])


def test_metrics_sort_timezones_and_exclude_corrupt_or_future_records():
    now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    attempts = [
        {"is_correct": 1, "created_at": "2026-10-01T08:00:00+08:00"},
        {"is_correct": 0, "created_at": "2026-10-01T01:00:00Z"},
        {"is_correct": "false", "created_at": "2026-10-01T02:00:00Z"},
        {"is_correct": 0, "created_at": "broken"},
        {"is_correct": 0, "created_at": "2099-01-01T00:00:00Z"},
    ]
    metrics = mastery_metrics(attempts, now=now)
    assert metrics["sample_count"] == 2 and metrics["correct_rate"] == 0.5
    assert metrics["excluded_sample_count"] == 3
    assert metrics["last_reviewed_at"] == "2026-10-01T01:00:00Z"
    recent = mastery_metrics(attempts[:2] * 10, now=now)
    assert recent["sample_count"] == 20 and recent["recent_sample_count"] == 10
    assert recent["correct_rate"] == 0  # 最近的十次来自 UTC 01:00，而非字符串排序。


def test_profile_evidence_coverage_prerequisites_and_recovery():
    now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    empty = mastery_metrics([], now=now)
    wrong = mastery_metrics([{"is_correct": 0, "created_at": "2026-10-01T01:00:00"}] * 3, now=now)
    nodes = [
        {"id": "pre", "label": "前置", "source_id": "a", "metrics": empty, "wrong_ids": []},
        {"id": "target", "label": "目标", "source_id": "a", "metrics": wrong, "wrong_ids": ["w1"]},
    ]
    edges = [{"from": "pre", "to": "target", "relation": "prerequisite", "excerpt": "前置是目标的前置知识"}]
    profile = learning_profile(nodes, edges)
    assert profile["observed_node_count"] == 1 and profile["unassessed_node_count"] == 1
    assert profile["attempt_count"] == 3 and profile["study_time"] is None
    assert profile["weaknesses"][0]["prerequisites"][0]["excerpt"] == edges[0]["excerpt"]
    assert len(profile["weaknesses"][0]["reasons"]) == 2
    recovered = mastery_metrics([{"is_correct": 1, "created_at": "2026-10-01T02:00:00"}] * 10, now=now)
    recovered["wrong_count"] = 3
    nodes[1].update(metrics=recovered, wrong_ids=[])
    assert learning_profile(nodes, edges)["weaknesses"] == []


def test_plan_rejects_cycles_and_ignores_unrelated_graph_changes():
    nodes = [{"id": key, "label": key, "source_id": "a", "metrics": mastery_metrics([])} for key in ("a", "b", "c", "d")]
    edge = {"from": "a", "to": "b", "relation": "prerequisite", "excerpt": "a是b的前置知识"}
    graph = {"nodes": nodes, "edges": [edge]}
    first = recommend_plan(graph, "b")
    assert [step["node_id"] for step in first["steps"]] == ["a", "b"]
    graph["edges"].append({"from": "c", "to": "d", "relation": "depends_on", "excerpt": "c依赖d"})
    assert recommend_plan(graph, "b")["evidence_revision"] == first["evidence_revision"]
    graph["edges"].append({"from": "b", "to": "a", "relation": "prerequisite", "excerpt": "b是a的前置知识"})
    with pytest.raises(ValueError, match="循环"):
        recommend_plan(graph, "b")
