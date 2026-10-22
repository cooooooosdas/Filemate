"""Bounded read contracts for the course knowledge workspace."""

from dataclasses import dataclass
from typing import Literal, TypedDict

from filemate.course_graph.models import CourseGraphError

RelationKind = Literal["prerequisite", "depends_on", "part_of", "contains", "application", "related_to"]
RELATIONS = ("prerequisite", "depends_on", "part_of", "contains", "application", "related_to")
SYSTEM_GROUPS = ("@unassigned", "@no-source")


@dataclass(frozen=True)
class WorkspaceFilter:
    """Keep node membership independent from visible relation types."""

    chapter_id: str | None = None
    source_id: str | None = None
    relations: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if self.relations is not None and (
            not isinstance(self.relations, tuple)
            or any(r not in RELATIONS for r in self.relations)
            or len(set(self.relations)) != len(self.relations)
        ):
            raise CourseGraphError("invalid_relation_filter", 422)


class WorkspaceAlias(TypedDict):
    label: str
    origin: str


class WorkspaceNode(TypedDict):
    id: str
    label: str
    aliases: list[WorkspaceAlias]
    chapter_ids: list[str]
    source_count: int
    source_status: Literal["available", "no_valid_source"]
    member_count: int


class WorkspaceSearchNode(WorkspaceNode):
    matched_label: str


class WorkspaceGroup(TypedDict):
    id: str
    parent_id: str | None
    title: str
    sort_order: int
    concept_count: int
    child_count: int


WorkspaceRelation = TypedDict("WorkspaceRelation", {
    "id": str, "from": str, "to": str, "relation": RelationKind,
    "relation_ids": list[str], "evidence_count": int,
})


class WorkspaceSource(TypedDict):
    source_id: str
    original_name: str
    chapter_id: str | None
    active: bool


class WorkspaceNavigation(TypedDict):
    course_id: str
    name: str
    graph_digest: str
    groups: list[WorkspaceGroup]
    group_total: int
    group_limit: int
    group_offset: int
    sources: list[WorkspaceSource]
    source_total: int
    source_limit: int
    source_offset: int
    total_concepts: int


class WorkspaceConceptPage(TypedDict):
    course_id: str
    graph_digest: str
    items: list[WorkspaceSearchNode]
    total: int
    limit: int
    offset: int


class WorkspaceGroupEdge(TypedDict):
    from_group: str
    to_group: str
    relation_count: int


class WorkspaceCanvas(TypedDict):
    course_id: str
    graph_digest: str
    mode: Literal["groups", "concepts"]
    nodes: list[WorkspaceNode]
    edges: list[WorkspaceRelation]
    groups: list[WorkspaceGroup]
    group_edges: list[WorkspaceGroupEdge]
    total_concepts: int
    total_edges: int
    truncated: bool
    node_has_more: bool
    edge_has_more: bool
    group_total: int
    group_offset: int
    group_limit: int
    requested_id: str | None
    resolved_id: str | None


class WorkspaceSourceRef(TypedDict):
    evidence_id: str
    source_id: str
    original_name: str
    excerpt: str
    page: int | None
    chunk_id: str | None


class WorkspaceDetail(TypedDict):
    course_id: str
    graph_digest: str
    requested_id: str
    resolved_id: str
    node: WorkspaceNode
    source_refs: list[WorkspaceSourceRef]
    total_refs: int
    limit: int
    offset: int


class WorkspaceCitation(TypedDict):
    course_id: str
    graph_digest: str
    requested_id: str
    resolved_id: str
    evidence_id: str
    source_id: str
    original_name: str
    page: int | None
    chunk_id: str | None
    before: str
    quote: str
    after: str


def validate_page(limit: int, offset: int, maximum: int = 200) -> None:
    """Reject coercion and unbounded direct service calls as well as HTTP calls."""
    if type(limit) is not int or type(offset) is not int or not 1 <= limit <= maximum or not 0 <= offset <= 1_000_000:
        raise CourseGraphError("invalid_pagination", 422)
