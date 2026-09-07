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
      @click="closeMobileNav"
    />

    <aside id="main-navigation" class="sidebar" aria-label="主导航" @keydown.esc="closeMobileNav" @keydown.tab="trapMobileFocus">
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

      <nav class="nav-groups">
        <section v-for="group in menuGroups" :key="group.label" class="nav-group">
          <p class="nav-group-label">{{ group.label }}</p>
          <router-link
            v-for="item in group.items"
            :key="item.path"
            :to="item.path"
            :title="item.title"
            :aria-label="item.title"
            class="nav-item"
            @click="mobileNavOpen = false"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.title }}</span>
          </router-link>
        </section>
      </nav>

      <div class="sidebar-foot">
        <div class="service-state" :class="{ online: backendConnected, checking: backendConnected === null }" aria-live="polite">
          <span class="state-indicator" />
          <span>{{ backendConnected === null ? '正在连接…' : backendConnected ? '服务已连接' : '服务未连接' }}</span>
        </div>
        <button class="version-label" title="应用设置" aria-label="打开应用设置" @click="showSettings = true">v1.3 α</button>
      </div>
    </aside>

    <main id="main-content" class="workspace" tabindex="-1">
      <div v-if="backendConnected === false" class="service-banner" role="alert">
        <el-icon><Connection /></el-icon>
        <div>
          <strong>本地服务尚未连接</strong>
          <span>请运行 <code>scripts/dev.ps1</code>，启动后可导入、检索和保存学习资料。</span>
        </div>
        <button type="button" :disabled="serviceChecking" @click="loadShellState">
          {{ serviceChecking ? '检查中…' : '重新检查' }}
        </button>
      </div>

      <header class="topbar">
        <div class="topbar-title">
          <button
            ref="mobileMenuButton"
            class="icon-button mobile-menu-button"
            aria-label="打开导航"
            :aria-expanded="mobileNavOpen"
            aria-controls="main-navigation"
            @click="openMobileNav"
          >
            <el-icon><Menu /></el-icon>
          </button>
          <div>
            <span class="workspace-label">我的空间</span><span class="breadcrumb-divider" aria-hidden="true">/</span><span class="page-title">{{ pageTitle }}</span>
          </div>
        </div>

        <div class="topbar-actions">
          <button class="finder-trigger" aria-label="查找功能" @click="showFinder = true"><el-icon><Search /></el-icon><span>查找功能</span><kbd>Ctrl K</kbd></button>
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
          <div class="avatar" aria-label="FileMate 学习伙伴">
            <img src="./assets/filemate-mascot.png" alt="" aria-hidden="true" />
          </div>
        </div>
      </header>

      <div class="content-scroll">
        <router-view v-slot="{ Component }">
          <transition name="page-fade" mode="out-in">
            <component :is="Component" :key="`${$route.path === '/ai-tools' ? $route.path : $route.fullPath}-${refreshToken}`" />
          </transition>
        </router-view>
      </div>
    </main>

    <el-dialog v-model="showSettings" title="应用设置" width="min(660px, calc(100vw - 32px))">
      <div class="settings-list">
        <div class="setting-row">
          <el-icon><Monitor /></el-icon>
          <div>
            <strong>显示模式</strong>
            <span>浅色背景与自然绿强调色</span>
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
            <span>{{ backendConnected ? '可以导入、查看和保存资料' : '请启动服务后重新连接' }}</span>
          </div>
          <el-tag :type="backendConnected ? 'success' : 'danger'" effect="plain">
            {{ backendConnected ? '在线' : '离线' }}
          </el-tag>
        </div>
      </div>
      <LLMSettingsPanel :backend-connected="backendConnected" />
      <template #footer>
        <el-button @click="showSettings = false">关闭</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="showFinder" title="查找功能" width="min(520px, calc(100vw - 32px))" @opened="finderInput?.focus()" @closed="finderQuery = ''">
      <div class="finder">
        <label class="finder-input"><el-icon><Search /></el-icon><input ref="finderInput" v-model="finderQuery" aria-label="输入功能名称" placeholder="试试：面试、资料、计划…" @keydown.enter.prevent="openFirstResult" /></label>
        <nav class="finder-results" aria-label="功能查找结果"><router-link v-for="item in finderResults" :key="item.path" :to="item.path" @click="showFinder = false"><el-icon><component :is="item.icon" /></el-icon><span>{{ item.title }}</span><small>{{ item.group }}</small></router-link></nav>
        <p v-if="!finderResults.length" class="finder-empty" role="status">没有找到这个功能，换个关键词试试。</p>
        <p class="finder-hint">Enter 打开第一项 · Esc 关闭</p>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
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
  Menu,
  Monitor,
  Notebook,
  Reading,
  Refresh,
  Setting,
  Tickets,
  Microphone,
  DataAnalysis,
  FolderOpened,
  Aim,
  Search
} from '@element-plus/icons-vue'
import Logo from './components/Logo.vue'
import LLMSettingsPanel from './components/LLMSettingsPanel.vue'
import { checkHealth } from './services/api'

