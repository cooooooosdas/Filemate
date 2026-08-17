<template>
  <div class="study-plan-page">
    <header class="page-header">
      <div>
        <h1>把课程资料变成每日复习计划</h1>
        <p>围绕考试日期拆解重点、主动回忆、练习与模拟，并持续记录完成进度。</p>
        <p v-if="restoredTitle" class="restore-note">已恢复：{{ restoredTitle }}，完成状态会自动保存到本机。</p>
      </div>
    </header>

    <section class="planner-card">
      <label
        class="upload-zone"
        for="study-plan-file"
        :class="{ ready: selectedFile, dragging: isDragging }"
        @dragover.prevent="isDragging = true"
        @dragleave.prevent="isDragging = false"
        @drop.prevent="handleDrop"
      >
        <input
          id="study-plan-file"
          name="study_plan_file"
          hidden
          type="file"
          accept=".pdf,.doc,.docx,.ppt,.pptx,.txt"
          @change="handleFileSelect"
        />
        <span class="upload-icon">{{ selectedFile ? '✓' : '＋' }}</span>
        <div>
          <strong>{{ selectedFile?.name || '选择课程资料' }}</strong>
          <p>{{ selectedFile ? formatFileSize(selectedFile.size) : 'PDF / Word / PPT / TXT，最大 25 MB' }}</p>
        </div>
      </label>

      <div class="form-grid">
        <label>
          <span>考试日期</span>
          <input v-model="form.examDate" name="exam_date" autocomplete="off" type="date" :min="minimumExamDate" />
        </label>
        <label>
          <span>每日学习时长</span>
          <select v-model.number="form.dailyMinutes" name="daily_minutes">
            <option :value="30">30 分钟</option>
            <option :value="60">60 分钟</option>
            <option :value="90">90 分钟</option>
            <option :value="120">120 分钟</option>
            <option :value="180">180 分钟</option>
          </select>
        </label>
        <label class="wide-field">
          <span>学习目标</span>
          <input v-model.trim="form.goal" name="study_goal" autocomplete="off" type="text" placeholder="例如：掌握核心概念，期末达到 85 分…" />
        </label>
        <label class="wide-field">
          <span>薄弱知识点 <em>可选，用逗号分隔</em></span>
          <input v-model.trim="form.weakTopics" name="weak_topics" autocomplete="off" type="text" placeholder="例如：动态规划、概率分布、指针…" />
        </label>
      </div>

      <button class="generate-button" :disabled="!canGenerate || isGenerating" @click="createPlan">
        <span v-if="isGenerating" class="spinner"></span>
        {{ isGenerating ? 'AI 正在分析资料并排期…' : '生成个性化学习计划' }}
      </button>
    </section>

    <section v-if="plan" class="plan-results">
      <div class="plan-summary">
        <div class="summary-copy">
          <span class="eyebrow">YOUR STUDY ROUTE</span>
          <h2>{{ plan.title }}</h2>
          <p>{{ plan.strategy }}</p>
        </div>
        <div class="summary-metrics">
          <div><strong>{{ plan.daily_plan.length }}</strong><span>学习日</span></div>
          <div><strong>{{ plan.daily_minutes }}</strong><span>分钟/天</span></div>
          <div><strong>{{ completionRate }}%</strong><span>已完成</span></div>
        </div>
      </div>

      <div class="progress-track" role="progressbar" :aria-valuenow="completionRate" aria-valuemin="0" aria-valuemax="100">
        <span :style="{ width: `${completionRate}%` }"></span>
      </div>

      <div v-if="plan.topics.length" class="topic-row">
        <span
          v-for="topic in plan.topics"
          :key="topic.name"
          class="topic-chip"
          :class="topic.priority"
          :title="topic.reason"
        >
          {{ topic.name }}
        </span>
      </div>

      <div class="result-toolbar">
        <p>考试日：{{ formatDate(plan.exam_date) }} · {{ plan.goal }}</p>
        <div>
          <button @click="exportCsv">导出 CSV</button>
          <button @click="exportIcs">加入日历 (.ics)</button>
        </div>
      </div>

      <div class="day-list">
        <article
          v-for="(day, index) in plan.daily_plan"
          :key="`${day.date}-${index}`"
          class="day-card"
          :class="{ completed: completedDays.has(index) }"
        >
          <button
            class="completion-toggle"
            :aria-label="completedDays.has(index) ? '标记为未完成' : '标记为已完成'"
            @click="toggleDay(index)"
          >
            {{ completedDays.has(index) ? '✓' : index + 1 }}
          </button>
          <div class="day-date">
            <strong>{{ formatWeekday(day.date) }}</strong>
            <span>{{ formatDate(day.date) }}</span>
          </div>
          <div class="day-content">
            <div class="day-heading">
              <h3>{{ day.focus }}</h3>
              <span>{{ day.duration_minutes }} 分钟 · {{ day.review_method }}</span>
            </div>
            <ul>
              <li v-for="task in day.tasks" :key="task">{{ task }}</li>
            </ul>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  generateStudyPlan,
  getStudyPlans,
  updateStudyPlanDay,
  type StudyPlan
} from '../services/api'

