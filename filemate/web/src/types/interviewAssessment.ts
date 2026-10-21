export interface AssessmentEvidence {
  kind: 'answer' | 'interaction' | 'timing'
  attempt_id: string
  quote: string
  question_index?: number
  event_id?: string
  task_id?: string
  started_at?: string
  submitted_at?: string
}
export interface RubricDimension {
  id: string; name: string; range: [number, number]; weight: number; required: boolean
  evidence_kind: 'answer' | 'audio' | 'interaction' | 'timing'
  scope: string; anchors: Record<string, string>
}
export interface AssessedDimension extends RubricDimension {
  status: 'assessed' | 'missing'; score: number | null
  evidence: AssessmentEvidence[]; reason: string; suggestion: string
}
export interface InterviewRubric {
  id: string; version: string; category: string; track: string
  calibration: string; dimensions: RubricDimension[]; weight_rule: string
}
export interface SixReport {
  version: '2.6'; assessment_id: string; artifact_id: string; generated_at: string; purpose: string
  rubric: InterviewRubric
  input: {
    interview_id: string; target_role: string; scenario: string; configuration: Record<string, unknown>
    comparison_conditions?: { version: number; difficulty: string | null; duration_minutes: number | null; source_id: string; questions_digest: string; task_prompts_digest: string }
    turns: { attempt_id: string; version: number; question_index: number; question: string; answer: string }[]
    tasks: { task_id: string; title: string; status: string; attempt_id: string | null }[]
    events: { event_key: string; kind: string; text: string; created_at: string; attempt_id: string | null }[]
  }
  result: {
    dimensions: AssessedDimension[]; overall_score: number | null
    completeness: 'complete' | 'partial' | 'pending'; core_missing: string[]
    weighting: { applied_weight: number; rule: string }; strengths: string[]; practice: string[]
  }
  provenance: Record<string, string>
}
export interface AssessmentSummary {
  assessment_id: string; interview_id: string; mode: 'local' | 'model'
  status: 'running' | 'cancelling' | 'succeeded' | 'failed' | 'cancelled' | 'interrupted'
  created_at: string; error_code: string | null; input_digest: string
  rubric_id: string; rubric_version: string
}
export interface AssessmentRecord extends Omit<AssessmentSummary, 'rubric_id' | 'rubric_version'> { report: SixReport | null }
export interface AssessmentContext {
  enabled: boolean; input_digest: string; rubric: InterviewRubric
  answered: number; model_requests_remaining: number; history: AssessmentSummary[]
}
export interface AssessmentCommand {
  request_key: string; expected_digest: string; mode: 'local' | 'model'; external_consent: boolean
}
export interface AssessmentComparison {
  comparable: boolean; reason: string
  dimensions: { id: string; name: string; before: number | null; after: number | null; delta: number | null }[]
}
