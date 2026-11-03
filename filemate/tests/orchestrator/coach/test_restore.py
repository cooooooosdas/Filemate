# ruff: noqa: F811
"""Real business backup round trips never restore external-call authority."""

import json

import pytest

from filemate.execution import data_actions
from filemate.operations.personal_backup import PersonalBackup
from filemate.study.orchestrator.repository import atomic, put

from .conftest import coach_module
from .test_requests import request, service, service_case  # noqa: F401


def backup_for(case, tmp_path):
    return PersonalBackup(
        case["storage"], "synthetic-coach-owner", tmp_path / "inbox", tmp_path / "archive"
    )


def test_old_backup_without_learning_coach_keeps_its_artifact_inventory(coach_case):
    storage = coach_case["storage"]
    before = [
        tuple(row)
        for row in storage._conn().execute("SELECT * FROM artifacts ORDER BY artifact_id")
    ]
    with atomic(storage) as conn:
        coach_module("privacy").normalize_restored_coach(conn)
    after = [
        tuple(row)
        for row in storage._conn().execute("SELECT * FROM artifacts ORDER BY artifact_id")
    ]
    assert after == before


def test_restore_rotates_epoch_without_resuming_or_refunding(service_case):
    storage = service_case["storage"]
    body = request(service_case, mode="llm")
    repo = coach_module("repository").CoachRepository(storage, clock=service_case["clock"])
    context = (
        coach_module("context")
        .CoachContextReader(storage, clock=service_case["clock"])
        .read(body.input)
    )
    claim = repo.claim(body, context)
    before = coach_module("context").read_restore_epoch(storage._conn())
    with atomic(storage) as conn:
        data_actions.issue(conn, "learning_coach_confirm", claim.view.work_id, "synthetic")
        coach_module("privacy").normalize_restored_coach(conn)
    assert coach_module("context").read_restore_epoch(storage._conn()) != before
    assert repo.find(body.request_key).status == "interrupted"
    assert not repo.active(claim.view.work_id, claim.claim_epoch)
    assert (
        not storage._conn()
        .execute("SELECT 1 FROM data_action_previews WHERE action LIKE 'learning_coach_%'")
        .fetchone()
    )
    assert storage.get_source(service_case["world"]["sources"][0]) is not None


def test_ready_result_survives_signed_personal_backup_but_old_authority_does_not(
    service_case, tmp_path
):
    backup = backup_for(service_case, tmp_path)
    managed = tmp_path / "inbox" / "synthetic-notes.txt"
    managed.parent.mkdir()
    managed.write_text("", encoding="utf-8")
    with service_case["storage"]._conn() as conn:
        conn.execute(
            "UPDATE sources SET source_path=? WHERE source_id=?",
            (str(managed), service_case["world"]["sources"][0]),
        )
    api, body = service(service_case), request(service_case)
    original = api.request(body)
    raw = backup.export()
    p = backup.preview(raw)
    before = coach_module("context").read_restore_epoch(service_case["storage"]._conn())
    assert backup.restore(p["backup_id"], p["confirmation_token"])["restored"]
    assert coach_module("context").read_restore_epoch(service_case["storage"]._conn()) != before
    current_facts = {(f.kind, f.record_id): f.revision for f in api.reader.read(body.input).facts}
    assert {
        f.kind: (f.revision, current_facts.get((f.kind, f.record_id)))
        for f in original.proposal.facts
        if current_facts.get((f.kind, f.record_id)) != f.revision
    } == {}
    assert api.get(body.request_key).work_id == original.work_id
    assert api.get(body.request_key).proposal == original.proposal
    assert not service_case["storage"]._conn().execute("PRAGMA foreign_key_check").fetchall()


def test_personal_restore_blocks_a_live_learning_coach(service_case, tmp_path):
    api, body = service(service_case), request(service_case)
    api.request(body)
    backup = backup_for(service_case, tmp_path)
    raw = backup.export()
    with service_case["storage"]._conn() as conn:
        row = conn.execute(
            "SELECT content FROM artifacts WHERE artifact_id=?",
            (coach_module("repository").work_id(body.request_key),),
        ).fetchone()
        record = json.loads(row[0])
        record["status"] = "running"
        conn.execute(
            "UPDATE artifacts SET content=? WHERE artifact_id=?",
            (json.dumps(record), coach_module("repository").work_id(body.request_key)),
        )
    p = backup.preview(raw)
    with pytest.raises(ValueError, match="教练"):
        backup.restore(p["backup_id"], p["confirmation_token"])


def test_malformed_restored_control_data_is_quarantined_without_breaking_original_data(
    service_case,
):
    storage = service_case["storage"]
    with atomic(storage) as conn:
        put(conn, "synthetic-corrupt-coach", "learning_coach_request", {})
        conn.execute(
            "UPDATE artifacts SET content='synthetic-private-broken-json' WHERE artifact_id='synthetic-corrupt-coach'"
        )
        coach_module("privacy").normalize_restored_coach(conn)
    assert storage.get_source(service_case["world"]["sources"][0]) is not None
    record = storage.get_artifact("synthetic-corrupt-coach")["content"]
    assert record["status"] == "interrupted" and "synthetic-private-broken-json" not in json.dumps(
        record
    )


@pytest.mark.parametrize("kind", ["request", "result", "runtime"])
def test_corrupt_restored_coach_still_returns_a_safe_status(service_case, kind):
    api, body = service(service_case), request(service_case)
    view = api.request(body)
    identifier = {
        "request": view.work_id,
        "result": coach_module("repository").result_id(view.work_id),
        "runtime": coach_module("context").RUNTIME_ID,
    }[kind]
    with atomic(service_case["storage"]) as conn:
        conn.execute(
            "UPDATE artifacts SET content='broken-json' WHERE artifact_id=?", (identifier,)
        )
        coach_module("privacy").normalize_restored_coach(conn)
    result = api.get(body.request_key)
    assert result.status in {"ready", "stale", "interrupted"}
    if kind != "runtime":
        assert result.proposal is None


def test_restore_expires_unused_preview_but_retains_original_confirm_receipt(service_case):
    from .test_commands import commands, confirm_body
    from .test_plans import ready

    case, _, draft = ready(service_case)
    api = commands(case)
    preview = api.preview(draft)
    original = api.confirm(confirm_body(draft, preview))
    with atomic(case["storage"]) as conn:
        coach_module("privacy").normalize_restored_coach(conn)
    assert api.confirm(confirm_body(draft, preview)) == original
    assert api.find(original.request_key) == original
    with pytest.raises(coach_module("models").OrchestratorError):
        api.preview_undo(original.operation_id)
