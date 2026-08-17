<template>
  <div class="dashboard">
    <section class="dashboard-intro" aria-labelledby="dashboard-title">
      <div>
        <h2 id="dashboard-title">{{ hasHistory ? '继续推进你的学习闭环' : '从第一份学习资料开始' }}</h2>
        <p>
          {{ hasHistory
            ? 'FileMate 已把资料处理、确认和学习产物串在一起。先完成最接近截止线的一步。'
            : '导入课件、作业或考试通知，系统会先给出可确认的分类与日程，再生成学习产物。' }}
        </p>
        <time class="today-context">{{ todayLabel }} · 本地学习空间</time>
      </div>
      <div class="intro-actions">
        <el-button type="primary" size="large" @click="router.push('/import')">
          <el-icon><Upload /></el-icon>
          导入学习资料
        </el-button>
        <el-button size="large" @click="router.push('/ai-tools')">
          <el-icon><MagicStick /></el-icon>
          打开资料理解
        </el-button>
      </div>
    </section>

    <div v-if="loading" class="state-panel" aria-live="polite">
      <el-icon class="loading-icon"><Loading /></el-icon>
      <div>
        <strong>正在读取本地学习记录</strong>
        <span>只会访问 FileMate 的本机数据目录</span>
      </div>
    </div>

    <div v-else-if="errorMessage" class="state-panel error-panel" role="alert">
      <el-icon><Warning /></el-icon>
      <div>
        <strong>暂时无法读取学习记录</strong>
        <span>{{ errorMessage }}</span>
      </div>
      <el-button @click="loadDashboard">重新连接</el-button>
    </div>

    <template v-else>
      <section class="metric-strip" aria-label="学习资产概览">
        <div>
          <span>学习资料</span>
          <strong>{{ metrics.total }}</strong>
        </div>
        <div>
          <span>近 7 天新增</span>
          <strong>{{ metrics.thisWeek }}</strong>
        </div>
        <div>
          <span>等待确认</span>
          <strong :class="{ warning: metrics.pending > 0 }">{{ metrics.pending }}</strong>
        </div>
        <div>
          <span>已可信归档</span>
          <strong>{{ metrics.confirmed }}</strong>
        </div>
        <p>所有数字均来自本机处理记录</p>
      </section>

      <div class="dashboard-grid">
        <div class="primary-column">
          <section class="panel next-panel">
            <div class="panel-heading">
              <div>
                <h3>今天建议先完成</h3>
              </div>
              <span class="evidence-label">基于当前资料状态</span>
            </div>

            <ol class="action-list">
              <li v-for="(action, index) in nextActions" :key="action.title">
                <span class="action-index">0{{ index + 1 }}</span>
                <div class="action-copy">
                  <strong>{{ action.title }}</strong>
                  <span>{{ action.description }}</span>
                </div>
                <el-button :type="index === 0 ? 'primary' : 'default'" @click="router.push(action.route)">
                  {{ action.cta }}
                  <el-icon><ArrowRight /></el-icon>
                </el-button>
              </li>
            </ol>
          </section>

          <section class="panel recent-panel">
            <div class="panel-heading">
              <div>
                <h3>最近处理</h3>
              </div>
              <button class="text-button" @click="router.push('/history')">
                查看全部
                <el-icon><ArrowRight /></el-icon>
              </button>
            </div>

            <div v-if="recentFiles.length === 0" class="empty-state">
              <div class="empty-icon"><el-icon><DocumentAdd /></el-icon></div>
              <div>
                <strong>还没有学习资料</strong>
                <span>支持 PDF、Word、PPT 与常见图片格式</span>
              </div>
              <el-button type="primary" @click="router.push('/import')">导入第一份资料</el-button>
            </div>

            <ul v-else class="asset-list">
              <li v-for="file in recentFiles" :key="file.session_id">
                <span class="asset-icon"><el-icon><Document /></el-icon></span>
                <div class="asset-copy">
                  <strong :title="getFileName(file.source_path)">{{ getFileName(file.source_path) }}</strong>
                  <span>{{ formatTime(file.created_at) }} · {{ file.category || '待分类' }}</span>
                </div>
                <span class="status-chip" :class="statusClass(file.status)">
                  {{ statusLabel(file.status) }}
                </span>
              </li>
            </ul>
          </section>
        </div>

        <aside class="secondary-column">
          <section class="panel loop-panel">
            <div class="panel-heading compact">
              <div>
                <h3>从资料到掌握</h3>
              </div>
            </div>
            <ol class="learning-loop">
              <li v-for="(stage, index) in learningLoop" :key="stage.title">
                <span class="loop-marker"><el-icon><component :is="stage.icon" /></el-icon></span>
                <div>
                  <span>阶段 0{{ index + 1 }}</span>
                  <strong>{{ stage.title }}</strong>
                  <p>{{ stage.description }}</p>
                </div>
                <span class="availability" :class="stage.state">{{ stage.label }}</span>
              </li>
            </ol>
          </section>

          <section class="panel profile-panel">
            <div class="profile-title">
              <span class="profile-icon"><el-icon><DataAnalysis /></el-icon></span>
              <div>
                <h3>等待首轮评测</h3>
              </div>
            </div>
            <p>
              完成题目作答后，系统才会根据知识掌握、错因、学习节律等证据生成画像。
            </p>
            <div class="profile-placeholder" aria-label="尚无学习画像数据">
              <span v-for="item in profileDimensions" :key="item">{{ item }}<i>待评测</i></span>
            </div>
            <el-button plain @click="router.push('/ai-tools')">先从资料生成练习</el-button>
          </section>

          <section class="privacy-note">
            <el-icon><Lock /></el-icon>
            <p><strong>本地优先</strong><span>资料与学习轨迹默认保存在你的设备中。</span></p>
          </section>
        </aside>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Aim,
  ArrowRight,
  DataAnalysis,
  Document,
  DocumentAdd,
  Loading,
  Lock,
  MagicStick,
  Reading,
  RefreshRight,
  Upload,
  Warning
} from '@element-plus/icons-vue'
import { getHistory } from '../services/api'
import type { HistoryItem, SessionStatus } from '../types'

