<template>
  <section class="portfolio-page growth-report-panel">
    <header><div><p class="eyebrow">每一条都能回看</p><h2>成长报告</h2><p>选择期间，保存带记录依据的学习回顾。</p></div></header>
    <form class="report-period" @submit.prevent="generate"><label>报告开始日期<input v-model="start" type="date" required :max="end"></label><label>报告结束日期<input v-model="end" type="date" required :min="start" :max="today"></label><button type="submit" class="primary" :disabled="busy">生成成长报告</button></form>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="busy" role="status">正在整理记录…</p>
    <div v-if="report" class="portfolio-panel">
      <h3>{{ report.period.start_date }} 至 {{ report.period.end_date }}</h3><p>北京时间（UTC+8） · 截至 {{ report.data_as_of }} 的快照</p><p v-if="report.status === 'pending_assessment'">该期间暂无有效活动记录，待评测。</p>
      <div class="report-metrics"><article><span>课程作答</span><strong>{{ report.metrics.quiz_attempts }}次</strong><p>答对 {{ report.metrics.quiz_correct }}次 · 正确率 {{ report.metrics.quiz_accuracy == null ? '待评测（不足5条）' : `${report.metrics.quiz_accuracy}%` }}</p></article><article><span>编译器判题</span><strong>{{ report.metrics.compiler_submissions }}次</strong><p>AC {{ report.metrics.compiler_accepted }}次</p><p v-for="(count, verdict) in report.metrics.compiler_verdicts" :key="verdict">{{ verdict }} · {{ count }}次</p></article><article><span>面试回答</span><strong>{{ report.metrics.interview_answers }}条</strong><p>{{ report.metrics.interview_scored_answers }}条有效模型评分 · {{ report.metrics.interview_model_score == null ? '待评测（不足5条）' : `${report.metrics.interview_model_score}分（模型参考）` }}</p></article><article><span>完成学期任务</span><strong>{{ report.metrics.semester_completed_tasks }}项</strong><p>完成时间在所选期间内，当前有效任务</p></article></div>
      <p>旧学习计划截至生成时：{{ report.plan_snapshot.completed_days }}/{{ report.plan_snapshot.days }} 个学习日已勾选；无法确定逐日完成时间，不计入期间新增成果。</p><p>排除的异常、已修订或无效记录：{{ Object.values(report.excluded_records).reduce((sum, value) => sum + value, 0) }}条。</p><p class="notice">{{ report.notice }}</p>
      <ul><li v-for="item in report.recommendations" :key="item.href"><RouterLink :to="item.href">{{ item.text }}</RouterLink></li></ul>
      <div class="actions"><button type="button" :disabled="busy" @click="download('markdown')">导出报告 Markdown</button><button type="button" :disabled="busy" @click="download('json')">导出报告 JSON</button></div>
      <h3>记录依据 · 共 {{ report.evidence_total }}条</h3><ul class="report-records"><li v-for="record in report.records" :key="`${record.kind}:${record.record_id}`"><RouterLink :to="record.href">{{ kinds[record.kind] }} · {{ record.label }}</RouterLink><span>{{ record.created_at }} · {{ record.value == null ? '未评估' : record.value }}</span></li></ul><div class="actions"><button type="button" :disabled="busy || !page" @click="paginate(page - 1)">上一页依据</button><span>第{{ page + 1 }}/{{ Math.max(1, Math.ceil(report.evidence_total / 20)) }}页</span><button type="button" :disabled="busy || (page + 1) * 20 >= report.evidence_total" @click="paginate(page + 1)">下一页依据</button></div>
    </div>
    <h3>最近30份报告</h3><ul class="document-list"><li v-for="item in history" :key="item.artifact_id"><button type="button" :disabled="busy" @click="open(item.artifact_id)">{{ item.title }}</button></li></ul><p v-if="!history.length && !busy">暂无保存报告。</p><button v-if="error" type="button" :disabled="busy" @click="load">重新读取报告</button>
  </section>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { exportGrowthReport, generateGrowthReport, getGrowthEvidence, getGrowthReport, getGrowthReports } from '../services/api'
import type { GrowthReport, SavedDocument } from '../types/portfolio'
const dateParts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date())
const part = (name: string) => dateParts.find(p => p.type === name)!.value
const today = `${part('year')}-${part('month')}-${part('day')}`, end = ref(today), start = ref(new Date(new Date(`${today}T00:00:00+08:00`).getTime() - 29 * 86400000 + 8 * 3600000).toISOString().slice(0, 10))
const report = ref<GrowthReport | null>(null), history = ref<SavedDocument[]>([]), page = ref(0), busy = ref(false), error = ref('')
const kinds = { quiz: '课程练习', coding: '编译器判题', interview: '面试回答', semester: '学期任务' }
async function perform(action: () => Promise<void>) { busy.value = true; error.value = ''; try { await action() } catch (e: any) { error.value = e.message || '报告暂不可用，原记录保留' } finally { busy.value = false } }
const load = () => perform(async () => { history.value = await getGrowthReports() })
const generate = () => perform(async () => { const result = await generateGrowthReport(start.value, end.value); report.value = result; page.value = 0; history.value = await getGrowthReports() })
const open = (id: string) => perform(async () => { report.value = await getGrowthReport(id); page.value = 0 })
const paginate = (next: number) => perform(async () => { if (!report.value) return; const result = await getGrowthEvidence(report.value.artifact_id, next * 20); report.value.records = result.items; page.value = next })
const download = (format: 'markdown' | 'json') => perform(async () => { if (!report.value) return; const blob = await exportGrowthReport(report.value.artifact_id, format); const url = URL.createObjectURL(blob as unknown as Blob); const link = document.createElement('a'); link.href = url; link.download = `growth-report.${format === 'markdown' ? 'md' : 'json'}`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000) })
onMounted(load)
</script>
<style src="../styles/portfolio.css"></style>
<style scoped>.growth-report-panel{padding:26px 0;font-size:17px}.growth-report-panel h2{font-size:28px}.report-period{display:flex;flex-wrap:wrap;gap:16px;align-items:end;margin-bottom:20px}.report-period label{margin-bottom:0}.report-metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.report-metrics article{background:var(--bg-primary,#f8fbff);padding:18px;border-radius:12px}.report-metrics strong{display:block;font-size:32px}.report-records{padding:0;list-style:none}.report-records li{padding:12px 0;border-bottom:1px solid var(--border-color);overflow-wrap:anywhere}.report-records span{display:block;font-size:16px;color:var(--text-secondary)}@media(max-width:480px){.report-metrics{grid-template-columns:1fr}.report-period{align-items:stretch;flex-direction:column}}</style>