const formatIsoDate = (date: Date) => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const tomorrow = new Date()
tomorrow.setDate(tomorrow.getDate() + 1)
const defaultExam = new Date()
defaultExam.setDate(defaultExam.getDate() + 14)

const selectedFile = ref<File | null>(null)
const isDragging = ref(false)
const isGenerating = ref(false)
const plan = ref<StudyPlan | null>(null)
const planId = ref('')
const restoredTitle = ref('')
const completedDays = ref<Set<number>>(new Set())
const minimumExamDate = formatIsoDate(tomorrow)
const form = ref({
  examDate: formatIsoDate(defaultExam),
  dailyMinutes: 60,
  goal: '掌握核心知识并通过考试',
  weakTopics: ''
})

const canGenerate = computed(() => Boolean(selectedFile.value && form.value.examDate && form.value.goal))
const completionRate = computed(() => {
  if (!plan.value?.daily_plan.length) return 0
  return Math.round((completedDays.value.size / plan.value.daily_plan.length) * 100)
})
const resetForFile = (file: File) => {
  if (file.size > 25 * 1024 * 1024) {
    ElMessage.error('文件不能超过 25 MB')
    return
  }
  selectedFile.value = file
  plan.value = null
  planId.value = ''
  restoredTitle.value = ''
  completedDays.value = new Set()
}

const handleFileSelect = (event: Event) => {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) resetForFile(file)
}

const handleDrop = (event: DragEvent) => {
  isDragging.value = false
  const file = event.dataTransfer?.files[0]
  if (file) resetForFile(file)
}

const createPlan = async () => {
  if (!selectedFile.value) return
  isGenerating.value = true
  try {
    const response = await generateStudyPlan(
      selectedFile.value,
      form.value.examDate,
      form.value.dailyMinutes,
      form.value.goal,
      form.value.weakTopics
    )
    plan.value = response.plan
    planId.value = response.plan_id
    restoredTitle.value = ''
    completedDays.value = new Set(response.completed_days)
    ElMessage.success(`已生成 ${response.plan.daily_plan.length} 天学习计划`)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '学习计划生成失败')
  } finally {
    isGenerating.value = false
  }
}

const toggleDay = async (index: number) => {
  if (!planId.value) {
    ElMessage.error('计划尚未持久化，请重新生成')
    return
  }
  const previous = new Set(completedDays.value)
  const next = new Set(completedDays.value)
  next.has(index) ? next.delete(index) : next.add(index)
  completedDays.value = next
  try {
    const updated = await updateStudyPlanDay(planId.value, index, next.has(index))
    completedDays.value = new Set(updated.completed_days)
  } catch (error) {
    completedDays.value = previous
    ElMessage.error(error instanceof Error ? error.message : '学习进度保存失败')
  }
}

const restoreLatestPlan = async () => {
  try {
    const [latest] = await getStudyPlans(undefined, 1)
    if (!latest) return
    plan.value = latest.plan_data
    planId.value = latest.plan_id
    completedDays.value = new Set(latest.completed_days)
    restoredTitle.value = latest.title
  } catch {
    // 后端未启动时由全局服务状态提示，不阻塞页面表单。
  }
}

