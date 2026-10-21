import type { CoachCommand } from './interviewCoach'
export type RuntimeKind = 'start'|'resume'|'submit'|'advance'|'event'|'skip'|'finish'
export interface InterviewRuntime {
  status:'prepared'|'running'|'interrupted'|'finished'|'expired'
  revision:number; version_token:string; current_task:number; duration_seconds:number
  started_at:string|null; deadline:string|null; ended_at:string|null; server_now:string
  remaining_seconds:number; event_cooldown_seconds:number; audience_count:number; ai_reserved:number
  tasks:{task_index:number;task_id:string;kind:string;title:string;prompt:string;status:string;attempt_id:string|null}[]
  events:{sequence:number;event_key:string;kind:string;task_index:number;text:string;attempt_id:string|null;created_at:string}[]
}
export interface RuntimeCommand extends CoachCommand {
  kind:RuntimeKind; expected_token:string; task_index:number
  answer?:string; expected_attempt_id?:string|null
  fluency_metrics?:unknown; visual_metrics?:unknown
}
