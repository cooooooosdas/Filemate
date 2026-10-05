export interface ResumeProject { project_id: string; title: string; role: string; description: string; submission_id: string | null }
export interface ResumeProfile {
  schema_version: 1; revision: number; name: string; email: string; phone: string; school: string; major: string
  degree: string; education_period: string; target_role: string; skills: string[]; projects: ResumeProject[]
}
export interface ResumeDocument {
  artifact_id: string; profile_revision: number; profile: ResumeProfile; selected_fact_ids: string[]
  mode: 'local' | 'llm'; generated_at: string; markdown: string; fact_policy: string
}
export interface SavedDocument { artifact_id: string; title: string; created_at: string }
export interface SemesterCourse { course_id: string; title: string; objective: string; weekly_minutes: number; weekday: number; source_id: string | null; exam_date: string | null }
export interface SemesterConfig { schema_version: 1; revision: number; title: string; start_date: string; end_date: string; courses: SemesterCourse[] }
export interface SemesterTask { task_id: string; course_id: string; kind: 'weekly' | 'exam'; week: number; title: string; due_date: string; minutes: number; completed: boolean; completed_at: string | null }
export interface SemesterState { config: SemesterConfig; tasks: SemesterTask[]; created_at: string }
export interface SemesterPreview { task_count: number; week_count: number; previous_completed: number; weekly_minutes: number; confirmation_token: string; notice: string }
export interface GrowthRecord { kind: 'quiz' | 'coding' | 'interview' | 'semester'; record_id: string; created_at: string; value: number | string | null; label: string; href: string }
export interface GrowthReport {
  artifact_id: string; period: { start_date: string; end_date: string; time_zone: string }; data_as_of: string; status: string
  metrics: { quiz_attempts: number; quiz_correct: number; quiz_accuracy: number | null; compiler_submissions: number; compiler_accepted: number; compiler_verdicts: Record<string, number>; interview_answers: number; interview_scored_answers: number; interview_model_score: number | null; semester_completed_tasks: number }
  plan_snapshot: { days: number; completed_days: number; excluded_plans: number }; excluded_records: Record<string, number>
  recommendations: { text: string; href: string }[]; notice: string; evidence_total: number; records: GrowthRecord[]
}
