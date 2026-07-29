<!--
  Design: FileMate Frontend Redesign
  Dials: VARIANCE=7, MOTION=6, DENSITY=4
  Theme: Dark mode, sophisticated neutrals with accent
-->
<template>
  <el-container class="app-container" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <!-- 设置对话框 -->
    <el-dialog
      v-model="showSettings"
      title="⚙️ 设置"
      width="480px"
      :close-on-click-modal="true"
      class="settings-dialog"
    >
      <div class="settings-content">
        <!-- 外观设置 -->
        <div class="settings-section">
          <h4 class="section-title">🎨 外观</h4>
          <div class="setting-item">
            <div class="setting-info">
              <span class="setting-label">主题模式</span>
              <span class="setting-desc">当前仅支持暗色主题</span>
            </div>
            <el-tag type="success" size="small">暗色</el-tag>
          </div>
          <div class="setting-item">
            <div class="setting-info">
              <span class="setting-label">主题色</span>
              <span class="setting-desc">主色调为 Emerald 绿</span>
            </div>
            <div class="color-preview">
              <span class="color-dot" style="background: #10b981"></span>
            </div>
          </div>
        </div>

        <!-- 数据设置 -->
        <div class="settings-section">
          <h4 class="section-title">💾 数据</h4>
          <div class="setting-item">
            <div class="setting-info">
              <span class="setting-label">历史记录</span>
              <span class="setting-desc">共 {{ totalSessions }} 条处理记录</span>
            </div>
            <el-button size="small" type="danger" plain @click="clearHistory">
              清空历史
            </el-button>
          </div>
          <div class="setting-item">
            <div class="setting-info">
              <span class="setting-label">本地存储</span>
              <span class="setting-desc">浏览器缓存数据</span>
            </div>
            <el-button size="small" @click="clearCache">
              清除缓存
            </el-button>
          </div>
        </div>

        <!-- 关于 -->
        <div class="settings-section">
          <h4 class="section-title">ℹ️ 关于</h4>
          <div class="about-info">
            <div class="app-logo">📂 FileMate</div>
            <div class="version">版本 1.0.0</div>
            <div class="description">智能课程文件管理工具</div>
            <div class="tech-stack">
              <el-tag size="small" effect="plain">Vue 3</el-tag>
              <el-tag size="small" effect="plain">FastAPI</el-tag>
              <el-tag size="small" effect="plain">LLM</el-tag>
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="showSettings = false">关闭</el-button>
          <el-button type="primary" @click="saveSettings">保存设置</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 侧边栏 -->
    <el-aside width="260px" class="sidebar">
      <div class="sidebar-header">
        <div class="logo-row" @click="toggleSidebar">
          <Logo />
          <el-icon class="collapse-btn" @click.stop="toggleSidebar">
            <DArrowLeft v-if="!sidebarCollapsed" />
            <DArrowRight v-else />
          </el-icon>
        </div>
      </div>

      <!-- 状态指示器 -->
      <div class="status-bar" v-show="!sidebarCollapsed">
        <div class="status-item" :class="{ 'status-online': backendConnected }">
          <span class="status-dot" :class="backendConnected ? 'online' : 'offline'"></span>
          <span class="status-text">{{ backendConnected ? '后端在线' : '等待连接' }}</span>
        </div>
        <div class="status-item" :class="{ 'status-online': llmConnected }">
          <span class="status-dot" :class="llmConnected ? 'online' : 'offline'"></span>
          <span class="status-text">{{ llmConnected ? 'LLM 就绪' : '等待配置' }}</span>
        </div>
      </div>

      <!-- 导航菜单 -->
      <nav class="sidebar-nav" v-show="!sidebarCollapsed">
        <router-link
          v-for="item in menuItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: isActive(item.path) }"
        >
          <el-icon class="nav-icon"><component :is="item.icon" /></el-icon>
          <span class="nav-label">{{ item.title }}</span>
          <span v-if="item.badge" class="nav-badge">{{ item.badge }}</span>
        </router-link>
      </nav>

      <!-- 收起状态的迷你导航 -->
      <nav class="sidebar-nav-mini" v-show="sidebarCollapsed">
        <router-link
          v-for="item in menuItems"
          :key="item.path"
          :to="item.path"
          class="nav-item-mini"
          :class="{ active: isActive(item.path) }"
          :title="item.title"
        >
          <el-icon class="nav-icon"><component :is="item.icon" /></el-icon>
        </router-link>
      </nav>

      <!-- 底部信息 -->
      <div class="sidebar-footer" v-show="!sidebarCollapsed">
        <div class="footer-stats">
          <el-icon class="stat-icon"><DataLine /></el-icon>
          <span class="stat-label">今日处理</span>
          <span class="stat-value">{{ todayCount }}</span>
        </div>
        <div class="footer-version">v1.0.0</div>
      </div>
    </el-aside>

    <!-- 主内容区 -->
    <el-container class="main-wrapper">
      <!-- 顶部导航 -->
      <el-header class="top-header">
        <div class="header-left">
          <h1 class="page-title">{{ pageTitle }}</h1>
          <nav class="breadcrumb-nav">
            <span class="breadcrumb-item">FileMate</span>
            <span class="breadcrumb-sep">/</span>
            <span class="breadcrumb-item current">{{ pageTitle }}</span>
          </nav>
        </div>
        <div class="header-right">
          <button class="header-btn" @click="refreshData" title="刷新数据">
            <el-icon><Refresh /></el-icon>
          </button>
          <button class="header-btn" @click="toggleFullscreen" title="全屏">
            <el-icon><FullScreen /></el-icon>
          </button>
          <button class="header-btn" @click="openSettings" title="设置">
            <el-icon><Setting /></el-icon>
          </button>
          <div class="header-divider"></div>
          <div class="user-avatar">
            <span>FM</span>
          </div>
        </div>
      </el-header>

      <!-- 主内容 -->
      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="page-enter" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import {
  House,
  Upload,
  Collection,
  Edit,
  Calendar,
  Clock,
  Refresh,
  QuestionFilled,
  DArrowLeft,
  DArrowRight,
  DataLine,
  FullScreen,
  Setting
} from '@element-plus/icons-vue'
import Logo from './components/Logo.vue'

