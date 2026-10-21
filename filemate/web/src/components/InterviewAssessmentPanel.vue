<template>
  <section v-if="available" class="six-report" aria-labelledby="six-report-title">
    <header class="six-header">
      <div><p class="eyebrow">训练复盘 / 版本 2.6</p><h2 id="six-report-title">从回答里，看见下一步</h2><p>六个维度，每一项评价都有原文依据。</p></div>
      <span class="calibration">专家校准：待校准</span>
    </header>
    <div class="actions">
      <button class="primary" :disabled="blocked || !writable || !state.context?.answered" @click="generate('local')"><IconFileAnalytics :size="21" />整理证据报告</button>
      <button :disabled="state.busy || state.loading" @click="refresh"><IconRefresh :size="20" />刷新记录</button>
      <span v-if="state.context">本场模型重算剩余 {{ state.context.model_requests_remaining }} 次</span>
    </div>
    <div v-if="writable" class="model-request">
      <label><input v-model="consent" type="checkbox" :disabled="blocked" />授权本次分析：向已配置模型发送本场问题、最新回答、目标岗位及任务／模拟互动证据。</label>
      <p>不发送音视频或观察摘要；供应商的数据保存策略请在设置中核对。整理证据报告无需外发，也不会生成能力分。</p>
      <div class="actions"><button :disabled="blocked || !consent || !state.context?.answered || !state.context.model_requests_remaining" @click="generate('model')"><IconChartRadar :size="21" />{{ state.busy ? '正在生成新版本…' : '生成六维参考评价' }}</button><button v-if="state.busy || serverBusy" @click="cancel">取消分析</button></div>
    </div>
    <p v-else class="notice">六维重算已关闭，已有版本仍可阅读和导出。</p>
    <p v-if="state.loading || state.busy" role="status">{{ state.cancelling ? '正在取消，等待当前模型请求结束…' : state.busy ? '正在核对原文与评分依据，旧报告保留。' : '正在读取报告与版本…' }}</p>
    <p v-if="state.error || error" role="alert" class="notice error">{{ state.error || error }}</p>
    <p v-if="selectedIsHistorical" class="notice">正在查看历史快照。当前回答或任务已变化，历史分数不会代替最新回答的评价。</p>
    <article v-if="report">
      <div class="report-overview">
        <div class="score-overview"><span>整体训练参考</span><strong>{{ scoreLabel(report.result.overall_score) }}<small v-if="report.result.overall_score != null"> / 100</small></strong><p>{{ completeness[report.result.completeness] }} · 已评估 {{ report.result.dimensions.filter(d => d.score != null).length }} / 6 维</p><p>{{ report.result.weighting.rule }}</p><p>有效权重 {{ report.result.weighting.applied_weight }} / 100。{{ report.purpose }}</p></div>
        <figure class="radar">
          <svg viewBox="0 0 260 260" role="img" aria-label="六维参考图；缺失维度不补零，部分评分仅显示已评估点">
            <polygon v-for="scale in [1, 0.5]" :key="scale" :points="chart.axes.map(a => `${130 + (a.x - 130) * scale},${130 + (a.y - 130) * scale}`).join(' ')" class="radar-grid" />
            <line v-for="(axis, index) in chart.axes" :key="index" x1="130" y1="130" :x2="axis.x" :y2="axis.y" class="radar-grid" />
            <polygon v-if="chart.polygon" :points="chart.polygon" class="radar-area" />
            <circle v-for="point in chart.points" :key="point.index" :cx="point.x" :cy="point.y" r="5" class="radar-point"><title>{{ point.index + 1 }}. {{ report.result.dimensions[point.index]?.name }}：{{ scoreLabel(report.result.dimensions[point.index]?.score ?? null) }}</title></circle>
            <text v-for="(axis, index) in chart.axes" :key="`label-${index}`" :x="130 + (axis.x - 130) * 1.2" :y="134 + (axis.y - 130) * 1.2" text-anchor="middle">{{ index + 1 }}</text>
          </svg>
          <figcaption>编号对应下方六维卡片。缺证据不画分数。</figcaption>
        </figure>
      </div>
      <div class="dimension-grid">
        <section v-for="(dim, index) in report.result.dimensions" :key="dim.id" class="dimension-card" :aria-labelledby="`six-dim-${dim.id}`">
          <header><h3 :id="`six-dim-${dim.id}`"><span>{{ index + 1 }}</span>{{ dim.name }}</h3><strong>{{ scoreLabel(dim.score) }}</strong></header>
          <p class="dimension-meta">权重 {{ dim.weight }}% · {{ dim.required ? '核心维度' : '可选证据维度' }}</p>
          <p>{{ dim.reason }}</p>
          <blockquote v-for="(evidence, ei) in dim.evidence" :key="ei"><span>{{ evidence.kind === 'answer' ? '回答原句' : evidence.kind === 'interaction' ? '已回应的模拟互动' : '实际任务' }}<template v-if="evidence.question_index != null"> · 第{{ evidence.question_index + 1 }}题</template></span>{{ evidence.quote }}<small v-if="evidence.started_at">{{ evidence.started_at }} → {{ evidence.submitted_at }}</small></blockquote>
          <p class="next-step"><IconArrowRight :size="19" /><span>{{ dim.suggestion }}</span></p>
          <details><summary>评分标准与适用边界</summary><p>{{ dim.scope }}</p><ul><li v-for="(text, anchor) in dim.anchors" :key="anchor">{{ anchor }}：{{ text }}</li></ul><p v-for="evidence in dim.evidence" :key="evidence.attempt_id + evidence.quote">回答版本 ID：{{ evidence.attempt_id }}</p></details>
        </section>
      </div>
      <section class="practice"><h3>下一次练习，先做这几件事</h3><p v-if="!report.result.practice.length">尚无足够评价依据。先回答当前问题，再主动生成参考评价。</p><ol v-else><li v-for="id in report.result.practice" :key="id"><b>{{ dimension(id)?.name }}</b>：{{ dimension(id)?.suggestion }}</li></ol><p v-if="report.result.strengths.length">当前有依据的相对优势：{{ report.result.strengths.map(id => dimension(id)?.name).join('、') }}。这是本次文本训练参考。</p></section>
      <details class="originals"><summary>当前报告的原回答与任务记录</summary><article v-for="turn in report.input.turns" :key="turn.attempt_id"><h3>第{{ turn.question_index + 1 }}题 · 回答版本 {{ turn.version }}</h3><p>{{ turn.question }}</p><blockquote>{{ turn.answer }}</blockquote></article><p v-for="task in report.input.tasks" :key="task.task_id">{{ task.title }} · {{ task.status }} · {{ task.attempt_id ? '有回答依据' : '未回答' }}</p><p v-for="event in report.input.events.filter(e => e.kind === 'audience')" :key="event.event_key">{{ event.created_at }} · 模拟互动：{{ event.text }} · {{ event.attempt_id ? '已回应' : '未回应，不评分' }}</p></details>
      <footer class="report-footer"><p>{{ report.rubric.id }} / {{ report.rubric.version }}<br />{{ report.generated_at }} · {{ report.provenance.model }} · {{ report.provenance.rules_version }}</p><div class="actions"><button v-for="format in formats" :key="format" :disabled="blocked || exporting" @click="download(format)"><IconDownload :size="18" />{{ format === 'markdown' ? 'Markdown' : format.toUpperCase() }}</button></div></footer>
    </article>
    <p v-else-if="!state.loading">先整理证据，查看已有回答；主动授权后再生成六维参考评价。缺少证据的维度显示待评测。</p>
    <details class="history" @toggle="historyOpened">
      <summary><IconHistory :size="20" />报告版本与历史比较</summary>
      <div class="actions"><button :disabled="blocked || historyLoading" @click="loadHistory(true)">查看所有练习的报告</button><span>每次重算保留一份新版本</span></div>
      <ul><li v-for="item in history" :key="item.assessment_id"><div><b>{{ formatDate(item.created_at) }} · {{ item.mode === 'model' ? '模型参考' : '证据整理' }}</b><span>{{ statusNames[item.status] }} · 标准 {{ item.rubric_version }}</span></div><div class="actions"><button :disabled="blocked || item.status !== 'succeeded'" @click="select(item)">查看此版本</button><button v-if="report && item.assessment_id !== report.assessment_id" :disabled="blocked || comparing || item.status !== 'succeeded'" @click="compare(item)">与当前报告比较</button></div></li></ul>
      <p v-if="!history.length">还没有保存的六维报告。</p><button v-if="allHistory && history.length < historyTotal" :disabled="historyLoading" @click="loadHistory(false)">加载更多历史</button>
      <p v-if="comparison" role="status">{{ comparison.reason }}</p>
      <div v-if="comparison?.comparable" class="comparison-table"><table><caption>所选历史 → 当前查看报告；缺失分数不计算差值</caption><thead><tr><th>维度</th><th>所选历史</th><th>当前报告</th><th>差值</th></tr></thead><tbody><tr v-for="item in comparison.dimensions" :key="item.id"><th>{{ item.name }}</th><td>{{ scoreLabel(item.before) }}</td><td>{{ scoreLabel(item.after) }}</td><td>{{ item.delta == null ? '不可计算' : (item.delta > 0 ? '+' : '') + scoreLabel(item.delta) }}</td></tr></tbody></table></div>
    </details>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { IconArrowRight, IconChartRadar, IconDownload, IconFileAnalytics, IconHistory, IconRefresh } from '@tabler/icons-vue'
