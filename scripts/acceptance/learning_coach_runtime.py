"""Actual isolated HTTP, rollback, restore and JSON1 rejection acceptance."""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx

from filemate.llm_client.exceptions import LLMConfigError
from filemate.operations.personal_backup import PersonalBackup
from filemate.runtime_governance import resource_scope
from filemate.study.orchestrator.coach.commands import CoachCommands
from filemate.study.orchestrator.coach.context import CoachContextReader, read_restore_epoch
from filemate.study.orchestrator.coach.models import (
    CoachConfirm,
    CoachDraft,
    CoachRequest,
    OrchestratorError,
)
from filemate.study.orchestrator.coach.service import CoachService
from filemate.study.orchestrator.models import UndoConfirmRequest
from scripts.acceptance.learning_coach_fixture import ROOT, seed_coach, source_identity
from scripts.acceptance.orchestrator_journey import free_port, start, stop, wait_ready
from scripts.acceptance.orchestrator_runtime import output_path, write_json

API = "/api/learning/orchestrator/coach"


@contextmanager
def sqlite_profile(force_no_json1: bool) -> Iterator[dict[str, int]]:
    """Reject JSON1 SQL functions at connection boundaries without caching results."""
    original = sqlite3.connect
    stats = {"json1_rejections": 0, "sql_statements": 0, "json1_probe_rejected": False}

    def check_sql(sql: str, conn: sqlite3.Connection) -> None:
        stats["sql_statements"] += 1
        if force_no_json1:
            registered = getattr(conn, "registered_json_functions", set())
            for name in re.findall(r"\b(json(?:_\w+)?)\s*\(", sql, re.IGNORECASE):
                if name.lower() not in registered:
                    stats["json1_rejections"] += 1
                    raise sqlite3.OperationalError("no such function: " + name.lower())

    class ProfileCursor(sqlite3.Cursor):
        def execute(self, sql: str, parameters: Any = ()):
            check_sql(sql, self.connection)
            return super().execute(sql, parameters)

        def executemany(self, sql: str, parameters: Any):
            check_sql(sql, self.connection)
            return super().executemany(sql, parameters)

    class ProfileConnection(sqlite3.Connection):
        def execute(self, sql: str, parameters: Any = ()):
            check_sql(sql, self)
            return super().execute(sql, parameters)

        def executemany(self, sql: str, parameters: Any):
            check_sql(sql, self)
            return super().executemany(sql, parameters)

        def executescript(self, sql: str):
            check_sql(sql, self)
            return super().executescript(sql)

        def cursor(self, factory=ProfileCursor):
            return super().cursor(factory)

        def create_function(self, name: str, count: int, function, **kwargs: Any):
            result = super().create_function(name, count, function, **kwargs)
            if force_no_json1 and name.lower().startswith("json"):
                registered = getattr(self, "registered_json_functions", set())
                if function is None:
                    registered.discard(name.lower())
                else:
                    registered.add(name.lower())
                self.registered_json_functions = registered
            return result

    def connect(*args: Any, **kwargs: Any):
        kwargs["factory"] = ProfileConnection
        return original(*args, **kwargs)

    sqlite3.connect = connect
    try:
        probe = connect(":memory:")
        try:
            probe.execute("SELECT json_extract('{}', '$')")
        except sqlite3.OperationalError:
            stats["json1_probe_rejected"] = True
        finally:
            probe.close()
        yield stats
    finally:
        sqlite3.connect = original


@contextmanager
def start_api(
    case: dict[str, Any], *, force_no_json1: bool = False, enabled: bool = True
) -> Iterator[tuple[httpx.Client, str]]:
    """Run only a new loopback process against the fixture database."""
    root = case["root"].resolve()
    db = case["store"].db_path.resolve()
    if db.parent != root or db.name != "synthetic.db":
        raise ValueError("owned_fixture_database_required")
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ) | {
        "PYTHONUTF8": "1",
        "FILEMATE_ENV": "development",
        "FILEMATE_IDENTITY_MODE": "local",
        "FILEMATE_DATA_DIR": str(root),
        "FILEMATE_DB_PATH": str(db),
        "FILEMATE_UPLOAD_DIR": str(root / "inbox"),
        "FILEMATE_ARCHIVE_DIR": str(root / "archive"),
        "FILEMATE_ENABLE_LEARNING_ORCHESTRATOR": "1",
        "FILEMATE_ENABLE_LEARNING_COACH": "1" if enabled else "0",
        "FILEMATE_ENABLE_COURSE_GRAPH": "1",
        "FILEMATE_ENABLE_WRONGBOOK_V2": "1",
        "FILEMATE_HOST": "127.0.0.1",
        "FILEMATE_PORT": str(port),
        "FILEMATE_CORS_ORIGINS": base,
        "FILEMATE_FIXTURE_NO_JSON1": "1" if force_no_json1 else "0",
        "NO_PROXY": "127.0.0.1,localhost,::1",
    }
    suffix = "enabled" if enabled else "disabled"
    with (root / f"http-{suffix}.log").open("xb") as log:
        process = start(
            [sys.executable, "-m", "scripts.acceptance.learning_coach_runtime", "--serve"],
            env,
            ROOT,
            log,
        )
        try:
            wait_ready(base + "/api/health", process)
            with httpx.Client(
                base_url=base, timeout=30, trust_env=False, headers={"Origin": base}
            ) as client:
                yield client, base
        finally:
            stop(process)


