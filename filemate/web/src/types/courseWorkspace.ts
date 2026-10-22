import type { RelationKind } from './courseGraph'

export type WorkspaceView = 'graph' | 'outline' | 'evidence'
export interface CoursePreference { desktop?: WorkspaceView; mobile?: WorkspaceView }
export type PreferenceStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
export interface CourseBrowse {
  scope: 'source' | 'course'; courseId: string; view: WorkspaceView; nodeId: string
  chapterId: string; sourceId: string; relations: RelationKind[] | null; notice: string
}
export interface WorkspaceFilter { chapter_id?: string; source_id?: string; relations?: RelationKind[] | null }
export interface WorkspaceNode {
  id: string; label: string; aliases: { label: string; origin: string }[]; chapter_ids: string[]
  source_count: number; source_status: 'available' | 'no_valid_source'; member_count: number
}
export interface WorkspaceGroup {
  id: string; parent_id: string | null; title: string; sort_order: number; concept_count: number; child_count: number
}
export interface WorkspaceRelation {
  id: string; from: string; to: string; relation: RelationKind; relation_ids: string[]; evidence_count: number
}
export interface WorkspaceIdentity { course_id: string; graph_digest: string }
export interface WorkspaceNavigation extends WorkspaceIdentity {
  name: string; groups: WorkspaceGroup[]; group_total: number; group_limit: number; group_offset: number
  sources: { source_id: string; original_name: string; chapter_id: string | null; active: boolean }[]
  source_total: number; source_limit: number; source_offset: number; total_concepts: number
}
export interface WorkspaceConceptPage extends WorkspaceIdentity {
  items: (WorkspaceNode & { matched_label: string })[]; total: number; limit: number; offset: number
}
export interface WorkspaceCanvas extends WorkspaceIdentity {
  mode: 'groups' | 'concepts'; nodes: WorkspaceNode[]; edges: WorkspaceRelation[]; groups: WorkspaceGroup[]
  group_edges: { from_group: string; to_group: string; relation_count: number }[]
  total_concepts: number; total_edges: number; truncated: boolean; node_has_more: boolean; edge_has_more: boolean
  group_total: number; group_offset: number; group_limit: number; requested_id: string | null; resolved_id: string | null
}
export interface WorkspaceSourceRef {
  evidence_id: string; source_id: string; original_name: string; excerpt: string; page: number | null; chunk_id: string | null
}
export interface WorkspaceDetail extends WorkspaceIdentity {
  requested_id: string; resolved_id: string; node: WorkspaceNode; source_refs: WorkspaceSourceRef[]
  total_refs: number; limit: number; offset: number
}
export interface WorkspaceCitation extends WorkspaceIdentity {
  requested_id: string; resolved_id: string; evidence_id: string; source_id: string; original_name: string
  page: number | null; chunk_id: string | null; before: string; quote: string; after: string
}
export interface WorkspaceChapterPath extends WorkspaceIdentity { items: WorkspaceGroup[] }
export interface WorkspaceNavigationOptions {
  parent_id?: string; group_limit?: number; group_offset?: number; source_limit?: number; source_offset?: number
}
export interface WorkspaceConceptOptions extends WorkspaceFilter { q?: string; limit?: number; offset?: number }
export interface WorkspaceApi {
  getCourseWorkspace(cid: string, options?: WorkspaceNavigationOptions, signal?: AbortSignal): Promise<WorkspaceNavigation>
  getCourseCanvas(cid: string, filters: WorkspaceFilter, focus?: string, groupOffset?: number, signal?: AbortSignal): Promise<WorkspaceCanvas>
  getCourseChapterPath(cid: string, chapterId: string, signal?: AbortSignal): Promise<WorkspaceChapterPath>
  getCourseConceptPage(cid: string, options: WorkspaceConceptOptions, signal?: AbortSignal): Promise<WorkspaceConceptPage>
  getCourseWorkspaceDetail(cid: string, nid: string, offset?: number, signal?: AbortSignal): Promise<WorkspaceDetail>
  getCourseCitation(cid: string, nid: string, eid: string, signal?: AbortSignal): Promise<WorkspaceCitation>
  getCourseBrowserScope(): Promise<string | null>
}