import { assessmentHistory, cancelInterviewAnalysis, compareAssessments, createAssessment, exportAssessment, getAssessmentContext, readAssessment, type InterviewSession } from '../services/api'
import { saveDownload } from '../services/downloads'
import { createAssessmentFlow, radarGeometry, scoreLabel, type AssessmentFlowState } from '../interview/assessment'
import { reportInputKey } from '../interview/report-state'
import type { AssessmentComparison, AssessmentSummary } from '../types/interviewAssessment'

const props = defineProps<{ session: InterviewSession; busy: boolean; resetKey: number; readOnly: boolean }>()
const emit = defineEmits<{ availability: [value: boolean] }>()
const state = shallowRef<AssessmentFlowState>({ sessionId: '', context: null, selected: null, loading: false, busy: false, error: '' })
const flow = createAssessmentFlow({ context: getAssessmentContext, create: createAssessment, read: readAssessment, cancel: cancelInterviewAnalysis }, value => state.value = value)
const buildEnabled = import.meta.env.VITE_ENABLE_INTERVIEW_ASSESSMENT === 'true'
const writable = computed(() => buildEnabled && state.value.context?.enabled && !props.readOnly)
const available = computed(() => !!writable.value || !!state.value.context?.history.length)
const serverBusy = computed(() => state.value.context?.history.some(i => ['running', 'cancelling'].includes(i.status)))
const blocked = computed(() => props.busy || state.value.busy || state.value.loading || !!serverBusy.value)
const consent = ref(false), error = ref(''), exporting = ref(false), historyLoading = ref(false), comparing = ref(false)
const report = computed(() => state.value.selected?.report)
const selectedIsHistorical = computed(() => !!report.value && (report.value.input.interview_id !== props.session.interview_id || state.value.selected?.input_digest !== state.value.context?.input_digest))
const chart = computed(() => radarGeometry(report.value?.result.dimensions || []))
const history = shallowRef<AssessmentSummary[]>([]), historyTotal = ref(0), allHistory = ref(false)
const comparison = shallowRef<AssessmentComparison | null>(null)
let epoch = 0, disposed = false
const formats = ['pdf', 'json', 'markdown'] as const
const completeness = { complete: '证据完整', partial: '部分维度有依据', pending: '待评测' }
const statusNames = { running: '分析中', cancelling: '取消中', succeeded: '已保存', failed: '分析失败', cancelled: '已取消', interrupted: '已中断' }
const message = (e: unknown) => e instanceof Error ? e.message : '操作未完成，请重试。'
const dimension = (id: string) => report.value?.result.dimensions.find(d => d.id === id)
const formatDate = (value: string) => new Date(value).toLocaleString('zh-CN', { hour12: false })