const router = useRouter()
const loading = ref(true)
const errorMessage = ref('')
const history = ref<HistoryItem[]>([])

const todayLabel = new Intl.DateTimeFormat('zh-CN', {
  month: 'long',
  day: 'numeric',
  weekday: 'long'
}).format(new Date())

const hasHistory = computed(() => history.value.length > 0)
const recentFiles = computed(() => history.value.slice(0, 5))

const metrics = computed(() => {
  const weekAgo = Date.now() - 7 * 24 * 60 * 60 * 1000
  return {
    total: history.value.length,
    thisWeek: history.value.filter(item => new Date(item.created_at).getTime() >= weekAgo).length,
    pending: history.value.filter(item => ['pending', 'processing', 'done'].includes(item.status)).length,
    confirmed: history.value.filter(item => item.status === 'confirmed').length
  }
})

const nextActions = computed(() => {
  const actions = []
  if (metrics.value.pending > 0) {
    actions.push({
      title: `确认 ${metrics.value.pending} 份待处理资料`,
      description: '复核分类、命名与日程，确认后再执行归档。',
      route: '/classification',
      cta: '去确认'
    })
  } else {
    actions.push({
      title: hasHistory.value ? '补充今天的学习资料' : '建立第一份学习资产',
      description: '导入课件、作业或通知，生成可追溯的学习上下文。',
      route: '/import',
      cta: '去导入'
    })
  }
  actions.push({
    title: '把资料转成可练习的内容',
    description: '从真实资料生成摘要、知识卡、笔记与题目。',
    route: '/ai-tools',
    cta: '资料理解'
  })
  actions.push({
    title: '安排下一段专注时间',
    description: '结合考试日期和薄弱点生成可执行计划。',
    route: '/study-plan',
    cta: '制定计划'
  })
  return actions
})

const learningLoop = [
  { title: '沉淀资料', description: '分类、命名、日程与可信归档', icon: Reading, state: 'available', label: '可用' },
  { title: '理解知识', description: '摘要、笔记、知识卡与资料问答', icon: MagicStick, state: 'available', label: '可用' },
  { title: '练习诊断', description: '题目作答、错因分析与错题复习', icon: Aim, state: 'building', label: '建设中' },
  { title: '动态提升', description: '学习画像、计划更新与能力验证', icon: RefreshRight, state: 'building', label: '建设中' }
]

const profileDimensions = ['知识掌握', '错因结构', '学习节律', '资源偏好']

function getFileName(path: string): string {
  return path?.split(/[/\\]/).pop() || '未命名资料'
}

