<template>
  <section class="interview-review-panel" aria-labelledby="interview-report-title">
    <header><div><p>学习空间复盘 · V2.4</p><h2 id="interview-report-title">面试复盘报告</h2></div><span>专家校准：待校准</span></header>
    <p class="privacy-note">视频只在当前页面内存中，不上传，刷新后清除。回答、节奏和观察摘要保存在学习空间；模型建议仅供训练参考。</p>
    <div class="report-actions">
      <button class="primary" :disabled="busy || !session.turns.length" @click="generate">{{ generating ? '正在生成…' : report ? '更新规则复盘报告' : '生成规则复盘报告' }}</button>
      <button v-for="format in formats" :key="format.value" :disabled="busy || !report" @click="download(format.value)">导出 {{ format.label }}</button>
      <button :disabled="busy" @click="load">刷新报告</button>
    </div>
    <p v-if="loadLoading" role="status">正在读取复盘报告…</p>
    <p v-if="error" role="alert" class="report-error">{{ error }}</p>
    <div class="content-request">
      <label>选择内容分析的回答<select v-model="selectedTurn" :disabled="busy" aria-label="选择内容分析的回答"><option v-for="turn in session.turns" :key="turn.turn_id" :value="turn.turn_id">第{{ turn.question_index + 1 }}题 · {{ turn.question.slice(0, 35) }}</option></select></label>
      <label class="consent"><input v-model="consent" type="checkbox" :disabled="busy" />确认向已配置模型发送这一题的问题、回答和目标方向；不发送音视频或视觉观察。</label>
      <small>模型供应商的数据保存策略需另行核对；规则复盘和导出无需发送给外部模型。</small>
      <div><button :disabled="busy || !consent || !selectedTurn" @click="analyze">{{ analyzing ? '内容分析中…' : '分析这一题的内容' }}</button><button v-if="analyzing" @click="cancel">取消本次分析</button></div>
    </div>
    <article v-if="report" class="report-body">
      <p>{{ report.purpose }}</p>
      <div class="report-facts"><span>已回答 <b>{{ report.answered }} / {{ report.total }}</b></span><span>内容评估 <b>{{ report.assessed }} 题</b></span><span>语音证据 <b>{{ report.expression.speech_turns }} 题</b></span><span>视觉采样 <b>{{ report.visual.sample_count }}</b></span></div>
      <h3>表达与停顿</h3>
      <p>语速：{{ report.expression.chars_per_minute == null ? '待评测' : `${report.expression.chars_per_minute} 字/分钟` }}；口头语：{{ report.expression.filler_count ?? '待评测' }}；较长识别间隔：{{ report.expression.long_pause_count ?? '待评测' }}。</p>
      <small>{{ report.expression.method }}</small>
      <h3>面部可观察行为</h3>
      <p>人脸采样检出比例：{{ ratio(report.visual.face_observed_ratio) }}；低亮度采样比例：{{ ratio(report.visual.low_light_ratio) }}。</p>
      <small>{{ report.visual.method }} 头部、眼部和嘴角变化不等于注意力或真实心理状态。</small>
      <h3>点击时间点回看</h3>
      <p v-if="!report.timeline.length">没有采集时间证据，待评测。</p>
      <ol v-else class="report-timeline"><li v-for="(event, index) in report.timeline" :key="index"><button :disabled="event.timebase !== 'recording' || !recordingIndexes.includes(event.question_index)" @click="$emit('seek', event.question_index, event.start)">第{{ event.question_index + 1 }}题 · {{ time(event.start) }}{{ event.end > event.start ? `-${time(event.end)}` : '' }} · {{ event.label }}</button><small>{{ event.timebase === 'recording' ? recordingIndexes.includes(event.question_index) ? '本地录像时间' : '录像已清除，保留观察时间' : event.timebase === 'speech' ? '语音识别时间，未与录像对齐' : '视觉采集时间，未与录像对齐' }}</small></li></ol>
      <h3>专业内容与逻辑结构</h3>
      <details v-for="turn in report.turns" :key="turn.turn_id"><summary>第{{ turn.question_index + 1 }}题 · {{ turn.content_analysis.areas ? '模型参考建议' : '内容待评估' }}</summary><p>{{ turn.question }}</p><blockquote>{{ turn.answer }}</blockquote><p>规则表达线索：{{ turn.structure.cues.join('、') || '未观察到预设线索' }}；这些线索不代表内容准确。</p><p v-if="turn.data_error" class="report-error">部分分析数据异常，已跳过，原回答保留。</p><div v-for="(area, name) in turn.content_analysis.areas" :key="name" class="analysis-area"><b>{{ areaLabels[String(name)] || name }} · {{ statusLabels[area.status] }}</b><p v-if="area.evidence">原句：{{ area.evidence }}</p><p>{{ area.suggestion }}</p></div><p v-if="turn.content_analysis.keywords?.length">原回答关键词：{{ turn.content_analysis.keywords.join("、") }}</p><div v-for="(quote, name) in turn.content_analysis.dimension_evidence" :key="name" class="quote-evidence">{{ name }}维度原句：{{ quote }}</div></details>
      <h3>薄弱项与下一步</h3>
      <p v-if="!report.review_focus.length">薄弱知识点待评估，不由回答长度或面部动作推断。</p>
      <ul v-else><li v-for="(item, index) in report.review_focus" :key="index">第{{ item.question_index + 1 }}题 · {{ item.area }}（模型待核对）：{{ item.suggestion }}</li></ul>
      <ul><li v-for="suggestion in report.suggestions" :key="suggestion">{{ suggestion }}</li></ul>
      <small>生成时间：{{ report.generated_at }} · {{ report.calibration }}</small>
    </article>
    <p v-else-if="!loadLoading">提交回答后可生成复盘报告。未采集的语音、视觉和专业评价显示待评测。</p>
    <details class="operation-log"><summary>操作记录（最近100条）</summary><ul><li v-for="event in events" :key="event.event_id">{{ event.created_at }} · {{ actionLabels[event.action] || event.action }}</li></ul></details>
    <footer><button :disabled="busy" @click="clear">清空本场分析</button><button class="danger" :disabled="busy" @click="remove">删除本场练习</button><small>清空保留原回答和语音节奏；删除会先显示影响，需确认。</small></footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { analyzeInterviewTurn, cancelInterviewAnalysis, clearInterviewAnalysis, deleteInterviewSession, exportInterviewReview, generateInterviewReview, getInterviewReview, previewInterviewDelete, type InterviewSession } from '../services/api'
