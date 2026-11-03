import { reviewHTTP as api } from './api'
import type { ApiResponse } from '../types'
import type { DayView, UndoConfirmRequest } from '../types/orchestrator'
import type { CoachCapabilities, CoachCatalogPage, CoachCatalogRequest, CoachConfirm, CoachContext, CoachDraft, CoachInput, CoachPreview, CoachReceipt, CoachRequest, CoachRunView, CoachUndoPreview } from '../types/learning-coach'

const root = '/api/learning/orchestrator/coach'
function result<T>(response: ApiResponse<T>): T {
  if (response?.success === true && response.data != null) return response.data
  throw new Error('学习教练请求未完成，请保留当前内容并重新读取')
}
const getResult = async <T>(path: string): Promise<T> => result(await api.get<unknown, ApiResponse<T>>(root + path, { timeout: 15000 }))
const post = async <T>(path: string, body: unknown, timeout = 30000): Promise<T> => result(await api.post<unknown, ApiResponse<T>>(root + path, body, { timeout }))
export const capabilities = (): Promise<CoachCapabilities> => getResult('/capabilities')
export const catalog = (body: CoachCatalogRequest): Promise<CoachCatalogPage> => post('/catalog', body)
export const context = (body: CoachInput): Promise<CoachContext> => post('/context', body)
export const request = (body: CoachRequest): Promise<CoachRunView> => post('/requests', body, body.mode === 'llm' ? 65000 : 30000)
export const get = (key: string): Promise<CoachRunView> => getResult('/requests/' + encodeURIComponent(key))
export const cancel = (key: string): Promise<CoachRunView> => post('/requests/' + encodeURIComponent(key) + '/cancel', {})
export const preview = (body: CoachDraft): Promise<CoachPreview> => post('/proposals/preview', body)
export const confirm = (body: CoachConfirm): Promise<CoachReceipt> => post('/proposals/confirm', body)
export const operation = (key: string): Promise<CoachReceipt> => getResult('/operations/' + encodeURIComponent(key))
export const undoPreview = (id: string): Promise<CoachUndoPreview> => post('/operations/' + encodeURIComponent(id) + '/undo-preview', {})
export const undoConfirm = (id: string, body: UndoConfirmRequest): Promise<CoachReceipt> => post('/operations/' + encodeURIComponent(id) + '/undo-confirm', body)
export const day = (date: string): Promise<DayView> => post('/day', { study_date: date })
