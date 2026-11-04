import { readHttpStatus } from './http-status.ts'
import type { KnowledgeArtifact, ReverseGoalPlan, ReverseGoalTask } from '../services/api.ts'
import type { LocationQuery, LocationQueryRaw } from 'vue-router'
import type { OrchestratorSnapshot, TaskView } from '../types/orchestrator.ts'
import type { TaskNavigation, TodayTarget } from '../types/today.ts'

export function resolveCoachAction(action: unknown): TodayTarget | null {
  const entry = record(action), ref = record(entry?.target_ref), referenceId = id(ref?.id)
  if (!ref || !referenceId) return null
  if (entry?.action === 'read_source' && ref.kind === 'source') return target('/ai-tools', { source: referenceId }, '打开原资料')
  if (entry?.action === 'review_question' && ref.kind === 'question') return target('/wrongbook', { wrong_id: referenceId }, '打开原错题')
  const course = id(ref.course_id)
  if (entry?.action === 'train_concept' && ref.kind === 'concept' && course) return target('/knowledge-graph', { graph_scope: 'course', course, node: referenceId }, '打开原知识点')
  if (entry?.action === 'rehearse_interview' && ref.kind === 'interview') return target('/interview', { interview: referenceId }, '打开原面试')
  if (entry?.action === 'practice_problem' && ref.kind === 'problem') return target('/programming', { problem: referenceId }, '打开原编程题')
  return null
}

export function studyTrainingActions(day: unknown): { label: string; target: TodayTarget }[] {
  return rows(record(day)?.training_actions, 7).flatMap(action => {
    const destination = resolveCoachAction(action)
    if (!destination) return []
    const label = typeof action.title === 'string' ? action.title.slice(0, 160) : destination.label
    return [{ label, target: destination }]
  })
}

type Row = Record<string, unknown>
const record = (value: unknown): Row | undefined => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Row : undefined
const rows = (value: unknown, limit = 200): Row[] => Array.isArray(value) ? value.slice(0, limit).flatMap(item => record(item) ? [item as Row] : []) : []
const id = (value: unknown): string | null => typeof value === 'string' && value.trim() && value.length <= 128 && !/[\u0000-\u001f]/.test(value) ? value : null
const target = (path: string, query: Record<string, string>, label: string): TodayTarget => ({ path, query, label })
const member = (value: unknown, values: string[]) => typeof value === 'string' && values.includes(value)

export function readRouteReference(query: Record<string, unknown>, key: string, max = 128): { value: string | null; present: boolean; notice: string } {
  const value = query?.[key]
  if (value === undefined) return { value: null, present: false, notice: '' }
  if (typeof value !== 'string' || !value.trim() || value.length > max || /[\x00-\x1f]/.test(value)) return { value: null, present: true, notice: '任务链接含重复或无效参数，请重新选择原记录。' }
  return { value, present: true, notice: '' }
}

export function normalizeWrongbookQuery(query: LocationQuery, v2: boolean): { query: LocationQueryRaw; blocked: boolean; changed: boolean; notice: string } {
  const wrong = readRouteReference(query, 'wrong_id'), focus = readRouteReference(query, 'focus')
  const blocked = !!wrong.notice || !!focus.notice || !!(wrong.value && focus.value && wrong.value !== focus.value)
  const result: LocationQueryRaw = { ...query }
  if (blocked) return { query: result, blocked: true, changed: false, notice: '错题链接无法唯一定位原记录，请返回目录重新选择。' }
  if (v2 && wrong.value) { delete result.wrong_id; result.focus = wrong.value }
  return { query: result, blocked: false, changed: v2 && !!wrong.value, notice: '' }
}

export async function loadExactTodayGoal(goalId: string, recent: ReverseGoalPlan[], read: (id: string) => Promise<KnowledgeArtifact>): Promise<{ goal: ReverseGoalPlan | null; notice: string }> {
  if (!id(goalId)) return { goal: null, notice: '目标链接无效，请重新选择。' }
  const cached = recent.find(goal => goal.goal_id === goalId)
  if (cached) return { goal: JSON.parse(JSON.stringify(cached)) as ReverseGoalPlan, notice: '' }
  try {
    const artifact = await read(goalId)
    const goal = artifact?.artifact_id === goalId ? readStoredGoal(artifact) : null
    return { goal, notice: goal ? '' : '指定目标记录无效，原数据保留，请重新选择或修复。' }
  } catch (error) {
    return { goal: null, notice: readHttpStatus(error) === 404
      ? '指定目标不存在或当前账号无法访问，请重新选择。' : '暂时无法读取指定目标，请重试。' }
  }
}

