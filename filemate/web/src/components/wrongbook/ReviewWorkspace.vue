<template>
  <main class="review-workspace">
    <header class="review-header"><div><p class="section-kicker"><Notebook :size="20" /> REVIEW WORKSPACE</p><h1>错题复盘</h1><p>先独立回答，再用证据找到下一步。</p></div><button class="primary" :disabled="s.loading || !s.capability?.write_enabled" @click="begin"><VideoPlay :size="20" />开始本次复习</button></header>
    <section v-if="s.summary" class="review-overview" aria-label="复习概览"><span><b>{{ s.summary.due_count }}</b> 今日到期</span><span><b>{{ s.summary.active_review_count }}</b> 进行中的新规则复习</span><span><b>{{ s.summary.saved_review_attempt_count }}</b> 已保存复习作答</span></section>
    <p v-if="notice" role="status" class="review-notice">{{ notice }}</p>
    <p v-if="s.capabilityError || s.capability?.write_enabled === false" class="review-notice">{{ s.capabilityError || '服务端暂未启用新规则写入，当前可浏览历史与证据。' }} <button v-if="s.capabilityError" @click="c.initialize()">重新连接</button></p>
    <form class="review-filters" @submit.prevent="apply()"><label class="review-search"><Search :size="20" /><input v-model="filters.q" type="search" maxlength="160" placeholder="搜索题目、知识点或资料" aria-label="搜索全部错题" /></label><label>状态<select v-model="filters.status"><option v-for="(label,key) in statuses" :key="key" :value="key">{{ label }}</option></select></label><button :disabled="s.loading">查找</button><button type="button" @click="clearFilters">清除筛选</button><details class="advanced-filters"><summary>更多筛选</summary><div class="filter-grid">
      <label>来源／课程名称<input v-model="optionQuery" type="search" maxlength="120" /></label><button type="button" @click="loadOptions(true)">查找来源与课程</button>
      <label>资料<select v-model="filters.source_id"><option value="">全部资料</option><option v-for="o in sources" :key="o.id" :value="o.id">{{ o.label }}</option></select></label><label>课程<select v-model="filters.course_id"><option value="">全部课程</option><option v-for="o in courses" :key="o.id" :value="o.id">{{ o.label }}</option></select></label><button v-if="optionsMore" type="button" @click="loadOptions(false)">加载更多筛选选项</button><p v-if="optionsError" role="alert">{{ optionsError }}</p>
      <label>知识点<input v-model="filters.knowledge_q" maxlength="120" /></label><label>错因<select v-model="filters.cause"><option value="">全部错因</option><option value="unconfirmed">尚未确定</option><option v-for="o in reviewCauses" :key="o.value" :value="o.value">{{ o.label }}</option></select></label>
      <label>最少错误<input v-model.number="filters.min_errors" type="number" min="0" max="1000000" /></label><label>最多错误<input v-model.number="filters.max_errors" type="number" min="0" max="1000000" /></label>
      <label v-for="(label,key) in dateLabels" :key="key">{{ label }}（上海）<input :value="localDate(filters[key])" type="datetime-local" @change="setDate(key,$event)" /></label>
      <label>排序<select v-model="filters.sort"><option value="due">到期时间</option><option value="updated">最近更新</option><option value="errors">错误次数</option><option value="created">收录时间</option></select></label><label>顺序<select v-model="filters.direction"><option value="asc">升序</option><option value="desc">降序</option></select></label>
    </div></details></form>
    <p v-if="s.message" role="status" class="review-notice">{{ s.message }}</p><button v-if="s.detailNeedsRefresh" @click="c.refreshAfterAnswer()">重新读取详情</button><p v-if="s.writeError && !s.preview" role="alert" class="review-error">{{ s.writeError }}</p>
    <FocusReview v-if="focusMode && s.capability?.write_enabled" :key="s.scope || 'memory'" ref="focusRef" :scope="s.scope" :filters="s.filters" :enabled="s.capability.write_enabled" @exit="back" />
    <div v-else class="review-columns" :class="{'has-selection': !!route.query.focus}">
      <ReviewList :items="s.items" :selected="s.selected" :total="s.total" :offset="s.offset" :has-more="s.hasMore" :loading="s.loading" :error="s.listError" @select="pick" @page="apply" @reload="c.loadPage(s.filters,s.offset)" />
      <section class="review-main" aria-label="单题复盘"><button class="back-catalog" @click="back"><ArrowRight :size="18" class="back-icon" />返回目录</button><p v-if="s.detailLoading" role="status">正在读取题目…</p><div v-else-if="s.detailError" role="alert"><h2>暂时无法打开此题</h2><p>{{ s.detailError }}</p><button @click="c.select(s.selected)">重试此题</button></div><template v-else-if="s.detail"><p class="review-meta">{{ reviewStateLabel(s.detail) }} · 错误 {{ s.detail.error_count }} 次 · 复习作答 {{ s.detail.review_attempt_count }} 次</p><ReviewQuestion :key="s.detail.wrong_id" :question="s.detail.question" :identity="s.detail.wrong_id" :submission="c.submission" :readonly="!s.capability?.write_enabled || s.detail.read_only_snapshot || s.detail.data_error" @saved="saved" /><ReviewEvidence ref="evidenceRef" :key="s.detail.wrong_id" :c="c" :d="s.detail" /></template><div v-else class="review-empty"><Reading :size="40" /><h2>从目录选择一道题</h2><p>你的真实作答、错因和复习进程会在这里汇合。</p></div></section>
    </div>
  </main>
