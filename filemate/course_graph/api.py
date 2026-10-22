"""Tenant-scoped, opt-in HTTP boundary for reviewed course graphs."""

import json
import os
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field

from filemate.course_graph import fusion, privacy, review
from filemate.course_graph.drafts import DraftService
from filemate.course_graph.extraction import CourseGraphProvider
from filemate.course_graph.models import CourseGraphError, ItemDecision
from filemate.course_graph.projection import concept_detail, course_graph
from filemate.course_graph.repository import CourseGraphRepository, require_course
from filemate.execution.storage import SQLiteStorage
from filemate.llm_client import LLMClient, LLMConfig

Key = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{16,80}$")]
Identity = Annotated[str, Field(min_length=1, max_length=120)]


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CreateCourse(StrictBody):
    name: str = Field(min_length=1, max_length=80)
    request_key: Key


class Chapter(StrictBody):
    title: str = Field(min_length=1, max_length=120)
    parent_id: Identity | None = None
    sort_order: int = Field(default=0, ge=0, le=100_000)
    expected_revision: int = Field(ge=0)


class Sources(StrictBody):
    source_ids: list[Identity] = Field(min_length=1, max_length=10)
    chapter_id: Identity | None = None
    expected_revision: int = Field(ge=0)


class CreateDraft(StrictBody):
    source_ids: list[Identity] = Field(min_length=1, max_length=10)
    mode: Literal["local", "llm"]
    request_key: Key


class Command(StrictBody):
    request_key: Key


class Extract(Command):
    mode: Literal["local", "llm"]
    allow_external_model: bool = False


class Decisions(StrictBody):
    expected_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    decisions: list[ItemDecision] = Field(min_length=1, max_length=2000)


class Confirm(Command):
    confirmed: Literal[True]
    confirmation_token: str = Field(min_length=1, max_length=256)


class Merge(StrictBody):
    concept_ids: list[Identity] = Field(min_length=2, max_length=20)
    target_id: Identity


class MergeConfirm(Merge, Confirm):
    pass


class Operation(StrictBody):
    action: Literal["undo", "restore"]


class CourseRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request: Request):
            try:
                return await handler(request)
            except CourseGraphError as exc:
                return JSONResponse(status_code=exc.status_code, content={"success": False,
                    "error": exc.code, "data": {"error_code": exc.code, **exc.details}},
                    headers={"Cache-Control": "no-store"})
            except sqlite3.Error:
                return JSONResponse(status_code=503, content={"success": False,
                    "error": "课程数据暂不可用，请稍后重试", "data": {"error_code": "storage_unavailable"}},
                    headers={"Cache-Control": "no-store"})
        return guarded


def _enabled():
    if os.getenv("FILEMATE_ENABLE_COURSE_GRAPH", "0") != "1":
        raise HTTPException(503, "课程图谱尚未启用，原图谱仍可使用")


def _result(data):
    return {"success": True, "data": data, "error": None}


