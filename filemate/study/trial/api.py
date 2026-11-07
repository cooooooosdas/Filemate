"""Tenant-bound trial endpoints with strict body and pagination validation."""

from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query, Request

from filemate.study.orchestrator.api import DecisionRoute, response
from filemate.study.orchestrator.models import (
    OrchestratorError,
    ScopeRequest,
    StrictRequest,
    utc_now,
)

from .models import DeleteRecord, FeedbackInput, ReflectionInput
from .records import TrialRecords, enabled
from .weekly import WeeklyReader


class TrialRoute(DecisionRoute):
    def validate_query(self, request: Request) -> None:
        if request.method == "GET" and self.path == "/api/trial/records":
            pairs = list(request.query_params.multi_items())
            keys = {key for key, _ in pairs}
            if keys <= {"kind", "limit", "offset"} and len(keys) == len(pairs):
                return
        super().validate_query(request)


def require_enabled():
    if not enabled():
        raise OrchestratorError("trial_workspace_disabled", 503)


def create_router(get_storage: Callable):
    router = APIRouter(prefix="/api/trial", route_class=TrialRoute)

    def records():
        return TrialRecords(get_storage(), clock=utc_now)

    @router.get("/capabilities")
    def capabilities():
        return response(
            {
                "enabled": enabled(),
                "ui_contract": "trial-workspace-v1",
                "limits": {"feedback_per_day": 10, "text_characters": 2000, "page": 50},
            }
        )

    @router.post("/weekly/context", dependencies=[Depends(require_enabled)])
    def weekly(body: ScopeRequest):
        return response(WeeklyReader(get_storage(), clock=utc_now).read(body))

    @router.post("/reflections", dependencies=[Depends(require_enabled)])
    def reflection(body: ReflectionInput):
        return response(records().save_reflection(body))

    @router.post("/feedback", dependencies=[Depends(require_enabled)])
    def feedback(body: FeedbackInput):
        return response(records().save_feedback(body))

    @router.get("/requests/{request_key}")
    def find_request(request_key: str = Path(pattern=r"^[A-Za-z0-9_-]{16,80}$")):
        result = records().find_request(request_key)
        if result is None:
            raise OrchestratorError("request_not_found", 404)
        return response(result)

    @router.get("/records")
    def list_records(
        kind: Literal["reflection", "feedback"] | None = None,
        limit: int = Query(default=20, ge=1, le=50),
        offset: int = Query(default=0, ge=0, le=10000),
    ):
        return response(records().list_records(kind, limit=limit, offset=offset))

    @router.get("/records/{record_id}")
    def detail(record_id: str = Path(pattern=r"^trial-record-[a-f0-9]{64}$")):
        return response(records().detail(record_id))

    @router.post("/records/{record_id}/delete-preview")
    def delete_preview(
        body: StrictRequest, record_id: str = Path(pattern=r"^trial-record-[a-f0-9]{64}$")
    ):
        return response(records().delete_preview(record_id))

    @router.post("/records/{record_id}/delete-confirm")
    def delete_confirm(
        body: DeleteRecord, record_id: str = Path(pattern=r"^trial-record-[a-f0-9]{64}$")
    ):
        return response(records().delete_confirm(record_id, body))

    return router
