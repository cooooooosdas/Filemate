# ruff: noqa: F811
"""Unverified work stays visible without becoming ability or goal evidence."""

from datetime import datetime, timedelta, timezone

from filemate.tests.wrongbook.conftest import answer_payload
from filemate.wrongbook.repository import ReviewRepository


def test_overview_mastery_and_growth_exclude_assistance_and_unknown(review_store):
    from filemate.portfolio.growth import REPORT_ZONE, GrowthRepository, ReportRequest
    from filemate.study.knowledge_graph import mastery_metrics

    store, _, _, _, clock = review_store
    clock[0] = datetime.now(timezone.utc) - timedelta(minutes=1)
    repo = ReviewRepository(store, clock=lambda: clock[0])
    repo.submit(answer_payload(review_store, "A", answer_revealed=True))
    repo.submit(answer_payload(review_store, "栈后进先出", index=1, key="synthetic-pending-01"))
    repo.submit(answer_payload(review_store, "A", key="synthetic-self-report-01", self_reported_result="correct"))
    repo.submit(answer_payload(review_store, "A", key="synthetic-objective-01"))
    analytics = store.get_learning_analytics()
    assert analytics["quiz_attempt_count"] == 1
    assert analytics["quiz_attempt_total"] == 4
    assert analytics["unverified_quiz_attempt_count"] == 3
    assert analytics["evidence_profile"]["metrics"]["quiz"]["sample_count"] == 1
    assert analytics["evidence_profile"]["metrics"]["wrong"]["sample_count"] == 0
    attempts = [dict(r) for r in store._conn().execute("SELECT * FROM quiz_attempts")]
    assert mastery_metrics(attempts)["sample_count"] == 1
    today = datetime.now(REPORT_ZONE).date()
    report = GrowthRepository(store).generate(ReportRequest(start_date=today, end_date=today))
    assert report["metrics"]["quiz_attempts"] == 1


def test_due_candidates_exclude_paused_invalid_and_limit_after_filter(review_store):
    store = review_store[0]
    repo = ReviewRepository(store, clock=lambda: review_store[4][0])
    wrong = repo.submit(answer_payload(review_store))["wrong_id"]
    with store._conn() as conn:
        conn.execute("UPDATE wrong_questions SET next_review_at='bad-date' WHERE wrong_id=?", (wrong,))
    assert repo.due_page() == [] and repo.summary()["invalid_time_count"] == 1
    with store._conn() as conn:
        conn.execute("UPDATE wrong_questions SET next_review_at='2000-01-01', schedule_status='paused'")
    assert repo.due_page() == [] and repo.summary()["due_count"] == 0


from filemate.tests.course_graph.conftest import course_context, course_store  # noqa: F401
from filemate.tests.course_graph.test_learning_links import (  # noqa: F401
    confirm,
    learning_context,
)


def test_course_graph_never_converts_pending_null_to_wrong(learning_context):
    from filemate.course_graph.learning_evidence import node_learning_evidence

    store, cid, _, nid, aid, question = learning_context
    confirm(learning_context)
    repo = ReviewRepository(store)
    repo.submit({"artifact_id": aid, "question_index": 0, "expected_question": question,
                 "user_answer": "后进先出", "answer_revealed": True, "request_key": "synthetic-assisted-01"})
    repo.submit({"artifact_id": aid, "question_index": 0, "expected_question": question,
                 "user_answer": "", "action": "dont_know", "request_key": "synthetic-unsure-01"})
    result = node_learning_evidence(store, cid, nid, now=datetime.now(timezone.utc))
    assert result["counts"]["attempts"] == 0
    assert result["status"] == "no_evidence"
