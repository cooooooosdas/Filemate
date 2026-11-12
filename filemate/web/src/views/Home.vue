<template>
  <div class="dashboard" :aria-busy="loading">
    <div class="welcome-board">
    <header class="welcome">
      <div class="welcome-copy"><div class="welcome-meta"><span>{{ greeting }}</span><time>{{ todayLabel }}</time></div><h1>今天，<br />让知识<span class="title-dot">成形。</span></h1><p>打开课件，读原文、记笔记、做练习。</p></div>
      <HeroEncouragement />
      <StudyMotif class="welcome-motif" />
    </header>
    <section class="home-action" aria-label="开始这次学习" :aria-busy="homeStatus === 'loading'">
      <div v-if="firstVisit" class="first-visit"><h2>从一份课件，开始学习</h2><ol><li>导入课件</li><li>阅读提问</li><li>练习复习</li></ol></div>
      <div class="home-action-row">
        <button v-if="action.kind === 'sample'" class="solid-link hero-start" :disabled="sampleBusy" @click="trySample">{{ sampleBusy ? '正在导入原创示例…' : action.title }}<el-icon><ArrowRight /></el-icon></button>
        <button v-else-if="action.kind === 'retry'" class="solid-link hero-start" @click="loadHomeState">{{ action.title }}</button>
        <span v-else-if="action.kind === 'pending'" role="status">{{ action.title }}</span>
        <router-link v-else class="solid-link hero-start" :to="action.route">{{ action.title }}<el-icon><ArrowRight /></el-icon></router-link>
        <router-link v-if="firstVisit" to="/import?intent=study">直接导入我的课件</router-link>
      </div>
      <p v-if="firstVisit" class="sample-note">原创示例会保存到当前空间，不调用模型。</p>
      <p v-if="homeError" role="alert">{{ homeError }}</p>
    </section>
    </div>
    <span v-if="loading" class="sr-only" role="status">正在读取你的学习记录…</span>
    <div class="dashboard-workspace">
      <div class="desk-grid">
        <div class="desk-main">
          <section class="focus-sheet" aria-labelledby="focus-heading">
            <div class="section-heading"><h2 id="focus-heading">这次想做什么？</h2><span class="section-hint">直接开始</span></div>
            <div class="task-entries">
              <article v-for="task in studyTasks" :key="task.id" class="task-entry">
                <component :is="action.route === task.route ? 'div' : RouterLink" class="task-entry-main" :to="action.route === task.route ? undefined : task.route">
                  <span class="task-symbol"><el-icon aria-hidden="true"><component :is="task.icon" /></el-icon></span>
                  <span class="task-entry-copy"><strong>{{ task.title }}</strong><span>{{ task.description }}</span></span>
                  <el-icon class="task-entry-arrow" aria-hidden="true"><ArrowRight /></el-icon>
                </component>
                <details v-if="task.links.length" class="task-details"><summary>相关功能</summary><nav class="task-entry-links" :aria-label="`${task.title}的相关功能`"><router-link v-for="link in task.links" :key="link.route" :to="link.route">{{ link.label }}<el-icon aria-hidden="true"><ArrowRight /></el-icon></router-link></nav></details>
              </article>
            </div>
          </section>
          <section class="recent-section" aria-labelledby="recent-heading">
            <div class="section-heading"><h2 id="recent-heading">归档处理记录</h2><router-link to="/history">全部记录<el-icon><ArrowRight /></el-icon></router-link></div>
            <section v-if="history.length" class="overview" aria-label="最近 100 条处理记录概览">
              <div><span>处理记录</span><strong>{{ history.length }}<small>份</small></strong></div>
              <div><span>近 7 天新增</span><strong>{{ metrics.thisWeek }}<small>份</small></strong></div>
              <router-link to="/history"><span>待确认归档</span><strong :class="{ amber: metrics.pending > 0 }">{{ metrics.pending }}<small>份</small></strong><el-icon><ArrowRight /></el-icon></router-link>
              <div><span>已归档</span><strong>{{ metrics.confirmed }}<small>份</small></strong></div>
            </section>
            <DataState v-if="!recentFiles.length" compact :loading="loading" :error="errorMessage" empty title="还没有归档处理记录" @retry="loadDashboard"><template #icon><el-icon aria-hidden="true"><FolderOpened /></el-icon></template><template #empty><p>这里记录分类与归档操作。</p></template><template #action><router-link to="/knowledge">打开我的资料<el-icon><ArrowRight /></el-icon></router-link></template></DataState>
            <div v-else class="file-list">
              <div class="file-list-head"><span>文件</span><span>状态</span></div>
              <router-link v-for="file in recentFiles" :key="file.session_id" class="file-row" to="/history" :aria-label="`在处理记录中查看 ${getFileName(file.source_path)}`">
                <span class="file-mark" :class="{ presentation: /pptx?$/i.test(file.source_path) }">{{ fileExtension(file.source_path) }}</span>
                <span class="file-copy"><strong :title="getFileName(file.source_path)">{{ getFileName(file.source_path) }}</strong><small>{{ file.category || '待分类' }}<span>·</span>{{ formatTime(file.created_at) }}</small></span>
                <span class="file-status" :class="statusClass(file.status)"><i />{{ statusLabel(file.status) }}</span><el-icon class="row-arrow"><ArrowRight /></el-icon>
              </router-link>
            </div>
            <p v-if="history.length" class="record-note">最近 {{ history.length }} 条处理记录 · 按次记录</p>
          </section>
        </div>
        <aside class="desk-aside">
          <section class="today-sheet" aria-labelledby="today-heading">
            <span class="today-symbol" aria-hidden="true"><el-icon><Calendar /></el-icon></span>
            <div class="section-heading"><h2 id="today-heading">今日行动</h2></div>
            <p class="today-summary">选定优先目标，安排可用时间，从有依据的下一步开始。</p>
            <router-link class="today-start" to="/today">打开今日行动<el-icon><ArrowRight /></el-icon></router-link>
          </section>
          <section class="partner-note"><div><h2>最近学了什么？</h2><p>回看练习、面试和学习记录。</p><router-link to="/growth">查看学习记录<el-icon><ArrowRight /></el-icon></router-link></div><picture><source srcset="../assets/optimized/filemate-mascot-home.webp" type="image/webp" /><img src="../assets/optimized/filemate-mascot-home.png" alt="" aria-hidden="true" width="220" height="294" loading="lazy" decoding="async" /></picture></section>
          <router-link class="privacy-link" to="/trust"><el-icon><Lock /></el-icon><span>资料如何保存与使用</span><el-icon><ArrowRight /></el-icon></router-link>
        </aside>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { ArrowRight, Calendar, FolderOpened, Lock, Microphone, Reading } from '../icons'
