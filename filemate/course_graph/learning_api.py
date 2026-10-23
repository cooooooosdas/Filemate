"""Strict learning commands using the established tenant and preview boundaries."""

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import Field, model_validator

from filemate.course_graph import (
    cross_links,
    learning_commands,
    learning_evidence,
    learning_paths,
    question_links,
)
from filemate.course_graph.api import Command, Confirm, Identity, StrictBody
from filemate.course_graph.learning_work import LearningWorkService
from filemate.course_graph.practice import PracticeService
from filemate.course_graph.workspace_api import DetailQuery, ReadQuery, _result, strict_query
from filemate.execution.storage import SQLiteStorage
from filemate.llm_client import LLMClient, LLMConfig


class NodesQuery(DetailQuery):
    status: Literal['no_evidence', 'practiced', 'needs_reinforcement', 'recently_stable'] | None = None


class CandidatesQuery(DetailQuery):
    q: str = Field(default='', max_length=160)


class QuestionRef(StrictBody):
    artifact_id: Identity
    question_index: int = Field(ge=0, le=100_000)
    question_digest: str = Field(pattern=r'^[a-f0-9]{64}$')


class Links(StrictBody):
    items: list[QuestionRef] = Field(min_length=1, max_length=20)
    active: bool = True


class LinksConfirm(Links, Confirm):
    pass


class Practice(Command):
    difficulty: Literal['simple', 'standard', 'advanced'] = 'simple'
    count: int = Field(default=1, ge=1, le=5)
    mode: Literal['local', 'llm'] = 'local'
    allow_external_model: bool = False

    @model_validator(mode='after')
    def consent(self):
        if self.mode == 'llm' and not self.allow_external_model:
            raise ValueError('external_model_consent_required')
        return self


class Decision(StrictBody):
    index: int = Field(ge=0, le=4)
    verdict: Literal['accept', 'reject']
    question: dict | None = None


class Review(StrictBody):
    decisions: list[Decision] = Field(min_length=1, max_length=5)


class ReviewConfirm(Review, Confirm):
    pass


class Path(StrictBody):
    goal: str = Field(min_length=1, max_length=500)
    concept_ids: list[Identity] | None = Field(default=None, min_length=1, max_length=30)
    chapter_id: Identity | None = None
    goal_id: Identity | None = None
    daily_minutes: int = Field(default=20, ge=5, le=180)
    days: int = Field(default=7, ge=1, le=7)


class PathConfirm(Path, Confirm):
    pass


class Related(StrictBody):
    other_course_id: Identity
    other_concept_id: Identity
    active: bool = True
    relation: Literal['related'] = 'related'


class RelatedConfirm(Related, Confirm):
    pass


class Transition(StrictBody):
    action: Literal['undo', 'restore']


class TransitionConfirm(Transition, Confirm):
    pass


def register_learning_routes(router: APIRouter, storage_provider: Callable[[], SQLiteStorage]) -> None:
    """Keep model work explicit and all GETs free of side effects."""
    Store = Annotated[SQLiteStorage, Depends(storage_provider)]
    guard = [Depends(strict_query)]

    def practice(store):
        return PracticeService(store, lambda: LLMClient(LLMConfig.from_env()), lambda: datetime.now(timezone.utc))

    @router.get('/{cid}/learning/nodes', dependencies=guard)
    def nodes(cid: str, store: Store, params: Annotated[NodesQuery, Query()]):
        return _result(learning_evidence.list_learning_nodes(store, cid, now=datetime.now(timezone.utc), **params.model_dump()))

    @router.get('/{cid}/concepts/{nid}/learning', dependencies=guard)
    def evidence(cid: str, nid: str, store: Store, params: Annotated[DetailQuery, Query()]):
        return _result(learning_evidence.node_learning_evidence(store, cid, nid, now=datetime.now(timezone.utc), **params.model_dump()))

    @router.get('/{cid}/concepts/{nid}/question-candidates', dependencies=guard)
    def candidates(cid: str, nid: str, store: Store, params: Annotated[CandidatesQuery, Query()]):
        return _result(question_links.question_candidates(store, cid, nid, **params.model_dump()))

    @router.post('/{cid}/concepts/{nid}/question-links/preview')
    def links_preview(cid: str, nid: str, body: Links, store: Store):
        return _result(question_links.preview_question_links(store, cid, nid, **body.model_dump()))

    @router.post('/{cid}/concepts/{nid}/question-links/confirm')
    def links_confirm(cid: str, nid: str, body: LinksConfirm, store: Store):
        return _result(question_links.confirm_question_links(store, cid, nid, **body.model_dump()))

    @router.post('/{cid}/concepts/{nid}/practice-drafts')
    def generate(cid: str, nid: str, body: Practice, store: Store):
        return _result(practice(store).generate(cid, nid, **body.model_dump()))

    @router.get('/{cid}/learning/work/{wid}', dependencies=guard)
    def work(cid: str, wid: str, store: Store, params: Annotated[ReadQuery, Query()]):
        return _result(LearningWorkService(store, lambda: datetime.now(timezone.utc)).get(cid, wid))

    @router.post('/{cid}/learning/work/{wid}/cancel')
    def cancel(cid: str, wid: str, body: Command, store: Store):
        return _result(LearningWorkService(store, lambda: datetime.now(timezone.utc)).cancel(cid, wid, body.request_key))

    @router.post('/{cid}/learning/work/{wid}/review/preview')
    def review_preview(cid: str, wid: str, body: Review, store: Store):
        return _result(practice(store).preview(cid, wid, body.model_dump(exclude_none=True)['decisions']))

    @router.post('/{cid}/learning/work/{wid}/review/confirm')
    def review_confirm(cid: str, wid: str, body: ReviewConfirm, store: Store):
        return _result(practice(store).confirm(cid, wid, **body.model_dump(exclude_none=True)))

    @router.post('/{cid}/learning/path/preview')
    def path_preview(cid: str, body: Path, store: Store):
        return _result(learning_paths.preview_path(store, cid, body.model_dump()))

    @router.post('/{cid}/learning/path/confirm')
    def path_confirm(cid: str, body: PathConfirm, store: Store):
        fields = body.model_dump()
        command = {key: fields.pop(key) for key in ('confirmation_token', 'request_key', 'confirmed')}
        return _result(learning_paths.confirm_path(store, cid, fields, **command))

    @router.get('/{cid}/concepts/{nid}/related-courses', dependencies=guard)
    def related(cid: str, nid: str, store: Store, params: Annotated[DetailQuery, Query()]):
        return _result(cross_links.list_cross_links(store, cid, nid, **params.model_dump()))

    @router.post('/{cid}/concepts/{nid}/related-courses/preview')
    def related_preview(cid: str, nid: str, body: Related, store: Store):
        return _result(cross_links.preview_cross_link(store, cid, nid, **body.model_dump()))

    @router.post('/{cid}/concepts/{nid}/related-courses/confirm')
    def related_confirm(cid: str, nid: str, body: RelatedConfirm, store: Store):
        return _result(cross_links.confirm_cross_link(store, cid, nid, **body.model_dump()))

    @router.post('/{cid}/learning/operations/{oid}/preview')
    def transition_preview(cid: str, oid: str, body: Transition, store: Store):
        return _result(learning_commands.preview_learning_transition(store, cid, oid, body.action))

    @router.post('/{cid}/learning/operations/{oid}/confirm')
    def transition_confirm(cid: str, oid: str, body: TransitionConfirm, store: Store):
        return _result(learning_commands.transition_learning_operation(store, cid, oid, **body.model_dump()))
