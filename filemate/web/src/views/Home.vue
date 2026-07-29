<!--
  View: Home
  Design: Premium SaaS dashboard with sophisticated dark theme
  Animations: Focal entrance, stagger reveals, micro-feedback
-->
<template>
  <div class="home-page">
    <!-- Welcome Hero -->
    <section class="welcome-hero">
      <div class="hero-content">
        <div class="hero-badge" ref="badgeRef">
          <span class="badge-dot"></span>
          <span>AI-Powered</span>
        </div>
        <h1 class="hero-title" ref="titleRef">
          欢迎使用 <span class="gradient-text">FileMate</span>
        </h1>
        <p class="hero-subtitle" ref="subtitleRef">
          智能文件管理，让学习资料井井有条。自动分类、智能命名、日程同步。
        </p>
        <div class="hero-actions" ref="actionsRef">
          <button class="btn-primary" @click="$router.push('/import')">
            <el-icon><Upload /></el-icon>
            <span>立即上传</span>
          </button>
          <button class="btn-secondary" @click="$router.push('/history')">
            <el-icon><Clock /></el-icon>
            <span>查看历史</span>
          </button>
        </div>
      </div>

      <!-- Decorative elements -->
      <div class="hero-decoration">
        <div class="deco-card deco-1">
          <span class="deco-icon">📄</span>
          <span class="deco-label">文档</span>
        </div>
        <div class="deco-card deco-2">
          <span class="deco-icon">📊</span>
          <span class="deco-label">数据</span>
        </div>
        <div class="deco-card deco-3">
          <span class="deco-icon">🎯</span>
          <span class="deco-label">目标</span>
        </div>
        <div class="deco-ring"></div>
      </div>
    </section>

    <!-- Stats Row -->
    <section class="stats-section">
      <div
        v-for="(stat, index) in statsData"
        :key="stat.label"
        class="stat-card"
        :class="{ 'animate-in': statsVisible }"
        :style="{ '--accent': stat.color, '--delay': index * 0.08 + 's' }"
      >
        <div class="stat-icon-wrap">
          <span class="stat-icon">{{ stat.icon }}</span>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stat.value }}</div>
          <div class="stat-label">{{ stat.label }}</div>
        </div>
        <div v-if="stat.trend !== undefined" class="stat-trend" :class="stat.trend >= 0 ? 'up' : 'down'">
          {{ stat.trend >= 0 ? '↑' : '↓' }} {{ Math.abs(stat.trend) }}%
        </div>
      </div>
    </section>

    <!-- Features Grid -->
    <section class="features-section">
      <div class="section-header">
        <h2 class="section-title">核心功能</h2>
        <p class="section-desc">一站式解决文件管理难题</p>
      </div>

      <div class="features-grid">
        <div
          v-for="(feature, index) in features"
          :key="feature.title"
          class="feature-card"
          :class="{ 'animate-in': featuresVisible }"
          :style="{ '--delay': index * 0.1 + 's' }"
          @click="$router.push(feature.route)"
          @mouseenter="handleFeatureHover(index)"
          @mouseleave="handleFeatureLeave(index)"
        >
          <div class="feature-icon" :style="{ background: feature.gradient }">
            {{ feature.icon }}
          </div>
          <div class="feature-content">
            <h3>{{ feature.title }}</h3>
            <p>{{ feature.desc }}</p>
          </div>
          <div class="feature-arrow">
            <el-icon><ArrowRight /></el-icon>
          </div>
        </div>
      </div>
    </section>

    <!-- Recent Files -->
    <section class="recent-section">
      <div class="section-header-inline">
        <h2 class="section-title">最近处理</h2>
        <button class="view-all-btn" @click="$router.push('/history')">
          查看全部
          <el-icon><ArrowRight /></el-icon>
        </button>
      </div>

      <div v-if="recentFiles.length === 0" class="empty-state">
        <div class="empty-illustration">
          <div class="empty-icon">📭</div>
          <div class="empty-pulse"></div>
        </div>
        <h3>暂无处理记录</h3>
        <p>上传第一个文件，开始智能管理之旅</p>
        <button class="btn-primary btn-small" @click="$router.push('/import')">
          <el-icon><Upload /></el-icon>
          上传文件
        </button>
      </div>

      <div v-else class="recent-list">
        <div
          v-for="(file, index) in recentFiles.slice(0, 6)"
          :key="file.session_id"
          class="recent-item"
          :class="{ 'animate-in': recentVisible }"
          :style="{ '--delay': index * 0.05 + 's' }"
        >
          <div class="file-icon">{{ getFileIcon(file.source_path) }}</div>
          <div class="file-info">
            <div class="file-name">{{ getFileName(file.source_path) }}</div>
            <div class="file-meta">
              <span class="file-time">{{ formatTime(file.created_at) }}</span>
            </div>
          </div>
          <span class="file-category" :class="'cat-' + file.category">
            {{ getCategoryLabel(file.category) }}
          </span>
        </div>
      </div>
    </section>

    <!-- Quick Tips -->
    <section class="tips-section">
      <div class="tip-card">
        <div class="tip-icon">💡</div>
        <div class="tip-content">
          <h4>使用提示</h4>
          <p>支持 Word、PDF、PPT 等多种文件格式。文件会自动进行分类、命名和日程提取。</p>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Upload, Clock, ArrowRight } from '@element-plus/icons-vue'
