export type GraphMode = 'local' | 'llm'
export type RelationKind = 'prerequisite' | 'depends_on' | 'part_of' | 'contains' | 'application' | 'related_to'
export interface CourseDecision { item_id: string; verdict: 'accept' | 'reject' | 'revise'; label?: string; aliases?: string[]; relation?: RelationKind; from_label?: string; to_label?: string; semantic_checked?: boolean }
export interface CourseCandidate {
  item_id: string; kind: 'node' | 'edge'; validation: 'valid' | 'needs_semantic_review' | 'invalid'; error_codes?: string[]
  original: { label?: string; from?: string; to?: string; relation?: string; excerpt?: string }
  parsed?: { label?: string; from?: string; to?: string; relation?: string; excerpt: string; page?: number | null; chunk_id?: string | null; legacy_mapping_ambiguous?: boolean }
  decision: 'pending' | CourseDecision; review_status?: string
}
export interface CourseExtraction { source_id: string; status: string; mode: GraphMode; error_code?: string; source_current: boolean; payload: { nodes?: CourseCandidate[]; edges?: CourseCandidate[]; coverage?: { input_characters: number; source_truncated: boolean } } }
export interface CourseDraft { course_id: string; draft_id: string; status: string; revision_digest: string; sources: CourseExtraction[] }
export interface CourseChapter { chapter_id: string; title: string; parent_id: string | null; sort_order: number; revision: number }
export interface GraphCourse { course_id: string; name: string; revision: number; chapters?: CourseChapter[]; sources?: { source_id: string; chapter_id: string | null; active: number; original_name: string; revision: number }[] }
export interface CourseSourceRef { evidence_id: string; source_id: string; excerpt: string; page?: number | null; chunk_id?: string | null; char_start?: number; char_end?: number }
export interface CourseConcept { id: string; label: string; revision: number; member_ids: string[]; aliases: { label: string; origin: string }[]; source_count: number; source_status: string; learning_status: string; source_refs: CourseSourceRef[]; merge_candidates?: { concept_id: string; label: string; reason: string }[] }
export interface CourseGraphPage { nodes: CourseConcept[]; edges: { from: string; to: string; relation: string; source_refs: CourseSourceRef[] }[]; total: number; limit: number; offset: number; self_edge_count: number; omitted_edge_count: number }
export interface CourseOperation { operation_id: string; kind: string; status: string; created_at: string; draft_id?: string; reversible: boolean; learning?: boolean }
export interface GraphPage<T> { items: T[]; total: number; limit: number; offset: number }
export interface CourseReviewPreview { confirmation_token: string; revision_digest: string; nodes: number; relations: number; items: { source_id: string; item_id: string; kind: string; parsed: { label?: string; from?: string; to?: string; excerpt: string; legacy_mapping_ambiguous?: boolean }; decision: CourseDecision }[] }
export interface CourseMergePreview { confirmation_token: string; concepts: (CourseConcept & { concept_id: string; source_refs: (CourseSourceRef & { original_name: string })[] })[]; self_edge_count: number; ids: { concepts: string[] } }
export interface CourseActionPreview { confirmation_token: string; affected?: Record<string, number>; support_impact?: { preserved_concepts: number; losing_support_concepts: number }; retains_learning_history?: boolean }
export interface GraphConfirmation { confirmed: true; confirmation_token: string; request_key: string }
