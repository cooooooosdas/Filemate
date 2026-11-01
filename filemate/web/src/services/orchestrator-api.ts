import { reviewHTTP as api } from './api'
import type { ApiResponse } from '../types'
import type { ConfirmRequest, DayView, GoalOptionsPage, GoalOptionsRequest, OperationReceipt, OrchestratorCapabilities, OrchestratorSnapshot, PreviewRequest, SchedulePreview, ScopeRequest, UndoConfirmRequest, UndoPreview } from '../types/orchestrator'

const root = '/api/learning/orchestrator'
function result<T>(response: ApiResponse<T>): T {
  if (response?.success === true && response.data != null) return response.data
  throw new Error(response?.error || '学习安排操作未完成')
}
export async function getOrchestratorCapabilities(): Promise<OrchestratorCapabilities> {
  return result(await api.get<unknown, ApiResponse<OrchestratorCapabilities>>(`${root}/capabilities`, { timeout: 15000 }))
}
export async function getOrchestratorGoalOptions(request: GoalOptionsRequest): Promise<GoalOptionsPage> {
  return result(await api.post<unknown, ApiResponse<GoalOptionsPage>>(`${root}/goal-options`, request, { timeout: 15000 }))
}
export async function readOrchestratorSnapshot(scope: ScopeRequest): Promise<OrchestratorSnapshot> {
  return result(await api.post<unknown, ApiResponse<OrchestratorSnapshot>>(`${root}/snapshot`, scope, { timeout: 15000 }))
}
export async function previewOrchestratorSchedule(request: PreviewRequest): Promise<SchedulePreview> {
  return result(await api.post<unknown, ApiResponse<SchedulePreview>>(`${root}/preview`, request, { timeout: 30000 }))
}
export async function confirmOrchestratorSchedule(request: ConfirmRequest): Promise<OperationReceipt> {
  return result(await api.post<unknown, ApiResponse<OperationReceipt>>(`${root}/confirm`, request, { timeout: 30000 }))
}
export async function getOrchestratorToday(): Promise<DayView> {
  return result(await api.get<unknown, ApiResponse<DayView>>(`${root}/today`, { timeout: 15000 }))
}
export async function findOrchestratorOperation(requestKey: string): Promise<OperationReceipt> {
  return result(await api.get<unknown, ApiResponse<OperationReceipt>>(`${root}/operations/${encodeURIComponent(requestKey)}`, { timeout: 15000 }))
}
export async function previewOrchestratorUndo(operationId: string): Promise<UndoPreview> {
  return result(await api.post<unknown, ApiResponse<UndoPreview>>(`${root}/operations/${encodeURIComponent(operationId)}/undo-preview`, {}, { timeout: 30000 }))
}
export async function confirmOrchestratorUndo(operationId: string, request: UndoConfirmRequest): Promise<OperationReceipt> {
  return result(await api.post<unknown, ApiResponse<OperationReceipt>>(`${root}/operations/${encodeURIComponent(operationId)}/undo-confirm`, request, { timeout: 30000 }))
}
