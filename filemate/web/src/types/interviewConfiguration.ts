export type InterviewCategory = 'general' | 'technical' | 'project' | 'creator' | 'learning_expression'
export interface InterviewConfiguration {
  schema_version: 1
  category: InterviewCategory
  track: string
  language: 'zh-CN' | 'en-US'
  difficulty: '入门' | '标准' | '压力面'
  duration_minutes: number
  difficulty_strategy: 'standard' | 'challenge'
  question_strategy: 'fixed' | 'random' | 'ai' | 'mixed'
  media_preferences: { camera:boolean; microphone:boolean; transcription:boolean; local_recording:boolean; post_analysis:boolean }
}
export interface InterviewDraftContent {
  configuration: InterviewConfiguration
  target_role: string
  source_id: string
  project_name: string
  project_details: string
}
export interface InterviewDraft {
  revision: number
  content: InterviewDraftContent | null
  updated_at?: string | null
  error?: string | null
}
export interface ConfigurationStatus {
  enabled: boolean
  draft: InterviewDraft
  capabilities?: { runtime: string; timing_active: boolean; question_strategies: string[]; creator_active: boolean }
}
export interface SaveInterviewDraft {
  content: InterviewDraftContent
  expected_revision: number
  request_key: string
}
export interface SessionConfiguration {
  origin: 'snapshot' | 'legacy' | 'unavailable'
  category: string
  track: string
  language: string | null
  duration_minutes: number | null
  timing_active: boolean
  error?: string
  media_preferences?: InterviewConfiguration['media_preferences']
}
