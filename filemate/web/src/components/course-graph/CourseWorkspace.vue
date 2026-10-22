<template>
  <section ref="root" class="course-workspace" :aria-busy="state.loading || booting">
    <header class="cw-header"><div><p class="cw-kicker">FileMate · 知识工作台</p><h1>{{ state.navigation?.name || '从一门课开始' }}</h1><p>按章节展开知识，随时核对原文。</p></div><div class="cw-header-actions"><button id="course-directory-trigger" class="cw-directory-toggle" @click="directoryOpen = true"><IconLayoutSidebar :size="21" aria-hidden="true" />课程目录</button><button :disabled="state.loading || booting" @click="refresh"><IconRefresh :size="20" aria-hidden="true" />刷新</button><button id="course-manager-trigger" @click="panels.open('manager', 'course-manager-trigger')">整理课程</button></div></header>
    <p v-if="bootError" role="alert" class="cw-status cw-error">{{ bootError }}<button @click="initialize">重新读取</button></p>
    <p v-if="state.error" role="alert" class="cw-status cw-error">{{ state.error }}<button @click="refresh">重试读取</button></p>
    <p v-if="state.stale && state.navigation" role="status" class="cw-status">当前保留上次读取的快照，请刷新后核对最新内容。</p>
    <p v-if="state.notice" role="status" class="cw-status">{{ state.notice }}</p>
    <p v-if="booting || state.loading" role="status" class="cw-caption">正在读取课程与知识关系…</p>
    <template v-if="!booting && !state.browse.courseId">
      <div class="cw-empty"><IconBooks :size="48" aria-hidden="true" /><h2>{{ courses.total ? '选择要继续的课程' : '让资料成为你的知识地图' }}</h2><p>先建立课程，再选择已有资料，核对后成为你的知识图谱。</p><button class="cw-primary" @click="panels.open('manager', 'course-manager-trigger')">整理课程与资料</button><CourseNavigation v-if="courses.total" :courses="courses" :browse="state.browse" :navigation="null" :loading="state.loading" @course="chooseCourse" @course-page="coursePage" /></div>
    </template>
    <template v-else-if="state.browse.courseId">
      <div class="cw-tools"><form class="cw-search" @submit.prevent="controller.search(searchText, true)"><IconSearch :size="22" aria-hidden="true" /><input v-model="searchText" maxlength="160" type="search" aria-label="搜索整门课程的知识点" placeholder="搜索整门课程的知识点" @input="controller.search(searchText)" /><button :disabled="state.searching">搜索</button></form><nav class="cw-views" aria-label="知识工作台视图"><button v-for="view in views" :key="view.id" :aria-pressed="state.browse.view === view.id" @click="controller.setView(view.id)"><component :is="view.icon" :size="20" aria-hidden="true" />{{ view.label }}</button></nav><button v-if="state.detail && state.browse.view !== 'evidence'" class="cw-detail-toggle" @click="detailOpen = true">查看来源</button></div>
      <section v-if="searchText.trim() && (state.searchPage || state.searching)" class="cw-search-results" aria-label="全课程搜索结果"><p class="cw-caption">{{ state.searching ? '正在搜索…' : `找到 ${state.searchPage?.total ?? 0} 个结果，展示前50个；可补充关键词缩小范围。` }}</p><div class="cw-list-buttons"><button v-for="item in state.searchPage?.items" :key="item.id" @click="chooseSearch(item)">{{ item.label }}<span v-if="item.matched_label !== item.label"> · {{ item.matched_label }}</span></button></div><p v-if="state.searchPage?.total === 0">没有找到匹配的概念，试试资料中的其他名称。</p></section>
      <details class="cw-filter-details"><summary>关系类型{{ state.browse.relations?.length === 0 ? ' · 连线已隐藏' : '' }}</summary><label v-for="relation in workspaceRelations" :key="relation"><input type="checkbox" :checked="state.browse.relations === null || state.browse.relations.includes(relation)" @change="toggleRelation(relation)" />{{ relationLabels[relation] }}</label></details>
      <div v-if="state.browse.chapterId || state.browse.sourceId" class="cw-list-buttons"><span class="cw-caption">已限定章节或资料范围</span><button @click="controller.setFilters({ relations: state.browse.relations })">查看全部范围</button></div>
      <div class="cw-grid" :class="{ 'cw-evidence-mode': state.browse.view === 'evidence' }">
        <CourseNavigation :courses="courses" :browse="state.browse" :navigation="state.navigation" :loading="state.loading" @course="chooseCourse" @filter="setFilters" @course-page="coursePage" @navigation-page="controller.pageNavigation" />
        <main class="cw-main">
          <CourseCanvas v-if="state.browse.view === 'graph' && state.canvas" :data="state.canvas" :selected-id="state.detail?.resolved_id || ''" :reduced-motion="reducedMotion" @select="selectNode" @expand="selectNode" @open-group="openGroup" @group-page="controller.pageGroups" @open-list="controller.setView('outline')" @overview="overview" />
          <CourseOutline v-else-if="state.browse.view === 'outline'" :page="state.listPage" :selected-id="state.detail?.resolved_id || ''" :loading="state.loading" @select="selectNode" @page="controller.page" />
          <CourseEvidence v-else-if="state.browse.view === 'evidence'" :detail="state.detail" can-open @open-citation="openCitation" @page="controller.pageReferences" />
          <div v-else class="cw-empty"><h3>课程内容正在读取</h3><p>读取失败时可用上方按钮重试。</p></div>
        </main>
        <aside v-if="state.browse.view !== 'evidence'" class="cw-detail"><CourseEvidence :detail="state.detail" can-open @open-citation="openCitation" @page="controller.pageReferences" /></aside>
      </div>
    </template>
    <el-drawer @keydown.tab.capture="trapPanelFocus" v-model="directoryOpen" title="课程目录" direction="ltr" size="min(360px, 100vw)" class="cw-dialog" :append-to-body="true"><CourseNavigation :courses="courses" :browse="state.browse" :navigation="state.navigation" :loading="state.loading" @course="chooseCourse" @filter="setFilters" @course-page="coursePage" @navigation-page="controller.pageNavigation" /></el-drawer>
    <el-drawer @keydown.tab.capture="trapPanelFocus" v-model="detailOpen" @opened="focusCitationTrigger" title="知识点与来源" size="min(500px, 100vw)" class="cw-dialog" :append-to-body="true"><CourseEvidence :detail="state.detail" can-open @open-citation="openCitation" @page="controller.pageReferences" /></el-drawer>
    <el-drawer @keydown.tab.capture="trapPanelFocus" :model-value="panels.state.active === 'source'" title="核对原文" size="min(720px, 100vw)" class="cw-dialog" append-to-body :before-close="() => closeCitation()"><CourseSourcePanel :citation="state.citation" :loading="state.citationLoading" :error="state.error || state.notice" @retry="openCitation(citationId)" @closed="closeCitation" /></el-drawer>
    <el-drawer @keydown.tab.capture="trapPanelFocus" :model-value="panels.state.active === 'manager'" title="整理课程与资料" size="min(1280px, 100vw)" class="cw-dialog" append-to-body :before-close="closeManager" :destroy-on-close="false"><CourseManager v-if="panels.state.managerMounted" :key="panels.state.managerEpoch" ref="manager" :course-id="state.browse.courseId" :sources="sources" @changed="changed" /></el-drawer>
  </section>
