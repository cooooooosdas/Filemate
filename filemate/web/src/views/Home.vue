<template>
  <div class="dashboard">
    <header class="welcome">
      <div class="welcome-copy"><div class="welcome-meta"><span>{{ greeting }}，学习者</span><time>{{ todayLabel }}</time></div><h1>今天，<br class="mobile-break" />按你的节奏来<span class="title-dot">。</span></h1><p>把资料变成知识，把想做的事慢慢完成。</p></div>
      <div class="welcome-action"><span class="desk-label">MY LEARNING DESK</span><router-link class="solid-link" to="/import"><el-icon><Plus /></el-icon>导入新资料</router-link><span class="format-hint">PDF / WORD / PPT / TXT</span></div>
    </header>
    <div v-if="loading" class="load-state" role="status"><el-icon class="loading-icon"><Loading /></el-icon>正在读取你的学习记录…</div>
    <div v-else-if="errorMessage" class="load-state error" role="alert"><p>{{ errorMessage }}</p><el-button @click="loadDashboard">重新加载</el-button></div>
    <template v-else>
      <section class="overview" aria-label="最近 100 条处理记录概览">
        <div><span>处理记录</span><strong>{{ history.length }}<small>份</small></strong></div>
        <div><span>近 7 天新增</span><strong>{{ metrics.thisWeek }}<small>份</small></strong></div>
        <router-link to="/history"><span>待确认归档</span><strong :class="{ amber: metrics.pending > 0 }">{{ metrics.pending }}<small>份</small></strong><el-icon><ArrowRight /></el-icon></router-link>
        <div><span>已归档</span><strong>{{ metrics.confirmed }}<small>份</small></strong></div>
      </section>
      <div class="desk-grid">
        <div class="desk-main">
          <section class="focus-sheet" aria-labelledby="focus-heading">
            <div class="section-heading"><h2 id="focus-heading">今天想做什么？</h2><span>选一个方向，就从这里开始</span></div>
            <div class="intent-options" role="group" aria-label="选择本次学习方向">
              <button v-for="intent in intents" :key="intent.id" type="button" :aria-pressed="selectedIntent === intent.id" @click="selectedIntent = intent.id"><el-icon><component :is="intent.icon" /></el-icon>{{ intent.label }}</button>
            </div>
            <div class="focus-body">
              <span class="focus-symbol"><el-icon><component :is="focusAction.icon" /></el-icon></span>
              <div aria-live="polite"><span class="focus-caption">你的下一小步</span><h3>{{ focusAction.title }}</h3><p>{{ focusAction.description }}</p></div>
              <router-link class="solid-link" :to="focusAction.route">{{ focusAction.action }}<el-icon><ArrowRight /></el-icon></router-link>
            </div>
            <div class="study-shortcuts">
              <router-link to="/ai-tools"><el-icon><Reading /></el-icon><span><strong>读懂一份资料</strong><small>总结重点 · 提问 · 生成练习</small></span><el-icon><ArrowRight /></el-icon></router-link>
              <router-link to="/interview"><el-icon><Microphone /></el-icon><span><strong>练一场面试</strong><small>练习回答，再回看自己的表现</small></span><el-icon><ArrowRight /></el-icon></router-link>
            </div>
          </section>
          <section class="recent-section" aria-labelledby="recent-heading">
            <div class="section-heading"><h2 id="recent-heading">最近处理的资料</h2><router-link to="/history">全部记录<el-icon><ArrowRight /></el-icon></router-link></div>
            <div v-if="!recentFiles.length" class="empty-files"><el-icon><DocumentAdd /></el-icon><h3>把第一份资料放进来</h3><p>支持 PDF、Word、PPT 和 TXT 文件。</p><router-link to="/import">导入资料<el-icon><ArrowRight /></el-icon></router-link></div>
            <div v-else class="file-list">
              <div class="file-list-head"><span>文件</span><span>状态</span></div>
              <router-link v-for="file in recentFiles" :key="file.session_id" class="file-row" to="/history" :aria-label="`在处理记录中查看 ${getFileName(file.source_path)}`">
                <span class="file-mark" :class="{ presentation: /pptx?$/i.test(file.source_path) }">{{ fileExtension(file.source_path) }}</span>
                <span class="file-copy"><strong :title="getFileName(file.source_path)">{{ getFileName(file.source_path) }}</strong><small>{{ file.category || '待分类' }}<span>·</span>{{ formatTime(file.created_at) }}</small></span>
                <span class="file-status" :class="statusClass(file.status)"><i />{{ statusLabel(file.status) }}</span><el-icon class="row-arrow"><ArrowRight /></el-icon>
              </router-link>
            </div>
            <p class="record-note">显示最近 {{ history.length }} 条处理记录 · 同一文件多次导入会分别记录</p>
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
          <section class="partner-note"><div><span class="partner-label">A LITTLE EVERY DAY</span><h2>每一小步，<br />都有迹可循。</h2><p>练习、错题与复习，<br />留下属于你的学习轨迹。</p><router-link to="/growth">查看学习记录<el-icon><ArrowRight /></el-icon></router-link></div><img src="../assets/filemate-mascot.png" alt="FileMate 学习伙伴" width="1086" height="1448" /></section>
          <router-link class="privacy-link" to="/trust"><el-icon><Lock /></el-icon><span>资料如何保存与使用</span><el-icon><ArrowRight /></el-icon></router-link>
        </aside>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowRight, Calendar, DocumentAdd, FolderChecked, Loading, Lock, Microphone, Plus, Reading } from '@element-plus/icons-vue'
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
  { id: 'organize', label: '整理资料', icon: DocumentAdd },
  { id: 'review', label: '复习备考', icon: Reading },
  { id: 'interview', label: '面试练习', icon: Microphone }
] as const
const selectedIntent = ref<(typeof intents)[number]['id']>('organize')
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
.dashboard { max-width:1280px; margin:0 auto; }
a { color:inherit; text-decoration:none; }
.welcome { display:flex; justify-content:space-between; align-items:center; gap:24px; padding:32px; margin-bottom:24px; background:#edf4ee; border:1px solid var(--border-subtle); border-radius:var(--radius-panel); }
.welcome-meta { display:flex; flex-wrap:wrap; align-items:center; gap:10px 16px; color:var(--accent); font-size:12px; font-weight:600; }
.welcome time { color:var(--text-muted); font-size:12px; font-weight:400; }
.welcome h1 { margin:18px 0 12px; font-size:clamp(28px,3vw,42px); font-weight:600; letter-spacing:-.045em; line-height:1.3; text-wrap:balance; }
.title-dot { color:var(--accent); }
.welcome p { margin:0; color:var(--text-secondary); font-size:14px; line-height:1.8; }.mobile-break { display:none; }
.welcome-action { flex-shrink:0; display:grid; justify-items:center; gap:12px; padding-left:24px; border-left:1px solid var(--accent-border); }
.desk-label,.format-hint { font:10px var(--font-mono); letter-spacing:.06em; color:var(--text-muted); }
.welcome-action .solid-link { min-height:48px; }
.solid-link { display:inline-flex; align-items:center; justify-content:center; gap:10px; min-height:44px; padding:0 18px; background:var(--accent); color:white; border-radius:var(--radius-control); font-size:13px; font-weight:600; white-space:nowrap; transition:background var(--motion-fast); }.solid-link:hover { background:var(--accent-hover); }
.overview { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); padding:22px 24px; border:1px solid var(--border-subtle); border-radius:var(--radius-panel); background:var(--bg-surface); margin-bottom:24px; }
.overview > * { position:relative; display:flex; flex-direction:column; gap:8px; padding:0 26px; border-right:1px solid var(--border-subtle); }.overview > :first-child { padding-left:0; }.overview > :last-child { border-right:0; }
.overview span { font-size:12px; color:var(--text-secondary); }.overview strong { font-size:27px; font-weight:500; font-variant-numeric:tabular-nums; line-height:1.2; }.overview small { margin-left:8px; font-size:11px; font-weight:400; color:var(--text-muted); }.overview .el-icon { position:absolute; right:26px; top:4px; color:var(--text-muted); }.overview a:hover { color:var(--accent); }.amber { color:var(--warning); }
.desk-grid { display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:24px; align-items:start; }.desk-main,.desk-aside { min-width:0; }
.section-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; }.section-heading h2 { margin:0; font-size:16px; font-weight:600; }.section-heading > span { color:var(--text-muted); font-size:12px; }.section-heading a { display:inline-flex; align-items:center; gap:7px; min-height:44px; font-size:12px; color:var(--text-secondary); }.section-heading a:hover { color:var(--accent); }
.focus-sheet { padding:24px; border:1px solid var(--border-subtle); border-radius:var(--radius-panel); background:var(--bg-surface); }
.focus-body { display:grid; grid-template-columns:48px minmax(0,1fr); gap:16px; align-items:center; padding:26px 0; }.focus-symbol { display:grid; place-items:center; width:48px; height:56px; border-radius:10px; background:var(--accent-soft); color:var(--accent); font-size:24px; }.focus-body h3 { margin:7px 0 8px; font-size:20px; line-height:1.5; font-weight:600; text-wrap:balance; }.focus-body p { margin:0; color:var(--text-secondary); font-size:13px; line-height:1.8; }
.focus-body .solid-link { grid-column:2; justify-self:start; }
.focus-caption { color:var(--accent); font-size:11px; font-weight:600; }
.intent-options { display:flex; flex-wrap:wrap; gap:6px; margin-top:24px; padding:5px; border:1px solid var(--border-subtle); border-radius:var(--radius-control); background:var(--bg-base); }
.intent-options button { display:flex; align-items:center; justify-content:center; gap:8px; flex:1; min-height:44px; padding:0 10px; color:var(--text-secondary); border:1px solid transparent; border-radius:7px; background:transparent; font-size:12px; white-space:nowrap; transition:background var(--motion-fast),color var(--motion-fast); }
.intent-options button:hover { background:var(--accent-soft); }
.intent-options button[aria-pressed=true] { color:var(--accent); background:white; border-color:var(--accent-border); font-weight:600; }
.intent-options .el-icon { font-size:17px; }
.study-shortcuts { display:grid; grid-template-columns:1fr 1fr; padding-top:18px; border-top:1px solid var(--border-subtle); gap:20px; }.study-shortcuts a { display:flex; align-items:center; gap:12px; min-height:52px; }.study-shortcuts a > .el-icon:first-child { font-size:21px; color:var(--accent); }.study-shortcuts a > .el-icon:last-child { margin-left:auto; color:var(--text-muted); font-size:12px; }.study-shortcuts strong,.study-shortcuts small { display:block; }.study-shortcuts strong { font-size:13px; font-weight:500; }.study-shortcuts small { margin-top:6px; color:var(--text-muted); font-size:11px; line-height:1.6; }.study-shortcuts a:hover strong { color:var(--accent); }
.recent-section { margin-top:24px; padding:20px 24px; background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:var(--radius-panel); }.file-list { margin-top:8px; }.file-list-head { display:flex; justify-content:space-between; padding:10px 32px 10px 0; color:var(--text-muted); font-size:11px; }
.file-row { display:grid; grid-template-columns:40px minmax(0,1fr) auto 12px; align-items:center; gap:12px; min-height:79px; padding:12px 8px; border-top:1px solid var(--border-subtle); transition:background var(--motion-fast); border-radius:4px; }.file-row:hover { background:var(--bg-elevated); }
.file-mark { display:grid; place-items:center; width:35px; height:43px; font-size:9px; font-weight:600; letter-spacing:.02em; color:var(--accent); background:#e7efea; border:1px solid #d1dfd6; border-radius:4px 10px 4px 4px; }.file-mark.presentation { color:#936333; background:#f4ede2; border-color:#e6d9c6; }.file-copy { min-width:0; }.file-copy strong { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:13px; font-weight:500; }.file-copy small { display:flex; gap:8px; margin-top:7px; color:var(--text-muted); font-size:11px; }
.file-status { display:flex; align-items:center; gap:6px; color:var(--text-secondary); font-size:11px; white-space:nowrap; }.file-status i { width:5px; height:5px; border-radius:50%; background:currentColor; }.file-status.success { color:var(--success); }.file-status.warning { color:var(--warning); }.file-status.danger { color:var(--danger); }.row-arrow { font-size:12px; color:var(--text-muted); }.record-note { margin-top:14px; color:var(--text-muted); font-size:11px; line-height:1.7; }
.today-sheet { padding:20px 22px 24px; background:var(--bg-surface); border:1px solid var(--border-subtle); border-top:3px solid var(--accent); border-radius:var(--radius-panel); }.today-summary { margin:2px 0 16px; color:var(--text-secondary); font-size:12px; line-height:1.6; }
.task-list { margin:0; padding:0; list-style:none; }.task-list li + li { border-top:1px solid #d6e2d9; }.task-list a { display:grid; grid-template-columns:16px minmax(0,1fr); gap:12px; padding:16px 0; }.task-circle { width:14px; height:14px; margin-top:3px; border:1px solid #8ba696; border-radius:50%; }.task-list strong { display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; font-size:13px; font-weight:500; line-height:1.7; }.task-list small { display:block; margin-top:7px; color:var(--text-muted); font-size:11px; }.task-list a:hover strong { color:var(--accent); }.today-start { width:100%; margin-top:14px; }
.today-empty { padding:20px 0 0; }.today-empty > .el-icon { font-size:27px; color:var(--accent); }.today-empty p { font-size:13px; color:var(--text-secondary); line-height:1.9; }.today-empty a,.partner-note a,.empty-files a { display:inline-flex; align-items:center; gap:10px; min-height:44px; color:var(--accent); font-size:12px; }
.partner-note { position:relative; isolation:isolate; display:flex; min-height:220px; overflow:hidden; margin-top:24px; padding:22px 0 12px 2px; border-bottom:1px solid var(--border-subtle); }.partner-note > div { position:relative; z-index:1; }.partner-label { font-size:11px; color:var(--text-muted); }.partner-note h2 { margin:12px 0 10px; font-size:22px; line-height:1.55; font-weight:500; letter-spacing:.03em; }.partner-note p { font-size:12px; color:var(--text-secondary); line-height:1.8; }.partner-note img { position:absolute; width:145px; height:auto; right:-8px; bottom:12px; z-index:0; }
.privacy-link { display:flex; gap:10px; align-items:center; min-height:56px; font-size:11px; color:var(--text-muted); }.privacy-link > :last-child { margin-left:auto; }
.load-state { display:flex; align-items:center; justify-content:center; flex-wrap:wrap; gap:12px; min-height:240px; color:var(--text-secondary); font-size:14px; }.error { color:var(--danger); }.loading-icon { animation:spin 1s linear infinite; }@keyframes spin { to { transform:rotate(360deg); } }
.empty-files { text-align:center; padding:44px 16px; margin-top:10px; border-block:1px solid var(--border-subtle); }.empty-files > .el-icon { font-size:28px; color:var(--accent); }.empty-files h3 { font-size:15px; font-weight:500; }.empty-files p { font-size:13px; color:var(--text-secondary); }.review-error { font-size:13px; color:var(--text-secondary); }.review-error button { min-height:44px; color:var(--accent); background:transparent; border:0; }
@media(min-width:1600px) { .desk-grid { grid-template-columns:minmax(0,1fr) 320px; gap:36px; } }
@media(max-width:1150px) { .desk-grid { grid-template-columns:minmax(0,1fr) 265px; gap:20px; }.focus-body { grid-template-columns:40px 1fr; }.focus-body .solid-link { grid-column:2; justify-self:start; }.study-shortcuts { grid-template-columns:1fr; gap:8px; }.partner-note img { width:115px; right:-10px; } }
@media(max-width:700px) { .welcome { align-items:flex-start; padding-top:4px; }.welcome h1 { font-size:25px; }.welcome p { max-width:230px; font-size:12px; line-height:1.8; }.mobile-break { display:block; }.welcome .solid-link { padding:0 12px; font-size:12px; }.overview { padding:18px 0; gap:18px 0; grid-template-columns:1fr 1fr; }.overview > * { padding:0 20px; }.overview > :nth-child(3) { padding-left:0; }.overview > :nth-child(2) { border:0; }.overview strong { font-size:24px; }.desk-grid { grid-template-columns:1fr; }.focus-sheet { padding:20px; }.section-heading > span { display:none; }.file-row { gap:9px; grid-template-columns:35px minmax(0,1fr) auto; }.row-arrow { display:none; }.file-list-head { padding-right:8px; }.partner-note img { width:140px; right:16px; }.today-sheet { margin-top:4px; }.partner-note { min-height:235px; } }
@media (max-width: 700px) {
  .welcome { flex-direction:column; padding:24px; gap:22px; }
  .welcome h1 { font-size:32px; }
  .welcome-action { width:100%; padding:18px 0 0; border-left:0; border-top:1px solid var(--accent-border); justify-items:start; grid-template-columns:1fr auto; align-items:center; }
  .welcome-action .solid-link { grid-column:2; grid-row:1 / 3; }
  .welcome .format-hint { font-size:8px; }
  .desk-label { font-size:9px; }
  .overview { padding:20px; }
  .recent-section { padding:16px 20px; }
  .focus-body h3 { font-size:18px; }
  .intent-options { gap:2px; }
  .intent-options button { padding-inline:6px; font-size:11px; gap:5px; }
  .intent-options .el-icon { font-size:15px; }
}
</style>
