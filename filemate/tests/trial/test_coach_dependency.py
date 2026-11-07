"""A selected reflection cannot outlive its explicit deletion in derived coach text."""

import pytest

from filemate.runtime_governance import resource_scope
from filemate.study.orchestrator.coach.commands import CoachCommands
from filemate.study.orchestrator.coach.context import CoachContextReader
from filemate.study.orchestrator.coach.models import (
    CoachConfirm,
    CoachDraft,
    CoachInput,
    CoachRequest,
)
from filemate.study.orchestrator.coach.service import CoachService
from filemate.study.orchestrator.models import OrchestratorError
from filemate.study.trial.models import DeleteRecord, ReflectionInput
from filemate.study.trial.records import TrialRecords
from filemate.study.trial.weekly import WeeklyReader
from scripts.acceptance.learning_coach_fixture import seed_coach


def test_deleting_reflection_purges_coach_copy_and_preserves_body_free_receipts(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_ORCHESTRATOR", "1")
    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_COACH", "1")
    case = seed_coach(tmp_path / "case", "exam")
    store = case["store"]
    clock = lambda: case["now"]
    secret = "仅用于合成复盘隐私回归的独有反思正文"
    try:
        with resource_scope(case["budget_store"], "local", "local", managed_db_path=store.db_path):
            records = TrialRecords(store, clock=clock)
            weekly = WeeklyReader(store, clock=clock).read(case["input"].scope)
            saved = records.save_reflection(
                ReflectionInput(
                    scope=weekly.scope,
                    expected_revision=weekly.revision,
                    request_key="reflection_for_coach_0001",
                    confirmed=True,
                    notes=secret,
                )
            )
            body = CoachInput.model_validate(
                case["input"].model_dump()
                | {"reflection_id": saved["record_id"], "question": secret}
            )
            context = CoachContextReader(store, clock=clock).read(body)
            service = CoachService(store, clock=clock)
            run = service.request(
                CoachRequest(
                    input=body,
                    expected_context_revision=context.context_revision,
                    request_key="coach_from_reflection_0001",
                )
            )
            draft = CoachDraft(
                work_id=run.work_id,
                expected_context_revision=run.context_revision,
                days=[day.model_dump(exclude={"schedule"}) for day in run.proposal.days],
                new_actions=run.proposal.new_actions,
                overlap_choices=[],
            )
            commands = CoachCommands(store, clock=clock)
            plan_preview = commands.preview(draft)
            receipt = commands.confirm(
                CoachConfirm.model_validate(
                    draft.model_dump()
                    | {
                        "confirmation_token": plan_preview.confirmation_token,
                        "request_key": "confirm_reflection_coach_0001",
                        "confirmed": True,
                    }
                )
            )
            assert receipt.plan_id is not None
            preview = records.delete_preview(saved["record_id"])
            assert preview["affected"]["learning_coach_results"] >= 1
            assert preview["affected"]["learning_coach_plans"] >= 1
            command = DeleteRecord(
                request_key="delete_reflection_coach_0001",
                confirmed=True,
                confirmation_token=preview["confirmation_token"],
            )
            records.delete_confirm(saved["record_id"], command)
            rows = store._conn().execute("SELECT content FROM artifacts").fetchall()
            assert all(secret not in row["content"] for row in rows)
            assert records.find_request(command.request_key)["deleted"] is True
            assert records.find_request("reflection_for_coach_0001")["status"] == "deleted"
            with pytest.raises(OrchestratorError) as error:
                CoachContextReader(store, clock=clock).read(body)
            assert error.value.status_code == 404
    finally:
        store.close()
