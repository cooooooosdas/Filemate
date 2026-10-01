export type VisualKind = 'no_face' | 'low_light' | 'head_turn' | 'head_pose_change' | 'smile_change' | 'look_direction_change'
export interface VisualEvent { kind: VisualKind; start: number; end: number }
export interface VisualMetrics {
  source: 'mediapipe_local_v1'
  timeline_origin: 'recording' | 'visual'
  duration_seconds: number
  sample_count: number
  face_samples: number
  low_light_samples: number
  dropped_samples: number
  events: VisualEvent[]
  events_truncated: boolean
}
export interface ContentArea { status: 'covered' | 'partial' | 'missing' | 'not_applicable'; evidence: string; suggestion: string }
export interface ContentAnalysis {
  source?: 'llm_reference'
  areas?: Record<string, ContentArea>
  dimension_evidence?: Record<string, string>
  keywords?: string[]
}
export interface InterviewTimeline {
  question_index: number; start: number; end: number; kind: string; label: string
  timebase: 'recording' | 'speech' | 'visual'
}
export interface InterviewReport {
  version: string; artifact_id: string; generated_at: string; interview_id: string
  target_role: string; scenario: string; status: string; answered: number; total: number; assessed: number
  overall_score: number | null; calibration: string; purpose: string
  expression: { speech_turns: number; duration_seconds: number; chars_per_minute: number | null; filler_count: number | null; long_pause_count: number | null; method: string }
  visual: { sample_count: number; face_observed_ratio: number | null; low_light_ratio: number | null; method: string }
  turns: { turn_id: string; question_index: number; question: string; answer: string; score: number | null; scoring_mode: string; feedback: string; content_analysis: ContentAnalysis; structure: { cues: string[]; character_count: number }; data_error: boolean }[]
  timeline: InterviewTimeline[]
  review_focus: { question_index: number; area: string; evidence: string; suggestion: string; source: string }[]
  suggestions: string[]; privacy: Record<string, string>
}
export interface InterviewReviewEvent { event_id: number; action: string; detail: string; created_at: string }
export interface InterviewDeletePreview { interview_id: string; answers: number; reports: number; confirmation_token: string; scope: string }
