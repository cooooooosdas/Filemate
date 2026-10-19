import type { MediaEvidence } from './interviewAudio'
import type { InterviewSession, InterviewFluencyMetrics } from '../services/api'
import type { ContentAnalysis, VisualMetrics } from './interviewReview'
export interface AttemptView {
 attempt_id: string; interview_id: string; turn_id: string; version: number; question_index: number
 question: string; answer: string; created_at: string; origin: string; analysis_status: string
 score: number | null; evaluation: { score?: number; feedback?: string; content_analysis?: ContentAnalysis; dimensions?: Record<string,number> }
 latest_run_id: string | null; data_error: boolean
}
export interface CoachSnapshot {
 session: InterviewSession; revision: number; displayed_index: number; phase: 'question'|'feedback'|'summary'
 external_consent: boolean; consent_revision: number; provider_identity: string; current_attempt: AttemptView|null
 active_run_id: string|null; pending_retries: string[]; data_error: boolean
}
export interface CoachMutationResult { snapshot: CoachSnapshot; receipt: Record<string,unknown> }
export interface CoachCommand { request_key: string; expected_revision: number }
export interface CoachAnswer extends CoachCommand { answer: string; question_index: number; expected_attempt_id: string|null; fluency_metrics?: InterviewFluencyMetrics | MediaEvidence; visual_metrics?: VisualMetrics }
export interface CoachAnalysis extends CoachCommand { attempt_id: string; consent_revision: number }
export interface CoachAdvance extends CoachCommand { from_index: number; expected_attempt_id: string }
export interface CoachFocus extends CoachCommand { question_index: number|null }
export interface CoachConsent extends CoachCommand { allowed: boolean }
export interface CoachAttempts { items: AttemptView[]; next_before_version: number|null }
export interface DraftContext { questionIndex:number; attemptId:string|null; versionToken:string }
export interface CoachDraftStore {
 load(id:string):{text:string;context:DraftContext}|null|undefined
 save(id:string,value:{text:string;context:DraftContext}):void
 remove(id:string):void
}
export interface CoachClientState {
 sessionId: string|null; epoch: number; snapshot: CoachSnapshot|null; draft: string; draftContext:DraftContext|null; composing: boolean
 pending: 'idle'|'save'|'analysis'|'advance'|'consent'; error: {code:string;message:string}|null
}
export type CoachEvent = {type:'open';id:string;epoch:number} | {type:'snapshot';id:string;epoch:number;value:CoachSnapshot} | {type:'draft';text:string;composing:boolean;context?:DraftContext|null} | {type:'pending';value:CoachClientState['pending']} | {type:'error';id:string;epoch:number;value:CoachClientState['error']} | {type:'dispose'}
export interface CoachView {
 phase: CoachSnapshot['phase']; questionIndex:number; question:string; attemptId:string|null
 analysisStatus:string; score:number|null; feedback:string; analysis:ContentAnalysis|null
 canSubmit:boolean; canAdvance:boolean; canRetry:boolean
}
export interface CoachApi {
 runtime?(id:string,kind:import('./interviewRuntime').RuntimeKind):Promise<CoachMutationResult>
 get(id:string):Promise<CoachSnapshot>; submit(id:string,input:CoachAnswer):Promise<CoachMutationResult>
 analyze(id:string,input:CoachAnalysis):Promise<CoachMutationResult>; advance(id:string,input:CoachAdvance):Promise<CoachMutationResult>
 consent(id:string,input:CoachConsent):Promise<CoachMutationResult>
 focus(id:string,input:CoachFocus):Promise<CoachMutationResult>
 attempts(id:string,turnId:string,options?:{limit?:number;before_version?:number}):Promise<CoachAttempts>
}
