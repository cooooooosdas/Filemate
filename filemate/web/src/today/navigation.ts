import type { KnowledgeArtifact, ReverseGoalPlan } from '../services/api.ts'
import type { OrchestratorSnapshot, TaskView } from '../types/orchestrator.ts'
import type { TaskNavigation, TodayTarget } from '../types/today.ts'

type Row = Record<string, unknown>
const record = (value: unknown): Row | undefined => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Row : undefined
const rows = (value: unknown, limit = 200): Row[] => Array.isArray(value) ? value.slice(0, limit).flatMap(item => record(item) ? [item as Row] : []) : []
const id = (value: unknown): string | null => typeof value === 'string' && value.trim() && value.length <= 128 && !/[\u0000-\u001f]/.test(value) ? value : null
const target = (path: string, query: Record<string, string>, label: string): TodayTarget => ({ path, query, label })
const member = (value: unknown, values: string[]) => typeof value === 'string' && values.includes(value)

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