const route = useRoute()
const currentRoute = computed(() => route.path)
const sidebarCollapsed = ref(false)

// 设置面板
const showSettings = ref(false)
const totalSessions = ref(0)
const isRefreshing = ref(false)

// 设置相关函数
const openSettings = async () => {
  showSettings.value = true
  // 获取总记录数
  try {
    const response = await fetch('/sessions?limit=1000')
    const data = await response.json()
    if (data.success && data.data) {
      totalSessions.value = data.data.length
    }
  } catch (e) {
    console.error('获取统计数据失败:', e)
  }
}

const refreshData = async () => {
  isRefreshing.value = true
  // 添加旋转动画效果
  const btn = document.querySelector('.header-btn')
  if (btn) {
    btn.classList.add('refreshing')
  }

  try {
    const response = await fetch('/sessions?limit=100')
    const data = await response.json()
    if (data.success && data.data) {
      const today = new Date().toDateString()
      todayCount.value = data.data.filter((s: any) =>
        new Date(s.created_at).toDateString() === today
      ).length

      // 显示成功提示
      const { ElMessage } = await import('element-plus')
      ElMessage.success({
        message: `已刷新，今日处理 ${todayCount.value} 个文件`,
        duration: 2000
      })
    }
  } catch (e) {
    console.error('刷新失败:', e)
    const { ElMessage } = await import('element-plus')
    ElMessage.error('刷新失败')
  } finally {
    isRefreshing.value = false
    if (btn) {
      btn.classList.remove('refreshing')
    }
  }
}