</template>
<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, shallowReactive, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { IconBooks, IconHierarchy, IconLayoutList, IconLayoutSidebar, IconQuote, IconRefresh, IconSearch } from '@tabler/icons-vue'
import * as api from '../../services/api'
import type { GraphCourse, GraphPage, RelationKind } from '../../types/courseGraph'
import type { PreferenceStorage, WorkspaceFilter, WorkspaceNode, WorkspaceView } from '../../types/courseWorkspace'
import { courseBrowseQuery, createCoursePreferences, readCourseBrowse, workspaceRelations } from '../../course-graph/browse-state'
import { createCourseWorkspaceController } from '../../course-graph/workspace-state'
import { relationLabels } from '../../course-graph/workspace-layout'
import CourseNavigation from './CourseNavigation.vue'
import CourseCanvas from './CourseCanvas.vue'
import CourseOutline from './CourseOutline.vue'
import CourseEvidence from './CourseEvidence.vue'
import CourseManager from './CourseManager.vue'
import CourseSourcePanel from './CourseSourcePanel.vue'
import { createWorkspacePanels, nextPanelFocus } from '../../course-graph/workspace-panels'
import '../../styles/course-workspace.css'

defineProps<{ sources: api.KnowledgeSource[] }>()
const route = useRoute(), router = useRouter(), controller = createCourseWorkspaceController(api, shallowReactive), state = controller.state
const root = ref<HTMLElement | null>(null), width = ref(1200)
const manager = ref<{ canLeave(): Promise<boolean> } | null>(null)
const panels = createWorkspacePanels(() => manager.value?.canLeave() ?? Promise.resolve(true), id => { void nextTick(() => document.getElementById(id)?.focus()) }, shallowReactive)
const directoryOpen = computed({ get: () => panels.state.active === 'directory', set: value => { void (value ? panels.open('directory', 'course-directory-trigger') : panels.close('directory')) } })
const detailOpen = computed({ get: () => panels.state.active === 'detail', set: value => { void (value ? panels.open('detail') : panels.close('detail')) } })
function trapPanelFocus(event: KeyboardEvent) {
  const drawer = (event.target as HTMLElement).closest('[role=dialog]')
  if (!drawer) return
  const controls = [...drawer.querySelectorAll<HTMLElement>('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex="0"]')].filter(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden')
  const index = nextPanelFocus(controls.indexOf(document.activeElement as HTMLElement), controls.length, event.shiftKey)
  if (index >= 0) { event.preventDefault(); event.stopPropagation(); controls[index]!.focus() }
}
let citationId = '', citationTrigger = '', sourceFromDetail = false
function focusCitationTrigger() { if (citationTrigger) document.getElementById(citationTrigger)?.focus() }
async function openCitation(id: string, trigger = '') { citationId = id; if (trigger) { citationTrigger = trigger; sourceFromDetail = panels.state.active === 'detail' }; await panels.open('source', citationTrigger); await controller.openCitation(id) }
async function closeCitation() { controller.closeCitation(); if (await panels.close('source') && sourceFromDetail) { sourceFromDetail = false; detailOpen.value = true } }
async function closeManager(done: () => void) { if (await panels.close('manager')) done() }
async function changed(cid: string) {
  if (cid === state.browse.courseId) await controller.invalidateAfterMutation()
  try { courses.value = await api.listGraphCourses() } catch { bootError.value = '内容已保存，课程列表暂未刷新，可重试读取。' }
}
function restored() { panels.invalidate(); controller.closeCitation(); void initialize() }
async function canLeave() { return manager.value?.canLeave() ?? true }
const courses = shallowRef<GraphPage<GraphCourse>>({ items: [], total: 0, limit: 50, offset: 0 })
const searchText = ref(''), booting = ref(true), bootError = ref(''), reducedMotion = ref(false)
const views: { id: WorkspaceView; label: string; icon: typeof IconHierarchy }[] = [{ id: 'graph', label: '关系图', icon: IconHierarchy }, { id: 'outline', label: '大纲', icon: IconLayoutList }, { id: 'evidence', label: '证据', icon: IconQuote }]
let preferences: ReturnType<typeof createCoursePreferences> | null = null, resize: ResizeObserver | undefined, media: MediaQueryList | undefined
let disposed = false, bootstrap = 0, ready = false
const memoryStorage: PreferenceStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} }
function storage() { try { return window.localStorage } catch { return memoryStorage } }
async function initialize() {
  const generation = ++bootstrap; booting.value = true; bootError.value = ''; ready = false
  try {
    const [scope, page] = await Promise.all([api.getCourseBrowserScope(), api.listGraphCourses()])
    if (disposed || generation !== bootstrap) return
    controller.resetIdentity(scope); preferences = createCoursePreferences(storage(), scope); courses.value = page
    const explicit = typeof route.query.course === 'string' ? route.query.course : ''
    const cid = explicit || preferences.lastCourse() || page.items[0]?.course_id || ''
    const browse = readCourseBrowse({ ...route.query, graph_scope: 'course', ...(cid ? { course: cid } : {}) }, preferences.get(cid, width.value < 640), width.value < 640)
    if (cid) {
      try {
        const selected = await api.getGraphCourse(cid)
        if (disposed || generation !== bootstrap) return
        if (!courses.value.items.some(c => c.course_id === cid)) courses.value = { ...page, items: [selected, ...page.items] }
      } catch (cause) {
        if ((cause as { status?: number }).status !== 404) throw cause
        preferences.forget(cid); browse.courseId = ''; browse.nodeId = ''; browse.notice = '原课程当前不可用，请重新选择。'
      }
    }
    await controller.open(browse)
    if (!disposed && generation === bootstrap) { ready = true; syncUrl() }
  } catch { if (!disposed && generation === bootstrap) bootError.value = '课程暂时无法读取，请重试。' }
  finally { if (!disposed && generation === bootstrap) booting.value = false }
}
function syncUrl() {
  if (!ready || disposed) return
  const query = courseBrowseQuery(state.browse)
  if (JSON.stringify(query) !== JSON.stringify(route.query)) void router.replace({ query })
  if (state.browse.courseId) preferences?.set(state.browse.courseId, width.value < 640, state.browse.view)
}
async function chooseCourse(cid: string) {
  directoryOpen.value = false; detailOpen.value = false; searchText.value = ''
  const next = readCourseBrowse({ graph_scope: 'course', course: cid }, preferences?.get(cid, width.value < 640) || null, width.value < 640)
  await router.push({ query: courseBrowseQuery(next) })
}
async function coursePage(delta: number) { try { courses.value = await api.listGraphCourses('', courses.value.offset + delta*50) } catch { bootError.value = '课程列表读取失败，请重试。' } }
async function setFilters(filters: WorkspaceFilter) { directoryOpen.value = false; await controller.setFilters(filters) }
async function openGroup(id: string) { await setFilters({ chapter_id: id, relations: state.browse.relations }) }
async function selectNode(id: string) { await controller.selectNode(id); if (width.value < 820 && state.detail) { directoryOpen.value = false; detailOpen.value = true } }
async function chooseSearch(item: WorkspaceNode) { await controller.selectSearchResult(item); searchText.value = ''; if (width.value < 820 && state.detail) detailOpen.value = true }
async function overview() { await controller.open({ ...state.browse, nodeId: '', chapterId: '', sourceId: '', notice: '' }) }
async function refresh() { if (!ready) await initialize(); else await controller.refresh() }
function toggleRelation(relation: RelationKind) { const chosen = new Set(state.browse.relations ?? workspaceRelations); if (chosen.has(relation)) chosen.delete(relation); else chosen.add(relation); void controller.setFilters({ chapter_id: state.browse.chapterId || undefined, source_id: state.browse.sourceId || undefined, relations: [...chosen] }) }
function expired() { panels.invalidate(); ++bootstrap; ready = false; preferences?.clearMemory(); controller.resetIdentity(null); courses.value = { items: [], total: 0, limit: 50, offset: 0 }; bootError.value = '登录状态已变化，请重新登录后读取课程。' }
function motion() { reducedMotion.value = !!media?.matches }
watch(() => state.browse, syncUrl)
watch(() => route.fullPath, async () => {
  if (!ready || route.query.graph_scope === 'source') return
  const next = readCourseBrowse(route.query, preferences?.get(String(route.query.course || ''), width.value < 640) || null, width.value < 640)
  if (JSON.stringify(courseBrowseQuery(next)) !== JSON.stringify(courseBrowseQuery(state.browse))) { if (next.courseId !== state.browse.courseId) panels.invalidate(); searchText.value = ''; await controller.open(next) }
})
onMounted(() => {
  if (root.value) { width.value = root.value.clientWidth; resize = new ResizeObserver(entries => { width.value = entries[0]?.contentRect.width || width.value }); resize.observe(root.value) }
  media = matchMedia('(prefers-reduced-motion: reduce)'); motion(); media.addEventListener('change', motion)
  window.addEventListener('filemate:session-expired', expired); window.addEventListener('filemate:data-restored', restored); void initialize()
})
onUnmounted(() => { disposed = true; ++bootstrap; controller.dispose(); resize?.disconnect(); media?.removeEventListener('change', motion); window.removeEventListener('filemate:session-expired', expired); window.removeEventListener('filemate:data-restored', restored) })
defineExpose({ canLeave })
</script>