import { getHistory } from '../services/api'

const statsVisible = ref(false)
const featuresVisible = ref(false)
const recentVisible = ref(false)

const statsData = ref([
  { icon: '📁', label: '总文件数', value: 0, color: '#10b981', trend: 0 },
  { icon: '📅', label: '本周处理', value: 0, color: '#8b5cf6', trend: 0 },
  { icon: '⏳', label: '待确认', value: 0, color: '#f59e0b', trend: 0 },
  { icon: '✅', label: '已完成', value: 0, color: '#10b981', trend: 0 }
])

const features = [
  {
    icon: '📤',
    title: '智能导入',
    desc: '多种格式自动解析，拖拽上传',
    route: '/import',
    gradient: 'linear-gradient(135deg, #10b981 0%, #34d399 100%)'
  },
  {
    icon: '🏷️',
    title: '自动分类',
    desc: 'AI 智能识别文件类型',
    route: '/classification',
    gradient: 'linear-gradient(135deg, #ec4899 0%, #f472b6 100%)'
  },
  {
    icon: '✏️',
    title: '命名建议',
    desc: '规范化文件名易查找',
    route: '/naming',
    gradient: 'linear-gradient(135deg, #06b6d4 0%, #22d3ee 100%)'
  },
  {
    icon: '📆',
    title: '日程同步',
    desc: '自动提取截止日期',
    route: '/schedule',
    gradient: 'linear-gradient(135deg, #10b981 0%, #34d399 100%)'
  }
]

const recentFiles = ref<any[]>([])

const getFileIcon = (path: string) => {
  const ext = path?.split('.').pop()?.toLowerCase() || ''
  const icons: Record<string, string> = {
    doc: '📄', docx: '📄', pdf: '📕', ppt: '📊', pptx: '📊',
    txt: '📝', jpg: '🖼️', png: '🖼️', gif: '🖼️'
  }
  return icons[ext] || '📁'
}

const getFileName = (path: string) => {
  return path?.split(/[/\\]/).pop() || '未知文件'
}

const getCategoryLabel = (category: string) => {
  const labels: Record<string, string> = {
    '课件': '课件',
    '作业': '作业',
    '竞赛通知': '竞赛',
    '考试通知': '考试',
    '参考资料': '资料',
    '大创通知': '大创',
    '待确认': '待确认'
  }
  return labels[category || ''] || category || '待确认'
}

const formatTime = (time: string) => {
  if (!time) return ''
  const date = new Date(time)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  if (hours < 24) return `${hours}小时前`
  if (days < 7) return `${days}天前`
  return date.toLocaleDateString('zh-CN')
}

const handleFeatureHover = (index: number) => {
  // Micro-feedback: scale icon slightly
}

const handleFeatureLeave = (index: number) => {
  // Reset
}

onMounted(async () => {
  // Entrance animations - staggered reveal
  requestAnimationFrame(() => {
    setTimeout(() => { statsVisible.value = true }, 100)
    setTimeout(() => { featuresVisible.value = true }, 300)
    setTimeout(() => { recentVisible.value = true }, 500)
  })

  try {
    const history = await getHistory(undefined, 100)
    const total = history.length

    const now = new Date()
    const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
    const week = history.filter((h: any) =>
      new Date(h.created_at) >= weekAgo
    ).length

    const pending = history.filter((h: any) =>
      h.status === 'pending' || h.status === 'processing' || h.status === 'done'
    ).length

    const completed = history.filter((h: any) =>
      h.status === 'confirmed'
    ).length

    statsData.value[0].value = total
    statsData.value[1].value = week
    statsData.value[2].value = pending
    statsData.value[3].value = completed

    recentFiles.value = history
  } catch (e) {
    console.error('加载数据失败:', e)
  }
})
</script>