function locate(items: unknown, requested: unknown, key: string): { index: number | null; notice: string } {
  const ref = readRouteReference({ ref: requested }, 'ref', 512)
  if (!ref.present) return { index: null, notice: '' }
  if (!ref.value || !Array.isArray(items) || items.length > 10000) return { index: null, notice: ref.notice || '任务超出当前可定位范围，请重新选择。' }
  const matches: number[] = []
  items.forEach((item, index) => { if (record(item)?.[key] === ref.value) matches.push(index) })
  return matches.length === 1 ? { index: matches[0]!, notice: '' } : { index: null, notice: '原任务不存在、已移除或标识重复，请重新选择；不会打开另一项任务。' }
}
export function locateGoalTask(goal: ReverseGoalPlan | null, requested: unknown): { index: number | null; notice: string } {
  return locate(goal?.tasks, requested, 'task_id')
}
export function locatePlanDay(days: unknown, requested: unknown): { index: number | null; notice: string } {
  if (requested === undefined) return { index: null, notice: '' }
  if (typeof requested !== 'string' || !/^[1-9]\d{0,14}$/.test(requested) || !Number.isSafeInteger(Number(requested))) return { index: null, notice: '计划天数链接无效，请重新选择原学习日。' }
  return locate(Array.isArray(days) ? days.map(day => ({ day: typeof record(day)?.day === 'number' ? String(record(day)!.day) : null })) : days, requested, 'day')
}
export function locateSemesterTask(tasks: unknown, requested: unknown): { index: number | null; page: number | null; notice: string } {
  const result = locate(tasks, requested, 'task_id')
  return { ...result, page: result.index === null ? null : Math.floor(result.index / 30) }
}
export function locateProgrammingProblem(problems: unknown, requested: unknown): { id: string | null; notice: string } {
  if (requested === undefined) return { id: null, notice: '请选择一道题开始练习。' }
  const result = locate(problems, requested, 'id')
  const ref = readRouteReference({ problem: requested }, 'problem')
  return { id: result.index !== null && !ref.notice ? ref.value : null, notice: result.notice || ref.notice }
}
export function goalTaskTarget(goal: ReverseGoalPlan, task: ReverseGoalTask): TodayTarget | null {
  if (!id(goal?.goal_id) || !task || task.status === 'invalidated') return null
  const route = task.route
  if (!['/import', '/ai-tools', '/wrongbook', '/study-plan', '/interview', '/analytics', '/skills', '/knowledge-graph', '/knowledge', '/programming', '/growth', '/goals'].includes(route)) return null
  if (route === '/goals') return target(route, { goal: goal.goal_id, task_id: task.task_id }, '复核原目标证据')
  if (route === '/interview') {
    const query: Record<string, string> = { goal: goal.goal_id, scenario: goal.goal_type === 'competition' ? '竞赛答辩' : goal.goal_type === 'postgraduate' ? '保研复试' : goal.goal_type === 'job' ? '求职面试' : '知识讲解', target: goal.title }
    if (id(task.source_id)) query.source = task.source_id!
    if (query.source && id(task.focus_wrong_id)) query.focus = task.focus_wrong_id!
    return target(route, query, '开始面试训练')
  }
  if (route === '/ai-tools' && id(goal.source_id)) return target(route, { source: goal.source_id! }, '学习原资料')
  if (route === '/wrongbook' && id(task.focus_wrong_id)) return target(route, { wrong_id: task.focus_wrong_id! }, '复习原错题')
  return target(route, {}, route === '/programming' ? '选择编程题' : '进入对应功能')
}

