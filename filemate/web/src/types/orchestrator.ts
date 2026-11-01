/** Scoped references; no second task database or client-generated receipts. */
export interface ScopeRequest { goal_id: string; course_id?: string | null; source_ids?: string[] }
export interface ScheduleOptions { available_minutes: number; item_order?: string[]; pinned_ids?: string[]; excluded_ids?: string[]; minute_overrides?: Record<string, number> }
export interface PreviewRequest { scope: ScopeRequest; expected_evidence_revision: string; options: ScheduleOptions }
export interface Confirmation { confirmation_token: string; request_key: string; confirmed: true }
export interface ConfirmRequest extends PreviewRequest, Confirmation {}
export interface UndoConfirmRequest extends Confirmation {}
export interface TaskView {
  task_id: string; kind: string; title: string; source_id: string | null; goal_id: string; course_id: string | null
  due_date: string | null; estimated_minutes: number | null; estimate_source: string | null; status: string; reason: string
  priority: number; rule_version: string; evidence_refs: Record<string, unknown>[]; origin_refs: Record<string, unknown>[]
  completion_ref: Record<string, unknown> | null; action_key: string | null; route: string; eligibility: string; recorded_errors: number
  dependency_ids: string[]; dependency_coverage: string
}
export interface TaskProjection { tasks: TaskView[]; completed: TaskView[]; unavailable: Record<string, unknown>[]; overlaps: Record<string, unknown>[]; coverage: Record<string, unknown> }
export interface EvidenceSnapshot { scope: ScopeRequest; as_of: string; study_date: string; evidence_revision: string; facts: Record<string, unknown>; evidence_refs: Record<string, unknown>[]; coverage: Record<string, unknown> }
export interface OrchestratorSnapshot { snapshot: EvidenceSnapshot; projection: TaskProjection }
export interface OrchestratorCapabilities { enabled: boolean; ui_contract?: 'today-workspace-v1'; rule_version: string; limits: { sources: number; candidates: number; selected: number; daily_operations: number } }
export interface GoalOptionsRequest { q: string; offset: number }
export interface GoalChoice { goal_id: string; title: string; goal_type: string | null; deadline: string | null; source_id: string | null; valid: boolean }
export interface GoalOptionsPage { items: GoalChoice[]; total: number; offset: number; limit: 30 }
export interface SchedulePreview {
  rule_version: string; selected: TaskView[]; deferred: { task_id: string; reason: string; pinned: boolean }[]
  deferred_count: number; deferred_counts: Record<string, number>; deferred_truncated: boolean; completed: TaskView[]
  coverage: Record<string, unknown>; estimated_minutes: number; scope: ScopeRequest; study_date: string; as_of: string
  evidence_revision: string; day_revision: number; changes: Record<string, unknown>; confirmation_token: string; expires_in_seconds: number
}
export interface UndoPreview { operation_id: string; study_date: string; day_revision: number; confirmation_token: string; expires_in_seconds: number }
export interface OperationReceipt { operation_id: string; request_key: string; study_date: string; revision: number; status: 'confirmed' | 'undone'; affected: Record<string, number> }
export interface DayView { study_date: string; revision: number; status: 'confirmed' | 'not_confirmed' | 'stale'; scope: ScopeRequest | null; options: ScheduleOptions | null; selected: TaskView[]; completed: TaskView[]; stale_refs: string[]; latest_operation?: OperationReceipt | null }
export interface OrchestratorClient {
  getOrchestratorCapabilities(): Promise<OrchestratorCapabilities>
  getOrchestratorGoalOptions(request: GoalOptionsRequest): Promise<GoalOptionsPage>
  readOrchestratorSnapshot(scope: ScopeRequest): Promise<OrchestratorSnapshot>
  previewOrchestratorSchedule(request: PreviewRequest): Promise<SchedulePreview>
  confirmOrchestratorSchedule(request: ConfirmRequest): Promise<OperationReceipt>
  getOrchestratorToday(): Promise<DayView>
  findOrchestratorOperation(requestKey: string): Promise<OperationReceipt>
  previewOrchestratorUndo(operationId: string): Promise<UndoPreview>
  confirmOrchestratorUndo(operationId: string, request: UndoConfirmRequest): Promise<OperationReceipt>
}
