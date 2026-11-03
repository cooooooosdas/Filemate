<template>
  <section class="coach-evidence" aria-label="学习依据">
    <template v-if="external && context">
      <h3>本次会发送哪些内容</h3>
      <p>发送这次问题、目标与资料标识、日期预算、下列证据，以及 {{ externalTasks }} 项候选任务摘要。</p>
      <p class="coach-quotation">{{ externalQuestion }}</p>
      <p v-if="externalCoverage">{{ externalCoverage }}</p>
      <p>本次只授权一次模型请求。代码、录音和录像不在这份外发内容中。</p>
    </template>
    <template v-else>
      <h3>按需选择训练依据</h3>
      <p>资料范围沿用当前目标。再选择相关记录，核对后才用于建议。</p>
      <div class="coach-kinds" aria-label="依据类型"><button v-for="item in kinds" :key="item.kind" type="button" :disabled="disabled || reading" :aria-pressed="kind === item.kind" @click="chooseKind(item.kind)">{{ item.label }}</button></div>
      <form v-if="kind" class="coach-search" @submit.prevent="load(0)"><label>查找已保存记录<input v-model="query" maxlength="120" :disabled="disabled || reading" /></label><button type="submit" :disabled="disabled || reading">查找</button></form>
      <p v-if="reading" role="status">正在读取所选记录…</p><p v-if="error" role="alert">{{ error }}</p>
      <p v-if="kind && !reading && !page?.items.length">没有找到可选记录。可以先在原功能中完成一次练习。</p>
      <fieldset v-if="page?.items.length" :disabled="disabled || reading"><legend>选择与当前目标有关的记录</legend><label v-for="item in page.items" :key="item.id" class="coach-check"><input type="checkbox" :checked="selected(item.id)" :disabled="!item.valid" @change="pick(item, ($event.target as HTMLInputElement).checked)" /><span>{{ item.label }}<span v-if="!item.valid"> · 当前不可用</span></span></label></fieldset>
      <div v-if="page" class="coach-paging"><button type="button" :disabled="disabled || reading || !page.offset" @click="load(Math.max(0, page.offset - 30))">上一页</button><span>{{ page.total }} 条记录</span><button type="button" :disabled="disabled || reading || page.offset + page.limit >= page.total" @click="load(page.offset + 30)">下一页</button></div>
      <section v-for="(detail, id) in feedback" :key="id" class="coach-feedback-choice"><h4>选择本题需要改善的反馈</h4><p>这些是模型反馈，只作为训练参考，不是能力证明。</p><label v-for="item in detail.areas" :key="item.id" class="coach-check"><input type="checkbox" :disabled="disabled" :checked="input.selection.feedback_refs.some(ref => ref.interview_id === id && ref.feedback_item_id === item.id)" @change="pickFeedback(String(id), item.id, ($event.target as HTMLInputElement).checked)" /><span>{{ item.label }}：{{ item.evidence }}<span v-if="item.suggestion">；建议：{{ item.suggestion }}</span></span></label><p v-if="!detail.areas.length">当前回答还没有可确认的内容反馈，可先回面试页分析。</p></section>
      <section v-if="requirements.length" class="coach-feedback-choice"><h4>这次想训练哪些岗位要求</h4><label v-for="(item, index) in requirements" :key="index" class="coach-check"><input type="checkbox" :disabled="disabled" :checked="input.selection.requirement_indices.includes(index)" @change="pickRequirement(index, ($event.target as HTMLInputElement).checked)" /><span>{{ item.label }}<span v-if="item.evidence"> · {{ item.evidence }}</span></span></label></section>
    </template>
    <details v-if="facts.length" class="coach-facts"><summary>{{ external ? '核对外发的' : '查看已核对的' }} {{ facts.length }} 项依据</summary><article v-for="fact in facts" :key="fact.fact_id"><h4>{{ fact.display_text || fact.kind }}</h4><dl><template v-for="item in describe(fact)" :key="item.label"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></template></dl></article></details>
    <details v-if="external && context"><summary>核对全部外发字段</summary><pre>{{ JSON.stringify(context.external_payload, null, 2) }}</pre></details>
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getCareerPosition, getInterviewCoach } from '../../services/api'
import { coachError } from '../../today/coach-state'
import { coachEvidenceKinds } from '../../today/coach-presentation'
import type { CareerRequirement } from '../../types/career'
import type { CoachCatalogItem, CoachCatalogPage, CoachCatalogRequest, CoachContext, CoachFact, CoachInput, LearningCoachClient } from '../../types/learning-coach'