import type { InterviewReport, InterviewReviewEvent } from '../types/interviewReview'
const props = defineProps<{ session: InterviewSession; recordingIndexes: number[]; mediaBusy: boolean }>()
const emit = defineEmits<{ updated: [session: InterviewSession]; deleted: []; seek: [index: number, second: number]; cleared: [] }>()
const report = shallowRef<InterviewReport | null>(null)
const events = shallowRef<InterviewReviewEvent[]>([])
const selectedTurn = ref('')
const consent = ref(false)
const error = ref('')
const generating = ref(false)
const analyzing = ref(false)
const mutating = ref(false)
const loadLoading = ref(false)
const busy = computed(() => generating.value || analyzing.value || mutating.value || props.mediaBusy)
let epoch = 0
let disposed = false
const formats = [{ value: 'pdf' as const, label: 'PDF' }, { value: 'json' as const, label: 'JSON' }, { value: 'markdown' as const, label: 'Markdown' }]
const areaLabels: Record<string, string> = { completeness: '回答完整度', logic: '逻辑结构', technical_coverage: '专业知识覆盖', technical_expression: '技术表达', relevance: '问题相关性', star: 'STAR结构' }
const statusLabels = { covered: '有覆盖证据', partial: '部分覆盖', missing: '建议补充', not_applicable: '不适用' }
const actionLabels: Record<string, string> = { created: '创建练习', answer: '提交回答', report_generated: '生成报告', report_exported: '导出报告', content_analyzed: '内容分析', analysis_cancelled: '取消分析', analysis_cleared: '清空分析' }
const ratio = (value: number | null) => value == null ? '待评测' : `${(value * 100).toFixed(1)}%`
const time = (second: number) => `${Math.floor(second / 60).toString().padStart(2, '0')}:${Math.floor(second % 60).toString().padStart(2, '0')}`
const message = (e: unknown) => e instanceof Error ? e.message : '操作未完成，请重试'
async function load() {
  const current = ++epoch, id = props.session.interview_id
  loadLoading.value = true
  try { const data = await getInterviewReview(id); if (!disposed && current === epoch) { report.value = data.report; events.value = data.events; error.value = '' } }
  catch (e) { if (!disposed && current === epoch) error.value = message(e) }
  finally { if (current === epoch) loadLoading.value = false }
}
async function generate() {
  generating.value = true; error.value = ''
  const current = ++epoch
  try { const result = await generateInterviewReview(props.session.interview_id); if (!disposed && current === epoch) { report.value = result; await load() } }
  catch (e) { if (current === epoch) error.value = message(e) }
  finally { generating.value = false }
}
async function analyze() {
  if (!consent.value || !selectedTurn.value || busy.value) return
  analyzing.value = true; error.value = ''
  const current = ++epoch
  try { const updated = await analyzeInterviewTurn(props.session.interview_id, selectedTurn.value); if (!disposed && current === epoch) { analyzing.value = false; emit('updated', updated); report.value = null; await load() } }
  catch (e) { if (!disposed && current === epoch) error.value = message(e) }
  finally { if (current === epoch) analyzing.value = false }
}
async function cancel() {
  try { await cancelInterviewAnalysis(props.session.interview_id); epoch++; analyzing.value = false; error.value = '本次分析已取消，既有回答和报告保留。' }
  catch (e) { error.value = message(e) }
}
async function download(format: 'pdf' | 'json' | 'markdown') {
  mutating.value = true
  try { const blob = await exportInterviewReview(props.session.interview_id, format); if (disposed) return; const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `filemate-interview-${props.session.interview_id}.${format === 'markdown' ? 'md' : format}`; link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); await load() }
  catch (e) { error.value = message(e) }
  finally { mutating.value = false }
}
async function clear() {
  try { await ElMessageBox.confirm('清空内容评分、视觉观察和复盘报告，保留原回答与语音节奏。确认继续？', '清空分析', { confirmButtonText: '确认清空', cancelButtonText: '保留分析' }) }
  catch { return }
  mutating.value = true
  try { const updated = await clearInterviewAnalysis(props.session.interview_id); emit('updated', updated); emit('cleared'); report.value = null; await load() }
  catch (e) { error.value = message(e) }
  finally { mutating.value = false }
}
async function remove() {
  mutating.value = true
  try { const preview = await previewInterviewDelete(props.session.interview_id); await ElMessageBox.confirm(`将删除${preview.answers}条回答、${preview.reports}份报告及本场节奏、观察、关联Agent记录。${preview.scope} 当前页面的本场录像也将清除。`, '删除影响预览', { confirmButtonText: '确认删除本场练习', cancelButtonText: '保留练习', type: 'warning' }); await deleteInterviewSession(props.session.interview_id, preview.confirmation_token); emit('deleted') }
  catch (e) { if (e !== 'cancel' && e !== 'close') error.value = message(e) }
  finally { mutating.value = false }
}
watch(() => props.session.interview_id, () => { consent.value = false; selectedTurn.value = props.session.turns.at(-1)?.turn_id || ''; void load() }, { immediate: true })
watch(() => props.session.current_index, () => { consent.value = false; selectedTurn.value = props.session.turns.at(-1)?.turn_id || ''; void load() })
watch(selectedTurn, () => { consent.value = false })
onBeforeUnmount(() => { disposed = true; epoch++ })
</script>

