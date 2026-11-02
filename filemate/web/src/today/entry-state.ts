import { readHttpStatus } from './http-status.ts'
import type { TodayMode } from '../types/today.ts'

export function resolveTodayEntry(caps: unknown, error?: unknown): { view: 'loading' | 'legacy' | 'workspace' | 'error'; message: string } {
  if (error) {
    const status = readHttpStatus(error)
    return { view: 'error', message: status === 401 ? '登录已过期，请重新登录后重试。' : status === 429 ? '请求较多，请稍后手动重试。' : '暂时无法读取今日行动，请检查连接后重试。' }
  }
  if (caps === null || caps === undefined) return { view: 'loading', message: '' }
  const value = caps as { enabled?: unknown; ui_contract?: unknown }
  if (value.enabled === false) return { view: 'legacy', message: '' }
  if (value.enabled === true && value.ui_contract === 'today-workspace-v1') return { view: 'workspace', message: '' }
  return { view: 'error', message: '今日行动前后端版本不兼容，请更新后重试。' }
}

export function todayModes(goal: unknown, studyDate: string): TodayMode[] {
  const value = goal as { goal_type?: unknown; deadline?: unknown } | null
  const deadline = value?.deadline
  const valid = typeof deadline === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(deadline) &&
    Number.isFinite(Date.parse(`${deadline}T00:00:00Z`)) && new Date(`${deadline}T00:00:00Z`).toISOString().slice(0, 10) === deadline
  return value?.goal_type === 'exam' && valid && deadline! >= studyDate ? ['daily', 'exam', 'project'] : ['daily', 'project']
}