function formatTime(value: string): string {
  const date = new Date(value)
  const diffMinutes = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000))
  if (diffMinutes < 1) return '刚刚'
  if (diffMinutes < 60) return `${diffMinutes} 分钟前`
  if (diffMinutes < 1440) return `${Math.floor(diffMinutes / 60)} 小时前`
  if (diffMinutes < 10080) return `${Math.floor(diffMinutes / 1440)} 天前`
  return date.toLocaleDateString('zh-CN')
}

function statusLabel(status: SessionStatus): string {
  const labels: Record<SessionStatus, string> = {
    pending: '等待处理',
    processing: '处理中',
    done: '待确认',
    confirmed: '已归档',
    skipped: '已跳过',
    expired: '已过期',
    failed: '处理失败'
  }
  return labels[status]
}

function statusClass(status: SessionStatus): string {
  if (status === 'confirmed') return 'success'
  if (status === 'failed' || status === 'expired') return 'danger'
  if (status === 'done' || status === 'pending' || status === 'processing') return 'warning'
  return 'neutral'
}

async function loadDashboard(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    history.value = await getHistory(undefined, 100)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '请确认本地服务已经启动。'
  } finally {
    loading.value = false
  }
}

onMounted(loadDashboard)
</script>

<style scoped>
.dashboard {
  width: min(1380px, 100%);
  margin: 0 auto;
}

.dashboard-intro {
  padding: 4px 0 28px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 32px;
  border-bottom: 1px solid var(--border-subtle);
}

.today-context {
  display: block;
  margin-top: 12px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 600;
}

.dashboard-intro h2 {
  max-width: 720px;
  margin: 0;
  font-size: clamp(27px, 3vw, 40px);
  line-height: 1.2;
  letter-spacing: -0.035em;
}

.dashboard-intro > div > p {
  max-width: 720px;
  margin: 12px 0 0;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.75;
}

.intro-actions {
  flex: 0 0 auto;
  display: flex;
  gap: 10px;
}

.state-panel {
  min-height: 110px;
  margin-top: 24px;
  padding: 24px;
  display: flex;
  align-items: center;
  gap: 14px;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-panel);
}

.state-panel > .el-icon {
  color: var(--accent);
  font-size: 24px;
}

.state-panel div {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.state-panel span {
  color: var(--text-muted);
  font-size: 13px;
}

.error-panel > .el-icon {
  color: var(--danger);
}

.loading-icon {
  animation: spin 800ms linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.metric-strip {
  min-height: 86px;
  margin: 20px 0;
  padding: 14px 20px;
  display: grid;
  grid-template-columns: repeat(4, minmax(100px, 1fr)) auto;
  align-items: center;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-panel);
}

.metric-strip > div {
  min-height: 46px;
  padding: 0 20px;
  display: flex;
  flex-direction: column-reverse;
  justify-content: center;
  gap: 3px;
  border-left: 1px solid var(--border-subtle);
}

.metric-strip > div:first-child {
  padding-left: 0;
  border-left: 0;
}

.metric-strip span,
.metric-strip p {
  color: var(--text-muted);
  font-size: 11px;
}

.metric-strip strong {
  font-family: var(--font-mono);
  font-size: 21px;
  font-weight: 700;
}

.metric-strip strong.warning {
  color: var(--warning);
}

.metric-strip p {
  margin: 0;
  white-space: nowrap;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 7fr) minmax(310px, 5fr);
  gap: 20px;
  align-items: start;
}

.primary-column,
.secondary-column {
  min-width: 0;
  display: grid;
  gap: 20px;
}

.panel {
  padding: 22px;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-panel);
}