<style scoped>
.interview-review-panel{margin-top:24px;padding:24px;background:var(--bg-surface);border:1px solid var(--border-subtle);border-radius:16px;line-height:1.65;overflow-wrap:anywhere}.interview-review-panel header{display:flex;gap:16px;align-items:center;justify-content:space-between}.interview-review-panel header p{margin:0;color:var(--accent);font-size:12px}.interview-review-panel h2{margin:4px 0}.interview-review-panel small,.privacy-note,header>span{color:var(--text-secondary);font-size:12px}.report-actions,footer{display:flex;flex-wrap:wrap;gap:8px}.interview-review-panel button{border:1px solid var(--accent-border);border-radius:8px;padding:9px 12px;background:var(--bg-elevated);color:var(--accent);font:inherit;font-size:13px;cursor:pointer}.interview-review-panel button.primary{background:var(--accent);color:white}.interview-review-panel button:disabled{opacity:.5;cursor:default}.interview-review-panel button.danger,.report-error{color:#b44b4b}.content-request{margin:20px 0;padding:16px;background:var(--accent-soft);border-radius:12px;display:grid;gap:8px}.content-request select{width:100%;margin-top:6px;padding:10px;border:1px solid var(--border-default);background:white;border-radius:8px;color:var(--text-primary)}.consent{display:flex;gap:8px;align-items:flex-start;font-size:13px}.consent input{margin-top:5px;flex-shrink:0}.content-request button{margin-right:8px}.report-facts{display:flex;flex-wrap:wrap;gap:20px;border-bottom:1px solid var(--border-subtle);padding-bottom:16px}.report-facts b{margin-left:8px;color:var(--accent)}.report-timeline{padding-left:20px}.report-timeline li{margin-bottom:8px}.report-timeline small{display:block}.report-body details{border-top:1px solid var(--border-subtle);padding:12px 0}.report-body summary{cursor:pointer;font-weight:600}.report-body blockquote{margin:12px 0;padding:12px 16px;border-left:3px solid var(--accent);background:var(--accent-soft);white-space:pre-wrap}.analysis-area{padding:10px 0}.analysis-area p{margin:5px 0}.quote-evidence{color:var(--text-secondary);font-size:13px}.operation-log{margin:20px 0}footer{border-top:1px solid var(--border-subtle);padding-top:18px}footer small{flex-basis:100%}button:focus-visible,select:focus-visible,input:focus-visible{outline:3px solid var(--accent-border);outline-offset:2px}@media(max-width:600px){.interview-review-panel{padding:16px}.interview-review-panel header{align-items:start;flex-direction:column}.report-actions button{flex:1 1 auto;min-height:44px}.report-timeline{padding-left:0;list-style:none}.report-timeline button{text-align:left}.report-facts{gap:10px}}
</style>