<style scoped>
/* ═══════════════════════════════════════════════════════
   Design Tokens
   ═══════════════════════════════════════════════════════ */
.home-page {
  --bg-card: #16161e;
  --bg-elevated: #1e1e28;
  --border-subtle: rgba(255, 255, 255, 0.05);
  --border-default: rgba(255, 255, 255, 0.08);

  --text-primary: #f4f4f5;
  --text-secondary: #a1a1aa;
  --text-muted: #71717a;

  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 24px;

  --transition-fast: 0.15s cubic-bezier(0.4, 0, 0.2, 1);
  --transition-smooth: 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  --transition-bounce: 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);

  max-width: 1400px;
  margin: 0 auto;
}

/* ═══════════════════════════════════════════════════════
   Entrance Animations
   ═══════════════════════════════════════════════════════ */
.stat-card.animate-in,
.feature-card.animate-in,
.recent-item.animate-in {
  animation: fadeSlideIn 0.5s ease-out backwards;
  animation-delay: var(--delay, 0s);
}

@keyframes fadeSlideIn {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Hero animations with different timing */
.hero-badge {
  animation: fadeDown 0.5s cubic-bezier(0.16, 1, 0.3, 1) 0.1s backwards;
}

.hero-title {
  animation: fadeUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) 0.2s backwards;
}

.hero-subtitle {
  animation: fadeUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) 0.35s backwards;
}

.hero-actions {
  animation: fadeUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) 0.5s backwards;
}

.hero-decoration {
  animation: fadeIn 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.4s backwards;
}

@keyframes fadeDown {
  from {
    opacity: 0;
    transform: translateY(-16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes fadeUp {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* ═══════════════════════════════════════════════════════
   Micro-interactions
   ═══════════════════════════════════════════════════════ */

/* Button press feedback */
.btn-primary:active {
  transform: scale(0.97) translateY(1px);
  transition-duration: 0.1s;
}

.btn-secondary:active {
  transform: scale(0.98);
  transition-duration: 0.1s;
}

/* Feature card hover */
.feature-card {
  transition:
    transform var(--transition-fast),
    box-shadow var(--transition-fast),
    border-color var(--transition-fast),
    background var(--transition-fast);
}

.feature-card:hover {
  transform: translateY(-4px) scale(1.01);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
}

.feature-card .feature-icon {
  transition: transform var(--transition-bounce);
}

.feature-card:hover .feature-icon {
  transform: scale(1.08) rotate(-2deg);
}

/* Navigation active indicator */
.nav-item {
  transition:
    background var(--transition-fast),
    color var(--transition-fast),
    transform var(--transition-fast);
}

.nav-item:active {
  transform: scale(0.97);
}

/* Stat card subtle lift */
.stat-card {
  transition:
    transform var(--transition-fast),
    box-shadow var(--transition-fast),
    border-color var(--transition-fast),
    background var(--transition-fast);
}

.stat-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
}

/* Badge pulse animation */
.badge-dot {
  animation: badgePulse 2s ease-in-out infinite;
}

@keyframes badgePulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
    box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.4);
  }
  50% {
    opacity: 0.7;
    transform: scale(0.9);
    box-shadow: 0 0 0 4px rgba(34, 197, 94, 0);
  }
}

/* Hero decoration float */
.deco-card {
  animation: decoFloat 4s ease-in-out infinite;
}

.deco-1 { animation-delay: 0s; }
.deco-2 { animation-delay: 0.6s; }
.deco-3 { animation-delay: 1.2s; }

@keyframes decoFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}

/* Empty state pulse */
.empty-pulse {
  animation: emptyPulse 2s ease-in-out infinite;
}

@keyframes emptyPulse {
  0%, 100% {
    transform: translate(-50%, -50%) scale(1);
    opacity: 0.5;
  }
  50% {
    transform: translate(-50%, -50%) scale(1.4);
    opacity: 0;
  }
}

/* Recent item hover */
.recent-item {
  transition:
    background var(--transition-fast),
    border-color var(--transition-fast),
    transform var(--transition-fast);
}

.recent-item:hover {
  transform: translateX(4px);
  border-color: rgba(99, 102, 241, 0.2);
}