const route = useRoute()
const router = useRouter()
const sidebarCollapsed = ref(false)
const mobileNavOpen = ref(false)
const showSettings = ref(false)
const backendConnected = ref<boolean | null>(null)
const serviceChecking = ref(false)
const refreshing = ref(false)
const refreshToken = ref(0)
const showFinder = ref(false)
const finderQuery = ref('')
const finderInput = ref<HTMLInputElement | null>(null)
const mobileMenuButton = ref<HTMLButtonElement | null>(null)
let refreshTimer: number | undefined

const menuGroups = [
  {
    label: '工作空间',
    items: [
      { path: '/', title: '学习工作台', icon: House },
      { path: '/today', title: '今日学习', icon: DataLine },
      { path: '/schedule', title: '学习日程', icon: Calendar }
    ]
  },
  {
    label: '资料管理',
    items: [
      { path: '/import', title: '导入资料', icon: DocumentAdd },
      { path: '/knowledge', title: '个人知识库', icon: FolderOpened },
      { path: '/classification', title: '分类确认', icon: Collection },
      { path: '/naming', title: '命名确认', icon: Edit },
      { path: '/history', title: '处理记录', icon: Clock }
    ]
  },
  {
    label: '学习与练习',
    items: [
      { path: '/ai-tools', title: '学习工作区', icon: Reading },
      { path: '/study-plan', title: '学习计划', icon: Reading },
      { path: '/goals', title: '目标反推', icon: Aim },
      { path: '/wrongbook', title: '错题复盘', icon: Tickets },
      { path: '/interview', title: '模拟面试', icon: Microphone },
      { path: '/interview-bank', title: '题库管理', icon: Notebook },
      { path: '/growth', title: '成长数据', icon: DataAnalysis },
      { path: '/trust', title: '可信与隐私', icon: Lock }
    ]
  }
]

const pageTitle = computed(() => String(route.meta.title || '学习工作台'))
const finderResults = computed(() => menuGroups.flatMap(group => group.items.map(item => ({ ...item, group: group.label }))).filter(item => item.title.includes(finderQuery.value.trim())))

function openFirstResult(): void {
  const first = finderResults.value[0]
  if (first) { showFinder.value = false; void router.push(first.path) }
}
async function openMobileNav(): Promise<void> {
  mobileNavOpen.value = true
  await nextTick()
  document.querySelector<HTMLAnchorElement>('.sidebar .brand-link')?.focus()
}
function closeMobileNav(): void { mobileNavOpen.value = false; mobileMenuButton.value?.focus() }
function trapMobileFocus(event: KeyboardEvent): void {
  if (!mobileNavOpen.value) return
  const links = Array.from(document.querySelectorAll<HTMLElement>('.sidebar a, .sidebar button')).filter(item => item.getClientRects().length)
  const first = links[0], last = links[links.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
function handleShortcut(event: KeyboardEvent): void {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); mobileNavOpen.value = false; showFinder.value = !showFinder.value }
}
watch(() => route.fullPath, () => { mobileNavOpen.value = false })

async function loadShellState(): Promise<void> {
  serviceChecking.value = true
  try {
    backendConnected.value = await checkHealth()
  } catch {
    backendConnected.value = false
  } finally {
    serviceChecking.value = false
  }
}

