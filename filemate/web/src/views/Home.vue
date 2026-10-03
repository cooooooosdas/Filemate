<template>
  <div class="dashboard">
    <header class="welcome">
      <div class="welcome-copy"><div class="welcome-meta"><span>{{ greeting }}，学习者</span><time>{{ todayLabel }}</time></div><h1>今天，<br />让知识<span class="title-dot">成形。</span></h1><p>读懂一份资料，走向你的下一步。</p><router-link class="solid-link hero-start" to="/import"><el-icon><Plus /></el-icon>导入新资料<el-icon><ArrowRight /></el-icon></router-link></div>
      <HeroEncouragement />
      <KnowledgeBackdrop />
    </header>
    <div v-if="loading" class="load-state" role="status"><el-icon class="loading-icon"><Loading /></el-icon>正在读取你的学习记录…</div>
    <div v-else-if="errorMessage" class="load-state error" role="alert"><p>{{ errorMessage }}</p><el-button @click="loadDashboard">重新加载</el-button></div>
    <template v-else>
      <div class="desk-grid">
        <div class="desk-main">
          <section class="focus-sheet" aria-labelledby="focus-heading">
            <div class="section-heading"><h2 id="focus-heading">从这里继续</h2></div>
            <div class="intent-options" role="group" aria-label="选择本次学习方向">
              <button v-for="intent in intents" :key="intent.id" type="button" :aria-pressed="selectedIntent === intent.id" @click="selectedIntent = intent.id"><el-icon><component :is="intent.icon" /></el-icon>{{ intent.label }}</button>
            </div>
            <transition name="intent-reveal" mode="out-in"><div :key="selectedIntent" class="focus-body">
              <span class="focus-symbol"><el-icon><component :is="focusAction.icon" /></el-icon></span>
              <div aria-live="polite"><h3>{{ focusAction.title }}</h3><p>{{ focusAction.description }}</p></div>
              <router-link class="solid-link" :to="focusAction.route">{{ focusAction.action }}<el-icon><ArrowRight /></el-icon></router-link>
            </div></transition>
            <div class="study-shortcuts" aria-label="当前方向的相关功能">
              <router-link v-for="link in relatedTools" :key="link.route" :to="link.route"><el-icon><component :is="link.icon" /></el-icon><span><strong>{{ link.label }}</strong></span><el-icon><ArrowRight /></el-icon></router-link>
            </div>
          </section>
          <section class="recent-section" aria-labelledby="recent-heading">
            <div class="section-heading"><h2 id="recent-heading">最近处理的资料</h2><router-link to="/history">全部记录<el-icon><ArrowRight /></el-icon></router-link></div>
            <section class="overview" aria-label="最近 100 条处理记录概览">
              <div><span>处理记录</span><strong>{{ history.length }}<small>份</small></strong></div>
              <div><span>近 7 天新增</span><strong>{{ metrics.thisWeek }}<small>份</small></strong></div>
              <router-link to="/history"><span>待确认归档</span><strong :class="{ amber: metrics.pending > 0 }">{{ metrics.pending }}<small>份</small></strong><el-icon><ArrowRight /></el-icon></router-link>
              <div><span>已归档</span><strong>{{ metrics.confirmed }}<small>份</small></strong></div>
            </section>
            <div v-if="!recentFiles.length" class="empty-files"><el-icon><DocumentAdd /></el-icon><h3>把第一份资料放进来</h3><p>支持 PDF、Word、PPT 和 TXT 文件。</p><router-link to="/import">导入资料<el-icon><ArrowRight /></el-icon></router-link></div>
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
              <ol v-if="review.items.length" class="task-list"><li v-for="item in review.items.slice(0, 3)" :key="item.item_id"><router-link :to="item.route"><span class="task-circle" /><span><strong>{{ item.title }}</strong><small>{{ item.kind === 'wrong_question' ? '错题复习' : '学习计划' }} · {{ item.duration_minutes }} 分钟</small></span></router-link></li></ol>
              <div v-else class="today-empty"><el-icon><Calendar /></el-icon><p>给下次考试或复习留出时间，<br />安排会在这里提醒你。</p><router-link to="/study-plan">制定学习计划<el-icon><ArrowRight /></el-icon></router-link></div>
              <router-link v-if="review.items.length" class="solid-link today-start" to="/today">开始今日学习<el-icon><ArrowRight /></el-icon></router-link>
            </template>
          </section>
          <section class="partner-note"><div><h2>每一步，<br />都有迹可循。</h2><router-link to="/growth">查看学习记录<el-icon><ArrowRight /></el-icon></router-link></div><img src="../assets/filemate-mascot.png" alt="FileMate 学习伙伴" width="1086" height="1448" /></section>
          <router-link class="privacy-link" to="/trust"><el-icon><Lock /></el-icon><span>资料如何保存与使用</span><el-icon><ArrowRight /></el-icon></router-link>
        </aside>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowRight, Calendar, Cpu, DocumentAdd, FolderChecked, Loading, Lock, Microphone, Plus, Reading, Share, Tickets, Aim, VideoPlay } from '../icons'
