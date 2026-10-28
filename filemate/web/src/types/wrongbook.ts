/** 复习证据与工作台合同；可空结果不能转换为错误答案。 */
export type ReviewCause = 'concept_gap' | 'memory_gap' | 'reasoning_break' | 'expression_gap' | 'option_confusion' | 'careless' | 'method_gap' | 'condition_gap' | 'calculation_error' | 'code_error' | 'boundary_gap' | 'time_pressure' | 'other'
export type ReviewState = {
  learning_status: 'legacy' | 'new' | 'needs_review' | 'pending_check' | 'provisional' | 'criterion_met'
  schedule_status: 'active' | 'paused'
  scheduler_version: string
  review_stage: number
  eligible_count: number
  first_verified_at: string | null
  last_verified_at: string | null
  correct_streak: number
  mastered: number
  interval_days: number
  next_review_at: string
  paused_at: string | null
  revision: number
  error_cause: string
  error_cause_source: string
  error_cause_confidence: number
  error_cause_note: string
  error_causes: ReviewCause[]
  custom_tags: string[]
  diagnosed_at: string | null
  legacy_mastered: boolean | number
}
export type ReviewAnswer = {
  artifact_id: string; question_index: number; expected_question: Record<string, unknown>
  request_key: string; user_answer?: string; action?: 'answer' | 'dont_know'
  answer_revealed?: boolean; duration_ms?: number | null
  self_reported_result?: 'correct' | 'incorrect' | 'unsure' | null
}
export type ReviewAttempt = {
  attempt_id: string; artifact_id: string; question_index: number; user_answer: string
  is_correct: number | null; score: number | null; created_at: string; feedback: string
  judgement_method: string; judgement_status: string; rule_version: string; purpose: string
  answer_revealed: number; duration_ms: number | null; duration_source: string | null
}
export type ReviewAnswerResult = {
  attempt_id: string; wrong_id: string | null; is_correct: boolean | null; score: number | null
  feedback: string; judgement_method: string; judgement_status: string; rule_version: string
  reference_answer: string; eligible: boolean; reason: string
  before: Partial<ReviewState>; after: Partial<ReviewState>; review_event_id: string
}
export type ReviewDetail = ReviewState & {
  wrong_id: string; artifact_id: string; question_index: number; question: Record<string, unknown>
  latest_answer: string; error_count: number; review_count: number; review_attempt_count: number
  read_only_snapshot: boolean; data_error: boolean
  question_digest: string; source_id: string | null; knowledge_label: string
}
export type ReviewPage<T> = { items: T[]; total: number; limit: number; offset: number; has_more: boolean }
export type ReviewEvent = {
  event_id: string; action: string; attempt_id: string | null; undo_of: string | null
  before_state: Partial<ReviewState>; after_state: Partial<ReviewState>
  result: Record<string, unknown>; created_at: string
}
export type ReviewSummary = {
  total: number; paused_count: number; legacy_mastered_count: number; criterion_met_count: number
  pending_check_count: number; invalid_time_count: number; due_count: number; overdue_count: number
  rule_version: string; as_of: string; day_zone: 'Asia/Shanghai'
  active_review_count: number; saved_review_attempt_count: number
}
export type ReviewDiagnosis = {
  request_key: string; expected_revision: number; error_causes: ReviewCause[]
  primary_cause?: ReviewCause | null; custom_tags?: string[]; note?: string
}
export type ReviewSchedule = {
  request_key: string; expected_revision: number
  action: 'pause' | 'resume' | 'reschedule' | 'activate' | 'undo'
  next_review_at?: string | null; undo_event_id?: string | null; reason?: string
}
export type ReviewPreview = {
  wrong_id: string; before: ReviewState; after: Partial<ReviewState>
  confirmation_token: string; expires_in_seconds: number
}
export type ReviewScheduleReceipt = {
  wrong_id: string; revision: number; after: ReviewState; review_event_id: string
  affected: { wrong_questions: number }; reason: string
}

export type ReviewStatus = 'all' | 'due' | 'overdue' | 'active' | 'pending' | 'criterion_met' | 'legacy_completed' | 'paused' | 'history' | 'invalid'
export type ReviewFilter = {
  q?: string; source_id?: string; course_id?: string; knowledge_q?: string; status?: ReviewStatus
  cause?: ReviewCause | 'unconfirmed'; min_errors?: number; max_errors?: number
  due_from?: string; due_to?: string; created_from?: string; created_to?: string
  sort?: 'due' | 'updated' | 'errors' | 'created'; direction?: 'asc' | 'desc'; reviewable_only?: boolean
}
export type ReviewListItem = ReviewState & {
  wrong_id: string; artifact_id: string; question_index: number; question_digest: string
  source_id: string | null; source_name: string | null; stem: string; question_type: string; knowledge_label: string
  error_count: number; review_count: number; review_attempt_count: number
  created_at: string; updated_at: string; read_only_snapshot: boolean; data_error: boolean
}
export type ReviewCapabilities = { write_enabled: boolean; analysis_enabled?: boolean; rule_version: string }
export type ReviewOption = { id: string; label: string }
export type ReviewRef = { wrong_id: string; artifact_id: string; question_index: number; question_digest: string }
