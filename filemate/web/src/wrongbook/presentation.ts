import type { ReviewAnswerResult, ReviewCause, ReviewState } from '../types/wrongbook.ts'

export const reviewCauses: { value: ReviewCause; label: string }[] = [
  { value: 'concept_gap', label: '概念理解' }, { value: 'memory_gap', label: '记忆提取' },
  { value: 'reasoning_break', label: '推理断点' }, { value: 'expression_gap', label: '表达不清' },
  { value: 'option_confusion', label: '选项混淆' }, { value: 'careless', label: '审题疏漏' },
  { value: 'method_gap', label: '方法选择' }, { value: 'condition_gap', label: '适用条件' },
  { value: 'calculation_error', label: '计算失误' }, { value: 'code_error', label: '代码实现' },
  { value: 'boundary_gap', label: '边界情况' }, { value: 'time_pressure', label: '时间安排' },
  { value: 'other', label: '其他原因' },
]
const text = (value: unknown) => typeof value === 'string' ? value : ''
export function presentReviewQuestion(raw: Record<string, unknown>) {
  const kind = text(raw.question_type || raw.type)
  const type = ({ '选择题': 'choice', '填空题': 'fill', '简答题': 'short_answer' } as Record<string, string>)[kind] || kind
  const options = Array.isArray(raw.options)
    ? raw.options.map((value, index) => ({ key: String.fromCharCode(65 + index), text: String(value) }))
    : raw.options && typeof raw.options === 'object'
      ? Object.entries(raw.options).map(([key, value]) => ({ key, text: String(value) })) : []
  return { stem: text(raw.stem || raw.question), type: type === 'short_answer' && text(raw.code) ? 'code' : type, options,
    reference: text(raw.answer), explanation: text(raw.analysis || raw.explanation),
    code: text(raw.code), knowledge: text(raw.knowledge_point) }
}
export function reviewStateLabel(item: Partial<ReviewState> & { read_only_snapshot?: boolean; data_error?: boolean }) {
  if (item.read_only_snapshot) return '历史只读'
  if (item.data_error) return '记录待修复'
  if (item.schedule_status === 'paused') return '已暂停'
  if (item.scheduler_version !== 'review-interval-v2') return item.mastered ? '旧版两次复练完成' : '旧版复习记录'
  return ({ new: '开始复习', needs_review: '需要复习', pending_check: '待核对', provisional: '继续巩固', criterion_met: '达到本轮复习标准', legacy: '历史记录' } as Record<string, string>)[item.learning_status || ''] || '待核对'
}
export function reviewResultLabel(result: Pick<ReviewAnswerResult, 'is_correct' | 'judgement_status'>) {
  if (result.is_correct == null) return '已保存，待核对'
  if (result.judgement_status === 'assisted') return '已保存为看答案后的练习'
  return result.is_correct ? '客观规则核对正确' : '客观规则核对未通过'
}
export function reviewTime(value: string | null | undefined) {
  if (!value) return '暂无安排'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '时间待修复' : new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date)
}
export const reviewEventAction = (action: string) => action.startsWith('schedule_') ? action.slice(9) : action
