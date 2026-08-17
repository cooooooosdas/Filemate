<template>
  <div
    class="app-shell"
    :class="{
      'sidebar-collapsed': sidebarCollapsed,
      'mobile-nav-open': mobileNavOpen
    }"
  >
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <button
      v-if="mobileNavOpen"
      class="mobile-backdrop"
      aria-label="关闭导航"
      @click="mobileNavOpen = false"
    />

    <aside class="sidebar" aria-label="主导航">
      <div class="sidebar-head">
        <router-link class="brand-link" to="/" @click="mobileNavOpen = false">
          <Logo />
        </router-link>
        <button
          class="icon-button collapse-button"
          :aria-label="sidebarCollapsed ? '展开侧栏' : '收起侧栏'"
          @click="sidebarCollapsed = !sidebarCollapsed"
        >
          <el-icon><Fold v-if="!sidebarCollapsed" /><Expand v-else /></el-icon>
        </button>
      </div>

      <div class="service-state" :class="{ online: backendConnected }" aria-live="polite">
        <span class="state-indicator" />
        <div class="state-copy">
          <strong>{{ backendConnected ? '本地服务已连接' : '本地服务未连接' }}</strong>
          <span>{{ backendConnected ? '资料仅在本机处理' : '正在等待 Sidecar 启动' }}</span>
        </div>
      </div>

      <nav class="nav-groups">
        <section v-for="group in menuGroups" :key="group.label" class="nav-group">
          <p class="nav-group-label">{{ group.label }}</p>
          <router-link
            v-for="item in group.items"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            @click="mobileNavOpen = false"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.title }}</span>
            <span v-if="item.badge" class="nav-badge">{{ item.badge }}</span>
          </router-link>
        </section>
      </nav>

      <div class="sidebar-foot">
        <div class="today-summary">
          <el-icon><DataLine /></el-icon>
          <span>今日处理</span>
          <strong>{{ todayCount }}</strong>
        </div>
        <span class="version-label">v1.2</span>
      </div>
    </aside>

    <main id="main-content" class="workspace" tabindex="-1">
      <header class="topbar">
        <div class="topbar-title">
          <button
            class="icon-button mobile-menu-button"
            aria-label="打开导航"
            @click="mobileNavOpen = true"
          >
            <el-icon><Menu /></el-icon>
          </button>
          <div>
            <p>FileMate / {{ pageTitle }}</p>
            <h1>{{ pageTitle }}</h1>
          </div>
        </div>

        <div class="topbar-actions">
          <button
            class="icon-button"
            :class="{ spinning: refreshing }"
            aria-label="刷新当前页面"
            title="刷新当前页面"
            @click="refreshPage"
          >
            <el-icon><Refresh /></el-icon>
          </button>
          <button
            class="icon-button desktop-only"
            aria-label="切换全屏"
            title="切换全屏"
            @click="toggleFullscreen"
          >
            <el-icon><FullScreen /></el-icon>
          </button>
          <button
            class="icon-button"
            aria-label="打开设置"
            title="设置"
            @click="showSettings = true"
          >
            <el-icon><Setting /></el-icon>
          </button>
          <div class="avatar" aria-label="FileMate 本地用户">FM</div>
        </div>
      </header>

      <div class="content-scroll">
        <router-view v-slot="{ Component }">
          <transition name="page-fade" mode="out-in">
            <component :is="Component" :key="`${$route.fullPath}-${refreshToken}`" />
          </transition>
        </router-view>
      </div>
    </main>

    <el-dialog v-model="showSettings" title="应用设置" width="min(480px, calc(100vw - 32px))">
      <div class="settings-list">
        <div class="setting-row">
          <el-icon><Monitor /></el-icon>
          <div>
            <strong>显示模式</strong>
            <span>当前使用自然绿浅色工作台</span>
          </div>
          <el-tag effect="plain">浅色</el-tag>
        </div>
        <div class="setting-row">
          <el-icon><Lock /></el-icon>
          <div>
            <strong>数据边界</strong>
            <span>学习资料与执行记录默认保存在本机</span>
          </div>
          <el-tag type="success" effect="plain">本地优先</el-tag>
        </div>
        <div class="setting-row">
          <el-icon><Connection /></el-icon>
          <div>
            <strong>服务状态</strong>
            <span>{{ backendConnected ? 'FastAPI Sidecar 运行正常' : 'Sidecar 暂未连接' }}</span>
          </div>
          <el-tag :type="backendConnected ? 'success' : 'danger'" effect="plain">
            {{ backendConnected ? '在线' : '离线' }}
          </el-tag>
        </div>
      </div>
      <template #footer>
        <el-button @click="showSettings = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Calendar,
  Clock,
  Collection,
  Connection,
  DataLine,
  DocumentAdd,
  Edit,
  Expand,
  Fold,
  FullScreen,
  House,
  Lock,
  MagicStick,
  Menu,
  Monitor,
  Reading,
  Refresh,
  Setting,
  Tickets,
  Microphone,
  DataAnalysis,
  FolderOpened
} from '@element-plus/icons-vue'
import Logo from './components/Logo.vue'
import { checkHealth, getHistory } from './services/api'

