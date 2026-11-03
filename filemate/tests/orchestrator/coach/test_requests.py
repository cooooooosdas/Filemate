"""Durable requests, admission races and failure recovery over real SQLite."""

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from filemate.execution.storage import SQLiteStorage
from filemate.llm_client import LLMConfig
from filemate.runtime_governance import default_scope

from .conftest import coach_module, read_context


class CountingRunner:
    def __init__(self, *, block=False, error=None):
        self.calls = 0
        self.started = threading.Event()
        self.release = threading.Event()
        self.block, self.error = block, error
        self.options = None

    def run(self, config, scope, **kwargs):
        self.calls += 1
        self.options = kwargs
        self.started.set()
        if self.block:
            assert self.release.wait(8), "test runner was not released"
        return (
            {"error_code": self.error}
            if self.error
            else {"output": {"explanations": [], "task_order": [], "new_actions": []}}
        )


@pytest.fixture
def service_case(coach_case, monkeypatch):
    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_ORCHESTRATOR", "1")
    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_COACH", "1")
    return coach_case


def request(case, key="synthetic_coach_request_0001", *, mode="rule", **changes):
    context = read_context(case)
    return coach_module("models").CoachRequest.model_validate(
        {
            "input": context.input.model_dump(),
            "expected_context_revision": context.context_revision,
            "request_key": key,
            "mode": mode,
            "allow_external_model": mode == "llm",
            "consent_digest": context.external_digest if mode == "llm" else None,
            **changes,
        }
    )


def service(case, runner=None, config_factory=None):
    return coach_module("service").CoachService(
        case["storage"],
        clock=case["clock"],
        runner=runner,
        config_factory=config_factory or (lambda: LLMConfig(api_key="synthetic-private-key-only")),
    )


def test_rule_replay_is_persistent_and_never_reads_credentials(service_case):
    def forbidden():
        pytest.fail("local rule path accessed model credentials")

    api = service(service_case, config_factory=forbidden)
    body = request(service_case)
    first = api.request(body)
    assert first.status == "ready" and first.model_status == "not_requested"
    assert api.request(body).work_id == first.work_id
    assert api.get(body.request_key).proposal == first.proposal
    fresh_store = SQLiteStorage(service_case["storage"].db_path)
    try:
        fresh = coach_module("service").CoachService(fresh_store, clock=service_case["clock"])
        assert fresh.get(body.request_key).proposal == first.proposal
    finally:
        fresh_store.close()


def test_same_key_never_calls_twice_and_body_conflict_is_explicit(service_case):
    runner = CountingRunner(block=True)
    api, body = service(service_case, runner), request(service_case, mode="llm")
    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(api.request, body)
        assert runner.started.wait(5)
        other = pool.submit(api.request, body).result(timeout=3)
        assert other.status == "running"
        runner.release.set()
        assert owner.result(timeout=5).status == "ready"
    assert runner.calls == 1
    assert api.request(body).model_status == "succeeded"
    with pytest.raises(coach_module("models").OrchestratorError, match="request_conflict"):
        api.request(body.model_copy(update={"consent_digest": "0" * 64}))