.panel-heading {
  margin-bottom: 18px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.panel-heading.compact {
  margin-bottom: 8px;
}

.panel h3 {
  margin: 0;
  font-size: 18px;
  line-height: 1.3;
  letter-spacing: -0.015em;
}

.evidence-label {
  color: var(--text-muted);
  font-size: 11px;
}

.action-list,
.asset-list,
.learning-loop {
  margin: 0;
  padding: 0;
  list-style: none;
}

.action-list li {
  min-height: 76px;
  padding: 14px 0;
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  border-top: 1px solid var(--border-subtle);
}

.action-list li:first-child {
  border-top: 0;
}

.action-index {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 12px;
}

.action-copy,
.asset-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.action-copy strong,
.asset-copy strong {
  font-size: 14px;
}

.action-copy span,
.asset-copy span {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.text-button {
  min-height: 40px;
  padding: 0 2px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--accent);
  background: transparent;
  border: 0;
}

.empty-state {
  min-height: 156px;
  padding: 20px;
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px;
  background: var(--bg-elevated);
  border-radius: 12px;
}

.empty-state > div:not(.empty-icon) {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.empty-state span {
  color: var(--text-muted);
  font-size: 12px;
}

.empty-icon,
.asset-icon,
.profile-icon {
  display: grid;
  place-items: center;
  color: var(--accent);
  background: var(--accent-soft);
  border: 1px solid var(--accent-border);
  border-radius: 10px;
}

.empty-icon {
  width: 48px;
  height: 48px;
  font-size: 22px;
}

.asset-list li {
  min-height: 66px;
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  border-top: 1px solid var(--border-subtle);
}

.asset-list li:first-child {
  border-top: 0;
}

.asset-icon {
  width: 38px;
  height: 38px;
}

.asset-copy strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-chip {
  padding: 4px 8px;
  color: var(--text-secondary);
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  font-size: 11px;
  white-space: nowrap;
}

.status-chip.success { color: var(--success); }
.status-chip.warning { color: var(--warning); }
.status-chip.danger { color: var(--danger); }

.learning-loop li {
  position: relative;
  min-height: 94px;
  padding: 14px 0 14px 50px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: start;
  gap: 12px;
}

.learning-loop li:not(:last-child)::before {
  content: '';
  position: absolute;
  top: 48px;
  bottom: -8px;
  left: 19px;
  width: 1px;
  background: var(--border-strong);
}

.loop-marker {
  position: absolute;
  top: 13px;
  left: 0;
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  color: var(--accent);
  background: var(--bg-elevated);
  border: 1px solid var(--accent-border);
  border-radius: 10px;
}

.learning-loop div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.learning-loop div > span,
.learning-loop p {
  color: var(--text-muted);
  font-size: 11px;
}

.learning-loop strong {
  font-size: 14px;
}

.learning-loop p {
  margin: 0;
  line-height: 1.5;
}

.availability {
  padding-top: 2px;
  color: var(--text-muted);
  font-size: 11px;
  white-space: nowrap;
}

.availability.available {
  color: var(--success);
}

.profile-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.profile-icon {
  width: 42px;
  height: 42px;
  font-size: 20px;
}

.profile-panel > p {
  margin: 16px 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.7;
}

.profile-placeholder {
  margin-bottom: 16px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.profile-placeholder span {
  padding: 10px;
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: var(--text-secondary);
  background: var(--bg-elevated);
  border-radius: 8px;
  font-size: 11px;
}

.profile-placeholder i {
  color: var(--text-muted);
  font-style: normal;
}

.privacy-note {
  padding: 6px 4px;
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--text-muted);
}

.privacy-note > .el-icon {
  color: var(--accent);
  font-size: 18px;
}

.privacy-note p {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 11px;
}

.privacy-note strong {
  color: var(--text-secondary);
}

@media (max-width: 1120px) {
  .dashboard-intro {
    align-items: flex-start;
    flex-direction: column;
  }

  .metric-strip {
    grid-template-columns: repeat(4, 1fr);
  }

  .metric-strip p {
    grid-column: 1 / -1;
    margin-top: 10px;
  }

  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  .secondary-column {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .privacy-note {
    grid-column: 1 / -1;
  }
}

@media (max-width: 700px) {
  .intro-actions {
    width: 100%;
    flex-direction: column;
  }

  .intro-actions .el-button {
    width: 100%;
    margin: 0;
  }

  .metric-strip {
    grid-template-columns: repeat(2, 1fr);
    padding: 10px;
  }

  .metric-strip > div,
  .metric-strip > div:first-child {
    padding: 12px;
    border: 0;
  }

  .secondary-column {
    grid-template-columns: 1fr;
  }

  .privacy-note {
    grid-column: auto;
  }

  .action-list li {
    grid-template-columns: 28px minmax(0, 1fr);
  }

  .action-list .el-button {
    grid-column: 2;
    justify-self: start;
  }

  .empty-state {
    grid-template-columns: 48px minmax(0, 1fr);
  }

  .empty-state .el-button {
    grid-column: 1 / -1;
  }
}
</style>