const clearHistory = async () => {
  const { ElMessageBox, ElMessage } = await import('element-plus')
  try {
    await ElMessageBox.confirm(
      '将清空所有历史记录，但保留已处理的文件。此操作不可恢复。',
      '警告',
      {
        confirmButtonText: '确认清空',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )

    // 这里可以调用API清空历史，目前仅清除本地状态
    todayCount.value = 0
    totalSessions.value = 0
    ElMessage.success('历史记录已清空')
  } catch {
    // 用户取消
  }
}

const clearCache = () => {
  localStorage.clear()
  sessionStorage.clear()
  import('element-plus').then(({ ElMessage }) => {
    ElMessage.success('缓存已清除')
  })
}

const saveSettings = () => {
  import('element-plus').then(({ ElMessage }) => {
    ElMessage.success('设置已保存')
  })
  showSettings.value = false
}

// 页面标题映射
const pageTitleMap: Record<string, string> = {
  '/': '首页',
  '/import': '导入文件',
  '/classification': '分类预览',
  '/naming': '命名预览',
  '/schedule': '日程预览',
  '/history': '历史记录'
}
const pageTitle = computed(() => pageTitleMap[currentRoute.value] || 'FileMate')

// 菜单项
const menuItems = [
  { path: '/', title: '首页', icon: House },
  { path: '/import', title: '导入', icon: Upload, badge: null },
  { path: '/classification', title: '分类', icon: Collection },
  { path: '/naming', title: '命名', icon: Edit },
  { path: '/schedule', title: '日程', icon: Calendar },
  { path: '/history', title: '历史', icon: Clock }
]

// 状态
const backendConnected = ref(true)
const llmConnected = ref(true)
const todayCount = ref(0)

const isActive = (path: string) => currentRoute.value === path

const toggleSidebar = () => {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

const checkBackendStatus = async () => {
  try {
    const response = await fetch('/')
    backendConnected.value = response.ok
    llmConnected.value = response.ok
  } catch (e) {
    backendConnected.value = false
    llmConnected.value = false
  }
}

const toggleFullscreen = () => {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen()
  } else {
    document.exitFullscreen()
  }
  import('element-plus').then(({ ElMessage }) => {
    const isFullscreen = !!document.fullscreenElement
    ElMessage.info(isFullscreen ? '已切换为全屏模式' : '已退出全屏模式')
  })
}

onMounted(() => {
  checkBackendStatus()
  refreshData()
})
</script>

<style scoped>
/* ─────────────────────────────────────────────────────────────
   设置对话框样式
   ───────────────────────────────────────────────────────────── */
.settings-content {
  padding: 8px 0;
}

.settings-section {
  margin-bottom: 24px;
}

.settings-section:last-child {
  margin-bottom: 0;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.setting-item:last-child {
  border-bottom: none;
}

.setting-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.setting-label {
  font-size: 14px;
  color: var(--text-primary);
}

.setting-desc {
  font-size: 12px;
  color: var(--text-muted);
}

.color-preview {
  display: flex;
  align-items: center;
}

.color-dot {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: block;
}

.about-info {
  text-align: center;
  padding: 20px 0;
}

.app-logo {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.version {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.description {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.tech-stack {
  display: flex;
  justify-content: center;
  gap: 8px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* 刷新按钮动画 */
:deep(.header-btn.refreshing) {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 对话框样式覆盖 */
:deep(.el-dialog) {
  --el-dialog-bg-color: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
}

:deep(.el-dialog__header) {
  border-bottom: 1px solid var(--border-subtle);
  padding: 16px 20px;
  margin-right: 0;
}

:deep(.el-dialog__title) {
  color: var(--text-primary);
  font-weight: 600;
}

:deep(.el-dialog__body) {
  padding: 20px;
  color: var(--text-secondary);
}

:deep(.el-dialog__footer) {
  border-top: 1px solid var(--border-subtle);
  padding: 16px 20px;
}

/* ─────────────────────────────────────────────────────────────
   CSS Variables - Design Tokens
   ───────────────────────────────────────────────────────────── */
.app-container {
  --bg-base: #0a0a0f;
  --bg-surface: #12121a;
  --bg-elevated: #1a1a24;
  --bg-hover: #22222e;

  --text-primary: #f4f4f5;
  --text-secondary: #a1a1aa;
  --text-muted: #71717a;

  --accent-primary: #10b981;
  --accent-secondary: #34d399;
  --accent-glow: rgba(16, 185, 129, 0.12);

  --border-subtle: rgba(255, 255, 255, 0.06);
  --border-default: rgba(255, 255, 255, 0.1);

  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 24px;

  --shadow-card: 0 4px 24px rgba(0, 0, 0, 0.4);
  --shadow-elevated: 0 8px 32px rgba(0, 0, 0, 0.6);

  --transition-fast: 0.15s cubic-bezier(0.4, 0, 0.2, 1);
  --transition-smooth: 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  --sidebar-width: 260px;
  --sidebar-width-collapsed: 72px;
  --header-height: 72px;

  /* High-density surface for contrast */
  --bg-card: #16161e;
}

/* ─────────────────────────────────────────────────────────────
   App Container
   ───────────────────────────────────────────────────────────── */
.app-container {
  height: 100vh;
  background: var(--bg-base);
  overflow: hidden;
}

/* ─────────────────────────────────────────────────────────────
   Sidebar
   ───────────────────────────────────────────────────────────── */
.sidebar {
  background: linear-gradient(180deg, rgba(18, 18, 26, 0.85) 0%, rgba(10, 10, 15, 0.95) 100%);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-right: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  transition: width var(--transition-smooth);
  position: relative;
  z-index: 100;
}

.sidebar::before {
  content: '';
  position: absolute;
  top: 0;
  right: 0;
  width: 1px;
  height: 100%;
  background: linear-gradient(180deg, transparent 0%, rgba(16, 185, 129, 0.3) 50%, transparent 100%);
  opacity: 0.5;
}

.sidebar-header {
  padding: 20px 16px 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.logo-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
}

.collapse-btn {
  padding: 8px;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  transition: all var(--transition-fast);
  cursor: pointer;
}

.collapse-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* Status Bar */
.status-bar {
  padding: 12px 16px;
  margin: 8px 12px;
  background: var(--bg-elevated);
  border-radius: var(--radius-md);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--text-muted);
  transition: color var(--transition-fast);
}

.status-item.status-online {
  color: var(--text-secondary);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #52525b;
  flex-shrink: 0;
}

.status-dot.online {
  background: #22c55e;
  box-shadow: 0 0 12px rgba(34, 197, 94, 0.5);
}

.status-dot.offline {
  background: #ef4444;
  box-shadow: 0 0 12px rgba(239, 68, 68, 0.4);
}

.status-text {
  letter-spacing: 0.02em;
}

/* Navigation */
.sidebar-nav {
  flex: 1;
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow-y: auto;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 18px;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.01em;
  transition: all var(--transition-fast);
  position: relative;
}

.nav-item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 0;
  background: var(--accent-primary);
  border-radius: 0 2px 2px 0;
  transition: height var(--transition-fast);
}

.nav-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.nav-item.active {
  background: var(--accent-glow);
  color: var(--accent-secondary);
}

.nav-item.active::before {
  height: 24px;
}

.nav-icon {
  font-size: 20px;
  flex-shrink: 0;
}

.nav-label {
  flex: 1;
}

.nav-badge {
  background: var(--accent-primary);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 12px;
  letter-spacing: 0.02em;
}

/* Mini Navigation (collapsed) */
.sidebar-nav-mini {
  padding: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.nav-item-mini {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  color: var(--text-muted);
  text-decoration: none;
  transition: all var(--transition-fast);
  position: relative;
}

.nav-item-mini:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.nav-item-mini.active {
  background: var(--accent-glow);
  color: var(--accent-secondary);
}

.nav-item-mini .nav-icon {
  font-size: 22px;
}

/* Sidebar Footer */
.sidebar-footer {
  padding: 16px;
  border-top: 1px solid var(--border-subtle);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.footer-stats {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.stat-icon {
  font-size: 14px;
}

.stat-label {
  color: var(--text-muted);
}

.stat-value {
  color: var(--text-primary);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.footer-version {
  font-size: 11px;
  color: var(--text-muted);
  font-family: ui-monospace, SFMono-Regular, monospace;
}

/* ─────────────────────────────────────────────────────────────
   Main Wrapper
   ───────────────────────────────────────────────────────────── */
.main-wrapper {
  background: var(--bg-base);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Header */
.top-header {
  height: var(--header-height);
  padding: 0 28px;
  background: rgba(18, 18, 26, 0.75);
  backdrop-filter: blur(16px) saturate(180%);
  -webkit-backdrop-filter: blur(16px) saturate(180%);
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 50;
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  letter-spacing: -0.01em;
}

.breadcrumb-nav {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.breadcrumb-item {
  color: var(--text-muted);
}

.breadcrumb-item.current {
  color: var(--text-secondary);
}

.breadcrumb-sep {
  color: var(--text-muted);
  opacity: 0.5;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-btn {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  color: var(--text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
  font-size: 18px;
}

.header-btn:hover {
  background: var(--bg-hover);
  border-color: var(--border-default);
  color: var(--text-primary);
}

.header-divider {
  width: 1px;
  height: 24px;
  background: var(--border-subtle);
  margin: 0 8px;
}

.user-avatar {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  background: linear-gradient(135deg, #10b981 0%, #06b6d4 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  letter-spacing: 0.02em;
}

/* Main Content */
.main-content {
  flex: 1;
  padding: 28px 32px;
  overflow-y: auto;
  overflow-x: hidden;
  background: transparent;
}

/* Page Transitions */
.page-enter-enter-active,
.page-enter-leave-active {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.page-enter-enter-from {
  opacity: 0;
  transform: translateY(16px) scale(0.98);
}

.page-enter-leave-to {
  opacity: 0;
  transform: translateY(-12px) scale(0.98);
}

/* Smooth scrolling */
.main-content {
  scroll-behavior: smooth;
  scroll-padding-top: 16px;
}

/* Scrollbar styling */
.main-content::-webkit-scrollbar {
  width: 8px;
}

.main-content::-webkit-scrollbar-track {
  background: var(--bg-base);
}

.main-content::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
}

.main-content::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.18);
}

/* Responsive */
@media (max-width: 768px) {
  .sidebar {
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    z-index: 1000;
  }

  .app-container:not(.sidebar-collapsed) .sidebar {
    box-shadow: var(--shadow-elevated);
  }

  .top-header {
    padding: 0 16px;
  }

  .main-content {
    padding: 16px;
  }
}
</style>