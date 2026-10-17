<template>
  <div class="dashboard">
    <header class="welcome">
      <div class="welcome-copy"><div class="welcome-meta"><span>{{ greeting }}</span><time>{{ todayLabel }}</time></div><h1>今天，<br />让知识<span class="title-dot">成形。</span></h1><p>打开课件，读原文、记笔记、做练习。</p><router-link class="solid-link hero-start" to="/ai-tools"><el-icon><Reading /></el-icon>开始学习<el-icon><ArrowRight /></el-icon></router-link></div>
      <HeroEncouragement />
      <StudyMotif class="welcome-motif" />
    </header>
    <div v-if="loading" class="load-state" role="status"><el-icon class="loading-icon"><Loading /></el-icon>正在读取你的学习记录…</div>
    <div v-else-if="errorMessage" class="load-state error" role="alert"><p>{{ errorMessage }}</p><el-button @click="loadDashboard">重新加载</el-button></div>
    <template v-else>
      <div class="desk-grid">
        <div class="desk-main">
          <section class="focus-sheet" aria-labelledby="focus-heading">
            <div class="section-heading"><h2 id="focus-heading">这次想做什么？</h2><span class="section-hint">直接开始</span></div>
            <div class="task-entries">
              <article v-for="task in studyTasks" :key="task.id" class="task-entry">
                <router-link class="task-entry-main" :to="task.route">
                  <span class="task-symbol"><el-icon aria-hidden="true"><component :is="task.icon" /></el-icon></span>
                  <span class="task-entry-copy"><strong>{{ task.title }}</strong><span>{{ task.description }}</span></span>
                  <el-icon class="task-entry-arrow" aria-hidden="true"><ArrowRight /></el-icon>
                </router-link>
                <nav v-if="task.links.length" class="task-entry-links" :aria-label="`${task.title}的相关功能`"><router-link v-for="link in task.links" :key="link.route" :to="link.route">{{ link.label }}<el-icon aria-hidden="true"><ArrowRight /></el-icon></router-link></nav>
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
            <div v-if="!recentFiles.length" class="empty-files"><el-icon aria-hidden="true"><FolderOpened /></el-icon><h3>还没有归档处理记录</h3><p>这里记录分类与归档操作。已导入的学习资料可从知识库打开。</p><router-link to="/knowledge">打开我的资料<el-icon><ArrowRight /></el-icon></router-link></div>
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
            <div class="section-heading"><h2 id="today-heading">今日安排</h2><router-link to="/today" aria-label="查看全部今日学习任务"><el-icon><ArrowRight /></el-icon></router-link></div>
            <div v-if="reviewError" class="review-error" role="alert"><p>今日安排暂时无法读取。</p><button @click="loadReview" :disabled="reviewLoading">{{ reviewLoading ? '正在加载…' : '重试' }}</button></div>
            <template v-else-if="review">
              <p class="today-summary">{{ review.items.length ? `${review.items.length} 项待办 · 预计 ${review.recommended_minutes} 分钟` : '今天还没有待完成的安排' }}</p>
              <ol v-if="review.items.length" class="task-list"><li v-for="item in review.items.slice(0, 3)" :key="item.item_id"><router-link :to="todayItemTarget(item)"><span class="task-circle" /><span><strong>{{ item.title }}</strong><small>{{ item.kind === 'wrong_question' ? '错题复习' : '学习计划' }} · {{ item.duration_minutes }} 分钟</small></span></router-link></li></ol>
              <div v-else class="today-empty"><el-icon><Calendar /></el-icon><p>给下次考试或复习留出时间，<br />安排会在这里提醒你。</p><router-link to="/study-plan">制定学习计划<el-icon><ArrowRight /></el-icon></router-link></div>
              <router-link v-if="review.items.length" class="solid-link today-start" to="/today">开始今日学习<el-icon><ArrowRight /></el-icon></router-link>
            </template>
          </section>
          <section class="partner-note"><div><h2>最近学了什么？</h2><p>回看练习、面试和学习记录。</p><router-link to="/growth">查看学习记录<el-icon><ArrowRight /></el-icon></router-link></div><img src="../assets/filemate-mascot.png" alt="" aria-hidden="true" width="1086" height="1448" loading="lazy" /></section>
          <router-link class="privacy-link" to="/trust"><el-icon><Lock /></el-icon><span>资料如何保存与使用</span><el-icon><ArrowRight /></el-icon></router-link>
        </aside>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowRight, Calendar, FolderOpened, Loading, Lock, Microphone, Reading } from '../icons'