/* Logo glow pulse */
.logo-glow {
  animation: glowPulse 3s ease-in-out infinite;
}

@keyframes glowPulse {
  0%, 100% {
    opacity: 0.4;
    transform: translate(-50%, -50%) scale(1);
  }
  50% {
    opacity: 0.7;
    transform: translate(-50%, -50%) scale(1.15);
  }
}

/* ─────────────────────────────────────────────────────────────
   Base Styles (kept from previous version)
   ───────────────────────────────────────────────────────────── */

/* Hero Section */
.welcome-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 40px 48px;
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.06) 0%, rgba(6, 182, 212, 0.03) 100%);
  border: 1px solid rgba(16, 185, 129, 0.12);
  border-radius: var(--radius-xl);
  margin-bottom: 32px;
  position: relative;
  overflow: hidden;
}

.welcome-hero::before {
  content: '';
  position: absolute;
  top: -80px;
  right: -80px;
  width: 280px;
  height: 280px;
  background: radial-gradient(circle, rgba(16, 185, 129, 0.15) 0%, transparent 70%);
  pointer-events: none;
  animation: heroGlow 8s ease-in-out infinite;
}

@keyframes heroGlow {
  0%, 100% { opacity: 0.6; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.1); }
}

.hero-content {
  position: relative;
  z-index: 1;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background: rgba(34, 197, 94, 0.08);
  border: 1px solid rgba(34, 197, 94, 0.2);
  border-radius: 20px;
  font-size: 12px;
  color: #4ade80;
  margin-bottom: 16px;
  backdrop-filter: blur(8px);
}

.hero-badge .badge-dot {
  background: #22c55e;
  box-shadow: 0 0 8px rgba(34, 197, 94, 0.6);
}

.hero-title {
  font-size: 42px;
  font-weight: 800;
  color: var(--text-primary);
  margin: 0 0 12px;
  letter-spacing: -0.03em;
  line-height: 1.15;
}

.gradient-text {
  background: linear-gradient(135deg, #f0fdf4 0%, #86efac 25%, #22d3ee 50%, #67e8f9 75%, #f0fdf4 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  background-size: 200% 200%;
  animation: gradientShift 8s ease infinite;
}

@keyframes gradientShift {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}

.hero-subtitle {
  font-size: 18px;
  color: var(--text-secondary);
  margin: 0 0 28px;
  max-width: 520px;
  line-height: 1.7;
  font-weight: 420;
  letter-spacing: 0.01em;
}

.hero-actions {
  display: flex;
  gap: 14px;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 16px 32px;
  background: linear-gradient(135deg, #10b981 0%, #059669 50%, #047857 100%);
  border: none;
  border-radius: var(--radius-md);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition:
    transform var(--transition-fast),
    box-shadow var(--transition-fast),
    background var(--transition-fast);
  box-shadow: 0 4px 20px rgba(16, 185, 129, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.15);
  position: relative;
  overflow: hidden;
}

.btn-primary::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
  transition: left 0.5s ease;
}

.btn-primary:hover::before {
  left: 100%;
}

.btn-primary:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 32px rgba(16, 185, 129, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

.btn-secondary {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 14px 28px;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition:
    background var(--transition-fast),
    border-color var(--transition-fast),
    color var(--transition-fast),
    transform var(--transition-fast);
}

.btn-secondary:hover {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.15);
  color: var(--text-primary);
}

/* Hero Decoration */
.hero-decoration {
  position: relative;
  width: 200px;
  height: 160px;
}

.deco-card {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 14px 18px;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
}

.deco-1 { top: 0; left: 20px; }
.deco-2 { top: 50px; left: 100px; }
.deco-3 { top: 100px; left: 40px; }

.deco-icon { font-size: 24px; }
.deco-label {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.deco-ring {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 160px;
  height: 160px;
  border: 1px dashed rgba(16, 185, 129, 0.15);
  border-radius: 50%;
  animation: ringRotate 20s linear infinite;
}

@keyframes ringRotate {
  from { transform: translate(-50%, -50%) rotate(0deg); }
  to { transform: translate(-50%, -50%) rotate(360deg); }
}

/* Enhanced Stats Cards */
.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  position: relative;
  overflow: hidden;
  transition: box-shadow 0.3s ease, border-color 0.3s ease;
}

.stat-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 3px;
  height: 100%;
  background: var(--accent, #10b981);
  opacity: 0.6;
}

.stat-card:hover {
  border-color: rgba(16, 185, 129, 0.25);
  box-shadow: 0 4px 24px rgba(16, 185, 129, 0.1);
}

.stat-icon-wrap {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.03);
  border-radius: var(--radius-md);
}

