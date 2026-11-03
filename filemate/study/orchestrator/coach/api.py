"""Strict tenant-bound coach endpoints reuse existing authentication and responses."""

from collections.abc import Callable
from datetime import date
from typing import Annotated, ClassVar

from fastapi import APIRouter, Depends, Path
from pydantic import model_validator

from filemate.execution.storage import SQLiteStorage

from ..api import DecisionRoute, response
from ..models import StrictRequest, UndoConfirmRequest, utc_now
from .catalog import read_coach_catalog
from .commands import CoachCommands, CoachDayReader
from .context import CoachContextReader
from .models import (
    CoachCatalogRequest,
    CoachConfirm,
    CoachDraft,
    CoachInput,
    CoachRequest,
    OrchestratorError,
)
from .service import CoachService
from .settings import HARD_TIMEOUT_SECONDS, MAX_REQUESTS_PER_WINDOW, enabled

RequestKey = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{16,80}$")]
OperationId = Annotated[str, Path(pattern=r"^learning-coach-operation-[a-f0-9]{32}$")]


class CoachRoute(DecisionRoute):
    max_body_bytes = 65536
    public_validation_errors = frozenset({"model_consent_required"})
    error_aliases: ClassVar[dict[str, str]] = {
        "learning_coach_disabled": "coach_disabled",
        "coach_quota_exceeded": "coach_request_limit",
        "request_conflict": "request_key_conflict",
        "model_consent_changed": "model_consent_required",
    }


class CoachDayRequest(StrictRequest):
    study_date: str

    @model_validator(mode="after")
    def canonical_date(self):
        if (
            len(self.study_date) != 10
            or date.fromisoformat(self.study_date).isoformat() != self.study_date
        ):
            raise ValueError("invalid_study_date")
        return self


def require_enabled() -> None:
    if not enabled():
        raise OrchestratorError("coach_disabled", 503)


def create_router(get_storage: Callable[[], SQLiteStorage]) -> APIRouter:
    router = APIRouter(prefix="/api/learning/orchestrator/coach", route_class=CoachRoute)

    @router.get("/capabilities")
    def capabilities():
        return response(
            {
                "enabled": enabled(),
                "contract_version": "learning-coach-v1",
                "rule_version": "learning-coach-rules-v1",
                "prompt_version": "learning-coach-v1",
                "quota_window": "rolling_24h",
                "limits": {
                    "sources": 20,
                    "new_actions": 7,
                    "days": 7,
                    "daily_requests": MAX_REQUESTS_PER_WINDOW,
                    "running_models": 1,
                    "model_timeout_seconds": HARD_TIMEOUT_SECONDS,
                    "context_characters": 24000,
                    "message_bytes": 65536,
                    "body_bytes": 65536,
                },
            }
        )

    @router.post("/catalog", dependencies=[Depends(require_enabled)])
    def catalog(body: CoachCatalogRequest):
        return response(read_coach_catalog(get_storage(), body))

    @router.post("/context", dependencies=[Depends(require_enabled)])
    def context(body: CoachInput):
        return response(CoachContextReader(get_storage(), clock=utc_now).read(body))

    @router.post("/requests")
    def request(body: CoachRequest):
        result = CoachService(get_storage(), clock=utc_now).request(body)
        return response(result, status=202 if result.status == "running" else 200)

    @router.get("/requests/{request_key}")
    def get(request_key: RequestKey):
        return response(CoachService(get_storage(), clock=utc_now).get(request_key))

    @router.post("/requests/{request_key}/cancel")
    def cancel(request_key: RequestKey, body: StrictRequest):
        return response(CoachService(get_storage(), clock=utc_now).cancel(request_key))

    @router.post("/proposals/preview", dependencies=[Depends(require_enabled)])
    def preview(body: CoachDraft):
        return response(CoachCommands(get_storage(), clock=utc_now).preview(body))

    @router.post("/proposals/confirm")
    def confirm(body: CoachConfirm):
        return response(CoachCommands(get_storage(), clock=utc_now).confirm(body))

    @router.get("/operations/{request_key}")
    def operation(request_key: RequestKey):
        result = CoachCommands(get_storage(), clock=utc_now).find(request_key)
        if result is None:
            raise OrchestratorError("operation_not_found", 404)
        return response(result)

    @router.post("/operations/{operation_id}/undo-preview")
    def undo_preview(operation_id: OperationId, body: StrictRequest):
        return response(CoachCommands(get_storage(), clock=utc_now).preview_undo(operation_id))

    @router.post("/operations/{operation_id}/undo-confirm")
    def undo_confirm(operation_id: OperationId, body: UndoConfirmRequest):
        return response(
            CoachCommands(get_storage(), clock=utc_now).confirm_undo(operation_id, body)
        )

    @router.post("/day")
    def day(body: CoachDayRequest):
        return response(CoachDayReader(get_storage(), clock=utc_now).read(body.study_date))

    return router
