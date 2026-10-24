# ruff: noqa: F811
"""Exercise learning reads on both CI SQLite and the production SQLite runtime."""

from filemate.course_graph.learning_evidence import list_learning_nodes
from filemate.tests.course_graph.test_learning_evidence import NOW, attempt
from filemate.tests.course_graph.test_learning_links import confirm, learning_context  # noqa: F401


def test_learning_reads_with_empty_and_populated_evidence(learning_context):
    store, cid, _, nid, *_ = learning_context
    page = list_learning_nodes(store, cid, now=NOW)
    node = next(item for item in page['items'] if item['concept_id'] == nid)
    assert node['status'] == 'no_evidence' and node['counts']['attempts'] == 0
    confirm(learning_context)
    attempt(learning_context, NOW, correct=False)
    page = list_learning_nodes(store, cid, now=NOW)
    node = next(item for item in page['items'] if item['concept_id'] == nid)
    assert node['status'] == 'needs_reinforcement'
    assert node['counts']['attempts'] == node['counts']['wrong_attempts_7d'] == 1
