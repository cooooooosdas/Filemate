import type { getCourseBrowserScope, getGraphCourse, listGraphCourses } from '../services/api.ts'
import type { DayView, OperationReceipt, OrchestratorClient, OrchestratorSnapshot, PreviewRequest, SchedulePreview, TaskView, UndoPreview } from './orchestrator.ts'

export type { OrchestratorClient } from './orchestrator.ts'
export type TodayMode = 'daily' | 'exam' | 'project'
export interface TodayPreferences { mode: TodayMode; last_goal_id: string | null }
export interface TodayPresentation {
  goal_title: string; scope_label: string; next_task: TaskView | null; today_attempts: number | null
  historical_completed: number; coverage_notices: string[]
}
export interface TodayTarget { path: string; query: Record<string, string>; label: string }
export interface TaskNavigation { primary: TodayTarget | null; related: TodayTarget[]; notice: string }
export interface TodayStorage { getItem(key: string): string | null; setItem(key: string, value: string): void; removeItem(key: string): void }
export interface TodayReadPort {
  client: OrchestratorClient; getCourseBrowserScope: typeof getCourseBrowserScope
  listGraphCourses: typeof listGraphCourses; getGraphCourse: typeof getGraphCourse
}
export interface PendingLocator { kind: 'confirm' | 'undo'; request_key: string; study_date: string; operation_id?: string; epoch?: string }
export interface TodayState {
  phase: 'loading' | 'legacy' | 'ready' | 'error' | 'expired'; identity: string | null
  snapshot: OrchestratorSnapshot | null; day: DayView | null; draft: PreviewRequest | null
  preview: SchedulePreview | null; receipt: OperationReceipt | null
  undo_preview: UndoPreview | null; pending: PendingLocator | null
  write_status: 'idle' | 'previewing' | 'confirming' | 'unknown' | 'saved' | 'undo_preview' | 'undoing'
  error: string; dirty: boolean; generation: number
}