const route = useRoute()
const sidebarCollapsed = ref(false)
const mobileNavOpen = ref(false)
const showSettings = ref(false)
const backendConnected = ref(false)
const todayCount = ref(0)
const refreshing = ref(false)
const refreshToken = ref(0)

const menuGroups = [
  {
    label: '总览',
    items: [
      { path: '/', title: '学习工作台', icon: House },
      { path: '/today', title: '今日学习', icon: DataLine, badge: '推荐' }
    ]
  },
  {
    label: '学习资产',
    items: [
      { path: '/import', title: '导入资料', icon: DocumentAdd },
      { path: '/knowledge', title: '个人知识库', icon: FolderOpened },
      { path: '/classification', title: '分类确认', icon: Collection },
      { path: '/naming', title: '命名确认', icon: Edit },
      { path: '/schedule', title: '学习日程', icon: Calendar },
      { path: '/history', title: '处理记录', icon: Clock }
    ]
  },
  {
    label: '学习智能',
    items: [
      { path: '/ai-tools', title: '资料理解', icon: MagicStick, badge: '可用' },
      { path: '/study-plan', title: '学习计划', icon: Reading },
      { path: '/wrongbook', title: '错题复盘', icon: Tickets, badge: '新' },
      { path: '/interview', title: '模拟面试', icon: Microphone, badge: 'Beta' },
      { path: '/growth', title: '成长数据', icon: DataAnalysis }
    ]
  }
]

const pageTitle = computed(() => String(route.meta.title || '学习工作台'))

async function loadShellState(): Promise<void> {
  try {
    backendConnected.value = await checkHealth()
    const sessions = await getHistory(undefined, 100)
    const today = new Date().toDateString()
    todayCount.value = sessions.filter(
      item => new Date(item.created_at).toDateString() === today
    ).length
  } catch {
    backendConnected.value = false
    todayCount.value = 0
  }
}

async function refreshPage(): Promise<void> {
  refreshing.value = true
  await loadShellState()
  refreshToken.value += 1
  window.setTimeout(() => {
    refreshing.value = false
  }, 220)
  ElMessage.success('工作台已刷新')
}

async function toggleFullscreen(): Promise<void> {
  try {
    if (document.fullscreenElement) {
      await document.exitFullscreen()
    } else {
      await document.documentElement.requestFullscreen()
    }
  } catch {
    ElMessage.warning('当前环境不支持全屏切换')
  }
}

onMounted(loadShellState)
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
  color: var(--text-primary);
  background: var(--bg-base);
  transition: grid-template-columns var(--motion-panel);
}

.app-shell.sidebar-collapsed {
  grid-template-columns: var(--sidebar-width-collapsed) minmax(0, 1fr);
}

.sidebar {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #eef5ef;
  border-right: 1px solid var(--border-subtle);
  z-index: var(--z-sidebar);
}

.sidebar-head {
  min-height: 76px;
  padding: 16px 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.brand-link {
  min-width: 0;
  flex: 1;
  color: inherit;
  text-decoration: none;
}

.icon-button {
  width: 44px;
  height: 44px;
  flex: 0 0 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-control);
  cursor: pointer;
  transition: color var(--motion-fast), background var(--motion-fast), border-color var(--motion-fast);
}

.icon-button:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
  border-color: var(--border-strong);
}

.service-state {
  min-height: 62px;
  margin: 14px 12px 8px;
  padding: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-panel);
}

.state-indicator {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: var(--danger);
}

.service-state.online .state-indicator {
  background: var(--success);
}

.state-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.state-copy strong {
  font-size: 12px;
  font-weight: 600;
}

.state-copy span {
  color: var(--text-muted);
  font-size: 11px;
  white-space: nowrap;
}

.nav-groups {
  flex: 1;
  padding: 8px 10px 16px;
  overflow-y: auto;
}

.nav-group + .nav-group {
  margin-top: 18px;
}

.nav-group-label {
  margin: 0 10px 7px;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
}

