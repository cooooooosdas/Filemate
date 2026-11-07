import type {
  DayView,
  EvidenceSnapshot,
  ScheduleOptions,
  SchedulePreview,
  ScopeRequest,
  TaskProjection,
  UndoConfirmRequest,
} from './orchestrator'

export type CoachIntent = 'budget' | 'exam' | 'error_cause' | 'tomorrow' | 'next_step'
export interface FeedbackRef {
  interview_id: string
  attempt_id: string
  feedback_item_id: string
  expected_revision: string
}
export interface CoachSelection {
  interview_ids: string[]
  submission_ids: string[]
  concept_ids: string[]
  wrong_ids: string[]
  feedback_refs: FeedbackRef[]
  position_id: string | null
  requirement_indices: number[]
}
export interface CoachDayInput {
  study_date: string
  options: ScheduleOptions
}
export interface CoachInput {
  reflection_id?: string | null
  scope: ScopeRequest
  selection: CoachSelection
  intent: CoachIntent
  question: string
  days: CoachDayInput[]
}
export type CoachFactKind =
  | 'goal'
  | 'source'
  | 'attempt'
  | 'review'
  | 'cause'
  | 'concept'
  | 'relation'
  | 'interview_feedback'
  | 'compiler_result'
  | 'position_requirement'
  | 'plan'
export interface CoachFact {
  fact_id: string
  kind: CoachFactKind
  record_id: string
  revision: string
  observed_at: string | null
  display_text: string
  data: Record<string, unknown>
}
export interface CoachContext {
  input: CoachInput
  as_of: string
  context_revision: string
  restore_epoch: string
  snapshot: EvidenceSnapshot
  projection: TaskProjection
  facts: CoachFact[]
  coverage: Record<string, unknown>
  external_payload: Record<string, unknown>
  external_digest: string
}
export interface CoachCapabilities {
  enabled: boolean
  contract_version: 'learning-coach-v1'
  rule_version: string
  prompt_version: string
  quota_window: 'rolling_24h'
  limits: Record<string, number>
}
export interface CoachCatalogRequest {
  scope: ScopeRequest
  kind: 'interview' | 'submission' | 'concept' | 'wrong' | 'position'
  q?: string
  offset?: number
}
export interface CoachCatalogItem {
  id: string
  label: string
  updated_at: string | null
  revision: string
  valid: boolean
  source_id: string | null
}
export interface CoachCatalogPage {
  items: CoachCatalogItem[]
  total: number
  offset: number
  limit: number
}
export type CoachMethod =
  | 'reread'
  | 'trace_error'
  | 'compare_cases'
  | 'retry_independently'
  | 'rehearse'
  | 'practice'
