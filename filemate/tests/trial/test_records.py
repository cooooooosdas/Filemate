"""Trial records remain idempotent, private and removable with explicit previews."""

import pytest

from filemate.study.orchestrator.models import OrchestratorError

from .test_weekly import reader, scope


def feedback(key="feedback_request_0001", **changes):
    from filemate.study.trial.models import FeedbackInput

    return FeedbackInput.model_validate(
        {
            "request_key": key,
            "confirmed": True,
            "category": "bug",
            "module": "today",
            "description": "原创合成反馈内容，用于验证试行版保存与恢复流程。",
            "steps": "打开今日行动，读取当前安排。",
            "client_version": "synthetic-test",
            **changes,
        }
    )


def records(world):
    from filemate.study.trial.records import TrialRecords

    return TrialRecords(world["store"], clock=lambda: world["now"][0])


def test_feedback_request_replays_and_changed_content_conflicts(world):
    service = records(world)
    receipt = service.save_feedback(feedback())
    assert service.save_feedback(feedback()) == receipt
    assert service.find_request(feedback().request_key) == receipt
    assert service.list_records("feedback")["total"] == 1
    with pytest.raises(OrchestratorError, match="request_key_conflict"):
        service.save_feedback(
            feedback(description="另一份已经改变的合成反馈内容，用于拒绝同键覆盖。")
        )
    summary = service.list_records("feedback")["items"][0]
    assert "description" not in summary and "steps" not in summary
    assert service.detail(receipt["record_id"])["content"]["description"] == feedback().description


def test_deleted_requests_are_terminal_and_do_not_refund_daily_admissions(world):
    from filemate.study.trial.models import DeleteRecord

    service = records(world)
    for index in range(10):
        body = feedback(f"synthetic_feedback_{index:04}")
        receipt = service.save_feedback(body)
        preview = service.delete_preview(receipt["record_id"])
        command = DeleteRecord(
            request_key=f"delete_feedback_{index:04}",
            confirmed=True,
            confirmation_token=preview["confirmation_token"],
        )
        deleted = service.delete_confirm(receipt["record_id"], command)
        assert service.delete_confirm(receipt["record_id"], command) == deleted
        assert service.find_request(body.request_key)["status"] == "deleted"
        with pytest.raises(OrchestratorError) as error:
            service.save_feedback(body)
        assert error.value.status_code == 410
    with pytest.raises(OrchestratorError) as error:
        service.save_feedback(feedback("synthetic_feedback_extra"))
    assert error.value.status_code == 429
    assert service.list_records("feedback")["total"] == 0
    rows = (
        world["store"]
        ._conn()
        .execute("SELECT content FROM artifacts WHERE artifact_type='trial_record_request'")
        .fetchall()
    )
    assert len(rows) == 20
    assert all(feedback().description not in row["content"] for row in rows)


def test_reflection_binds_scope_and_revision_to_server_week(world):
    from filemate.study.trial.models import ReflectionInput

    weekly = reader(world).read(scope(world))
    body = ReflectionInput(
        scope=scope(world),
        expected_revision=weekly.revision,
        request_key="reflection_request_0001",
        confirmed=True,
        reason="time",
        notes="今天时间不足，下周先完成已经确定的复习任务。",
    )
    receipt = records(world).save_reflection(body)
    stored = records(world).detail(receipt["record_id"])["content"]
    assert stored["week_start"] == weekly.week_start
    assert stored["summary"]["total_tasks"] == 0
    assert stored["notes"] == body.notes
    with pytest.raises(OrchestratorError, match="weekly_revision_changed"):
        records(world).save_reflection(
            body.model_copy(
                update={"request_key": "reflection_request_0002", "expected_revision": "0" * 64}
            )
        )


def test_record_and_request_marker_rollback_together(world, monkeypatch):
    from filemate.study.trial import records as module

    original = module.put

    def fail_marker(conn, identifier, kind, *args, **kwargs):
        if kind == "trial_record_request":
            raise OSError("synthetic write failure")
        return original(conn, identifier, kind, *args, **kwargs)

    monkeypatch.setattr(module, "put", fail_marker)
    with pytest.raises(OSError):
        records(world).save_feedback(feedback())
    assert records(world).list_records()["total"] == 0
    assert records(world).find_request(feedback().request_key) is None


def test_generic_artifact_writers_cannot_forge_or_modify_trial_records(world):
    with pytest.raises(ValueError):
        world["store"].save_artifact(artifact_type="trial_feedback", content={})
    receipt = records(world).save_feedback(feedback())
    with pytest.raises(ValueError):
        world["store"].update_artifact(
            receipt["record_id"], title="changed", content={"changed": True}
        )


def test_personal_backup_preserves_deleted_tombstones_and_revokes_old_delete_tokens(
    world, tmp_path
):
    from filemate.operations.personal_backup import PersonalBackup
    from filemate.study.trial.models import DeleteRecord

    service = records(world)
    saved = service.save_feedback(feedback())
    preview = service.delete_preview(saved["record_id"])
    command = DeleteRecord(
        request_key="backup_delete_feedback_0001",
        confirmed=True,
        confirmation_token=preview["confirmation_token"],
    )
    service.delete_confirm(saved["record_id"], command)
    backup = PersonalBackup(
        world["store"], "synthetic-trial-owner", tmp_path / "inbox", tmp_path / "archive"
    )
    raw = backup.export()
    service.save_feedback(feedback("feedback_after_backup_0001"))
    restoration = backup.preview(raw)
    result = backup.restore(restoration["backup_id"], restoration["confirmation_token"])
    assert result["restored"] is True
    assert service.list_records()["total"] == 0
    assert service.find_request(feedback().request_key)["status"] == "deleted"
    assert service.find_request(command.request_key)["deleted"] is True
    with pytest.raises(OrchestratorError) as error:
        service.save_feedback(feedback())
    assert error.value.status_code == 410
    with pytest.raises(ValueError):
        from filemate.execution import data_actions

        data_actions.check(
            world["store"]._conn(),
            "trial_record_delete",
            saved["record_id"],
            command.confirmation_token,
            None,
        )