.nav-item {
  min-height: 44px;
  margin-bottom: 3px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--text-secondary);
  border: 1px solid transparent;
  border-radius: var(--radius-control);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  transition: color var(--motion-fast), background var(--motion-fast), border-color var(--motion-fast);
}

.nav-item:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.nav-item.router-link-active {
  color: var(--accent);
  background: var(--accent-soft);
  border-color: var(--accent-border);
}

.nav-item .el-icon {
  flex: 0 0 20px;
  font-size: 20px;
}

.nav-item > span:not(.nav-badge) {
  min-width: 0;
  flex: 1;
  white-space: nowrap;
}

.nav-badge {
  padding: 2px 6px;
  color: var(--accent);
  background: var(--accent-soft);
  border-radius: 5px;
  font-size: 10px;
  font-weight: 600;
}

.sidebar-foot {
  min-height: 62px;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid var(--border-subtle);
}

.today-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-muted);
  font-size: 12px;
}

.today-summary strong {
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.version-label {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 11px;
}

.workspace {
  min-width: 0;
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.topbar {
  min-height: var(--topbar-height);
  padding: 0 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  background: rgba(255, 255, 255, 0.92);
  border-bottom: 1px solid var(--border-subtle);
  z-index: var(--z-sticky);
}

.topbar-title {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.topbar-title p {
  margin: 0 0 3px;
  color: var(--text-muted);
  font-size: 11px;
}

.topbar-title h1 {
  margin: 0;
  font-size: 19px;
  line-height: 1.2;
  font-weight: 650;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.avatar {
  width: 38px;
  height: 38px;
  margin-left: 4px;
  display: grid;
  place-items: center;
  color: #ffffff;
  background: var(--accent);
  border-radius: 10px;
  font-size: 12px;
  font-weight: 800;
}

.content-scroll {
  flex: 1;
  min-height: 0;
  padding: 28px 32px 40px;
  overflow: auto;
}

.settings-list {
  display: grid;
  gap: 4px;
}

.setting-row {
  min-height: 72px;
  padding: 12px;
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.setting-row:last-child {
  border-bottom: 0;
}

.setting-row > .el-icon {
  color: var(--accent);
  font-size: 20px;
}

.setting-row div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.setting-row strong {
  font-size: 14px;
}

.setting-row span {
  color: var(--text-muted);
  font-size: 12px;
}

.sidebar-collapsed .sidebar-head {
  justify-content: center;
  padding-inline: 10px;
}

.sidebar-collapsed .brand-link,
.sidebar-collapsed .service-state,
.sidebar-collapsed .nav-group-label,
.sidebar-collapsed .nav-item > span,
.sidebar-collapsed .sidebar-foot {
  display: none;
}

.sidebar-collapsed .nav-groups {
  padding-inline: 9px;
}

.sidebar-collapsed .nav-group + .nav-group {
  margin-top: 12px;
}

.sidebar-collapsed .nav-item {
  justify-content: center;
  padding: 0;
}

.mobile-menu-button,
.mobile-backdrop {
  display: none;
}

.spinning {
  animation: spin 600ms linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity var(--motion-panel), transform var(--motion-panel);
}

.page-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.page-fade-leave-to {
  opacity: 0;
}

@media (max-width: 900px) {
  .app-shell,
  .app-shell.sidebar-collapsed {
    display: block;
  }

  .sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    width: min(var(--sidebar-width), calc(100vw - 48px));
    visibility: hidden;
    pointer-events: none;
    transform: translateX(-100%);
    transition: transform var(--motion-panel), visibility 0s linear 240ms;
  }

  .mobile-nav-open .sidebar {
    visibility: visible;
    pointer-events: auto;
    transform: translateX(0);
    transition-delay: 0s;
  }

  .mobile-backdrop {
    position: fixed;
    inset: 0;
    display: block;
    width: 100%;
    height: 100%;
    padding: 0;
    background: rgba(0, 0, 0, 0.58);
    border: 0;
    z-index: calc(var(--z-sidebar) - 1);
  }

  .mobile-menu-button {
    display: inline-flex;
  }

  .collapse-button {
    display: none;
  }

  .content-scroll {
    padding: 22px 20px 36px;
  }
}

@media (max-width: 560px) {
  .topbar {
    padding: 0 14px;
  }

  .topbar-title p,
  .desktop-only,
  .avatar {
    display: none;
  }

  .topbar-actions {
    gap: 5px;
  }

  .content-scroll {
    padding: 18px 14px 28px;
  }
}
</style>