import StudyMotif from '../components/StudyMotif.vue'
import { todayItemTarget } from '../navigation/route-state'
import HeroEncouragement from '../components/HeroEncouragement.vue'
import { getHistory, getTodayReview, type TodayReview } from '../services/api'
import type { HistoryItem, SessionStatus } from '../types'
const loading = ref(true)
const errorMessage = ref('')
const history = ref<HistoryItem[]>([])
const review = ref<TodayReview | null>(null)
const reviewError = ref(false)
const reviewLoading = ref(false)
const todayLabel = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(new Date())
const hour = new Date().getHours()
const greeting = hour < 6 ? '夜深了' : hour < 11 ? '早上好' : hour < 14 ? '中午好' : hour < 18 ? '下午好' : '晚上好'
const studyTasks = [
  { id: 'read', title: '读资料，整理笔记', description: '打开已有课件，提问或生成学习内容。', route: '/ai-tools', icon: Reading, links: [
    ...(import.meta.env.VITE_ENABLE_KNOWLEDGE_GRAPH === 'false' ? [] : [{ label: '知识图谱', route: '/knowledge-graph' }]),
    ...(import.meta.env.VITE_ENABLE_DIGITAL_HUMAN === 'false' ? [] : [{ label: '听导师讲解', route: '/digital-human' }]),
  ] },
  { id: 'review', title: '复习，查漏补缺', description: '按今日安排做练习，回顾还没弄懂的题。', route: '/today', icon: Calendar, links: [
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
async function loadReview(): Promise<void> {
  reviewLoading.value = true
  try { review.value = await getTodayReview(); reviewError.value = false }
  catch { reviewError.value = true }
  finally { reviewLoading.value = false }
}
async function loadDashboard(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  await Promise.all([
    getHistory(undefined, 100).then(items => { history.value = items }).catch(() => { errorMessage.value = '学习记录暂时无法读取，请检查服务连接后重试。' }),
    loadReview()
  ])
  loading.value = false
}
onMounted(loadDashboard)
</script>

<style scoped>
.dashboard { max-width:1360px; margin:0 auto; min-width:0; }
a { color:inherit; text-decoration:none; }
.welcome { --hero-background:radial-gradient(ellipse at 94% 6%,#426581,#263f60 52%,#152b4a); position:relative; isolation:isolate; display:grid; grid-template-columns:minmax(0,1.05fr) minmax(0,1fr); align-items:center; gap:40px; overflow:hidden; padding:44px; margin-bottom:32px; background:var(--hero-background); color:var(--hero-ink); border:1px solid #86a5c766; border-radius:24px; min-height:420px; }
.welcome-copy { position:relative; z-index:1; min-width:0; }
.welcome-meta { display:flex; flex-wrap:wrap; gap:10px 18px; color:var(--hero-highlight); font-size:17px; font-weight:500; }
.welcome time { color:var(--hero-copy); font-weight:400; }
.welcome h1 { margin:24px 0 20px; font-size:clamp(44px,4.6vw,70px); font-weight:650; letter-spacing:-.045em; line-height:1.18; }
.title-dot { color:var(--hero-highlight); }
.welcome p { margin:0 0 28px; color:var(--hero-copy); font-size:19px; line-height:1.7; }
.solid-link { display:inline-flex; align-items:center; justify-content:center; gap:12px; min-height:52px; padding:12px 22px; background:var(--accent); color:white; border-radius:12px; font-size:17px; font-weight:600; transition:background var(--motion-fast); }
.solid-link:hover { background:var(--accent-hover); }
.hero-start { min-height:56px; gap:14px; background:var(--hero-highlight); color:#15264a; }.hero-start:hover { background:#ffe5b4; }
.desk-grid { display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:28px; align-items:start; }.desk-main,.desk-aside { min-width:0; }
.section-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }.section-heading h2 { margin:0; font-size:24px; font-weight:600; letter-spacing:-.025em; }.section-heading a { display:inline-flex; align-items:center; gap:8px; min-height:44px; font-size:16px; color:var(--text-secondary); }.section-heading a:hover { color:var(--accent); }.section-hint { font-size:16px; color:var(--text-muted); }
.focus-sheet { padding:28px 28px 12px; border:1px solid var(--border-subtle); border-radius:18px; background:var(--bg-surface); }
.task-entries { margin-top:18px; }
.task-entry + .task-entry { border-top:1px solid var(--border-subtle); }
.task-entry-main { display:grid; grid-template-columns:48px minmax(0,1fr) 24px; gap:18px; align-items:center; min-height:106px; padding:18px 8px; border-radius:12px; transition:background var(--motion-fast); }
.task-entry-main:hover { background:var(--accent-soft); }
.task-symbol { display:grid; place-items:center; width:48px; height:52px; border:1px solid var(--accent-border); border-radius:12px; color:var(--accent); background:var(--bg-reading); font-size:26px; }
.task-entry-copy { min-width:0; }.task-entry-copy strong { display:block; font-size:24px; font-weight:600; line-height:1.45; letter-spacing:-.025em; overflow-wrap:anywhere; }.task-entry-copy > span { display:block; margin-top:6px; font-size:17px; line-height:1.7; color:var(--text-secondary); }
.task-entry-arrow { color:var(--accent); font-size:23px; transition:transform var(--motion-fast); }.task-entry-main:hover .task-entry-arrow { transform:translateX(3px); }
.task-entry-links { display:flex; flex-wrap:wrap; gap:0 18px; padding:0 8px 14px 74px; }.task-entry-links a { display:inline-flex; align-items:center; gap:8px; min-height:44px; font-size:16px; color:var(--text-secondary); }.task-entry-links a:hover { color:var(--accent); }.task-entry-links .el-icon { font-size:16px; }
.recent-section { container-type:inline-size; margin-top:28px; padding:24px 0; border-top:1px solid var(--border-strong); }
.overview { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); padding:20px 0; margin:16px 0; border-block:1px solid var(--border-subtle); }
.overview > * { position:relative; display:flex; flex-direction:column; gap:7px; padding:0 18px; min-width:0; border-right:1px solid var(--border-subtle); }.overview > :first-child { padding-left:0; }.overview > :last-child { border-right:0; }
.overview span { font-size:16px; color:var(--text-secondary); }.overview strong { font-size:32px; font-weight:550; font-variant-numeric:tabular-nums; line-height:1.2; }.overview small { margin-left:8px; font-size:16px; font-weight:400; color:var(--text-muted); }.overview .el-icon { position:absolute; right:12px; top:5px; color:var(--text-muted); }.overview a:hover { color:var(--accent); }.amber { color:var(--warning); }
.file-list-head { display:flex; justify-content:space-between; padding:16px 32px 12px 0; color:var(--text-muted); font-size:16px; }
.file-row { display:grid; grid-template-columns:40px minmax(0,1fr) auto 14px; align-items:center; gap:14px; min-height:86px; padding:14px 4px; border-top:1px solid var(--border-subtle); transition:background var(--motion-fast); }.file-row:hover { background:var(--bg-elevated); }
.file-mark { display:grid; place-items:center; width:36px; height:44px; font:var(--type-meta) var(--font-mono); color:var(--accent); background:var(--accent-soft); border:1px solid var(--accent-border); border-radius:4px 10px 4px 4px; }.file-mark.presentation { color:#936333; background:#f4ede2; border-color:#e6d9c6; }.file-copy { min-width:0; }.file-copy strong { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:17px; font-weight:500; }.file-copy small { display:flex; flex-wrap:wrap; gap:8px; margin-top:7px; color:var(--text-muted); font-size:16px; }
.file-status { display:flex; align-items:center; gap:7px; color:var(--text-secondary); font-size:16px; white-space:nowrap; }.file-status i { width:6px; height:6px; border-radius:50%; background:currentColor; }.file-status.success { color:var(--success); }.file-status.warning { color:var(--warning); }.file-status.danger { color:var(--danger); }.row-arrow { font-size:16px; color:var(--text-muted); }.record-note { margin-top:18px; color:var(--text-muted); font-size:16px; line-height:1.7; }
.today-sheet { padding:26px; background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:18px; }.today-summary { margin:12px 0 20px; color:var(--text-secondary); font-size:17px; line-height:1.7; }
.task-list { margin:0; padding:0; list-style:none; }.task-list li + li { border-top:1px solid var(--border-subtle); }.task-list a { display:grid; grid-template-columns:16px minmax(0,1fr); gap:12px; padding:18px 0; }.task-circle { width:15px; height:15px; margin-top:5px; border:1px solid var(--border-strong); border-radius:50%; }.task-list strong { display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; font-size:17px; font-weight:500; line-height:1.6; }.task-list small { display:block; margin-top:8px; color:var(--text-muted); font-size:16px; }.task-list a:hover strong { color:var(--accent); }.today-start { width:100%; margin-top:16px; }
.today-empty { padding:12px 0 0; }.today-empty > .el-icon { font-size:32px; color:var(--accent); }.today-empty p { font-size:17px; color:var(--text-secondary); line-height:1.8; }.today-empty a,.partner-note a,.empty-files a { display:inline-flex; align-items:center; gap:12px; min-height:48px; color:var(--accent); font-size:17px; }
.partner-note { position:relative; isolation:isolate; display:flex; min-height:230px; overflow:hidden; margin-top:24px; padding:16px 0; border-bottom:1px solid var(--border-subtle); }.partner-note > div { position:relative; z-index:1; max-width:72%; }.partner-note h2 { margin:8px 0 12px; font-size:24px; line-height:1.45; font-weight:600; }.partner-note p { font-size:17px; line-height:1.7; color:var(--text-secondary); margin:0 0 12px; }.partner-note img { position:absolute; width:110px; height:auto; right:-10px; bottom:12px; z-index:0; }
.privacy-link { display:flex; gap:10px; align-items:center; min-height:64px; font-size:16px; color:var(--text-secondary); }.privacy-link > :last-child { margin-left:auto; }
.load-state { display:flex; align-items:center; justify-content:center; flex-wrap:wrap; gap:12px; min-height:240px; color:var(--text-secondary); font-size:17px; }.error { color:var(--danger); }.loading-icon { animation:spin 1s linear infinite; }@keyframes spin { to { transform:rotate(360deg); } }
.empty-files { display:grid; justify-items:start; gap:10px; padding:28px 0 12px; }.empty-files > .el-icon { font-size:28px; color:var(--accent); }.empty-files h3 { margin:4px 0 0; font-size:21px; font-weight:550; }.empty-files p { margin:0; font-size:17px; line-height:1.8; max-width:42em; color:var(--text-secondary); }.review-error { font-size:17px; color:var(--text-secondary); }.review-error button { min-height:44px; color:var(--accent); background:transparent; border:0; }
@container(max-width:620px) { .overview { grid-template-columns:1fr 1fr; gap:22px 0; }.overview > :nth-child(2) { border:0; }.overview > :nth-child(3) { padding-left:0; } }
@media(max-width:1150px) { .welcome { padding:32px; gap:28px; }.welcome h1 { font-size:52px; }.welcome p { font-size:18px; }.desk-grid { grid-template-columns:minmax(0,1fr) 270px; gap:20px; }.focus-sheet { padding:24px 20px 8px; }.task-entry-main { gap:12px; grid-template-columns:44px minmax(0,1fr) 20px; }.task-symbol { width:44px; height:48px; }.task-entry-copy strong { font-size:22px; }.task-entry-links { padding-left:64px; }.today-sheet { padding:24px; } }
@media(max-width:1050px) { .desk-grid { grid-template-columns:1fr; }.desk-aside { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:24px; }.partner-note { margin:0; }.privacy-link { grid-column:1 / -1; } }
@media(max-width:900px) { .welcome { grid-template-columns:1fr; gap:28px; min-height:0; }.welcome h1 { font-size:46px; } }
@media(max-width:700px) { .welcome { padding:28px 24px; border-radius:18px; margin-bottom:24px; }.welcome h1 { font-size:44px; margin-top:20px; }.welcome p { font-size:18px; }.welcome-meta { font-size:16px; gap:8px 16px; }.overview { grid-template-columns:1fr 1fr; gap:20px 0; }.overview > :nth-child(3) { padding-left:0; }.overview > :nth-child(2) { border:0; }.desk-aside { display:block; }.focus-sheet { padding:22px 16px 6px; }.section-heading h2 { font-size:23px; }.section-hint { display:none; }.task-entry-main { padding:18px 0; gap:12px; }.task-entry-copy strong { font-size:22px; }.task-entry-copy > span { font-size:17px; }.task-entry-links { padding-left:0; gap:0 18px; }.file-row { grid-template-columns:36px minmax(0,1fr); gap:10px; }.file-status { grid-column:2; }.row-arrow,.file-list-head { display:none; }.partner-note { margin-top:20px; }.partner-note img { right:16px; } }
@media(prefers-reduced-motion:reduce) { .task-entry-arrow { transition:none; }.task-entry-main:hover .task-entry-arrow { transform:none; } }
</style>

<style scoped>
.welcome { --hero-ink: #15264a; --hero-copy: #405573; --hero-highlight: #2352d3; --quote-ink: #233d66; --quote-secondary: #405573; --quote-line: #a4c2ee; background: linear-gradient(115deg, #e6f0ff, #d5e6ff); border: 0; min-height: 340px; border-radius: 16px; }
.welcome h1 { font-size: clamp(42px,4.4vw,62px); letter-spacing: -.03em; margin-block: 22px 16px; }
.welcome-meta { color: #2352d3; }
.welcome-motif { position: absolute; width: 260px; bottom: -35px; right: 10px; opacity: .28; z-index: 0; pointer-events: none; }
.hero-start { background: var(--accent); color: #fff; }
.hero-start:hover { background: var(--accent-hover); }
.welcome :deep(.hero-encouragement) { padding-bottom: 40px; }
.welcome :deep(.hero-encouragement::before) { bottom: 35px; }
.focus-sheet, .today-sheet { background: #fff; border-color: transparent; border-radius: 16px; }
@media(max-width: 700px) { .welcome { min-height: 0; padding: 28px 24px; } .welcome-motif { display: none; } .welcome :deep(.hero-encouragement) { padding-bottom: 0; } }
</style>
