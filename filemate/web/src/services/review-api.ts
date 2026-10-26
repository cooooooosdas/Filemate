import type { ReviewAnswer, ReviewAnswerResult, ReviewAttempt, ReviewDetail, ReviewDiagnosis, ReviewEvent, ReviewPage, ReviewPreview, ReviewSchedule, ReviewScheduleReceipt, ReviewState, ReviewSummary } from '../types/wrongbook'
import type { ReviewCapabilities, ReviewFilter, ReviewListItem, ReviewOption } from '../types/wrongbook'
import type { ApiResponse } from '../types'
import { reviewHTTP as api, getCourseBrowserScope } from './api'
async function reviewResult<T>(request: Promise<ApiResponse<T>>): Promise<T> {
  const response = await request
  if (response.success && response.data) return response.data
  throw new Error(response.error || '复习操作未完成，请保留原稿后重试')
}
const reviewPath = (id: string) => `/wrongbook/v2/${encodeURIComponent(id)}`
export const getReviewSummary = (): Promise<ReviewSummary> => reviewResult(api.get<unknown, ApiResponse<ReviewSummary>>('/wrongbook/v2/summary'))
export const getReviewCapabilities = (): Promise<ReviewCapabilities> => reviewResult(api.get<unknown, ApiResponse<ReviewCapabilities>>('/wrongbook/v2/capabilities', { timeout: 10000 }))
export const getReviewBrowserScope = getCourseBrowserScope
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
