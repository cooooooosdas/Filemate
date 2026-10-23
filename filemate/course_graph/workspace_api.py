"""Strict read-only HTTP routes using the existing course permission boundary."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from filemate.course_graph import workspace_canvas, workspace_query, workspace_source
from filemate.course_graph.models import CourseGraphError
from filemate.course_graph.workspace_models import RelationKind, WorkspaceFilter
from filemate.execution.storage import SQLiteStorage


class ReadQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NavigationQuery(ReadQuery):
    parent_id: str | None = Field(default=None, min_length=1, max_length=120)
    group_limit: int = Field(default=200, ge=1, le=200)
    group_offset: int = Field(default=0, ge=0, le=1_000_000)
    source_limit: int = Field(default=50, ge=1, le=200)
    source_offset: int = Field(default=0, ge=0, le=1_000_000)


class FilterQuery(ReadQuery):
    chapter_id: str | None = Field(default=None, min_length=1, max_length=120)
    source_id: str | None = Field(default=None, min_length=1, max_length=120)
    relation: list[RelationKind] = Field(default_factory=list, max_length=6)
    hide_relations: bool = False

    def filters(self) -> WorkspaceFilter:
        if self.hide_relations and self.relation:
            raise CourseGraphError("invalid_relation_filter", 422)
        return WorkspaceFilter(self.chapter_id, self.source_id,
                               () if self.hide_relations else tuple(self.relation) if self.relation else None)


class ConceptPageQuery(FilterQuery):
    q: str = Field(default="", max_length=160)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=1_000_000)


class CanvasQuery(FilterQuery):
    focus: str | None = Field(default=None, min_length=1, max_length=120)
    limit: int = Field(default=100, ge=1, le=100)
    group_limit: int = Field(default=20, ge=1, le=20)
    group_offset: int = Field(default=0, ge=0, le=1_000_000)


class DetailQuery(ReadQuery):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=1_000_000)


def strict_query(request: Request) -> None:
    """Only relation is a repeatable query parameter."""
    for name in request.query_params:
        if name != "relation" and len(request.query_params.getlist(name)) > 1:
            raise CourseGraphError("invalid_query", 422)


def _result(data) -> JSONResponse:
    return JSONResponse({"success": True, "data": data, "error": None}, headers={"Cache-Control": "no-store"})


def register_workspace_routes(router: APIRouter, storage_provider: Callable[[], SQLiteStorage]) -> None:
    """Inherit the parent's opt-in switch, route errors and tenant storage dependency."""
    Store = Annotated[SQLiteStorage, Depends(storage_provider)]
    guard = [Depends(strict_query)]

    @router.get("/{cid}/workspace", dependencies=guard)
    def workspace(cid: str, store: Store, params: Annotated[NavigationQuery, Query()]):
        return _result(workspace_query.get_workspace(store, cid, **params.model_dump()))

    @router.get("/{cid}/workspace/chapter-path/{chapter_id}", dependencies=guard)
    def chapter_path(cid: str, chapter_id: str, store: Store, params: Annotated[ReadQuery, Query()]):
        return _result(workspace_query.get_chapter_path(store, cid, chapter_id))

    @router.get("/{cid}/concepts-page", dependencies=guard)
    def concepts(cid: str, store: Store, params: Annotated[ConceptPageQuery, Query()]):
        return _result(workspace_query.list_workspace_concepts(store, cid, filters=params.filters(),
                                                              q=params.q, limit=params.limit, offset=params.offset))

    @router.get("/{cid}/canvas", dependencies=guard)
    def canvas(cid: str, store: Store, params: Annotated[CanvasQuery, Query()]):
        return _result(workspace_canvas.get_workspace_canvas(store, cid, filters=params.filters(),
            focus=params.focus, limit=params.limit, group_limit=params.group_limit, group_offset=params.group_offset))

    @router.get("/{cid}/workspace/concepts/{nid}", dependencies=guard)
    def detail(cid: str, nid: str, store: Store, params: Annotated[DetailQuery, Query()]):
        return _result(workspace_canvas.get_workspace_detail(store, cid, nid, **params.model_dump()))

    @router.get("/{cid}/concepts/{nid}/source-evidence/{eid}", dependencies=guard)
    def citation(cid: str, nid: str, eid: str, store: Store, params: Annotated[ReadQuery, Query()]):
        return _result(workspace_source.get_workspace_citation(store, cid, nid, eid))
