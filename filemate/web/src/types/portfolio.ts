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