</template>
<script setup lang="ts">
import { reactive, ref, onMounted, onBeforeUnmount, nextTick, watch, computed } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { getLearningSource } from '../../services/api'
import * as reviewApi from '../../services/review-api'
const api = { ...reviewApi, getLearningSource }
import type { ReviewFilter, ReviewOption } from '../../types/wrongbook'
import { createReviewWorkspaceController } from '../../wrongbook/workspace-state'
import { browserReviewStorage } from '../../wrongbook/submission'
import { createReviewPreferences, readReviewBrowse, reviewBrowseQuery } from '../../wrongbook/browse-state'
import { reviewCauses, reviewStateLabel } from '../../wrongbook/presentation'
import { Notebook, Search, VideoPlay, Reading, ArrowRight } from '../../icons'
import FocusReview from './FocusReview.vue'
import ReviewList from './ReviewList.vue'
import ReviewQuestion from './ReviewQuestion.vue'
import ReviewEvidence from './ReviewEvidence.vue'
import './review-workspace.css'
const c = createReviewWorkspaceController(api, value => reactive(value) as typeof value, browserReviewStorage()), s = c.state, route = useRoute(), router = useRouter()
const filters = ref<ReviewFilter>({ status: 'all', sort: 'due', direction: 'asc' }), notice = ref(''), optionQuery = ref(''), sources = ref<ReviewOption[]>([]), courses = ref<ReviewOption[]>([]), optionsMore = ref(false), optionsError = ref('')
const statuses = { all:'全部记录',due:'今日到期',overdue:'已经逾期',active:'进行中新规则',pending:'待核对',criterion_met:'达到本轮标准',legacy_completed:'历史两次答对',paused:'已暂停',history:'历史只读',invalid:'记录待修复' }
const dateLabels = { due_from:'到期起点',due_to:'到期终点',created_from:'收录起点',created_to:'收录终点' }
const focusMode = computed(()=>route.query.mode === 'focus'), focusRef = ref<InstanceType<typeof FocusReview> | null>(null)
const evidenceRef=ref<{dirty():boolean;invalidate():void}|null>(null)
let preferences = createReviewPreferences(browserReviewStorage(),null), ready = false, optionOffset = 0, optionEpoch = 0
function browse() { return {filters:s.filters,focus: typeof route.query.focus === 'string' ? route.query.focus : '',offset:s.offset,mode:focusMode.value?'focus' as const:'browse' as const,notice:''} }
function remember() { preferences.setBrowse(browse(), document.querySelector('.content-scroll')?.scrollTop ?? window.scrollY) }
async function allow() { if (!c.dirty() && !focusRef.value?.dirty() && !evidenceRef.value?.dirty()) return true; try { await ElMessageBox.confirm('有未提交内容或待确认操作。离开后未提交正文不会保存；在途请求仍可能在服务器完成。是否离开？','保留当前复盘？',{confirmButtonText:'离开',cancelButtonText:'继续复盘',type:'warning'}); return true } catch { return false } }
onBeforeRouteLeave(async()=>{if(!await allow())return false;remember();return true}); onBeforeRouteUpdate(allow)
function apply(offset = 0) { const clean = readReviewBrowse(Object.fromEntries(Object.entries(filters.value).filter(([,v])=>v!==''&&v!=null).map(([k,v])=>[k,String(v)]))); notice.value = clean.notice; router.push({query:reviewBrowseQuery({...clean,offset})}) }
function clearFilters() { filters.value = {status:'all',sort:'due',direction:'asc'}; apply() }
function pick(id: string) { router.push({query:reviewBrowseQuery({...browse(),focus:id})}) }
function back() { router.push({query:reviewBrowseQuery({...browse(),focus:'',mode:'browse'})}) }
async function begin() { router.push({query:reviewBrowseQuery({...browse(),focus:'',mode:'focus'})}) }
async function routeLoad() { if (!ready) return; const b = readReviewBrowse(route.query); filters.value = {...b.filters}; notice.value = b.notice; if (!await c.loadPage(b.filters,b.offset)) return; if (b.mode === 'focus') { c.submission.resetIdentity(s.scope); remember(); return }; if (b.focus) await c.select(b.focus); else if (s.items[0]) await c.select(s.items[0].wrong_id); else c.clearSelection(); remember() }
watch(()=>route.query,routeLoad)
async function saved() { await Promise.all([c.refreshAfterAnswer(),c.loadPage(s.filters,s.offset),c.initialize()]) }
async function loadOptions(reset = true) { const e=++optionEpoch; if(reset)optionOffset=0; optionsError.value=''; try { const [a,b]=await Promise.all([api.getReviewFilterOptions('sources',{q:optionQuery.value,offset:optionOffset}),api.getReviewFilterOptions('courses',{q:optionQuery.value,offset:optionOffset})]); if(e!==optionEpoch)return; sources.value=reset?a.items:[...sources.value,...a.items];courses.value=reset?b.items:[...courses.value,...b.items]; optionsMore.value=a.has_more||b.has_more;optionOffset+=30 } catch { if(e===optionEpoch)optionsError.value='筛选选项读取失败，请重新查找。' } }
function localDate(value?: string) { return value ? value.slice(0,16) : '' }
function setDate(key: keyof typeof dateLabels,e: Event) { const value=(e.target as HTMLInputElement).value; filters.value[key]=value?`${value}:00+08:00`:undefined }
function unload(e: BeforeUnloadEvent) { remember(); if(c.dirty()||focusRef.value?.dirty()||evidenceRef.value?.dirty()){e.preventDefault();e.returnValue=''} }
async function identityChanged() { ready=false;evidenceRef.value?.invalidate();focusRef.value?.invalidate();c.resetIdentity(null);preferences.clearMemory();sources.value=[];courses.value=[];await initialize(false) }
async function initialize(restore=true) {
  await c.initialize();preferences=createReviewPreferences(browserReviewStorage(),s.scope);ready=true
  const saved=restore?preferences.getBrowse():null
  if(saved&&Object.keys(route.query).length===0) await router.replace({query:reviewBrowseQuery(saved.browse)})
  await routeLoad();await nextTick()
  if(saved&&JSON.stringify(reviewBrowseQuery(readReviewBrowse(route.query)))===JSON.stringify(reviewBrowseQuery(saved.browse))){const scroll=document.querySelector('.content-scroll');if(scroll)scroll.scrollTop=saved.scroll;else window.scrollTo(0,saved.scroll);remember()}
  loadOptions()
}
async function visible(){if(document.hidden||c.dirty()||focusRef.value?.dirty()||evidenceRef.value?.dirty())return;await c.initialize();await c.loadPage(s.filters,s.offset);if(s.detail)await c.refreshAfterAnswer()}
function reviewChanged(event:Event){if((event as CustomEvent).detail?.source!=='review-learning')void visible()}
onMounted(()=>{initialize();document.addEventListener('visibilitychange',visible);window.addEventListener('filemate:review-changed',reviewChanged);window.addEventListener('beforeunload',unload);window.addEventListener('filemate:session-expired',identityChanged);window.addEventListener('filemate:data-restored',identityChanged)})
onBeforeUnmount(()=>{document.removeEventListener('visibilitychange',visible);window.removeEventListener('filemate:review-changed',reviewChanged);c.dispose();++optionEpoch;window.removeEventListener('beforeunload',unload);window.removeEventListener('filemate:session-expired',identityChanged);window.removeEventListener('filemate:data-restored',identityChanged)})
</script>