async function refresh() { consent.value = false; error.value = ''; comparison.value = null; await flow.load(props.session.interview_id) }
async function generate(mode: 'local' | 'model') { if (blocked.value || !writable.value) return; comparison.value = null; error.value = ''; try { await flow.generate(mode, consent.value) } finally { consent.value = false } }
async function cancel() { consent.value = false; error.value = ''; comparison.value = null; await flow.cancel() }
async function download(format: typeof formats[number]) {
  if (!state.value.selected || !report.value || blocked.value) return
  const current = epoch, selected = state.value.selected
  exporting.value = true; error.value = ''
  try { const blob = await exportAssessment(selected.interview_id, selected.assessment_id, format); if (!disposed && current === epoch) await saveDownload(blob, `filemate-six-${selected.assessment_id}.${format === 'markdown' ? 'md' : format}`) }
  catch (e) { if (current === epoch) error.value = message(e) }
  finally { if (current === epoch) exporting.value = false }
}
async function select(item: AssessmentSummary) { comparison.value = null; await flow.select(item.interview_id, item.assessment_id) }
async function compare(item: AssessmentSummary) {
  if (!report.value) return
  const current = epoch, selected = report.value.assessment_id
  comparing.value = true; error.value = ''
  try { const result = await compareAssessments(item.assessment_id, selected); if (!disposed && current === epoch && report.value?.assessment_id === selected) comparison.value = result }
  catch (e) { if (current === epoch) error.value = message(e) }
  finally { if (current === epoch) comparing.value = false }
}
async function loadHistory(reset: boolean) {
  if (historyLoading.value) return
  const current = epoch
  historyLoading.value = true; error.value = ''
  try { const page = await assessmentHistory(reset ? 0 : history.value.length); if (!disposed && current === epoch) { history.value = reset ? page.items : [...history.value, ...page.items]; historyTotal.value = page.total; allHistory.value = true } }
  catch (e) { if (current === epoch) error.value = message(e) }
  finally { if (current === epoch) historyLoading.value = false }
}
function historyOpened() { if (!allHistory.value) history.value = state.value.context?.history || [] }
watch(available, value => emit('availability', value), { immediate: true })
watch(() => state.value.context, context => { if (!allHistory.value) history.value = context?.history || [] })
watch(() => [props.session.interview_id, props.resetKey, reportInputKey(props.session, props.busy)], (value, previous) => {
  if (previous && value[1] !== previous[1]) { flow.reset(); history.value = []; historyTotal.value = 0 }
  epoch++; consent.value = false; error.value = ''; comparison.value = null; allHistory.value = false; historyLoading.value = false; exporting.value = false; comparing.value = false
  void flow.load(props.session.interview_id)
}, { immediate: true })
onBeforeUnmount(() => { disposed = true; epoch++; flow.dispose() })
</script>