async function refreshPage(): Promise<void> {
  refreshing.value = true
  await loadShellState()
  refreshToken.value += 1
  refreshTimer = window.setTimeout(() => {
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

onMounted(() => { void loadShellState(); window.addEventListener('keydown', handleShortcut) })
onUnmounted(() => { window.removeEventListener('keydown', handleShortcut); window.clearTimeout(refreshTimer) })
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
  color: var(--text-primary);
  background: var(--bg-base);
}

.app-shell.sidebar-collapsed {
  grid-template-columns: var(--sidebar-width-collapsed) minmax(0, 1fr);
}

.sidebar {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #edf2ed;
  border-right: 1px solid var(--border-subtle);
  z-index: var(--z-sidebar);
}

.sidebar-head {
  min-height: 80px;
  padding: 20px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.brand-link {
  min-width: 0;
  flex: 1;
  color: inherit;
  text-decoration: none;
  transition: opacity var(--motion-fast);
}

.brand-link:hover {
  opacity: 0.92;
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
  border: 1px solid transparent;
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
  min-height: 44px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 11px;
  color: var(--text-secondary);
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
  padding: 12px 12px 20px;
  overflow-y: auto;
}

.nav-group + .nav-group {
  margin-top: 24px;
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
  margin-bottom: 2px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--text-secondary);
  border: 1px solid transparent;
  border-radius: var(--radius-control);
  text-decoration: none;
  font-size: 13px;
  font-weight: 400;
  transition: color var(--motion-fast), background var(--motion-fast), border-color var(--motion-fast);
}

.nav-item:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.nav-item.router-link-active {
  color: var(--accent);
  background: #dce9df;
  border-color: transparent;
  font-weight: 600;
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
  color: var(--brand-blue-strong);
  background: rgba(219, 233, 255, 0.82);
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

.service-banner {
  min-height: 52px;
  padding: 9px 20px;
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  color: var(--text-primary);
  background: #fff8eb;
  border-bottom: 1px solid #ead5ad;
  font-size: 12px;
}

.service-banner > .el-icon {
  color: var(--warning);
  font-size: 20px;
}

.service-banner > div {
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
}

.service-banner strong {
  font-size: 13px;
}

.service-banner span {
  color: var(--text-secondary);
}

.service-banner code {
  padding: 2px 5px;
  color: var(--text-primary);
  background: rgba(154, 101, 29, 0.08);
  border-radius: 4px;
  font-family: var(--font-mono);
}

.service-banner button {
  min-height: 34px;
  padding: 0 12px;
  color: var(--warning);
  background: transparent;
  border: 1px solid #d8b879;
  border-radius: 8px;
  font-weight: 700;
}

.service-banner button:disabled {
  opacity: 0.55;
}

.topbar {
  min-height: var(--topbar-height);
  padding: 0 36px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  background: var(--bg-base);
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
  color: var(--brand-blue-strong);
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
  width: 40px;
  height: 40px;
  margin-left: 4px;
  overflow: hidden;
  background: var(--brand-blue-soft);
  border: 1px solid var(--brand-blue-border);
  border-radius: 12px;
}

.avatar img {
  width: 100%;
  height: 145%;
  display: block;
  object-fit: cover;
  object-position: center 4%;
}

.content-scroll {
  flex: 1;
  min-height: 0;
  padding: 28px 36px 48px;
  overflow: auto;
  background: var(--bg-base);
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
  .service-banner {
    grid-template-columns: 20px minmax(0, 1fr);
    padding: 10px 14px;
  }

  .service-banner button {
    grid-column: 2;
    justify-self: start;
  }

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

.workspace-label { color: var(--text-muted); font-size: 12px; }
.breadcrumb-divider { color: var(--border-strong); margin: 0 14px; }
.page-title { font-size: 13px; font-weight: 500; }
.version-label { min-height: 44px; border: 0; background: transparent; }
.service-state.checking .state-indicator { background: var(--text-muted); }
.finder-trigger { display: flex; align-items: center; gap: 10px; min-height: 40px; padding: 0 12px; margin-right: 8px; border: 1px solid var(--border-subtle); border-radius: 8px; background: var(--bg-surface); color: var(--text-muted); font-size: 12px; }
.finder-trigger:hover { border-color: var(--accent-border); color: var(--accent); }
.finder-trigger kbd { margin-left: 24px; padding: 3px 5px; border: 1px solid var(--border-subtle); border-radius: 4px; font: 10px var(--font-mono); }
.finder-input { display: flex; align-items: center; gap: 12px; border: 1px solid var(--border-strong); border-radius: 8px; padding: 0 14px; color: var(--text-muted); }
.finder-input:focus-within { border-color: var(--accent); outline: 2px solid var(--accent-soft); }
.finder-input input { min-width: 0; width: 100%; min-height: 48px; border: 0; background: transparent; color: var(--text-primary); outline: none; font-size: 14px; }
.finder-results { max-height: 360px; overflow: auto; margin-top: 12px; }
.finder-results a { display: flex; align-items: center; gap: 12px; min-height: 48px; padding: 0 12px; border-radius: 8px; color: var(--text-primary); font-size: 13px; text-decoration: none; }
.finder-results a:hover { background: var(--accent-soft); }
.finder-results small { margin-left: auto; color: var(--text-muted); font-size: 11px; }
.finder-hint,.finder-empty { color: var(--text-muted); font-size: 12px; margin: 16px 0 0; }
.finder-hint { padding-top: 12px; border-top: 1px solid var(--border-subtle); }
@media(max-width: 1100px) { .finder-trigger kbd { display: none; } }
@media(max-width: 900px) {
  .sidebar-collapsed .brand-link { display: block; }
  .sidebar-collapsed .nav-group-label,.sidebar-collapsed .nav-item > span { display: block; }
  .sidebar-collapsed .sidebar-foot,.sidebar-collapsed .service-state { display: flex; }
  .sidebar-collapsed .nav-item { justify-content: flex-start; padding: 0 12px; }
}
@media(max-width: 560px) {
  .workspace-label,.breadcrumb-divider,.finder-trigger span,.finder-trigger kbd { display: none; }
  .finder-trigger { width: 44px; height: 44px; justify-content: center; padding: 0; margin: 0; border: 0; }
  .topbar-actions { gap: 0; }
  .topbar { gap: 6px; padding: 0 12px; }
  .topbar-title { gap: 4px; }
  .page-title { font-size: 12px; }
}

</style>