def serve() -> None:
    """Install test-only faults before serving the real application."""
    with sqlite_profile(os.environ.get("FILEMATE_FIXTURE_NO_JSON1") == "1") as stats:
        serve_application(stats)


def serve_application(stats: dict[str, Any]) -> None:
    """Import and serve only after the selected SQLite profile is active."""
    import uvicorn

    import server
    from filemate.study.orchestrator.coach import api

    original_service, original_reader = api.CoachService, api.CoachContextReader

    def missing_credentials():
        raise LLMConfigError("synthetic fixture has no external provider")

    class SafeService(original_service):
        def __init__(self, storage, **kwargs):
            super().__init__(storage, **kwargs, config_factory=missing_credentials)

    class FaultReader(original_reader):
        def read(self, body):
            if (Path(os.environ["FILEMATE_DATA_DIR"]) / "fail-context-read").exists():
                raise sqlite3.OperationalError("synthetic database failure")
            return super().read(body)

    api.CoachService, api.CoachContextReader = SafeService, FaultReader

    @server.app.middleware("http")
    async def mark_profile(request, call_next):
        response = await call_next(request)
        response.headers["X-FileMate-Fixture-Json1-Rejected"] = str(
            stats["json1_probe_rejected"]
        ).lower()
        return response

    uvicorn.run(
        server.app, host="127.0.0.1", port=int(os.environ["FILEMATE_PORT"]), access_log=False
    )


