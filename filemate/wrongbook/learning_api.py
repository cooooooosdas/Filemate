"""Expose strict tenant-bound review learning reads and commands."""

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from filemate.execution.storage import QuestionRevisionConflict
from filemate.runtime_governance import BudgetExceeded, GovernanceUnavailable
from filemate.wrongbook.analysis import ReviewAnalysisService
from filemate.wrongbook.analysis_models import (
    Adoption,
    AdoptionConfirm,
    Analyze,
    Cancel,
    LearningPlan,
    LearningPlanConfirm,
    UndoConfirm,
)
from filemate.wrongbook.analysis_repository import AnalysisGone, ReviewAnalysisRepository, enabled
from filemate.wrongbook.api import _enabled
from filemate.wrongbook.learning_commands import ReviewLearningCommands
from filemate.wrongbook.learning_context import ReviewLearningContext, public_context


def response(data):
    """Return a non-cacheable review result through the established envelope."""
    return JSONResponse(content={'success': True, 'data': data, 'error': None}, headers={'Cache-Control': 'no-store'})


class ReviewLearningRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request: Request):
            if request.method == 'GET':
                allowed = ({'attempt_id', 'course_id', 'credential_mode'} if request.url.path.endswith('/learning-context')
                    else {'limit', 'offset'} if request.url.path.endswith(('/connections', '/analyses')) else set())
                if any(k not in allowed or len(request.query_params.getlist(k)) != 1 for k in request.query_params):
                    raise HTTPException(422, '查询参数无效或重复')
            try:
                return await handler(request)
            except QuestionRevisionConflict as exc:
                raise HTTPException(409, '复盘证据已变化，请重新读取') from exc
            except AnalysisGone as exc:
                raise HTTPException(410, '分析证据已删除或恢复，请使用新预览') from exc
            except BudgetExceeded as exc:
                raise HTTPException(429, '本学习空间的调用额度暂已用完') from exc
            except GovernanceUnavailable as exc:
                raise HTTPException(503, '调用准入暂不可用，请稍后重试') from exc
            except LookupError as exc:
                raise HTTPException(404, '所选学习证据不存在') from exc
            except ValueError as exc:
                raise HTTPException(422, '复盘证据或参数已变化，请重新读取') from exc
            except sqlite3.Error:
                return JSONResponse(status_code=503, content={'success': False, 'data': None,
                    'error': '复盘数据暂不可用，请稍后重试'}, headers={'Cache-Control': 'no-store'})
        return guarded


def analysis_enabled():
    if not enabled():
        raise HTTPException(503, '按需AI复盘尚未启用；真实作答与历史仍可使用')


def create_router(get_storage):
    router = APIRouter(prefix='/wrongbook/v2', route_class=ReviewLearningRoute)

    @router.get('/{wrong_id}/learning-context')
    def context(wrong_id: str, attempt_id: str = Query(min_length=1, max_length=128),
                course_id: str | None = Query(None, min_length=1, max_length=128),
                credential_mode: Literal['server', 'browser'] = 'server'):
        return response(public_context(ReviewLearningContext(get_storage()).build(
            wrong_id, attempt_id, course_id, credential_mode=credential_mode)))

    @router.get('/{wrong_id}/connections')
    def connections(wrong_id: str, limit: int = Query(30, ge=1, le=30), offset: int = Query(0, ge=0, le=1_000_000)):
        return response(ReviewLearningContext(get_storage()).connections(wrong_id, limit=limit, offset=offset))

    @router.get('/analysis-requests/{request_key}')
    def recovery(request_key: str):
        view = ReviewAnalysisRepository(get_storage()).find_request(request_key)
        if view is None:
            raise LookupError('analysis_request_not_found')
        return response(view)

    @router.post('/{wrong_id}/analyses', dependencies=[Depends(analysis_enabled)])
    def analyze(wrong_id: str, body: Analyze):
        return response(ReviewAnalysisService(get_storage()).analyze(wrong_id, body.model_dump()))

    @router.get('/{wrong_id}/analyses')
    def analyses(wrong_id: str, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0, le=1_000_000)):
        return response(ReviewAnalysisRepository(get_storage()).page(wrong_id, limit=limit, offset=offset))

    @router.get('/{wrong_id}/analyses/{analysis_id}')
    def analysis(wrong_id: str, analysis_id: str):
        return response(ReviewAnalysisRepository(get_storage()).get(wrong_id, analysis_id))

    @router.post('/{wrong_id}/analyses/{analysis_id}/cancel')
    def cancel(wrong_id: str, analysis_id: str, body: Cancel):
        return response(ReviewAnalysisRepository(get_storage()).cancel(wrong_id, analysis_id, body.request_key))

    @router.post('/{wrong_id}/analyses/{analysis_id}/adoption-preview', dependencies=[Depends(analysis_enabled)])
    def adoption_preview(wrong_id: str, analysis_id: str, body: Adoption):
        return response(ReviewLearningCommands(get_storage()).preview_adoption(wrong_id, analysis_id, body.model_dump()))

    @router.post('/{wrong_id}/analyses/{analysis_id}/adoption-confirm', dependencies=[Depends(analysis_enabled)])
    def adoption_confirm(wrong_id: str, analysis_id: str, body: AdoptionConfirm):
        return response(ReviewLearningCommands(get_storage()).confirm_adoption(wrong_id, analysis_id,
            body.model_dump(exclude={'request_key', 'confirmed', 'confirmation_token'}),
            body.confirmation_token, body.request_key, body.confirmed))

    @router.post('/{wrong_id}/learning-plan-preview', dependencies=[Depends(_enabled)])
    def plan_preview(wrong_id: str, body: LearningPlan):
        return response(ReviewLearningCommands(get_storage()).preview_plan(wrong_id, body.model_dump()))

    @router.post('/{wrong_id}/learning-plan-confirm', dependencies=[Depends(_enabled)])
    def plan_confirm(wrong_id: str, body: LearningPlanConfirm):
        return response(ReviewLearningCommands(get_storage()).confirm_plan(wrong_id,
            body.model_dump(exclude={'request_key', 'confirmed', 'confirmation_token'}),
            body.confirmation_token, body.request_key, body.confirmed))

    @router.post('/{wrong_id}/learning-operations/{event_id}/undo-preview', dependencies=[Depends(_enabled)])
    def undo_preview(wrong_id: str, event_id: str, body: dict):
        if body:
            raise ValueError('unexpected_parameters')
        return response(ReviewLearningCommands(get_storage()).preview_undo(wrong_id, event_id))

    @router.post('/{wrong_id}/learning-operations/{event_id}/undo-confirm', dependencies=[Depends(_enabled)])
    def undo_confirm(wrong_id: str, event_id: str, body: UndoConfirm):
        return response(ReviewLearningCommands(get_storage()).confirm_undo(wrong_id, event_id,
            body.confirmation_token, body.request_key, body.confirmed))

    return router
