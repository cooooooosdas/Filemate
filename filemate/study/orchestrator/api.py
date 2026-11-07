"""Thin tenant-bound HTTP contracts; all errors are private and retryable."""

import json
import sqlite3
from collections.abc import Callable
from typing import ClassVar

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError

from filemate.execution.storage import SQLiteStorage

from .commands import OrchestratorCommands
from .context import read_goal_options
from .models import (
    LOCAL_ZONE,
    ConfirmRequest,
    GoalOptionsRequest,
    OrchestratorError,
    PreviewRequest,
    ScopeRequest,
    StrictRequest,
    UndoConfirmRequest,
    utc_now,
)
from .repository import OrchestratorRepository
from .scheduler import RULE_VERSION
from .settings import enabled
from .snapshot import SnapshotReader
from .task_views import project_tasks


def response(data=None, *, status=200, error=None):
    return JSONResponse(status_code=status, content=jsonable_encoder({'success': status < 400, 'data': data, 'error': error}),
                        headers={'Cache-Control': 'no-store'})


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_json_key')
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError('non_finite_json')


class DecisionRoute(APIRoute):
    max_body_bytes = 262144
    error_aliases: ClassVar[dict[str, str]] = {}
    public_validation_errors: ClassVar[frozenset[str]] = frozenset()

    def validate_query(self, request: Request) -> None:
        if request.query_params:
            raise OrchestratorError('unexpected_query_parameters', 422)

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request: Request):
            try:
                self.validate_query(request)
                if request.method == 'POST':
                    body = bytearray()
                    async for chunk in request.stream():
                        if len(body) + len(chunk) > self.max_body_bytes:
                            raise OrchestratorError('request_too_large', 413)
                        body.extend(chunk)
                    raw = bytes(body)
                    request._body = raw
                    try:
                        json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_constant)
                    except (ValueError, UnicodeError, RecursionError):
                        raise OrchestratorError('invalid_json', 422) from None
                result = await handler(request)
                result.headers['Cache-Control'] = 'no-store'
                return result
            except OrchestratorError as exc:
                code = self.error_aliases.get(exc.code, exc.code)
                return response({'error_code': code}, status=exc.status_code, error=code)
            except RequestValidationError as exc:
                for item in exc.errors():
                    code = str(item.get('ctx', {}).get('error', ''))
                    if code in self.public_validation_errors:
                        return response({'error_code': code}, status=422, error=code)
                return response(status=422, error='invalid_request')
            except (ValidationError, ValueError):
                return response(status=409, error='stored_evidence_invalid')
            except HTTPException as exc:
                return response(status=exc.status_code, error='request_unavailable')
            except (sqlite3.Error, OSError):
                return response(status=503, error='学习数据暂不可用，请保留输入并稍后重试')
        return guarded


def require_enabled():
    if not enabled():
        raise OrchestratorError('learning_orchestrator_disabled', 503)


def create_router(get_storage: Callable[[], SQLiteStorage]) -> APIRouter:
    router = APIRouter(prefix='/api/learning/orchestrator', route_class=DecisionRoute)

    @router.get('/capabilities')
    def capabilities():
        return response({'enabled': enabled(), 'rule_version': RULE_VERSION,
                         'ui_contract': 'today-workspace-v1',
                         'limits': {'sources': 20, 'candidates': 200, 'selected': 20, 'daily_operations': 100}})

    @router.post('/goal-options', dependencies=[Depends(require_enabled)])
    def goal_options(body: GoalOptionsRequest):
        return response(read_goal_options(get_storage(), body))

    @router.post('/snapshot', dependencies=[Depends(require_enabled)])
    def snapshot(body: ScopeRequest):
        snap = SnapshotReader(get_storage(), clock=utc_now).read(body)
        return response({'snapshot': snap, 'projection': project_tasks(snap)})

    @router.post('/preview', dependencies=[Depends(require_enabled)])
    def preview(body: PreviewRequest):
        return response(OrchestratorCommands(get_storage(), clock=utc_now).preview(body))

    @router.post('/confirm', dependencies=[Depends(require_enabled)])
    def confirm(body: ConfirmRequest):
        return response(OrchestratorCommands(get_storage(), clock=utc_now).confirm(body))

    @router.get('/today')
    def today():
        day = utc_now().astimezone(LOCAL_ZONE).date()
        return response(OrchestratorRepository(get_storage(), clock=utc_now).today(day))

    @router.get('/operations/{request_key}')
    def operation(request_key: str = Path(pattern=r'^[a-zA-Z0-9_-]{16,80}$')):
        result = OrchestratorRepository(get_storage()).find_request(request_key)
        if result is None:
            raise OrchestratorError('operation_not_found', 404)
        return response(result)

    @router.post('/operations/{operation_id}/undo-preview', dependencies=[Depends(require_enabled)])
    def undo_preview(operation_id: str, body: StrictRequest):
        return response(OrchestratorCommands(get_storage(), clock=utc_now).preview_undo(operation_id))

    @router.post('/operations/{operation_id}/undo-confirm', dependencies=[Depends(require_enabled)])
    def undo_confirm(operation_id: str, body: UndoConfirmRequest):
        return response(OrchestratorCommands(get_storage(), clock=utc_now).confirm_undo(operation_id, body))

    return router