.stat-icon { font-size: 24px; }
.stat-info { flex: 1; }
.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}
.stat-label { font-size: 13px; color: var(--text-muted); }

.stat-trend {
  font-size: 12px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.03);
}

.stat-trend.up { color: #22c55e; }
.stat-trend.down { color: #ef4444; }

/* Features Section */
.features-section { margin-bottom: 32px; }
.section-header { margin-bottom: 20px; }
.section-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
}
.section-desc { font-size: 14px; color: var(--text-muted); margin: 0; }

.features-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.feature-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  cursor: pointer;
  position: relative;
  overflow: hidden;
}

.feature-card::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(135deg, transparent 0%, rgba(255, 255, 255, 0.02) 100%);
  pointer-events: none;
}

.feature-card:active {
  transform: scale(0.99);
}

.feature-icon {
  width: 52px;
  height: 52px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  flex-shrink: 0;
}

.feature-content { flex: 1; min-width: 0; }
.feature-content h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
}
.feature-content p {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.feature-arrow {
  color: var(--text-muted);
  opacity: 0;
  transform: translateX(-8px);
  transition: all var(--transition-fast);
}

.feature-card:hover .feature-arrow {
  opacity: 1;
  transform: translateX(0);
  color: #6ee7b7;
}

/* Recent Section */
.recent-section { margin-bottom: 32px; }
.section-header-inline {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.view-all-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: transparent;
  border: none;
  color: #6ee7b7;
  font-size: 13px;
  cursor: pointer;
  transition: color var(--transition-fast);
}

.view-all-btn:hover { color: #c7d2fe; }

/* Empty State */
.empty-state {
  text-align: center;
  padding: 56px 24px;
  background: var(--bg-card);
  border: 1px dashed var(--border-default);
  border-radius: var(--radius-lg);
}

.empty-illustration {
  position: relative;
  display: inline-block;
  margin-bottom: 16px;
}

.empty-icon {
  font-size: 48px;
  position: relative;
  z-index: 1;
}

.empty-pulse {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 80px;
  height: 80px;
  background: rgba(99, 102, 241, 0.1);
  border-radius: 50%;
}

.empty-state h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.empty-state p {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0 0 20px;
}

.btn-small { padding: 10px 20px; font-size: 14px; }

/* Recent List */
.recent-list { display: flex; flex-direction: column; gap: 8px; }

.recent-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
}

.recent-item .file-icon { font-size: 24px; }
.recent-item .file-info { flex: 1; min-width: 0; }
.recent-item .file-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.recent-item .file-time { font-size: 12px; color: var(--text-muted); }

.recent-item .file-category {
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-muted);
}

.recent-item .file-category.cat-课件 {
  background: rgba(99, 102, 241, 0.12);
  color: #6ee7b7;
}

.recent-item .file-category.cat-作业 {
  background: rgba(236, 72, 153, 0.12);
  color: #f9a8d4;
}

.recent-item .file-category.cat-考试通知 {
  background: rgba(239, 68, 68, 0.12);
  color: #fca5a5;
}

/* Tips Section */
.tips-section { margin-bottom: 24px; }
.tip-card {
  display: flex;
  gap: 16px;
  padding: 20px 24px;
  background: rgba(16, 185, 129, 0.05);
  border: 1px solid rgba(16, 185, 129, 0.15);
  border-radius: var(--radius-md);
}

.tip-card .tip-icon { font-size: 20px; }
.tip-card h4 {
  font-size: 14px;
  font-weight: 600;
  color: #34d399;
  margin: 0 0 4px;
}
.tip-card p {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
  line-height: 1.6;
}

/* Responsive */
@media (max-width: 1024px) {
  .welcome-hero {
    padding: 32px;
    flex-direction: column;
    text-align: center;
  }

  .hero-content {
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  .hero-subtitle { max-width: 100%; }
  .hero-decoration { display: none; }

  .stats-section { grid-template-columns: repeat(2, 1fr); }
  .features-grid { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 640px) {
  .hero-title { font-size: 28px; }
  .hero-actions { flex-direction: column; width: 100%; }
  .btn-primary, .btn-secondary { width: 100%; justify-content: center; }

  .stats-section { grid-template-columns: 1fr; }
  .features-grid { grid-template-columns: 1fr; }
}
</style>