def create_router(storage_provider: Callable[[], SQLiteStorage]) -> APIRouter:
    """Resolve real request storage lazily, never cache a tenant in the router."""
    router = APIRouter(prefix="/api/knowledge-graph/courses", route_class=CourseRoute,
                       dependencies=[Depends(_enabled)])
    Store = Annotated[SQLiteStorage, Depends(storage_provider)]

    def drafts(store):
        return DraftService(store, lambda: CourseGraphProvider(LLMClient(LLMConfig.from_env())),
                            lambda: datetime.now(timezone.utc))

    @router.get("")
    def courses(store: Store, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=1_000_000),
                q: str = Query("", max_length=160)):
        return _result(CourseGraphRepository(store).list_courses(limit, offset, q))

    @router.post("")
    def create(body: CreateCourse, store: Store):
        return _result(CourseGraphRepository(store).create_course(**body.model_dump()))

    @router.get("/{cid}")
    def course(cid: str, store: Store):
        return _result(CourseGraphRepository(store).get_course(cid))

    @router.put("/{cid}/chapters/{chapter_id}")
    def chapter(cid: str, chapter_id: str, body: Chapter, store: Store):
        return _result(CourseGraphRepository(store).put_chapter(cid, chapter_id, **body.model_dump()))

    @router.post("/{cid}/sources")
    def sources(cid: str, body: Sources, store: Store):
        return _result(CourseGraphRepository(store).attach_sources(cid, **body.model_dump()))

    @router.get("/{cid}/sources/{sid}/remove-preview")
    def remove_preview(cid: str, sid: str, store: Store):
        return _result(privacy.preview_remove_source(store, cid, sid))

    @router.post("/{cid}/sources/{sid}/remove")
    def remove(cid: str, sid: str, body: Confirm, store: Store):
        return _result(privacy.remove_source(store, cid, sid, **body.model_dump()))

    @router.post("/{cid}/drafts")
    def create_draft(cid: str, body: CreateDraft, store: Store):
        return _result(drafts(store).create_group(cid, **body.model_dump()))

    @router.get("/{cid}/drafts/{did}")
    def draft(cid: str, did: str, store: Store):
        return _result(drafts(store).snapshot(cid, did))

    @router.post("/{cid}/drafts/{did}/sources/{sid}/extract")
    def extract(cid: str, did: str, sid: str, body: Extract, store: Store):
        service = drafts(store)
        snapshot = service.snapshot(cid, did)
        source = next((s for s in snapshot["sources"] if s["source_id"] == sid), None)
        if source is None or source["status"] == "unavailable":
            raise CourseGraphError("source_not_found", 404)
        if source["mode"] != body.mode:
            raise CourseGraphError("mode_conflict", 409)
        result = service.extract_source(cid, did, sid, body.request_key, body.allow_external_model)
        saved = next(s for s in result["sources"] if s["source_id"] == sid)
        if saved["status"] == "failed":
            code = saved["error_code"]
            raise CourseGraphError(code, 429 if code == "budget_exceeded" else 503 if code == "governance_unavailable" else 502)
        return _result(result)

    @router.post("/{cid}/drafts/{did}/cancel")
    def cancel(cid: str, did: str, body: Command, store: Store):
        return _result(drafts(store).cancel(cid, did, body.request_key))

    @router.post("/{cid}/drafts/{did}/decisions")
    def decisions(cid: str, did: str, body: Decisions, store: Store):
        return _result(review.save_decisions(store, cid, did, body.expected_digest, body.decisions))

    @router.post("/{cid}/drafts/{did}/review-preview")
    def review_preview(cid: str, did: str, store: Store):
        return _result(review.preview_review(store, cid, did))

    @router.post("/{cid}/drafts/{did}/confirm")
    def confirm(cid: str, did: str, body: Confirm, store: Store):
        return _result(review.confirm_review(store, cid, did, **body.model_dump()))

    @router.get("/{cid}/graph")
    def graph(cid: str, store: Store, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=1_000_000),
              q: str = Query("", max_length=160)):
        return _result(course_graph(store, cid, limit, offset, q))

    @router.get("/{cid}/concepts/{nid}")
    def concept(cid: str, nid: str, store: Store):
        detail = concept_detail(store, cid, nid)
        return _result({**detail, "merge_candidates": fusion.merge_candidates(store, cid, detail["id"])})

    @router.post("/{cid}/merges/preview")
    def merge_preview(cid: str, body: Merge, store: Store):
        return _result(fusion.preview_merge(store, cid, **body.model_dump()))

    @router.post("/{cid}/merges/confirm")
    def merge_confirm(cid: str, body: MergeConfirm, store: Store):
        return _result(fusion.confirm_merge(store, cid, **body.model_dump()))

    @router.get("/{cid}/operations")
    def operations(cid: str, store: Store, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=1_000_000)):
        conn = store._conn()
        require_course(conn, cid)
        total = conn.execute("SELECT COUNT(*) FROM kg_changes WHERE course_id=?", (cid,)).fetchone()[0]
        rows = conn.execute("SELECT * FROM kg_changes WHERE course_id=? ORDER BY rowid DESC LIMIT ? OFFSET ?", (cid, limit, offset))
        items = []
        for row in rows:
            meta = json.loads(row["metadata"])
            items.append({"operation_id": row["operation_id"], "kind": row["kind"], "status": row["status"],
                          "created_at": row["created_at"], "draft_id": meta.get("draft_id"),
                          "reversible": "ids" in meta and row["kind"] in {"review", "merge", "remove_source"}})
        return _result({"items": items, "total": total, "limit": limit, "offset": offset})

    @router.post("/{cid}/operations/{oid}/preview")
    def operation_preview(cid: str, oid: str, body: Operation, store: Store):
        return _result(fusion.preview_operation(store, cid, oid, body.action))

    @router.post("/{cid}/operations/{oid}/{action}")
    def operation(cid: str, oid: str, action: Literal["undo", "restore"], body: Confirm, store: Store):
        return _result(fusion.transition_operation(store, cid, oid, action, **body.model_dump()))

    return router
