import type { DayView, OrchestratorSnapshot, TaskView } from '../types/orchestrator.ts'
import type { TodayPresentation } from '../types/today.ts'

type Row = Record<string, unknown>
const record = (value: unknown): Row | undefined => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Row : undefined
const rows = (value: unknown, limit: number): Row[] => Array.isArray(value) ? value.slice(0, limit).flatMap(item => record(item) ? [item as Row] : []) : []
const identifier = (value: unknown): string | null => typeof value === 'string' && value.trim() && value.length <= 128 ? value : null
const sourceIds = (value: unknown): Set<string> | null => value === undefined ? new Set() : Array.isArray(value) && value.length <= 20 && value.every(identifier) ? new Set(value) : null
const calendar = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' })

function instant(value: unknown): number | null {
  if (typeof value !== 'string' || value.length > 64) return null
  const parts = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.\d{1,9})?(Z|[+-]\d{2}:\d{2})?$/.exec(value)
  if (!parts || Number(parts[1]!.slice(0, 4)) < 1 || Number(parts[2]) > 23 || Number(parts[3]) > 59 || Number(parts[4]) > 59) return null
  const date = Date.parse(`${parts[1]}T00:00:00Z`)
  if (!Number.isFinite(date) || new Date(date).toISOString().slice(0, 10) !== parts[1]) return null
  const parsed = Date.parse(value.replace(' ', 'T') + (parts[5] ? '' : 'Z'))
  return Number.isFinite(parsed) ? parsed : null
}

function sameScope(left: unknown, right: unknown): boolean {
  const a = record(left), b = record(right)
  if (!a || !b || !identifier(a.goal_id) || a.goal_id !== b.goal_id || (a.course_id ?? null) !== (b.course_id ?? null)) return false
  const aa = sourceIds(a.source_ids), bb = sourceIds(b.source_ids)
  return aa !== null && bb !== null && aa.size === bb.size && [...aa].every(id => bb.has(id))
}

function todayCount(facts: Row | undefined, snapshot: Row | undefined, sources: Set<string>, notices: string[]): number | null {
  const coverage = record(record(snapshot?.coverage)?.attempts), attempts = facts?.attempts
  const asOf = instant(snapshot?.as_of)
  const actualSources = new Set(rows(facts?.sources, 20).map(item => identifier(item.source_id)))
  if (!sources.size || ![...sources].every(source => actualSources.has(source)) || !Array.isArray(attempts) || attempts.length > 100 || !coverage || coverage.truncated !== false ||
    !Number.isInteger(coverage.total) || coverage.total !== coverage.returned || coverage.returned !== attempts.length || asOf === null) {
    notices.push('练习证据未完整读取，今日作答次数待核验。')
    return null
  }
  let count = 0, invalid = false
  const seen = new Map<string, string>()
  for (const raw of attempts) {
    const attempt = record(raw)
    if (!attempt) { invalid = true; continue }
    const source = identifier(attempt.source_id)
    if (!source) { invalid = true; continue }
    if (!sources.has(source) || attempt.judgement_status !== 'verified') continue
    const id = identifier(attempt.attempt_id), time = instant(attempt.created_at)
    if (!id || time === null || time > asOf || ![true, false, 0, 1].includes(attempt.is_correct as boolean | number)) { invalid = true; continue }
    const signature = JSON.stringify([source, attempt.created_at, attempt.is_correct])
    if (seen.has(id)) { if (seen.get(id) !== signature) invalid = true; continue }
    seen.set(id, signature)
    if (calendar.format(time) === snapshot?.study_date) count++
  }
  if (invalid) notices.push('部分作答缺少可核验的日期或判定，今日次数待核验。')
  return invalid ? null : count
}

/** Project only current scoped facts; completion is never a mastery estimate. */
export function presentToday(bundle: OrchestratorSnapshot, day: DayView | null): TodayPresentation {
  const outer = record(bundle), snapshot = record(outer?.snapshot), facts = record(snapshot?.facts)
  const scope = record(snapshot?.scope), goal = record(facts?.goal), projection = record(outer?.projection)
  const sources = sourceIds(scope?.source_ids) ?? new Set<string>(), notices: string[] = []
  const goalTitle = typeof goal?.title === 'string' && goal.title.trim()
    ? Array.from(goal.title.trim().slice(0, 320)).slice(0, 160).join('') : '选择今日优先目标'
  if (!sources.size) notices.push('尚未确定资料范围，选择目标与资料后再查看学习证据。')
  const coverageLabels: Record<string, string> = { reviews: '复习', plans: '学习计划', semester: '学期任务', goal_tasks: '目标任务', attempts: '练习', graph: '图谱', plan_links: '节点关联', interviews: '面试' }
  for (const [key, label] of Object.entries(coverageLabels)) {
    if (record(record(snapshot?.coverage)?.[key])?.truncated === true) notices.push(`${label}证据已截断，仅反映已读取范围。`)
  }
  if (record(record(snapshot?.coverage)?.plans)?.days_truncated === true) notices.push('学习计划天数已截断，历史任务仅反映已读取范围。')
  if (record(projection?.coverage)?.truncated === true || Array.isArray(projection?.completed) && projection.completed.length > 200) {
    notices.push('仅展示部分候选与历史任务，不能把已读取数量当作全部总量。')
  }
  const ownsSource = (item: Row) => item.source_id == null || typeof item.source_id === 'string' && sources.has(item.source_id)
  const completed = new Set(rows(projection?.completed, 200).filter(item => item.status === 'completed' &&
    item.goal_id === scope?.goal_id && identifier(item.task_id) && ownsSource(item))
    .map(item => String(item.task_id)))
  let next: TaskView | null = null
  const saved = record(day)
  if (saved && typeof saved.status === 'string' && ['confirmed', 'stale'].includes(saved.status) && saved.study_date === snapshot?.study_date && sameScope(saved.scope, scope)) {
    const pending = rows(projection?.tasks, 200)
    for (const selected of rows(saved.selected, 20)) {
      const current = pending.find(item => identifier(item.task_id) && item.task_id === selected.task_id &&
        item.goal_id === scope?.goal_id && item.status === 'pending' && item.eligibility === 'eligible' &&
        ownsSource(item))
      if (current) {
        const minutes = selected.estimated_minutes ?? current.estimated_minutes
        const estimate = selected.estimate_source ?? current.estimate_source
        next = { ...current, estimated_minutes: typeof minutes === 'number' && Number.isInteger(minutes) && minutes >= 1 && minutes <= 240 ? minutes : null,
          estimate_source: typeof estimate === 'string' ? estimate : null } as unknown as TaskView
        break
      }
    }
  }
  const count = todayCount(facts, snapshot, sources, notices)
  notices.push('任务完成与资料内练习记录不等于知识掌握；没有明确练习关联时不判断掌握情况。')
  return { goal_title: goalTitle, scope_label: `${scope?.course_id ? '已选课程 · ' : ''}${sources.size} 份明确资料`,
    next_task: next, today_attempts: count, historical_completed: completed.size, coverage_notices: notices.slice(0, 12) }
}