def test_pending_admission_race_does_not_interrupt_owner(service_case, monkeypatch):
    scope = default_scope()
    original = scope.store.admit_learning
    entered, release = threading.Event(), threading.Event()

    def held(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        return original(*args, **kwargs)

    monkeypatch.setattr(scope.store, "admit_learning", held)
    api, body = service(service_case), request(service_case)
    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(api.request, body)
        assert entered.wait(5)
        assert api.request(body).status == "running"
        release.set()
        assert owner.result(timeout=5).status == "ready"


def test_admission_survives_missing_local_receipt_and_same_key_never_restarts(service_case):
    api, body = service(service_case), request(service_case)
    first = api.request(body)
    with service_case["storage"]._conn() as conn:
        conn.execute(
            "DELETE FROM artifacts WHERE artifact_type IN ('learning_coach_request','learning_coach_result','learning_coach_runtime')"
        )
    recovered = api.request(body)
    assert recovered.status == "interrupted" and recovered.proposal is None
    assert recovered.work_id == first.work_id


def test_changed_body_after_lost_receipt_is_still_a_request_conflict(service_case):
    api = service(service_case)
    api.request(request(service_case))
    with service_case["storage"]._conn() as conn:
        conn.execute(
            "DELETE FROM artifacts WHERE artifact_type IN ('learning_coach_request','learning_coach_result','learning_coach_runtime')"
        )
    changed = service_case | {
        "input_data": service_case["input_data"] | {"question": "改成另一个学习问题"}
    }
    with pytest.raises(coach_module("models").OrchestratorError) as error:
        api.request(request(changed))
    assert error.value.status_code == 409


def test_thirty_first_request_is_denied_and_quota_does_not_follow_business_restore(service_case):
    api = service(service_case)
    backup = sqlite3.connect(":memory:")
    service_case["storage"]._conn().backup(backup)
    for index in range(30):
        assert (
            api.request(request(service_case, key=f"synthetic_quota_request_{index:04}")).status
            == "ready"
        )
    backup.backup(service_case["storage"]._conn())
    backup.close()
    with pytest.raises(coach_module("models").OrchestratorError) as error:
        api.request(request(service_case, key="synthetic_quota_request_0031"))
    assert error.value.status_code == 429


def test_model_does_not_hold_write_transaction_and_another_model_is_denied(service_case):
    runner = CountingRunner(block=True)
    api, body = service(service_case, runner), request(service_case, mode="llm")
    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(api.request, body)
        assert runner.started.wait(5)
        other = SQLiteStorage(service_case["storage"].db_path)
        try:
            assert other.save_artifact(artifact_type="notes", content={"synthetic": True})
        finally:
            other.close()
        with pytest.raises(coach_module("models").OrchestratorError) as error:
            api.request(request(service_case, key="synthetic_second_model_request", mode="llm"))
        assert error.value.status_code == 429
        runner.release.set()
        assert owner.result(timeout=5).status == "ready"
    assert runner.calls == 1


@pytest.mark.parametrize("action", ["cancel", "expire", "source", "restore", "midnight"])
def test_cancel_or_changed_epoch_cannot_publish_late_result(service_case, action):
    runner = CountingRunner(block=True)
    api, body = service(service_case, runner), request(service_case, mode="llm")
    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(api.request, body)
        assert runner.started.wait(5)
        if action == "cancel":
            assert api.cancel(body.request_key).status == "cancelled"
        elif action == "expire":
            service_case["world"]["now"][0] += timedelta(seconds=121)
        elif action == "source":
            service_case["storage"].delete_source(service_case["world"]["sources"][0])
        elif action == "restore":
            conn = service_case["storage"]._conn()
            row = conn.execute(
                "SELECT artifact_id,content FROM artifacts WHERE artifact_type='learning_coach_runtime'"
            ).fetchone()
            payload = json.loads(row["content"]) | {"restore_epoch": "synthetic-restored-epoch"}
            conn.execute(
                "UPDATE artifacts SET content=? WHERE artifact_id=?",
                (json.dumps(payload), row["artifact_id"]),
            )
            conn.commit()
        else:
            service_case["world"]["now"][0] += timedelta(days=1)
        runner.release.set()
        final = owner.result(timeout=5)
    assert final.status in {"cancelled", "interrupted", "stale"} and final.proposal is None
    assert api.request(body).status == final.status
    assert runner.calls == 1


@pytest.mark.parametrize(
    "code", ["timeout", "invalid_output", "quota_exceeded", "provider_unavailable"]
)
def test_failure_has_real_status_and_rule_fallback(service_case, code):
    api, body = service(service_case, CountingRunner(error=code)), request(service_case, mode="llm")
    view = api.request(body)
    assert view.status == "ready" and view.effective_mode == "rule_fallback"
    assert view.model_status == "failed" and view.safe_error_code == code
    assert view.proposal is not None


def test_missing_credentials_uses_safe_failure_without_runner(service_case):
    runner = CountingRunner()
    view = service(service_case, runner, lambda: LLMConfig(api_key="")).request(
        request(service_case, mode="llm")
    )
    assert view.model_status == "failed" and view.safe_error_code == "credentials_missing"
    assert runner.calls == 0


def test_missing_consent_or_stale_preview_never_calls_runner(service_case):
    runner = CountingRunner()
    api = service(service_case, runner)
    for changes in (
        {"allow_external_model": False},
        {"consent_digest": "0" * 64},
        {"expected_context_revision": "0" * 64},
    ):
        with pytest.raises((coach_module("models").OrchestratorError, ValueError)):
            api.request(request(service_case, mode="llm", **changes))
    assert runner.calls == 0


def test_protected_control_and_result_artifacts_cannot_be_overwritten(service_case):
    api = service(service_case)
    api.request(request(service_case))
    store = service_case["storage"]
    with store._conn() as conn:
        conn.execute(
            "INSERT INTO artifacts(artifact_id,artifact_type,content,metadata) VALUES ('synthetic-coach-operation','learning_coach_operation','{}','{}')"
        )
    rows = (
        store._conn()
        .execute(
            "SELECT artifact_id,artifact_type FROM artifacts WHERE artifact_type LIKE 'learning_coach_%'"
        )
        .fetchall()
    )
    assert rows
    for row in rows:
        with pytest.raises(ValueError):
            store.update_artifact(row["artifact_id"], title="tampered", content={})
        with pytest.raises(ValueError):
            store.save_artifact(artifact_id=row["artifact_id"], artifact_type="notes", content={})


def test_admission_failure_is_reported_as_failed_model_request(service_case, monkeypatch):
    from filemate.runtime_governance import BudgetExceeded

    def exhausted(*args, **kwargs):
        raise BudgetExceeded("synthetic-private-quota-message")

    monkeypatch.setattr(coach_module("service"), "admit_learning", exhausted)
    api, body = service(service_case), request(service_case, mode="llm")
    with pytest.raises(coach_module("models").OrchestratorError):
        api.request(body)
    saved = api.get(body.request_key)
    assert saved.status == "failed" and saved.model_status == "failed"
    assert saved.proposal is None and saved.safe_error_code == "quota_exceeded"


def test_credential_and_question_bodies_never_enter_control_artifact(service_case):
    api = service(service_case)
    view = api.request(request(service_case, mode="llm"))
    row = (
        service_case["storage"]
        ._conn()
        .execute("SELECT content FROM artifacts WHERE artifact_id=?", (view.work_id,))
        .fetchone()[0]
    )
    assert "synthetic-private-key-only" not in row
    assert service_case["input_data"]["question"] not in row


def test_rule_and_model_history_remain_readable_when_disabled(service_case, monkeypatch):
    api, body = service(service_case), request(service_case)
    saved = api.request(body)
    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_COACH", "0")
    assert api.get(body.request_key) == saved and api.request(body) == saved
    with pytest.raises(coach_module("models").OrchestratorError) as error:
        api.request(request(service_case, key="synthetic_disabled_request_02"))
    assert error.value.status_code == 503


def test_other_workspace_is_independent_of_running_model(service_case, tmp_path):
    runner = CountingRunner(block=True)
    api, body = service(service_case, runner), request(service_case, mode="llm")
    other = SQLiteStorage(tmp_path / "other-coach-space.db")
    other.init_schema()
    goal = other.save_artifact(
        artifact_type="reverse_goal_plan", content={"goal_type": "custom", "tasks": []}
    )
    case = {
        "storage": other,
        "clock": service_case["clock"],
        "input_data": service_case["input_data"] | {"scope": {"goal_id": goal}},
    }
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            owner = pool.submit(api.request, body)
            assert runner.started.wait(5)
            second = CountingRunner()
            assert (
                service(case, second)
                .request(request(case, key="synthetic_other_space_request", mode="llm"))
                .status
                == "ready"
            )
            assert second.calls == 1
            runner.release.set()
            assert owner.result(timeout=5).status == "ready"
    finally:
        runner.release.set()
        other.close()


def test_config_error_is_missing_credentials_and_exception_text_is_never_saved(service_case):
    from filemate.llm_client.exceptions import LLMConfigError

    def broken():
        raise LLMConfigError("synthetic-secret-config-message")

    view = service(service_case, config_factory=broken).request(request(service_case, mode="llm"))
    assert view.safe_error_code == "credentials_missing"
    body = "\n".join(
        row[0]
        for row in service_case["storage"]
        ._conn()
        .execute("SELECT content FROM artifacts WHERE artifact_type LIKE 'learning_coach_%'")
    )
    assert "synthetic-secret-config-message" not in body