import StudyMotif from '../components/StudyMotif.vue'
import HeroEncouragement from '../components/HeroEncouragement.vue'
import DataState from '../components/DataState.vue'
import { getHistory, getAccountState, getKnowledgeSources, listAIContexts, getWrongbookPage, getPrivacyBoundary, importLearningSource } from '../services/api'
import { resolveHomeAction, createSampleImporter } from '../home/action'
import type { HistoryItem, SessionStatus } from '../types'
const loading = ref(true)
const errorMessage = ref('')
const history = ref<HistoryItem[]>([])
const router = useRouter()
const homeStatus = ref<'loading' | 'error' | 'ready'>('loading'), authenticated = ref<boolean | null>(null)
const sourceId = ref<string | null>(null), due = ref(0), homeError = ref(''), sampleBusy = ref(false)
const action = computed(() => resolveHomeAction({ status: homeStatus.value, authenticated: authenticated.value, sourceId: sourceId.value, due: due.value }))
const firstVisit = computed(() => action.value.kind === 'sample')
let stateRevision = 0, disposed = false
async function loadHomeState() {
  const revision = ++stateRevision
  homeStatus.value = 'loading'; homeError.value = ''
  try {
    const [account, sources, reviews, sessions] = await Promise.all([getAccountState(), getKnowledgeSources(1), getWrongbookPage({ mastered: false, offset: 0, q: '', due_only: true }), listAIContexts(undefined, 1)])
    if (disposed || revision !== stateRevision) return
    authenticated.value = !!account.user; sourceId.value = sources.length ? sessions[0]?.source_id || sources[0]!.source_id : null; due.value = reviews.total
    homeStatus.value = 'ready'
  } catch {
    if (disposed || revision !== stateRevision) return
    homeStatus.value = 'error'; homeError.value = '学习状态暂时无法读取，请重试。'
  }
}
const importSample = createSampleImporter(async () => {
  await getPrivacyBoundary()
  const { default: sampleText } = await import('../home/sample.md?raw')
  return importLearningSource(new File([sampleText], '数据结构-队列-FileMate原创示例.md', { type: 'text/markdown' }))
})
async function trySample() {
  if (sampleBusy.value || !firstVisit.value) return
  sampleBusy.value = true; homeError.value = ''
  try { const source = await importSample(); if (!disposed) await router.push({ path: '/ai-tools', query: { source: source.source_id } }) }
  catch { if (!disposed) homeError.value = '示例导入未完成，请恢复连接后重试。' }
  finally { sampleBusy.value = false }
}
function refreshHome() { void loadHomeState() }
onMounted(() => { void loadHomeState(); window.addEventListener('focus', refreshHome); window.addEventListener('filemate:session-reset', refreshHome); window.addEventListener('filemate:data-restored', refreshHome) })
onUnmounted(() => { disposed = true; stateRevision++; window.removeEventListener('focus', refreshHome); window.removeEventListener('filemate:session-reset', refreshHome); window.removeEventListener('filemate:data-restored', refreshHome) })
const todayLabel = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(new Date())
const hour = new Date().getHours()
const greeting = hour < 6 ? '夜深了' : hour < 11 ? '早上好' : hour < 14 ? '中午好' : hour < 18 ? '下午好' : '晚上好'
const studyTasks = [
  { id: 'read', title: '读资料，整理笔记', description: '打开已有课件，提问或生成学习内容。', route: '/ai-tools', icon: Reading, links: [
    ...(import.meta.env.VITE_ENABLE_KNOWLEDGE_GRAPH === 'false' ? [] : [{ label: '知识图谱', route: '/knowledge-graph' }]),
    ...(import.meta.env.VITE_ENABLE_DIGITAL_HUMAN === 'false' ? [] : [{ label: '听导师讲解', route: '/digital-human' }]),
  ] },
  { id: 'review', title: '复习，查漏补缺', description: '回顾真实错题，在原题中重新验证。', route: '/wrongbook', icon: Calendar, links: [
    { label: '错题本', route: '/wrongbook' }, { label: '学习计划', route: '/study-plan' }, { label: '学习目标', route: '/goals' },
  ] },
  { id: 'interview', title: '练表达，准备面试', description: '选择场景作答，结束后回看回答与报告。', route: '/interview', icon: Microphone, links: [
    ...(import.meta.env.VITE_ENABLE_PROGRAMMING === 'false' ? [] : [{ label: '编程练习', route: '/programming' }]),
    ...(import.meta.env.VITE_ENABLE_CAREER === 'false' ? [] : [{ label: '岗位训练', route: '/career' }]),
    { label: '面试题库', route: '/interview-bank' },
  ] },
]
const recentFiles = computed(() => history.value.slice(0, 6))
const metrics = computed(() => ({
  thisWeek: history.value.filter(item => new Date(item.created_at).getTime() >= Date.now() - 7 * 86400000).length,
  pending: history.value.filter(item => item.status === 'done').length,
  confirmed: history.value.filter(item => item.status === 'confirmed').length
}))
function getFileName(path: string): string { return path?.split(/[/\\]/).pop() || '未命名资料' }
function fileExtension(path: string): string { const name = getFileName(path); return name.includes('.') ? name.split('.').pop()!.slice(0, 4).toUpperCase() : 'FILE' }
function formatTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '日期未知' : date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}
function statusLabel(status: SessionStatus): string {
  return { pending: '等待处理', processing: '处理中', done: '待确认', confirmed: '已归档', skipped: '已跳过', expired: '已过期', failed: '处理失败' }[status]
}
function statusClass(status: SessionStatus): string {
  if (status === 'confirmed') return 'success'
  if (status === 'failed' || status === 'expired') return 'danger'
  return status === 'done' ? 'warning' : 'neutral'
}
async function loadDashboard(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  await getHistory(undefined, 100).then(items => { history.value = items }).catch(() => { errorMessage.value = '学习记录暂时无法读取，请检查服务连接后重试。' })
  loading.value = false
}
onMounted(loadDashboard)
</script>

<style scoped src="../home/dashboard.css"></style>
