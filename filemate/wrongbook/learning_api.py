"""Expose strict tenant-bound review learning reads and commands."""

import sqlite3
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from filemate.execution.storage import QuestionRevisionConflict
from filemate.wrongbook.learning_context import ReviewLearningContext, public_context


def response(data):
    """Return a non-cacheable review result through the established envelope."""
    return JSONResponse(content={'success': True, 'data': data, 'error': None}, headers={'Cache-Control': 'no-store'})


class ReviewLearningRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request: Request):
            if request.method == 'GET':
                allowed = {'attempt_id', 'course_id', 'credential_mode'} if request.url.path.endswith('/learning-context') else {'limit', 'offset'}
                if any(k not in allowed or len(request.query_params.getlist(k)) != 1 for k in request.query_params):
                    raise HTTPException(422, '查询参数无效或重复')
            try:
                return await handler(request)
            except QuestionRevisionConflict as exc:
                raise HTTPException(409, '复盘证据已变化，请重新读取') from exc
            except LookupError as exc:
                raise HTTPException(404, '所选学习证据不存在') from exc
            except ValueError as exc:
                raise HTTPException(422, '复盘证据或参数已变化，请重新读取') from exc
            except sqlite3.Error:
                return JSONResponse(status_code=503, content={'success': False, 'data': None,
                    'error': '复盘数据暂不可用，请稍后重试'}, headers={'Cache-Control': 'no-store'})
        return guarded


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

    return router