const props = defineProps<{ client: LearningCoachClient; input: CoachInput; context: CoachContext | null; disabled: boolean; external?: boolean; goalType?: string | null }>()
const emit = defineEmits<{ update: [value: CoachInput] }>()
type Kind = CoachCatalogRequest['kind']
type Feedback = { attempt: string; run: string; areas: { id: string; label: string; evidence: string; suggestion: string }[] }
const kind = ref<Kind | null>(null), query = ref(''), page = ref<CoachCatalogPage | null>(null), reading = ref(false), error = ref('')
const feedback = ref<Record<string, Feedback>>({}), requirements = ref<CareerRequirement[]>([])
let generation = 0, disposed = false
const scopeKey = () => JSON.stringify(props.input.scope)
const kinds = computed(() => coachEvidenceKinds(props.goalType ?? props.context?.facts.find(f => f.kind === 'goal')?.data.goal_type as string | undefined))
const facts = computed(() => props.external ? (Array.isArray(props.context?.external_payload.facts) ? props.context.external_payload.facts as CoachFact[] : []) : props.context?.facts ?? [])
const externalQuestion = computed(() => { const input = props.context?.external_payload.input as CoachInput | undefined; return typeof input?.question === 'string' ? input.question : '' })
const externalTasks = computed(() => Array.isArray(props.context?.external_payload.tasks) ? props.context.external_payload.tasks.length : 0)
const externalCoverage = computed(() => { const c = props.context?.external_payload.coverage as { omitted_facts?: number; omitted_tasks?: number } | undefined; return c?.omitted_facts || c?.omitted_tasks ? `有 ${c.omitted_facts || 0} 项依据和 ${c.omitted_tasks || 0} 项任务未纳入本次模型内容。` : '' })
const fields: Record<string, string> = { title: '目标或资料', question_excerpt: '问题摘录', answer_excerpt: '原答摘录', quote: '证据原文', suggestion: '原反馈建议', label: '知识点', verdict: '编译器结论', problem_id: '题目', error_count: '实际错答记录', correct_streak: '连续答对记录', next_review_at: '下次复习', day_count: '计划学习日', completed_day_count: '自报已完成日', requirement: '岗位要求', evidence: '来源原句' }
function describe(fact: CoachFact) { return Object.entries(fact.data).filter(([key, value]) => key in fields && ['string', 'number', 'boolean'].includes(typeof value)).map(([key, value]) => ({ label: fields[key]!, value: String(value) })) }
function selected(id: string) { const s = props.input.selection; return kind.value === 'position' ? s.position_id === id : (kind.value === 'wrong' ? s.wrong_ids : kind.value === 'concept' ? s.concept_ids : kind.value === 'submission' ? s.submission_ids : s.interview_ids).includes(id) }
function update(change: (value: CoachInput) => void) { const value = JSON.parse(JSON.stringify(props.input)) as CoachInput; change(value); emit('update', value) }
async function chooseKind(value: Kind) { kind.value = value; query.value = ''; await load(0) }
async function load(offset: number) {
  if (!kind.value || props.disabled) return
  const ticket = ++generation, scope = scopeKey(); reading.value = true; error.value = ''
  try { const result = await props.client.catalog({ scope: props.input.scope, kind: kind.value, q: query.value, offset }); if (!disposed && ticket === generation && scope === scopeKey()) page.value = result }
  catch (e) { if (!disposed && ticket === generation) error.value = coachError(e) }
  finally { if (!disposed && ticket === generation) reading.value = false }
}
async function pick(item: CoachCatalogItem, checked: boolean) {
  if (!item.valid || !kind.value) return
  const current = kind.value, scope = scopeKey()
  error.value = ''
  const field = current === 'wrong' ? 'wrong_ids' : current === 'concept' ? 'concept_ids' : current === 'submission' ? 'submission_ids' : 'interview_ids'
  if (current !== 'position' && checked && props.input.selection[field].length >= (current === 'submission' ? 10 : current === 'concept' ? 5 : 3)) { error.value = '已达到本类选择上限，请先取消一项。'; return }
  update(value => { if (current === 'position') { value.selection.position_id = checked ? item.id : null; value.selection.requirement_indices = [] } else { value.selection[field] = checked ? [...value.selection[field], item.id].sort() : value.selection[field].filter(id => id !== item.id); if (current === 'interview' && !checked) value.selection.feedback_refs = value.selection.feedback_refs.filter(ref => ref.interview_id !== item.id) } })
  if (!checked) { if (current === 'interview') delete feedback.value[item.id]; if (current === 'position') requirements.value = []; return }
  if (current !== 'interview' && current !== 'position') return
  reading.value = true
  try {
    if (current === 'position') { const record = await getCareerPosition(item.id); if (!disposed && scope === scopeKey() && props.input.selection.position_id === item.id) requirements.value = record.position?.requirements.slice(0, 30) ?? [] }
    else {
      const snapshot = await getInterviewCoach(item.id), attempt = snapshot.current_attempt
      if (!disposed && scope === scopeKey() && props.input.selection.interview_ids.includes(item.id)) feedback.value[item.id] = { attempt: '', run: '', areas: [] }
      if (!disposed && scope === scopeKey() && props.input.selection.interview_ids.includes(item.id) && attempt?.latest_run_id) {
        const names: Record<string, string> = { logic: '逻辑与结构', clarity: '表达清晰度', relevance: '回答切题性', completeness: '内容完整性', professional: '专业内容', evidence: '具体依据', technical_coverage: '专业知识覆盖', technical_expression: '专业表达', star: '情境与行动复盘' }
        feedback.value[item.id] = { attempt: attempt.attempt_id, run: attempt.latest_run_id, areas: Object.entries(attempt.evaluation.content_analysis?.areas ?? {}).filter(([, item]) => typeof item.evidence === 'string' && item.evidence.trim()).map(([id, item]) => ({ id, label: names[id] || id, evidence: item.evidence.slice(0, 500), suggestion: item.suggestion.slice(0, 500) })) }
      }
    }
  } catch (e) { if (!disposed && scope === scopeKey()) error.value = coachError(e) }
  finally { if (!disposed) reading.value = false }
}
function pickFeedback(id: string, item: string, checked: boolean) { const detail = feedback.value[id]; if (!detail) return; if (checked && props.input.selection.feedback_refs.length >= 3) { error.value = '本次最多选择3项具体反馈。'; return } update(value => { value.selection.feedback_refs = value.selection.feedback_refs.filter(ref => !(ref.interview_id === id && ref.feedback_item_id === item)); if (checked) value.selection.feedback_refs.push({ interview_id: id, attempt_id: detail.attempt, feedback_item_id: item, expected_revision: detail.run }) }) }
function pickRequirement(index: number, checked: boolean) { if (checked && props.input.selection.requirement_indices.length >= 5) { error.value = '本次最多选择5项岗位要求。'; return } update(value => { value.selection.requirement_indices = value.selection.requirement_indices.filter(n => n !== index); if (checked) value.selection.requirement_indices.push(index); value.selection.requirement_indices.sort((a, b) => a - b) }) }
watch(scopeKey, () => { generation++; page.value = null; feedback.value = {}; requirements.value = []; reading.value = false; error.value = '' })
onBeforeUnmount(() => { disposed = true; generation++; feedback.value = {}; requirements.value = [] })
</script>