<style scoped>
.six-report{margin-top:28px;padding:28px;border:1px solid var(--border-default);border-radius:20px;background:var(--bg-surface);color:var(--text-primary);font-size:17px;line-height:1.65;overflow-wrap:anywhere}.six-header,.report-footer{display:flex;justify-content:space-between;gap:20px;align-items:flex-start}.six-header h2{font-size:clamp(24px,3vw,32px);letter-spacing:-.02em;margin:4px 0}.six-header p{margin:0 0 10px}.eyebrow{color:var(--accent);font-weight:650;font-size:15px}.calibration{border:1px solid var(--border-default);padding:6px 12px;border-radius:20px;font-size:15px;white-space:nowrap}.actions{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:12px 0}.actions>span,.dimension-meta,figcaption{font-size:15px;color:var(--text-secondary)}button{font:inherit;font-size:16px;border:1px solid var(--border-default);border-radius:10px;min-height:44px;padding:9px 14px;color:var(--text-primary);background:var(--bg-elevated);cursor:pointer;display:inline-flex;gap:8px;align-items:center;justify-content:center}button.primary{background:var(--action-fill,var(--accent));color:white;border-color:transparent}button:disabled{opacity:.5;cursor:default}button:focus-visible,summary:focus-visible,input:focus-visible{outline:3px solid var(--accent);outline-offset:3px}.model-request{border-left:3px solid var(--accent);padding:16px 20px;margin:20px 0;background:var(--accent-soft);border-radius:0 12px 12px 0}.model-request label{display:flex;align-items:flex-start;gap:10px}.model-request input{width:20px;height:20px;flex-shrink:0;margin-top:4px;accent-color:var(--accent)}.model-request p{font-size:15px;color:var(--text-secondary);margin:10px 0}.notice{border:1px solid var(--border-default);border-radius:10px;padding:14px}.error{color:var(--status-danger-text,#b44b4b)}.report-overview{display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:30px;align-items:center;padding:24px 0;border-bottom:1px solid var(--border-default)}.score-overview>span{font-weight:600}.score-overview>strong{display:block;font-size:clamp(32px,4vw,48px);line-height:1.5;color:var(--accent)}.score-overview small{font-size:18px;font-weight:500;color:var(--text-secondary)}.score-overview p{margin:8px 0}.radar{margin:0;text-align:center;min-width:0}.radar svg{width:100%;max-height:260px}.radar-grid{fill:none;stroke:var(--border-default);stroke-width:1.5}.radar-area{fill:var(--accent-soft);stroke:var(--accent);stroke-width:2}.radar-point{fill:var(--accent);stroke:var(--bg-surface);stroke-width:2}.radar text{fill:var(--text-primary);font-size:16px;font-weight:650}.dimension-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin:24px 0}.dimension-card{padding:20px;border:1px solid var(--border-default);border-radius:14px;min-width:0}.dimension-card header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.dimension-card h3{font-size:19px;margin:0;display:flex;gap:9px;align-items:baseline}.dimension-card h3 span{color:var(--accent);font-size:16px}.dimension-card header strong{color:var(--accent);font-size:23px;white-space:nowrap}.dimension-card p{margin:10px 0}.dimension-meta{margin-top:6px!important}blockquote{margin:14px 0;padding:14px 16px;border-left:3px solid var(--accent);background:var(--accent-soft);white-space:pre-wrap}blockquote>span,blockquote>small{display:block;font-size:15px;color:var(--text-secondary);margin-bottom:6px}.next-step{display:flex;gap:8px}.next-step svg{flex-shrink:0;margin-top:5px}details{margin:12px 0}summary{font-size:16px;font-weight:650;cursor:pointer;min-height:44px;align-content:center}details li{margin-bottom:8px}.practice{padding:4px 0 18px}.practice h3{font-size:22px}.practice li{margin:10px 0}.originals,.history{border-top:1px solid var(--border-default);padding-top:12px}.originals article{margin:16px 0}.report-footer{border-top:1px solid var(--border-default);padding-top:16px;align-items:center}.report-footer p{font-size:15px;color:var(--text-secondary);margin:0}.history summary{display:flex;gap:8px;align-items:center}.history ul{padding:0;list-style:none}.history li{display:flex;justify-content:space-between;gap:16px;align-items:center;border-bottom:1px solid var(--border-subtle);padding:12px 0}.history li span{display:block;font-size:15px;color:var(--text-secondary)}.comparison-table{overflow-x:auto}table{width:100%;border-collapse:collapse;min-width:380px}caption{text-align:left;margin:10px 0;font-size:15px}th,td{text-align:left;padding:10px;border-bottom:1px solid var(--border-default)}@media(max-width:760px){.six-report{padding:18px}.six-header,.report-footer{flex-direction:column;gap:10px}.report-overview{grid-template-columns:1fr;gap:8px}.radar{max-width:250px;justify-self:center}.dimension-grid{grid-template-columns:1fr}.history li{align-items:flex-start;flex-direction:column;gap:6px}.dimension-card{padding:16px}}
</style>
