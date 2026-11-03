import type { CoachCatalogRequest, CoachMethod, CoachPresentation, CoachRunView } from '../types/learning-coach'

export function coachEvidenceKinds(goalType: string | null | undefined): { kind: CoachCatalogRequest['kind']; label: string }[] {
  return [{ kind: 'wrong', label: '错题与作答' }, { kind: 'concept', label: '已确认知识点' }, { kind: 'submission', label: '编译器结果' }, ...(goalType === 'exam' ? [] : [{ kind: 'interview' as const, label: '面试反馈' }]), ...(goalType === 'job' ? [{ kind: 'position' as const, label: '目标岗位' }] : [])]
}

export const coachMethods: Record<CoachMethod, string> = { reread: '回到原资料', trace_error: '逐步检查错因', compare_cases: '比较相近例子', retry_independently: '独立重做', rehearse: '口头演练', practice: '针对性练习' }
export function presentCoach(run: CoachRunView): CoachPresentation {
  const model_status = run.status === 'stale' ? '依据已变化，请重新读取' : run.status === 'cancelled' ? '本次已取消' : run.status === 'running' ? '正在生成建议，可取消' : run.requested_mode === 'rule' ? '本地规则建议' : run.model_status === 'succeeded' ? '模型补充建议，请核对依据' : '模型暂不可用，已保留本地规则建议'
  const proposal = run.proposal
  const coverage_notices = [...(proposal?.limitations ?? [])]
  const deferred: Record<string, string> = { budget: '超出本次预算', estimate_required: '还需补充预计时长', excluded: '已主动排除', limit: '达到单日任务上限', prerequisite_unavailable: '前置任务尚未完成或未排入', dependency_cycle: '前置关系需修正', not_due: '尚未到期', paused: '已暂停', archived: '已归档', pending_check: '原作答待核验' }
  for (const day of proposal?.days ?? []) for (const [reason, count] of Object.entries(day.schedule.deferred_counts ?? {})) if (count > 0) coverage_notices.push(`${day.study_date}：${count}项候选任务${deferred[reason] ?? '当前不符合安排条件'}，未纳入本次安排。`)
  if (run.safe_error_code === 'credentials_missing') coverage_notices.push('尚缺有效模型凭据，可在可信与隐私中设置；当前仍可使用本地规则建议。')
  const external = proposal?.coverage.external as { omitted_facts?: number; omitted_tasks?: number } | undefined
  if (external?.omitted_facts) coverage_notices.push(`${external.omitted_facts}项依据未纳入模型外发体`)
  if (external?.omitted_tasks) coverage_notices.push(`${external.omitted_tasks}项原任务未纳入模型外发体`)
  return { facts: proposal?.facts ?? [], rule_days: proposal?.days ?? [], model_status,
    methods: (proposal?.explanations ?? []).map(item => ({ code: item.method_code, label: coachMethods[item.method_code], text: item.text, fact_ids: item.fact_ids })), coverage_notices }
}