/** Rebuild destinations from original domain identities, never stored URL text. */
export function resolveTodayTask(task: TaskView, bundle: OrchestratorSnapshot): TaskNavigation {
  const entry = record(task), snapshot = record(record(bundle)?.snapshot), scope = record(snapshot?.scope)
  const facts = record(snapshot?.facts), goal = record(facts?.goal)
  const unavailable = (): TaskNavigation => ({ primary: null, related: [], notice: '没有可定位的原任务，请先在对应功能中选择记录。' })
  if (!entry || !scope || !id(scope.goal_id) || entry.goal_id !== scope.goal_id ||
    (entry.course_id ?? null) !== (scope.course_id ?? null)) return unavailable()
  const sources = new Set(Array.isArray(scope.source_ids) ? scope.source_ids.slice(0, 20).filter(value => id(value)) : [])
  if (entry.source_id != null && (!id(entry.source_id) || !sources.has(entry.source_id))) return unavailable()
  const origins = rows(entry.origin_refs)
  let primary: TodayTarget | null = null, planRef: Row | undefined
  if (entry.kind === 'review') {
    const original = origins.find(ref => ref.kind === 'review' && id(ref.id))
    if (original) primary = target('/wrongbook', { wrong_id: original.id as string }, '开始独立复练')
  } else if (entry.kind === 'goal') {
    const original = origins.find(ref => ref.kind === 'goal' && ref.id === scope.goal_id && id(ref.template_id))
    if (original && rows(goal?.tasks).some(item => item.task_id === original.template_id)) {
      primary = target('/goals', { goal: scope.goal_id as string, task_id: original.template_id as string }, '打开原目标任务')
    }
  } else if (entry.kind === 'plan') {
    planRef = origins.find(ref => ref.kind === 'plan' && id(ref.id) && Number.isInteger(ref.day_index) && Number(ref.day_index) >= 0)
    const plan = planRef && rows(facts?.plans, 100).find(item => item.plan_id === planRef!.id && sources.has(item.source_id))
    const day = plan && rows(plan.days).find(item => item.day_index === planRef!.day_index && Number.isInteger(item.day) && Number(item.day) > 0)
    if (plan && day) primary = target('/study-plan', { plan: plan.plan_id as string, day: String(day.day) }, '打开这一天的计划')
  } else if (entry.kind === 'semester') {
    const original = origins.find(ref => ref.kind === 'semester' && id(ref.id) && id(ref.task_id))
    if (original && rows(facts?.semester).some(item => item.artifact_id === original.id && item.task_id === original.task_id)) {
      primary = target('/semester', { task_id: original.task_id as string }, '打开原学期任务')
    }
  }
  if (!primary) return unavailable()
  const related: TodayTarget[] = []
  const source = id(entry.source_id)
  if (source && sources.has(source)) related.push(target('/ai-tools', { source }, '查看对应资料'))
  const course = id(scope.course_id)
  if (course && planRef) {
    const concepts = new Set<string>()
    for (const link of rows(facts?.plan_links)) {
      const concept = id(link.concept_id)
      if (concept && link.plan_id === planRef.id && link.day_index === planRef.day_index && rows(facts?.graph).some(evidence =>
        evidence.concept_id === concept && evidence.status === 'confirmed' && sources.has(evidence.source_id))) concepts.add(concept)
    }
    for (const node of [...concepts].slice(0, 3)) related.push(target('/knowledge-graph', { graph_scope: 'course', course, node }, '查看明确关联的知识点'))
  }
  return { primary, related, notice: '' }
}

function validDate(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value) || Number(value.slice(0, 4)) < 1) return false
  const parsed = Date.parse(`${value}T00:00:00Z`)
  return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === value
}
const nullableString = (value: unknown) => value === null || typeof value === 'string'
const finite = (value: unknown) => typeof value === 'number' && Number.isFinite(value)

/** Restore the saved DTO only; fresh gap/ability assessment is not performed. */
export function readStoredGoal(artifact: KnowledgeArtifact): ReverseGoalPlan | null {
  const outer = record(artifact), content = record(outer?.content)
  if (!outer || outer.artifact_type !== 'reverse_goal_plan' || !id(outer.artifact_id) || !content ||
    typeof outer.created_at !== 'string' || typeof outer.updated_at !== 'string' ||
    typeof content.title !== 'string' || !content.title.trim() || !member(content.goal_type, ['exam', 'competition', 'job', 'postgraduate', 'custom']) ||
    !validDate(content.deadline) || !(content.target_score === null || finite(content.target_score)) ||
    !nullableString(content.source_id) || !nullableString(content.source_name) || content.source_id !== outer.source_id ||
    !member(content.evidence_status, ['ready', 'insufficient']) || typeof content.last_agent_run_id !== 'string') return null
  const evidence = record(content.evidence_snapshot)
  if (!evidence || !Object.values(evidence).every(finite) || !Array.isArray(content.gaps) || !Array.isArray(content.tasks)) return null
  if (!content.gaps.every(raw => {
    const gap = record(raw)
    return gap && ['name', 'current', 'target', 'evidence'].every(key => typeof gap[key] === 'string') && member(gap.status, ['ready', 'gap'])
  }) || !content.tasks.every(raw => {
    const task = record(raw)
    return task && id(task.task_id) && ['title', 'reason', 'route', 'due_date'].every(key => typeof task[key] === 'string') &&
      member(task.status, ['pending', 'completed', 'invalidated'])
  })) return null
  try {
    return { ...structuredClone(content), goal_id: outer.artifact_id, created_at: outer.created_at, updated_at: outer.updated_at } as ReverseGoalPlan
  } catch { return null }
}

export function todayTargetAvailable(path: string, available: ReadonlySet<string>, courseGraphEnabled: boolean): boolean {
  return available.has(path) && (path !== '/knowledge-graph' || courseGraphEnabled === true)
}