export interface CoachTarget {
  kind: 'source' | 'question' | 'concept' | 'interview' | 'problem'
  id: string
  revision: string
  artifact_id?: string | null
  question_index?: number | null
  course_id?: string | null
  attempt_id?: string | null
  problem_version?: number | null
}
export interface CoachAction {
  action_key: string
  action:
    | 'read_source'
    | 'review_question'
    | 'train_concept'
    | 'rehearse_interview'
    | 'practice_problem'
  target_ref: CoachTarget
  method_code: CoachMethod
  study_date: string
  minutes: number
  fact_ids: string[]
}
export interface CoachExplanation {
  task_id: string | null
  fact_ids: string[]
  reason_code: string
  method_code: CoachMethod
  text: string
}
export interface CoachProposal {
  rule_version: string
  prompt_version: string
  facts: CoachFact[]
  explanations: CoachExplanation[]
  days: (CoachDayInput & {
    schedule: Pick<
      SchedulePreview,
      | 'rule_version'
      | 'selected'
      | 'deferred'
      | 'deferred_count'
      | 'deferred_counts'
      | 'deferred_truncated'
      | 'completed'
      | 'coverage'
      | 'estimated_minutes'
    >
  })[]
  new_actions: CoachAction[]
  coverage: Record<string, unknown>
  overlaps: Record<string, unknown>[]
  limitations: string[]
}
export interface CoachRequest {
  input: CoachInput
  expected_context_revision: string
  request_key: string
  mode: 'rule' | 'llm'
  allow_external_model: boolean
  consent_digest: string | null
}
export interface CoachRunView {
  work_id: string
  request_key: string
  status: 'running' | 'ready' | 'failed' | 'cancelled' | 'interrupted' | 'stale'
  requested_mode: 'rule' | 'llm'
  effective_mode: 'rule' | 'model' | 'rule_fallback'
  model_status: 'not_requested' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'interrupted'
  safe_error_code: string | null
  context_revision: string
  proposal: CoachProposal | null
  provider?: string | null
  model?: string | null
  quota_window?: 'rolling_24h'
  rule_version: string
  prompt_version: string
}
export interface CoachDraft {
  work_id: string
  expected_context_revision: string
  days: CoachDayInput[]
  new_actions: CoachAction[]
  overlap_choices: { original_task_id: string; keep: 'original' | 'proposed' }[]
}
export interface CoachDayImpact {
  study_date: string
  selected: SchedulePreview['selected']
  selected_count: number
  estimated_minutes: number
  deferred_count: number
  deferred_counts: Record<string, number>
  completed_count: number
  preserves_completed: boolean
  pinned_count: number
  replaces_existing_schedule: boolean
}
export interface CoachPreview {
  draft: CoachDraft
  as_of: string
  issued_study_date: string
  day_revisions: Record<string, number>
  new_plan_id: string | null
  new_artifact_id: string | null
  resolved_actions: Pick<CoachAction, 'action_key' | 'study_date' | 'minutes'>[]
  changes: Record<string, unknown> & { days?: CoachDayImpact[] }
  confirmation_token: string
  expires_in_seconds: number
}
export interface CoachConfirm extends CoachDraft {
  request_key: string
  confirmed: true
  confirmation_token: string
}
export interface CoachReceipt {
  operation_id: string
  request_key: string
  status: 'confirmed' | 'undone'
  study_dates: string[]
  day_revisions: Record<string, number>
  plan_id: string | null
  affected: Record<string, number>
}
export interface CoachUndoPreview {
  operation_id: string
  issued_study_date: string
  day_revisions: Record<string, number>
  plan_revision: string | null
  confirmation_token: string
  expires_in_seconds: number
}
export interface CoachLocator {
  kind: 'request' | 'confirm' | 'undo'
  request_key: string
  issued_study_date: string
  operation_id?: string
}
export interface LearningCoachClient {
  capabilities(): Promise<CoachCapabilities>
  catalog(body: CoachCatalogRequest): Promise<CoachCatalogPage>
  context(body: CoachInput): Promise<CoachContext>
  request(body: CoachRequest): Promise<CoachRunView>
  get(key: string): Promise<CoachRunView>
  cancel(key: string): Promise<CoachRunView>
  preview(body: CoachDraft): Promise<CoachPreview>
  confirm(body: CoachConfirm): Promise<CoachReceipt>
  operation(key: string): Promise<CoachReceipt>
  undoPreview(id: string): Promise<CoachUndoPreview>
  undoConfirm(id: string, body: UndoConfirmRequest): Promise<CoachReceipt>
  day(date: string): Promise<DayView>
}
export interface CoachState {
  phase: 'closed' | 'loading' | 'ready' | 'running' | 'error' | 'expired'
  identity: string | null
  generation: number
  capabilities: CoachCapabilities | null
  input: CoachInput | null
  context: CoachContext | null
  run: CoachRunView | null
  draft: CoachDraft | null
  preview: CoachPreview | null
  undo_preview: CoachUndoPreview | null
  receipt: CoachReceipt | null
  pending: CoachLocator | null
  dirty: boolean
  error: string
}
export interface CoachPresentation {
  facts: CoachFact[]
  rule_days: CoachProposal['days']
  model_status: string
  methods: { code: CoachMethod; label: string; text: string; fact_ids: string[] }[]
  coverage_notices: string[]
}
