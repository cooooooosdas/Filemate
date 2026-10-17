import type { InterviewSession } from '../services/api'
export function reportInputKey(session:InterviewSession,pending:boolean):string {
 return JSON.stringify([session.interview_id,pending,session.turns.map(turn=>[turn.turn_id,turn.answer,turn.score,turn.scoring_mode,turn.attempt_id,turn.analysis_run_id,turn.source_revision,turn.analysis_status])])
}
