import type { GraphConfirmation, GraphMode, GraphPage } from './courseGraph'

export type TrainingStatus = 'no_evidence' | 'practiced' | 'needs_reinforcement' | 'recently_stable'
export interface LearningQuestion { question_type?: string; type?: string; stem?: string; question?: string; answer: string; options?: string[]; analysis?: string; explanation?: string; citation_ids?: string[] }
export interface QuestionRef { artifact_id: string; question_index: number; question_digest: string }
export interface QuestionCandidate extends QuestionRef { question: LearningQuestion; linked: boolean; source_id: string }
export interface LearningEvidence {
  concept_id: string; label: string; status: TrainingStatus; active_support: boolean; rule_version: string; as_of: string
  counts: { attempts: number; wrong_attempts_7d: number; due_reviews: number; completed_plan_days: number; [key: string]: number }
  question_refs: GraphPage<QuestionRef & { link_valid: boolean; source_available: boolean; stem: string }>
  attempts: GraphPage<{ attempt_id: string; is_correct: boolean; created_at: string }>
  wrongs: GraphPage<{ wrong_id: string; due: boolean; mastered: boolean }>
  plans: GraphPage<{ plan_id: string; day_index: number; title: string; completed: boolean; status: string }>
}
export interface LearningWork { work_id: string; status: string; kind: string; stale: boolean; error_code: string | null; payload: { questions?: LearningQuestion[]; label?: string; quotes?: { evidence_id: string; quote: string; source_id: string }[]; limitations?: string[] } }
export interface PracticeOptions { difficulty: 'simple' | 'standard' | 'advanced'; count: number; mode: GraphMode; allow_external_model: boolean }
export interface PracticeDecision { index: number; verdict: 'accept' | 'reject'; question?: LearningQuestion }
export interface PathOptions { goal: string; concept_ids?: string[]; chapter_id?: string | null; goal_id?: string | null; daily_minutes: number; days: number }
export interface LearningPreview { confirmation_token: string; accepted_count?: number; changed_count?: number; affected_count?: number; affected?: Record<string, number> }
export interface LearningReceipt { operation_id: string; plan_id?: string; artifact_id?: string; link_id?: string; route?: string }
export interface PathPreview extends LearningPreview { tasks: { concept_id: string; label: string; day_index: number; kind: string; duration_minutes: number; reason: string; reasons: Record<string, unknown>; route: string }[]; omitted_count: number; unsupported_count: number; scope_expanded_count: number }
export interface RelatedInput { other_course_id: string; other_concept_id: string; active: boolean; relation: 'related' }
export interface RelatedCourse { link_id: string; course_id: string; concept_id: string; course_name: string; label: string; route: string; affects_learning: false }
export interface AnswerReceipt { is_correct: boolean; feedback?: string; reference_answer?: string; attempt_id?: string }
export interface LearningApi {
  getCourseLearning(cid: string, nid: string, offset?: number, signal?: AbortSignal): Promise<LearningEvidence>
  getCourseQuestions(cid: string, nid: string, q?: string, offset?: number, signal?: AbortSignal): Promise<GraphPage<QuestionCandidate>>
  getCourseRelated(cid: string, nid: string, offset?: number, signal?: AbortSignal): Promise<GraphPage<RelatedCourse>>
  submitQuizAttempt(aid: string, index: number, answer: string, question?: object): Promise<AnswerReceipt>
  generateCoursePractice(cid: string, nid: string, body: PracticeOptions & { request_key: string }): Promise<LearningWork>
  getCourseLearningWork(cid: string, wid: string): Promise<LearningWork>
  cancelCourseLearningWork(cid: string, wid: string, key: string): Promise<LearningWork>
  previewCoursePractice(cid: string, wid: string, decisions: PracticeDecision[]): Promise<LearningPreview>
  confirmCoursePractice(cid: string, wid: string, decisions: PracticeDecision[], command: GraphConfirmation): Promise<LearningReceipt>
  previewCourseLinks(cid: string, nid: string, items: QuestionRef[], active: boolean): Promise<LearningPreview>
  confirmCourseLinks(cid: string, nid: string, items: QuestionRef[], active: boolean, command: GraphConfirmation): Promise<LearningReceipt>
  previewCoursePath(cid: string, options: PathOptions): Promise<PathPreview>
  confirmCoursePath(cid: string, body: PathOptions & GraphConfirmation): Promise<LearningReceipt>
  previewCourseRelated(cid: string, nid: string, body: RelatedInput): Promise<LearningPreview>
  confirmCourseRelated(cid: string, nid: string, body: RelatedInput & GraphConfirmation): Promise<LearningReceipt>
}