def run_runtime(root: Path, *, force_no_json1: bool = False) -> dict[str, Any]:
    """Prove rollback, old-authority expiry and feature-fault isolation on actual data."""
    with ExitStack() as stack:
        stats = stack.enter_context(sqlite_profile(force_no_json1))
        case = seed_coach(root, "exam")
        stack.enter_context(
            resource_scope(
                case["budget_store"], "local", "local", managed_db_path=case["store"].db_path
            )
        )
        store, body = case["store"], case["input"]
        checks: dict[str, bool] = {}
        try:
            clock = lambda: case["now"]
            reader = CoachContextReader(store, clock=clock)
            context = reader.read(body)
            request = CoachRequest(
                input=body,
                expected_context_revision=context.context_revision,
                request_key="synthetic_runtime_rule_0001",
                mode="rule",
            )
            service = CoachService(store, clock=clock)
            run = service.request(request)
            assert run.proposal is not None
            draft = CoachDraft(
                work_id=run.work_id,
                expected_context_revision=run.context_revision,
                days=[day.model_dump(exclude={"schedule"}) for day in run.proposal.days],
                new_actions=run.proposal.new_actions,
            )
            commands = CoachCommands(store, clock=clock)
            preview = commands.preview(draft)
            confirm = CoachConfirm.model_validate(
                draft.model_dump()
                | {
                    "request_key": "synthetic_runtime_confirm_01",
                    "confirmation_token": preview.confirmation_token,
                    "confirmed": True,
                }
            )
            count = store._conn().execute("SELECT COUNT(*) FROM study_plans").fetchone()[0]
            store._conn().execute(
                "CREATE TEMP TRIGGER synthetic_abort_plan BEFORE INSERT ON study_plans BEGIN SELECT RAISE(ABORT,'synthetic fault'); END"
            )
            store._conn().commit()
            failed = False
            try:
                commands.confirm(confirm)
            except sqlite3.Error:
                failed = True
            checks["transaction_failure_rolled_back"] = (
                failed
                and store._conn().execute("SELECT COUNT(*) FROM study_plans").fetchone()[0] == count
                and commands.find(confirm.request_key) is None
            )
            store._conn().execute("DROP TRIGGER synthetic_abort_plan")
            store._conn().commit()
            receipt = commands.confirm(confirm)
            undo = commands.preview_undo(receipt.operation_id)
            backup = PersonalBackup(
                store, "synthetic-learning-coach", root / "inbox", root / "archive"
            )
            raw = backup.export()
            old_epoch = read_restore_epoch(store._conn())
            restore = backup.preview(raw)
            checks["signed_backup_restored"] = (
                backup.restore(restore["backup_id"], restore["confirmation_token"])["restored"]
                is True
            )
            checks["restore_rotated_authority"] = read_restore_epoch(store._conn()) != old_epoch
            checks["confirmed_receipt_survives_restore"] = (
                commands.find(confirm.request_key) == receipt
            )
            rejected = False
            try:
                commands.confirm_undo(
                    receipt.operation_id,
                    UndoConfirmRequest(
                        request_key="synthetic_runtime_undo_0001",
                        confirmation_token=undo.confirmation_token,
                        confirmed=True,
                    ),
                )
            except OrchestratorError as error:
                rejected = error.status_code == 409
            checks["old_undo_authority_rejected"] = rejected
            checks["old_source_readable"] = store.get_source(body.scope.source_ids[0]) is not None
            schema = store.get_schema_version()
            store.close()
            with start_api(case, force_no_json1=force_no_json1) as (client, _):
                response = client.post(API + "/context", json=body.model_dump(mode="json"))
                response.raise_for_status()
                current = response.json()["data"]
                failure_request = {
                    "input": current["input"],
                    "expected_context_revision": current["context_revision"],
                    "request_key": "synthetic_runtime_model_fail",
                    "mode": "llm",
                    "allow_external_model": True,
                    "consent_digest": current["external_digest"],
                }
                failure = client.post(
                    API + "/requests", json=failure_request, headers={"X-FileMate-Action": "model"}
                )
                failure.raise_for_status()
                result = failure.json()["data"]
                checks["model_failure_preserves_rule_result"] = (
                    result["model_status"] == "failed"
                    and result["effective_mode"] == "rule_fallback"
                    and result["proposal"] is not None
                )
                marker = root / "fail-context-read"
                marker.write_text("synthetic", encoding="utf-8")
                damaged = client.post(API + "/context", json=body.model_dump(mode="json"))
                checks["database_fault_isolated"] = (
                    damaged.status_code == 503 and client.get("/api/health").status_code == 200
                )
                marker.unlink()
                checks["database_recovered"] = (
                    client.post(API + "/context", json=body.model_dump(mode="json")).status_code
                    == 200
                )
            with start_api(case, force_no_json1=force_no_json1, enabled=False) as (client, _):
                checks["disabled_feature_preserves_original_flow"] = (
                    client.post(API + "/context", json=body.model_dump(mode="json")).status_code
                    == 503
                    and client.post(
                        "/api/learning/orchestrator/snapshot", json=body.scope.model_dump()
                    ).status_code
                    == 200
                )
            report = source_identity() | {
                "data_type": "synthetic",
                "schema": schema,
                "force_no_json1": force_no_json1,
                "json1_profile": "forced_function_rejection" if force_no_json1 else "native",
                "json1_probe_rejected": stats["json1_probe_rejected"],
                "json1_rejections": stats["json1_rejections"],
                "workload_json1_rejections": stats["json1_rejections"]
                - int(stats["json1_probe_rejected"]),
                "checks": checks,
                "real_supplier_tested": False,
                "status": "PASS" if all(checks.values()) else "FAIL",
            }
            write_json(root / "runtime.json", report)
            return report
        finally:
            store.close()


def main(argv: list[str] | None = None) -> int:
    """Write separate native and forced-function-rejection runtime reports."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    root = output_path(args.output)
    root.mkdir(parents=True)
    os.environ["FILEMATE_ENABLE_LEARNING_ORCHESTRATOR"] = "1"
    os.environ["FILEMATE_ENABLE_LEARNING_COACH"] = "1"
    results = [
        run_runtime(root / label, force_no_json1=forced)
        for label, forced in (("native", False), ("no-json1", True))
    ]
    write_json(
        root / "report.json",
        {
            "results": results,
            "exit_code": 0 if all(row["status"] == "PASS" for row in results) else 1,
        },
    )
    return 0 if all(row["status"] == "PASS" for row in results) else 1


if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve()
    else:
        raise SystemExit(main())