const formatDate = (value: string) => new Intl.DateTimeFormat('zh-CN', {
  month: 'short',
  day: 'numeric'
}).format(new Date(`${value}T00:00:00`))

const formatWeekday = (value: string) => new Intl.DateTimeFormat('zh-CN', {
  weekday: 'short'
}).format(new Date(`${value}T00:00:00`))

const formatFileSize = (bytes: number) => bytes < 1024 * 1024
  ? `${Math.ceil(bytes / 1024)} KB`
  : `${(bytes / 1024 / 1024).toFixed(1)} MB`

const download = (content: string, type: string, filename: string) => {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

const csvCell = (value: string | number) => `"${String(value).replace(/"/g, '""')}"`
const exportCsv = () => {
  if (!plan.value) return
  const rows = plan.value.daily_plan.map((day, index) => [
    day.date,
    day.focus,
    day.tasks.join('；'),
    day.duration_minutes,
    day.review_method,
    completedDays.value.has(index) ? '已完成' : '未完成'
  ].map(csvCell).join(','))
  download(`\uFEFF日期,重点,任务,时长（分钟）,复习方法,状态\n${rows.join('\n')}`, 'text/csv;charset=utf-8', 'FileMate学习计划.csv')
}

const escapeIcs = (value: string) => value.replace(/\\/g, '\\\\').replace(/\n/g, '\\n').replace(/,/g, '\\,').replace(/;/g, '\\;')
const exportIcs = () => {
  if (!plan.value) return
  const events = plan.value.daily_plan.flatMap((day, index) => [
    'BEGIN:VEVENT',
    `UID:filemate-study-${day.date}-${index}@filemate`,
    `DTSTART;VALUE=DATE:${day.date.replace(/-/g, '')}`,
    `SUMMARY:${escapeIcs(`FileMate复习：${day.focus}`)}`,
    `DESCRIPTION:${escapeIcs(`${day.tasks.join('；')}（${day.duration_minutes}分钟，${day.review_method}）`)}`,
    'END:VEVENT'
  ])
  const content = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//FileMate//Study Plan//ZH-CN', ...events, 'END:VCALENDAR'].join('\r\n')
  download(content, 'text/calendar;charset=utf-8', 'FileMate学习计划.ics')
}

onMounted(restoreLatestPlan)
</script>

<style scoped>
.study-plan-page {
  max-width: 1120px;
  margin: 0 auto;
  padding: 28px;
  color: var(--text-primary);
}

.page-header,
.plan-summary,
.result-toolbar,
.day-card,
.day-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.page-header { margin-bottom: 28px; }
.page-header h1 { max-width: 720px; margin: 6px 0 10px; font-size: clamp(28px, 4vw, 46px); line-height: 1.08; letter-spacing: -0.04em; }
.page-header p, .summary-copy p, .result-toolbar p { margin: 0; color: var(--text-secondary); line-height: 1.7; }
.page-header .restore-note { margin-top: 8px; color: var(--accent); font-size: 13px; font-weight: 650; }

.planner-card, .plan-results { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 16px; padding: 24px; }
.upload-zone { display: flex; align-items: center; gap: 16px; padding: 20px; border: 1px dashed var(--border-strong); border-radius: 14px; cursor: pointer; transition: 0.2s ease; }
.upload-zone:hover, .upload-zone.dragging { border-color: var(--accent); background: var(--accent-soft); }
.upload-zone.ready { border-style: solid; border-color: var(--accent-border); }
.upload-zone strong { display: block; margin-bottom: 4px; }
.upload-zone p { margin: 0; color: var(--text-muted); font-size: 13px; }
.upload-icon { width: 42px; height: 42px; display: grid; place-content: center; background: var(--accent-soft); border-radius: 12px; color: var(--accent); font-size: 22px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 20px 0; }
.form-grid label { display: grid; gap: 8px; color: var(--text-secondary); font-size: 13px; }
.form-grid label em { color: var(--text-muted); font-style: normal; }
.wide-field { grid-column: 1 / -1; }
input, select { width: 100%; box-sizing: border-box; padding: 12px 14px; background: #ffffff; border: 1px solid var(--border-strong); border-radius: 10px; color: var(--text-primary); font: inherit; }
input:focus, select:focus { outline: 2px solid var(--accent-border); border-color: var(--accent); }
.generate-button { width: 100%; padding: 14px; border: 0; border-radius: 11px; background: var(--accent); color: #ffffff; font-weight: 750; cursor: pointer; }
.generate-button:disabled { opacity: 0.45; cursor: not-allowed; }
.spinner { display: inline-block; width: 12px; height: 12px; margin-right: 8px; border: 2px solid rgba(255,255,255,0.45); border-top-color: #ffffff; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.plan-results { margin-top: 24px; }
.summary-copy { max-width: 650px; }
.summary-copy h2 { margin: 6px 0 8px; font-size: 27px; }
.summary-metrics { display: flex; gap: 24px; }
.summary-metrics div { text-align: right; }
.summary-metrics strong, .summary-metrics span { display: block; }
.summary-metrics strong { font-size: 24px; }
.summary-metrics span { color: var(--text-muted); font-size: 11px; }
.progress-track { height: 6px; margin: 22px 0 16px; overflow: hidden; background: var(--bg-elevated); border-radius: 999px; }
.progress-track span { display: block; height: 100%; background: var(--accent); }
.topic-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }
.topic-chip { padding: 6px 10px; border-radius: 999px; background: var(--bg-elevated); color: var(--text-secondary); font-size: 12px; }
.topic-chip.high { background: #fbeaea; color: #a43e3e; }
.topic-chip.medium { background: #fbf1df; color: #8a5b18; }
.result-toolbar { padding: 16px 0; border-top: 1px solid var(--border-subtle); }
.result-toolbar div { display: flex; gap: 8px; }
.result-toolbar button { padding: 8px 12px; border: 1px solid var(--border-strong); border-radius: 8px; background: transparent; color: var(--text-secondary); cursor: pointer; }
.result-toolbar button:hover { border-color: var(--accent); color: var(--accent); }
.day-list { display: grid; gap: 10px; }
.day-card { justify-content: flex-start; gap: 14px; padding: 16px; background: var(--bg-base); border: 1px solid var(--border-subtle); border-radius: 13px; transition: opacity 0.2s ease; }
.day-card.completed { opacity: 0.55; }
.day-card.completed h3, .day-card.completed li { text-decoration: line-through; }
.completion-toggle { flex: 0 0 38px; width: 38px; height: 38px; border: 1px solid var(--accent-border); border-radius: 50%; background: transparent; color: var(--accent); font-weight: 700; cursor: pointer; }
.completed .completion-toggle { background: var(--accent); color: #ffffff; }
.day-date { flex: 0 0 72px; }
.day-date strong, .day-date span { display: block; }
.day-date strong { font-size: 13px; }
.day-date span { color: var(--text-muted); font-size: 11px; margin-top: 3px; }
.day-content { flex: 1; min-width: 0; }
.day-heading h3 { margin: 0; font-size: 15px; }
.day-heading span { color: var(--accent); font-size: 11px; }
.day-content ul { margin: 9px 0 0; padding-left: 18px; color: var(--text-secondary); font-size: 13px; line-height: 1.7; }

@media (max-width: 760px) {
  .study-plan-page { padding: 16px 0; }
  .planner-card, .plan-results { padding: 16px; border-radius: 14px; }
  .form-grid { grid-template-columns: 1fr; }
  .wide-field { grid-column: auto; }
  .plan-summary, .result-toolbar, .day-heading { align-items: flex-start; flex-direction: column; gap: 12px; }
  .summary-metrics { width: 100%; justify-content: space-between; }
  .summary-metrics div { text-align: left; }
  .day-card { align-items: flex-start; flex-wrap: wrap; }
  .day-content { flex-basis: calc(100% - 54px); }
  .day-date { display: none; }
}
</style>
