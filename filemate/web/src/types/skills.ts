export interface SkillCriterion { kind: 'quiz' | 'coding' | 'interview'; target_id: string; question_index: number | null; required_successes: number }
export interface Skill { skill_id: string; label: string; description: string; prerequisites: string[]; criteria: SkillCriterion[] }
export interface SkillEvidence extends SkillCriterion { available: boolean; met: boolean; observed_successes: number; records: { record_id: string; href: string }[] }
export interface SkillTree { schema_version: 1; revision: number; skills: Skill[]; evidence: Record<string, SkillEvidence[]>; states: Record<string, string>; rule: string }
export interface SkillTarget { kind: SkillCriterion['kind']; target_id: string; question_index: number | null; label: string }
