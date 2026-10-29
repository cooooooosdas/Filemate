import type { ReviewAnswer, ReviewAnswerResult, ReviewAttempt, ReviewDetail, ReviewDiagnosis, ReviewEvent, ReviewPage, ReviewPreview, ReviewSchedule, ReviewScheduleReceipt, ReviewState, ReviewSummary } from '../types/wrongbook'
import type { ReviewCapabilities, ReviewFilter, ReviewListItem, ReviewOption } from '../types/wrongbook'
import type { ReviewSessionPreview, ReviewSessionCheck, ReviewSessionReady } from '../types/wrongbook'
import type { ApiResponse } from '../types'
import { reviewHTTP as api, getCourseBrowserScope } from './api'
import { hasBrowserApiKey } from './llm-vault'
import type { ReviewLearningContext, ReviewAnalysis, ReviewConnection, AnalysisCommand, PlanSelection, AdoptionSelection, LearningPreview, LearningReceipt, LearningConfirmation } from '../types/reviewLearning'
async function reviewResult<T>(request: Promise<ApiResponse<T>>): Promise<T> {
  const response = await request
  if (response.success && response.data) return response.data
  throw new Error(response.error || '复习操作未完成，请保留原稿后重试')
}
const reviewPath = (id: string) => `/wrongbook/v2/${encodeURIComponent(id)}`
export const getReviewSessionPreview = (params: ReviewFilter & { available_minutes: number; minutes_per_question?: number }): Promise<ReviewSessionPreview> => reviewResult(api.get<unknown, ApiResponse<ReviewSessionPreview>>('/wrongbook/v2/session-preview', { params, timeout: 15000 }))
export const checkReviewSession = (body: ReviewSessionCheck): Promise<ReviewSessionReady> => reviewResult(api.post<unknown, ApiResponse<ReviewSessionReady>>('/wrongbook/v2/session-check', body, { timeout: 10000 }))
export const getReviewSummary = (): Promise<ReviewSummary> => reviewResult(api.get<unknown, ApiResponse<ReviewSummary>>('/wrongbook/v2/summary'))
export const getReviewCapabilities = (): Promise<ReviewCapabilities> => reviewResult(api.get<unknown, ApiResponse<ReviewCapabilities>>('/wrongbook/v2/capabilities', { timeout: 10000 }))
export const getReviewBrowserScope = getCourseBrowserScope
export const getReviewQuestionAccess = (aid:string,index:number):Promise<{legacy_writable:boolean;read_only_snapshot:boolean;question_digest:string;wrong_id?:string|null;review_route?:string|null}> => reviewResult(api.get<unknown,ApiResponse<{legacy_writable:boolean;read_only_snapshot:boolean;question_digest:string;wrong_id?:string|null;review_route?:string|null}>>(`/wrongbook/v2/question-access/${encodeURIComponent(aid)}/${index}`,{timeout:10000}))
export const getReviewPage = (params: ReviewFilter & { limit?: number; offset?: number } = {}, signal?: AbortSignal): Promise<ReviewPage<ReviewListItem>> => reviewResult(api.get<unknown, ApiResponse<ReviewPage<ReviewListItem>>>('/wrongbook/v2/page', { params, signal, timeout: 15000 }))
export const getReviewFilterOptions = (kind: 'sources' | 'courses', params: {q?: string; offset?: number; limit?: number} = {}): Promise<ReviewPage<ReviewOption>> => reviewResult(api.get<unknown, ApiResponse<ReviewPage<ReviewOption>>>('/wrongbook/v2/filter-options', { params: { kind, ...params }, timeout: 15000 }))
export const getReviewReceipt = (key: string): Promise<ReviewAnswerResult | ReviewScheduleReceipt> => reviewResult(api.get<unknown, ApiResponse<ReviewAnswerResult | ReviewScheduleReceipt>>(`/wrongbook/v2/receipts/${encodeURIComponent(key)}`, { timeout: 10000 }))
export const getReviewDetail = (id: string): Promise<ReviewDetail> => reviewResult(api.get<unknown, ApiResponse<ReviewDetail>>(reviewPath(id)))
export const getReviewAttempts = (id: string, params: {limit?: number; offset?: number} = {}): Promise<ReviewPage<ReviewAttempt>> => reviewResult(api.get<unknown, ApiResponse<ReviewPage<ReviewAttempt>>>(`${reviewPath(id)}/attempts`, {params}))
export const getReviewEvents = (id: string, params: {limit?: number; offset?: number} = {}): Promise<ReviewPage<ReviewEvent>> => reviewResult(api.get<unknown, ApiResponse<ReviewPage<ReviewEvent>>>(`${reviewPath(id)}/events`, {params}))
export const submitReviewAnswer = (input: ReviewAnswer): Promise<ReviewAnswerResult> => reviewResult(api.post<unknown, ApiResponse<ReviewAnswerResult>>('/wrongbook/v2/attempts', input))
export const setReviewDiagnosis = (id: string, input: ReviewDiagnosis): Promise<ReviewState & {wrong_id: string; review_event_id: string}> => reviewResult(api.patch<unknown, ApiResponse<ReviewState & {wrong_id: string; review_event_id: string}>>(`${reviewPath(id)}/diagnosis`, input))
export const previewReviewSchedule = (id: string, input: ReviewSchedule): Promise<ReviewPreview> => reviewResult(api.post<unknown, ApiResponse<ReviewPreview>>(`${reviewPath(id)}/schedule-preview`, input))
export const confirmReviewSchedule = (id: string, input: ReviewSchedule & {confirmed: true; confirmation_token: string}): Promise<ReviewScheduleReceipt> => reviewResult(api.post<unknown, ApiResponse<ReviewScheduleReceipt>>(`${reviewPath(id)}/schedule-confirm`, input))
export const getReviewCredentialMode = async (scope:string):Promise<'server'|'browser'> => await hasBrowserApiKey(scope).catch(()=>false) ? 'browser' : 'server'
export const getReviewLearningContext = (id:string,params:{attempt_id:string;course_id?:string;credential_mode:'server'|'browser'}):Promise<ReviewLearningContext> => reviewResult(api.get<unknown,ApiResponse<ReviewLearningContext>>(`${reviewPath(id)}/learning-context`,{params,timeout:15000}))
export const getReviewConnections = (id:string):Promise<ReviewPage<ReviewConnection>> => reviewResult(api.get<unknown,ApiResponse<ReviewPage<ReviewConnection>>>(`${reviewPath(id)}/connections`,{timeout:10000}))
export const getReviewAnalyses = (id:string):Promise<ReviewPage<ReviewAnalysis>> => reviewResult(api.get<unknown,ApiResponse<ReviewPage<ReviewAnalysis>>>(`${reviewPath(id)}/analyses`,{timeout:10000}))
export const getReviewAnalysis = (id:string,aid:string):Promise<ReviewAnalysis> => reviewResult(api.get<unknown,ApiResponse<ReviewAnalysis>>(`${reviewPath(id)}/analyses/${encodeURIComponent(aid)}`,{timeout:10000}))
export const getReviewAnalysisRequest = (key:string):Promise<ReviewAnalysis> => reviewResult(api.get<unknown,ApiResponse<ReviewAnalysis>>(`/wrongbook/v2/analysis-requests/${encodeURIComponent(key)}`,{timeout:10000}))
export const startReviewAnalysis = (id:string,body:AnalysisCommand):Promise<ReviewAnalysis> => reviewResult(api.post<unknown,ApiResponse<ReviewAnalysis>>(`${reviewPath(id)}/analyses`,body,{timeout:25000}))
export const cancelReviewAnalysis = (id:string,aid:string,body:{request_key:string}):Promise<ReviewAnalysis> => reviewResult(api.post<unknown,ApiResponse<ReviewAnalysis>>(`${reviewPath(id)}/analyses/${encodeURIComponent(aid)}/cancel`,body,{timeout:10000}))
export const previewReviewAdoption = (id:string,aid:string,body:AdoptionSelection):Promise<LearningPreview> => reviewResult(api.post<unknown,ApiResponse<LearningPreview>>(`${reviewPath(id)}/analyses/${encodeURIComponent(aid)}/adoption-preview`,body))
export const confirmReviewAdoption = (id:string,aid:string,body:AdoptionSelection & LearningConfirmation):Promise<LearningReceipt> => reviewResult(api.post<unknown,ApiResponse<LearningReceipt>>(`${reviewPath(id)}/analyses/${encodeURIComponent(aid)}/adoption-confirm`,body))
export const previewReviewLearningPlan = (id:string,body:PlanSelection):Promise<LearningPreview> => reviewResult(api.post<unknown,ApiResponse<LearningPreview>>(`${reviewPath(id)}/learning-plan-preview`,body))
export const confirmReviewLearningPlan = (id:string,body:PlanSelection & LearningConfirmation):Promise<LearningReceipt> => reviewResult(api.post<unknown,ApiResponse<LearningReceipt>>(`${reviewPath(id)}/learning-plan-confirm`,body))
export const previewReviewLearningUndo = (id:string,event:string):Promise<LearningPreview> => reviewResult(api.post<unknown,ApiResponse<LearningPreview>>(`${reviewPath(id)}/learning-operations/${encodeURIComponent(event)}/undo-preview`,{}))
export const confirmReviewLearningUndo = (id:string,event:string,body:LearningConfirmation):Promise<LearningReceipt> => reviewResult(api.post<unknown,ApiResponse<LearningReceipt>>(`${reviewPath(id)}/learning-operations/${encodeURIComponent(event)}/undo-confirm`,body))