import KnowledgeBackdrop from '../components/KnowledgeBackdrop.vue'
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
const intents = [
  { id: 'organize', label: '读懂资料', icon: DocumentAdd },
  { id: 'review', label: '复习备考', icon: Reading },
  { id: 'interview', label: '面试求职', icon: Microphone }
] as const
const selectedIntent = ref<(typeof intents)[number]['id']>('organize')
const relatedTools = computed(() => {
  if (selectedIntent.value === 'review') return [
    { label: '错题复盘', route: '/wrongbook', icon: Tickets },
    { label: '学习计划', route: '/study-plan', icon: Calendar },
    { label: '学习目标', route: '/goals', icon: Aim },
  ]
  if (selectedIntent.value === 'interview') return [
    ...(import.meta.env.VITE_ENABLE_PROGRAMMING === 'false' ? [] : [{ label: '编程练习', route: '/programming', icon: Cpu }]),
    { label: '面试题库', route: '/interview-bank', icon: Microphone },
    ...(import.meta.env.VITE_ENABLE_CAREER === 'false' ? [] : [{ label: '求职准备', route: '/career', icon: Aim }]),
  ]
  return [
    { label: '学习工作区', route: '/ai-tools', icon: Reading },
    ...(import.meta.env.VITE_ENABLE_KNOWLEDGE_GRAPH === 'false' ? [] : [{ label: '知识图谱', route: '/knowledge-graph', icon: Share }]),
    ...(import.meta.env.VITE_ENABLE_DIGITAL_HUMAN === 'false' ? [] : [{ label: '导师讲解', route: '/digital-human', icon: VideoPlay }]),
  ]
})
const focusAction = computed(() => {
  if (selectedIntent.value === 'review') {
    return { icon: Reading, title: '把学过的，再往前推一步', description: '回顾错题、巩固知识点，让复习跟上你的节奏。', action: '开始复习', route: '/today' }
  }
  if (selectedIntent.value === 'interview') {
    return { icon: Microphone, title: '给下一次面试，多一点准备', description: '选择练习场景，试着把思路完整地说出来。', action: '开始练习', route: '/interview' }
  }
  return {
    icon: metrics.value.pending ? FolderChecked : DocumentAdd,
    title: metrics.value.pending ? `${metrics.value.pending} 份资料等你确认` : '让第一份资料，找到自己的位置',
    description: metrics.value.pending ? '检查分类和文件名，确认后放到合适的位置。' : '课件、笔记和作业，整理好就是学习的起点。',
    action: metrics.value.pending ? '去确认' : '选择文件',
    route: metrics.value.pending ? '/history' : '/import'
  }
})
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
.welcome { --hero-background:radial-gradient(ellipse at 94% 6%,#426581,#263f60 52%,#152b4a); position:relative; isolation:isolate; display:grid; grid-template-columns:minmax(0,1.05fr) minmax(0,1fr); align-items:center; gap:32px; overflow:hidden; padding:42px; margin-bottom:28px; background:var(--hero-background); color:var(--hero-ink); border:1px solid #86a5c766; border-radius:28px; min-height:450px; }
.welcome-copy { position:relative; z-index:1; min-width:0; }
.welcome-meta { display:flex; flex-wrap:wrap; gap:10px 18px; color:var(--hero-highlight); font-size:15px; font-weight:600; }
.welcome time { color:var(--hero-copy); font-weight:400; }
.welcome h1 { margin:22px 0 18px; font-size:clamp(44px,4.6vw,70px); font-weight:650; letter-spacing:-.06em; line-height:1.18; }
.title-dot { color:var(--hero-highlight); }
.welcome p { margin:0 0 26px; color:var(--hero-copy); font-size:20px; line-height:1.6; }
.solid-link { display:inline-flex; align-items:center; justify-content:center; gap:12px; min-height:52px; padding:12px 22px; background:var(--accent); color:white; border-radius:12px; font-size:17px; font-weight:600; transition:background var(--motion-fast),transform var(--motion-fast); }
.solid-link:hover { background:var(--accent-hover); transform:translateY(-2px); }
.hero-start { min-height:56px; gap:14px; background:var(--hero-highlight); color:#15264a; }.hero-start:hover { background:#ffe5b4; }
.overview { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); padding:20px 0; margin-bottom:28px; border-block:1px solid var(--border-subtle); }
.overview > * { position:relative; display:flex; flex-direction:column; gap:7px; padding:0 24px; min-width:0; border-right:1px solid var(--border-subtle); }
.overview > :first-child { padding-left:0; }.overview > :last-child { border-right:0; }
.overview span { font-size:15px; color:var(--text-secondary); }.overview strong { font-size:34px; font-weight:550; font-variant-numeric:tabular-nums; line-height:1.2; }.overview small { margin-left:8px; font-size:14px; font-weight:400; color:var(--text-muted); }
.overview .el-icon { position:absolute; right:20px; top:5px; color:var(--text-muted); }.overview a:hover { color:var(--accent); }.amber { color:var(--warning); }
.desk-grid { display:grid; grid-template-columns:minmax(0,1fr) 310px; gap:24px; align-items:start; }.desk-main,.desk-aside { min-width:0; }
.section-heading { display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; }.section-heading h2 { margin:0; font-size:24px; font-weight:600; letter-spacing:-.03em; }.section-heading a { display:inline-flex; align-items:center; gap:8px; min-height:44px; font-size:16px; color:var(--text-secondary); }.section-heading a:hover { color:var(--accent); }
.focus-sheet { padding:30px; border:1px solid var(--border-subtle); border-radius:20px; background:var(--bg-surface); }
.intent-options { display:flex; gap:8px; margin-top:22px; border-bottom:1px solid var(--border-subtle); padding-bottom:22px; }
.intent-options button { display:flex; align-items:center; justify-content:center; gap:9px; flex:1; min-width:0; min-height:54px; padding:10px; color:var(--text-secondary); border:0; border-radius:12px; background:var(--bg-base); font-size:17px; font-weight:550; transition:background var(--motion-fast),color var(--motion-fast); }
.intent-options button:hover { background:var(--accent-soft); }.intent-options button[aria-pressed=true] { color:white; background:var(--accent); }.intent-options .el-icon { font-size:21px; }
.focus-body { display:grid; grid-template-columns:52px minmax(0,1fr); gap:18px; align-items:center; padding:32px 0 28px; min-height:240px; }
.focus-symbol { display:grid; place-items:center; width:52px; height:60px; border-radius:12px; background:var(--accent-soft); color:var(--accent); font-size:28px; }
.focus-body h3 { margin:0 0 14px; font-size:28px; line-height:1.4; font-weight:600; letter-spacing:-.03em; }.focus-body p { margin:0; color:var(--text-secondary); font-size:17px; line-height:1.8; }.focus-body .solid-link { grid-column:2; justify-self:start; }
.study-shortcuts { display:flex; flex-wrap:wrap; gap:10px 22px; padding-top:18px; border-top:1px solid var(--border-subtle); }.study-shortcuts a { display:flex; align-items:center; gap:8px; min-height:48px; }.study-shortcuts a > .el-icon:first-child { font-size:20px; color:var(--accent); }.study-shortcuts a > .el-icon:last-child { color:var(--text-muted); font-size:14px; }.study-shortcuts strong { font-size:16px; font-weight:500; }.study-shortcuts a:hover strong { color:var(--accent); }
.recent-section { container-type:inline-size; margin-top:26px; padding:28px 30px; background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:20px; }.recent-section .overview { margin-top:22px; }.file-list { margin-top:10px; }.file-list-head { display:flex; justify-content:space-between; padding:16px 32px 12px 0; color:var(--text-muted); font-size:14px; }
.file-row { display:grid; grid-template-columns:40px minmax(0,1fr) auto 14px; align-items:center; gap:14px; min-height:86px; padding:14px 4px; border-top:1px solid var(--border-subtle); transition:background var(--motion-fast); }.file-row:hover { background:var(--bg-elevated); }
.file-mark { display:grid; place-items:center; width:36px; height:44px; font:12px var(--font-mono); color:var(--accent); background:var(--accent-soft); border:1px solid var(--accent-border); border-radius:4px 10px 4px 4px; }.file-mark.presentation { color:#936333; background:#f4ede2; border-color:#e6d9c6; }.file-copy { min-width:0; }.file-copy strong { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:17px; font-weight:500; }.file-copy small { display:flex; flex-wrap:wrap; gap:8px; margin-top:7px; color:var(--text-muted); font-size:14px; }
.file-status { display:flex; align-items:center; gap:7px; color:var(--text-secondary); font-size:14px; white-space:nowrap; }.file-status i { width:6px; height:6px; border-radius:50%; background:currentColor; }.file-status.success { color:var(--success); }.file-status.warning { color:var(--warning); }.file-status.danger { color:var(--danger); }.row-arrow { font-size:14px; color:var(--text-muted); }.record-note { margin-top:18px; color:var(--text-muted); font-size:14px; line-height:1.7; }
.today-sheet { padding:28px; background:var(--panel-tint); border:1px solid var(--border-subtle); border-radius:20px; }.today-summary { margin:12px 0 20px; color:var(--text-secondary); font-size:16px; line-height:1.7; }
.task-list { margin:0; padding:0; list-style:none; }.task-list li + li { border-top:1px solid var(--border-subtle); }.task-list a { display:grid; grid-template-columns:16px minmax(0,1fr); gap:12px; padding:18px 0; }.task-circle { width:15px; height:15px; margin-top:5px; border:1px solid var(--border-strong); border-radius:50%; }.task-list strong { display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; font-size:17px; font-weight:500; line-height:1.6; }.task-list small { display:block; margin-top:8px; color:var(--text-muted); font-size:14px; }.task-list a:hover strong { color:var(--accent); }.today-start { width:100%; margin-top:16px; }
.today-empty { padding:12px 0 0; }.today-empty > .el-icon { font-size:32px; color:var(--accent); }.today-empty p { font-size:17px; color:var(--text-secondary); line-height:1.8; }.today-empty a,.partner-note a,.empty-files a { display:inline-flex; align-items:center; gap:12px; min-height:48px; color:var(--accent); font-size:16px; }
.partner-note { position:relative; isolation:isolate; display:flex; min-height:225px; overflow:hidden; margin-top:24px; padding:22px 0; border-bottom:1px solid var(--border-subtle); }.partner-note > div { position:relative; z-index:1; }.partner-note h2 { margin:10px 0 20px; font-size:28px; line-height:1.4; font-weight:550; }.partner-note img { position:absolute; width:140px; height:auto; right:0; bottom:16px; z-index:0; }
.privacy-link { display:flex; gap:10px; align-items:center; min-height:60px; font-size:14px; color:var(--text-secondary); }.privacy-link > :last-child { margin-left:auto; }
.load-state { display:flex; align-items:center; justify-content:center; flex-wrap:wrap; gap:12px; min-height:240px; color:var(--text-secondary); font-size:17px; }.error { color:var(--danger); }.loading-icon { animation:spin 1s linear infinite; }@keyframes spin { to { transform:rotate(360deg); } }
.empty-files { text-align:center; padding:40px 16px; margin-top:14px; border-top:1px solid var(--border-subtle); }.empty-files > .el-icon { font-size:36px; color:var(--accent); }.empty-files h3 { font-size:22px; font-weight:550; }.empty-files p { font-size:17px; color:var(--text-secondary); }.review-error { font-size:16px; color:var(--text-secondary); }.review-error button { min-height:44px; color:var(--accent); background:transparent; border:0; }
.intent-reveal-enter-active,.intent-reveal-leave-active { transition:opacity 220ms ease,transform 220ms ease; }.intent-reveal-enter-from { opacity:0; transform:translateY(14px); }.intent-reveal-leave-to { opacity:0; transform:translateY(-8px); }
@container(max-width:620px) { .overview { grid-template-columns:1fr 1fr; gap:22px 0; }.overview > :nth-child(2) { border:0; }.overview > :nth-child(3) { padding-left:0; } }
@media(max-width:1150px) { .welcome { padding:32px; }.welcome h1 { font-size:52px; }.welcome p { font-size:18px; }.desk-grid { grid-template-columns:minmax(0,1fr) 270px; gap:20px; }.focus-sheet,.recent-section { padding:24px; }.focus-body { grid-template-columns:1fr; gap:14px; }.focus-symbol { display:none; }.focus-body .solid-link { grid-column:1; }.intent-options button { gap:7px; font-size:16px; }.intent-options .el-icon { display:none; }.today-sheet { padding:24px; }.partner-note img { width:116px; } }
@media(max-width:900px) { .desk-grid { grid-template-columns:1fr; }.desk-aside { display:grid; grid-template-columns:1fr 1fr; gap:24px; }.partner-note { margin:0; }.privacy-link { grid-column:1 / -1; }.welcome { grid-template-columns:1fr; gap:28px; }.welcome h1 { font-size:46px; } }
@media(max-width:700px) { .welcome { padding:30px 24px; min-height:530px; }.welcome h1 { font-size:44px; margin-top:20px; }.welcome p { font-size:18px; }.welcome-meta { font-size:14px; gap:8px 16px; }.welcome-meta time { display:none; }.overview { grid-template-columns:1fr 1fr; gap:20px 0; padding:22px 0; }.overview > * { padding:0 18px; }.overview > :nth-child(3) { padding-left:0; }.overview > :nth-child(2) { border:0; }.overview strong { font-size:30px; }.overview span { font-size:15px; }.desk-aside { display:block; }.focus-sheet,.recent-section { padding:24px 20px; }.section-heading h2 { font-size:23px; }.intent-options { gap:5px; }.intent-options button { padding:12px 5px; white-space:nowrap; }.focus-body h3 { font-size:26px; }.focus-body { min-height:250px; padding-top:28px; }.file-row { grid-template-columns:36px minmax(0,1fr); gap:10px; }.file-status { grid-column:2; }.row-arrow { display:none; }.file-list-head { display:none; }.today-sheet { margin-top:0; }.partner-note { margin-top:20px; }.partner-note img { width:145px; right:16px; } }
</style>
