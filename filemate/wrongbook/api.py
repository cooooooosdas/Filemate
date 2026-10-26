"""Opt-in commands and always-readable tenant-bound review evidence."""

import os
import sqlite3
from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import Field, field_validator

from filemate.execution.storage import QuestionRevisionConflict, SQLiteStorage
from filemate.wrongbook.commands import ReviewCommands
from filemate.wrongbook.engine import RULE_VERSION
from filemate.wrongbook.models import Answer, Diagnosis, Schedule
from filemate.wrongbook.queries import ReviewFilter, ReviewQueries
from filemate.wrongbook.repository import ReviewRepository


class Confirm(Schedule):
    confirmation_token: str = Field(min_length=1, max_length=256)
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("请明确确认排期操作")
        return value


class ReviewRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request: Request):
            if request.method == "GET":
                allowed = {"limit", "offset"} if request.url.path.endswith(("/attempts", "/events")) else set()
                if request.url.path.endswith('/page'):
                    allowed = {*ReviewFilter.model_fields, 'limit', 'offset'}
                elif request.url.path.endswith('/filter-options'):
                    allowed = {'kind', 'q', 'limit', 'offset'}
                keys = list(request.query_params.keys())
                if any(key not in allowed or len(request.query_params.getlist(key)) != 1 for key in keys):
                    raise HTTPException(422, "查询参数无效或重复")
            try:
                return await handler(request)
            except QuestionRevisionConflict as exc:
                raise HTTPException(409, str(exc)) from exc
            except LookupError as exc:
                raise HTTPException(404, str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(422, "复习参数或数据无效，请重新读取后操作") from exc
            except sqlite3.Error:
                return JSONResponse(status_code=503, content={"success": False, "data": None,
                    "error": "复习数据暂不可用，请稍后重试"}, headers={"Cache-Control": "no-store"})
        return guarded


def _enabled():
    if os.getenv("FILEMATE_ENABLE_WRONGBOOK_V2", "0") != "1":
        raise HTTPException(503, "错题复盘2.0写入尚未启用，历史仍可查看")


def create_router(get_storage: Callable[[], SQLiteStorage]) -> APIRouter:
    router = APIRouter(prefix="/wrongbook/v2", route_class=ReviewRoute)

    def repo():
        return ReviewRepository(get_storage())

    def response(data):
        return JSONResponse(content={"success": True, "data": data, "error": None},
                            headers={"Cache-Control": "no-store"})

    @router.get("/summary")
    def summary():
        return response(repo().summary())

    @router.get('/capabilities')
    def capabilities():
        return response({'write_enabled': os.getenv('FILEMATE_ENABLE_WRONGBOOK_V2', '0') == '1', 'rule_version': RULE_VERSION})

    @router.get('/page')
    def page(request: Request, limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0, le=1_000_000)):
        filters = ReviewFilter.model_validate({key: value for key, value in request.query_params.items() if key not in {'limit', 'offset'}})
        return response(ReviewQueries(get_storage()).page(filters, limit=limit, offset=offset))

    @router.get('/filter-options')
    def options(kind: Literal['sources', 'courses'], q: str = Query('', max_length=160),
                limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0, le=1_000_000)):
        return response(ReviewQueries(get_storage()).options(kind, q=q, limit=limit, offset=offset))

    @router.get('/receipts/{request_key}')
    def receipt(request_key: str):
        return response(ReviewQueries(get_storage()).receipt(request_key))

    @router.get('/question-access/{artifact_id}/{question_index}')
    def question_access(artifact_id: str, question_index: int = Path(ge=0, le=100_000)):
        storage = get_storage()
        artifact = storage.get_artifact(artifact_id)
        if not artifact or artifact.get('artifact_type') != 'questions':
            raise LookupError('题集不存在')
        questions = artifact.get('content')
        if not isinstance(questions, list) or question_index >= len(questions):
            raise LookupError('题目不存在')
        history = bool((artifact.get('metadata') or {}).get('read_only_snapshot'))
        row = storage._conn().execute('SELECT scheduler_version,revision FROM wrong_questions WHERE artifact_id=? AND question_index=?', (artifact_id, question_index)).fetchone()
        owned = bool(row and (row['scheduler_version'] != 'legacy-v1' or row['revision'] > 1))
        return response({'legacy_writable': not history and not owned, 'read_only_snapshot': history})

    @router.post("/attempts", dependencies=[Depends(_enabled)])
    def answer(body: Answer):
        return response(repo().submit(body.model_dump()))

    @router.get("/{wrong_id}")
    def detail(wrong_id: str):
        return response(repo().detail(wrong_id))

    @router.get("/{wrong_id}/attempts")
    def attempts(wrong_id: str, limit: int = Query(30, ge=1, le=200), offset: int = Query(0, ge=0, le=1_000_000)):
        return response(repo().history(wrong_id, kind="attempts", limit=limit, offset=offset))

    @router.get("/{wrong_id}/events")
    def events(wrong_id: str, limit: int = Query(30, ge=1, le=200), offset: int = Query(0, ge=0, le=1_000_000)):
        return response(repo().history(wrong_id, kind="events", limit=limit, offset=offset))

    @router.patch("/{wrong_id}/diagnosis", dependencies=[Depends(_enabled)])
    def diagnosis(wrong_id: str, body: Diagnosis):
        return response(repo().diagnose(wrong_id, body.model_dump()))

    @router.post("/{wrong_id}/schedule-preview", dependencies=[Depends(_enabled)])
    def preview(wrong_id: str, body: Schedule):
        return response(ReviewCommands(repo()).preview(wrong_id, body.model_dump()))

    @router.post("/{wrong_id}/schedule-confirm", dependencies=[Depends(_enabled)])
    def confirm(wrong_id: str, body: Confirm):
        return response(ReviewCommands(repo()).confirm(wrong_id,
            body.model_dump(exclude={"confirmed", "confirmation_token"}), body.confirmation_token))

    return router
