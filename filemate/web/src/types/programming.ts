export interface CodingProblem {
  id: string; version: number; title: string; difficulty: string; tags: string[]
  statement: string; hint: string; starter: string; language: string; attribution: string
  examples: { input: string; output: string }[]; test_count: number; time_limit_ms: number; memory_limit_mb: number
}
export interface CodingTest {
  index: number; name: string; verdict: string; input: string; input_truncated: boolean
  expected: string; actual: string; stderr: string; elapsed_ms: number; peak_memory_bytes: number
  exit_code: number; reason: string
}
export interface CodingFeedback {
  provider: string; summary: string; issues: { line: number; kind: string; message: string }[]
  time_complexity: string; space_complexity: string; suggestion: string; created_at?: string
  failed_tests?: { index: number; name: string; verdict: string; message: string }[]
}
export interface CodingSubmission {
  submission_id: string; artifact_id: string; problem_id: string; status: string; active: number
  code: string; language: string; created_at: string; updated_at: string; notes: string; data_error: boolean
  result: { verdict?: string; passed?: number; total?: number; score?: number; compile_log?: string
    compile_reason?: string; error?: string; error_code?: string; tests?: CodingTest[] }
  review: CodingFeedback | null; local_feedback: CodingFeedback | null
}
export interface ProgrammingStatus {
  ready: boolean; installed: boolean; provider: string; error: string; languages: string[]; network: boolean
}
export interface CodingOverview {
  submissions: CodingSubmission[]; evidence_scope: string
  events: { event_id: number; submission_id: string | null; action: string; created_at: string }[]
  profile: {
    attempt_count: number; accepted_count: number; rule: string
    practiced_problem_count: number; average_submissions_per_problem: number | null
    weekly: { week_start: string; submissions: number; problems: number; verdicts: Record<string, number> }
    lowest_acceptance_tags: string[]
    categories: { tag: string; submissions: number; accepted: number; accept_rate: number | null; status: string }[]
    wrongbook: { problem_id: string; title: string; error_count: number; submission_count: number
      correct_streak: number; mastered: boolean; latest_submission_id: string; latest_error_id: string; last_review_at: string | null }[]
    trend: { submission_id: string; created_at: string; problem_id: string; verdict: string; score: number }[]
  }
}
