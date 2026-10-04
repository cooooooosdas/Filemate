<template>
  <div class="file-review-page">
    <WorkflowSteps :current="2" />
    <header class="review-heading">
      <div>
        <h1>让资料，<span>归位。</span></h1>
        <p>核对分类与名称，然后一次确认。</p>
      </div>
      <el-icon aria-hidden="true"><DocumentChecked /></el-icon>
    </header>

    <DataState v-if="loading" loading />
    <DataState v-else-if="loadError" :error="loadError" @retry="loadRequestedSession" />
    <DataState v-else-if="!currentFile" empty>
      <strong>选一份资料，开始核对</strong>
      <span>从导入结果或处理记录打开，分类与命名在这里一起确认。</span>
      <el-button type="primary" @click="router.push('/import?intent=archive')">导入资料</el-button>
    </DataState>

    <template v-else>
      <section class="review-sheet" aria-label="资料分类与命名审核" :aria-busy="busy">
        <div class="original-file">
          <el-icon aria-hidden="true"><Document /></el-icon>
          <div><span>原始文件</span><strong>{{ originalName }}</strong></div>
          <span class="review-status">{{ completed ? '已归档' : dirty ? '有未保存修改' : '待核对' }}</span>
        </div>

        <div class="review-layout">
          <div class="review-fields">
            <fieldset :disabled="busy || completed" class="category-options">
              <legend>放在哪一类？</legend>
              <div class="category-grid">
                <label v-for="category in categories" :key="category" :class="{ selected: selectedCategory === category }">
                  <input v-model="selectedCategory" type="radio" name="file-category" :value="category" />
                  <span>{{ category }}</span>
                </label>
              </div>
            </fieldset>
            <div class="name-field">
              <label for="review-filename">起一个清楚的名字</label>
              <el-input id="review-filename" v-model="editedName" :disabled="busy || completed"
                :aria-invalid="!!nameError" :aria-describedby="nameError ? 'filename-error' : undefined"
                placeholder="输入最终文件名" />
              <p v-if="nameError" id="filename-error" class="field-error" role="alert">{{ nameError }}</p>
            </div>
            <label v-if="hasDates" class="calendar-option">
              <input v-model="includeCalendar" type="checkbox" :disabled="busy || completed" />
              <span>同时生成学习日程</span>
            </label>
          </div>

          <aside class="archive-preview" aria-label="归档预览">
            <h2>{{ completed ? '资料的新位置' : '确认后的样子' }}</h2>
            <div class="folder-trail"><span>归档目录</span><span>{{ selectedCategory || '待确认' }}</span><span>{{ courseName }}</span></div>
            <strong class="preview-name">{{ previewName || '等待填写文件名' }}</strong>
            <p>{{ completed ? '执行记录已保存，可随时查看。' : '确认后才归档，不覆盖已有文件，可撤销。' }}</p>
            <div v-if="hasDates" class="dates-preview">
              <h3>{{ includeCalendar ? '日程预览' : '本次不生成日程' }}</h3>
              <ul v-if="includeCalendar"><li v-for="(date, index) in dates" :key="index"><time>{{ date.date }}</time><span>{{ date.event }}</span></li></ul>
            </div>
          </aside>
        </div>

        <div v-if="actionError" class="review-error" role="alert">
          <strong>{{ actionError }}</strong>
          <span>修改已保留；可重试，或重新读取记录核对执行状态。</span>
          <el-button :disabled="busy" @click="reloadWithConfirmation">重新读取记录</el-button>
        </div>
        <div v-if="!completed" class="review-actions">
          <span>{{ dirty ? '先保存可留待以后确认' : '请核对预览后确认' }}</span>
          <el-button :loading="operation === 'save'" :disabled="busy || !canSubmit || !dirty" @click="saveDraft">保存草稿</el-button>
          <el-button type="primary" :loading="operation === 'confirm'" :disabled="busy || !canSubmit" @click="confirmReview">
            确认并归档 <el-icon aria-hidden="true"><ArrowRight /></el-icon>
          </el-button>
        </div>
      </section>

      <section v-if="completed" class="review-complete" role="status">
        <el-icon aria-hidden="true"><CircleCheckFilled /></el-icon>
        <div><h2>资料已归档</h2><p>{{ destination || '归档记录已保存。' }}</p></div>
        <div class="completion-actions">
          <el-button v-if="canUndo" :loading="operation === 'undo'" :disabled="busy" @click="undoArchive">撤销归档</el-button>
          <el-button v-if="calendarReady" :loading="operation === 'download'" :disabled="busy" @click="downloadCalendar">下载日程</el-button>
          <el-button v-if="hasDates" :disabled="busy" @click="goToSchedule">查看日程</el-button>
          <el-button type="primary" :disabled="busy" @click="router.push('/history')">查看处理记录</el-button>
        </div>
      </section>

      <details class="category-history" @toggle="loadDistribution">
        <summary>资料分类概览</summary>
        <DataState v-if="distributionLoading" loading />
        <DataState v-else-if="distributionError" :error="distributionError" @retry="loadDistribution" />
        <p v-else-if="!distribution.length">暂无分类记录。</p>
        <template v-else>
          <p>最近 {{ distributionTotal }} 条处理记录，仅统计已保存的分类。</p>
          <div v-for="item in distribution" :key="item.name" class="distribution-row">
            <span>{{ item.name }}</span><div aria-hidden="true"><i :style="{ width: `${item.value / distributionMax * 100}%` }"></i></div><strong>{{ item.value }}</strong>
          </div>
        </template>
      </details>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight, CircleCheckFilled, Document, DocumentChecked } from '@element-plus/icons-vue'
import { confirmSession, downloadIcs, getHistory, getIcsContent, getSession, undoSession, updateSessionDraft } from '../services/api'
import { useFileStore } from '../stores/fileStore'
import type { Category, ProcessingSession } from '../types'
import { sessionDates } from '../utils/session-dates'
import DataState from '../components/DataState.vue'
import WorkflowSteps from '../components/WorkflowSteps.vue'

const categories: Category[] = ['课件', '作业', '参考资料', '考试通知', '竞赛通知', '大创通知', '待确认']
const route = useRoute()
const router = useRouter()
const fileStore = useFileStore()
const currentFile = ref<ProcessingSession | null>(null)
const selectedCategory = ref<Category>('待确认')
const editedName = ref('')
const includeCalendar = ref(true)
const loading = ref(false)
const loadError = ref('')
const actionError = ref('')
const operation = ref<'save' | 'confirm' | 'undo' | 'download' | null>(null)
const busy = computed(() => operation.value !== null)
const completed = computed(() => currentFile.value?.execution?.status === 'applied' || currentFile.value?.status === 'confirmed')
const canUndo = computed(() => !!(currentFile.value?.can_undo || currentFile.value?.execution?.can_undo))
const originalName = computed(() => currentFile.value?.source_path.split(/[/\\]/).pop() || '')
const sourceExtension = computed(() => originalName.value.match(/\.[^.]+$/)?.[0] || '')
const courseName = computed(() => String(currentFile.value?.entities.course_name || '未分类'))
const destination = computed(() => currentFile.value?.execution?.dest_path || '')
const dates = computed(() => sessionDates(currentFile.value))
const hasDates = computed(() => dates.value.length > 0)
const calendarReady = computed(() => !!currentFile.value?.execution?.ics_path && currentFile.value.execution.status === 'applied')
const nameError = computed(() => {
  const name = editedName.value.trim()
  if (!name) return '请填写文件名。'
  if (/[<>:"/\\|?*]/.test(name) || name === '.' || name === '..') return '文件名不能包含路径或特殊字符。'
  const extension = name.match(/\.[^.]+$/)?.[0]
  if (extension && extension.toLowerCase() !== sourceExtension.value.toLowerCase()) return `请保留 ${sourceExtension.value || '原文件'} 格式。`
  return ''
})
const previewName = computed(() => {
  const name = editedName.value.trim()
  return name && !/\.[^.]+$/.test(name) ? name + sourceExtension.value : name
})
const canSubmit = computed(() => !!currentFile.value && !nameError.value)
const dirty = computed(() => !!currentFile.value && !completed.value && (
  editedName.value !== currentFile.value.suggested_name || selectedCategory.value !== (currentFile.value.category || '待确认') ||
  (hasDates.value && includeCalendar.value !== (currentFile.value.entities.calendar_enabled !== false))
))
const distribution = ref<{ name: string; value: number }[]>([])
const distributionLoading = ref(false)
const distributionError = ref('')
const distributionTotal = computed(() => distribution.value.reduce((sum, item) => sum + item.value, 0))
const distributionMax = computed(() => Math.max(1, ...distribution.value.map(item => item.value)))

function acceptSession(session: ProcessingSession): void {
  currentFile.value = session
  fileStore.updateFile(session)
  fileStore.setCurrentFile(session)
  selectedCategory.value = session.category || '待确认'
  editedName.value = session.suggested_name
  includeCalendar.value = session.entities.calendar_enabled !== false
}

function edits(): Record<string, unknown> {
  return { category: selectedCategory.value, suggested_name: editedName.value.trim(), ...(hasDates.value ? { entities: { calendar_enabled: includeCalendar.value } } : {}) }
}

async function loadRequestedSession(): Promise<void> {
  const sessionId = typeof route.query.session === 'string' ? route.query.session : ''
  currentFile.value = null
  fileStore.setCurrentFile(null)
  if (!sessionId) return
  loading.value = true
  loadError.value = ''
  actionError.value = ''
  try { acceptSession(await getSession(sessionId)) }
  catch (error) { loadError.value = error instanceof Error ? error.message : '审核记录加载失败' }
  finally { loading.value = false }
}

async function allowLeaving(): Promise<boolean> {
  if (busy.value) { ElMessage.info('正在保存，请稍候。'); return false }
  if (!dirty.value) return true
  try {
    await ElMessageBox.confirm('分类或名称的修改尚未保存。', '离开审核页面？', {
      confirmButtonText: '不保存并离开', cancelButtonText: '继续核对', type: 'warning',
    })
    return true
  } catch { return false }
}

async function reloadWithConfirmation(): Promise<void> { if (await allowLeaving()) await loadRequestedSession() }
function guardUnload(event: BeforeUnloadEvent): void {
  if (dirty.value || busy.value) { event.preventDefault(); event.returnValue = '' }
}
function guardRefresh(event: Event): void {
  if (dirty.value || busy.value) { event.preventDefault(); ElMessage.info('请先保存草稿，再刷新页面。') }
}
onBeforeRouteLeave(allowLeaving)
onBeforeRouteUpdate(allowLeaving)
onMounted(() => { void loadRequestedSession(); window.addEventListener('beforeunload', guardUnload); window.addEventListener('filemate:before-refresh', guardRefresh) })
onBeforeUnmount(() => { window.removeEventListener('beforeunload', guardUnload); window.removeEventListener('filemate:before-refresh', guardRefresh) })

async function saveDraft(): Promise<void> {
  if (!currentFile.value || busy.value || completed.value || !canSubmit.value) return
  operation.value = 'save'
  actionError.value = ''
  try {
    acceptSession(await updateSessionDraft(currentFile.value.session_id, edits()))
    ElMessage.success('草稿已保存，文件尚未归档。')
  } catch (error) { actionError.value = error instanceof Error ? error.message : '草稿保存失败' }
  finally { operation.value = null }
}

async function confirmReview(): Promise<void> {
  if (!currentFile.value || busy.value || completed.value || !canSubmit.value) return
  operation.value = 'confirm'
  actionError.value = ''
  const session = currentFile.value
  try {
    const result = await confirmSession(session.session_id, { accepted: true, edits: edits() })
    if (!result.ok) throw new Error(result.error || '归档失败')
    // 已知确认成功后先锁定已归档状态，读取失败不能让用户再次编辑旧结果。
    acceptSession({ ...session, category: selectedCategory.value, suggested_name: editedName.value.trim(),
      entities: { ...session.entities, ...(hasDates.value ? { calendar_enabled: includeCalendar.value } : {}) },
      status: 'confirmed', execution: result.execution, can_undo: result.execution?.can_undo })
    ElMessage.success('资料已归档。')
    try { acceptSession(await getSession(session.session_id)) }
    catch { actionError.value = '归档已成功，完整记录暂时未能读取。' }
  } catch (error) { actionError.value = error instanceof Error ? error.message : '归档失败' }
  finally { operation.value = null }
}

async function undoArchive(): Promise<void> {
  if (!currentFile.value || busy.value || !canUndo.value) return
  try { await ElMessageBox.confirm('本次归档文件会恢复至原位置，本次日程会移除。', '撤销本次归档？', { confirmButtonText: '确认撤销', cancelButtonText: '保留归档', type: 'warning' }) }
  catch { return }
  operation.value = 'undo'
  actionError.value = ''
  const session = currentFile.value
  try {
    const result = await undoSession(session.session_id)
    if (!result.ok) throw new Error('撤销未完成')
    acceptSession({ ...session, status: 'done', execution: result.execution, can_undo: false })
    ElMessage.success('已撤销，可重新核对。')
    try { acceptSession(await getSession(session.session_id)) }
    catch { actionError.value = '撤销已成功，完整记录暂时未能读取。' }
  } catch (error) { actionError.value = error instanceof Error ? error.message : '撤销失败' }
  finally { operation.value = null }
}

function goToSchedule(): void { if (currentFile.value) void router.push({ path: '/schedule', query: { session: currentFile.value.session_id } }) }
async function downloadCalendar(): Promise<void> {
  if (!currentFile.value || busy.value || !calendarReady.value) return
  operation.value = 'download'
  actionError.value = ''
  try { downloadIcs(await getIcsContent(currentFile.value.session_id), `${previewName.value}.ics`) }
  catch (error) { actionError.value = error instanceof Error ? error.message : '日程下载失败' }
  finally { operation.value = null }
}
async function loadDistribution(event?: Event): Promise<void> {
  if (event && event.target instanceof HTMLDetailsElement && !event.target.open) return
  if (distributionLoading.value) return
  distributionLoading.value = true
  distributionError.value = ''
  try {
    const counts: Record<string, number> = {}
    for (const item of await getHistory(undefined, 100)) { const name = item.category || '待确认'; counts[name] = (counts[name] || 0) + 1 }
    distribution.value = Object.entries(counts).map(([name, value]) => ({ name, value }))
  } catch (error) { distributionError.value = error instanceof Error ? error.message : '分类记录加载失败' }
  finally { distributionLoading.value = false }
}
</script>

<style scoped>
.file-review-page { max-width: 1120px; margin: 0 auto; }
.review-heading { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 22px 8px 32px; }
.review-heading h1 { margin: 0; color: var(--text-primary); font-size: clamp(36px, 4vw, 52px); letter-spacing: -.045em; line-height: 1.2; }
.review-heading h1 span { color: var(--accent); }
.review-heading p { margin: 16px 0 0; color: var(--text-secondary); font-size: 19px; }
.review-heading > .el-icon { font-size: 72px; color: var(--accent); padding: 22px; border-radius: 28px; background: var(--accent-soft); }
.review-sheet { overflow: hidden; background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 24px; }
.original-file { display: flex; align-items: center; gap: 16px; padding: 24px 30px; border-bottom: 1px solid var(--border-subtle); }
.original-file > .el-icon { flex: 0 0 auto; font-size: 28px; color: var(--accent); }
.original-file > div { flex: 1; min-width: 0; }
.original-file span { color: var(--text-secondary); font-size: 15px; }
.original-file strong { display: block; margin-top: 7px; overflow-wrap: anywhere; font-size: 20px; color: var(--text-primary); }
.review-status { flex: 0 0 auto; background: var(--accent-soft); border-radius: 8px; padding: 8px 12px; }
.review-layout { display: grid; grid-template-columns: minmax(0, 7fr) minmax(0, 5fr); }
.review-fields { padding: 30px; }
.category-options { padding: 0; margin: 0; border: 0; min-width: 0; }
.category-options legend, .name-field > label { padding: 0; font-size: 22px; font-weight: 750; color: var(--text-primary); }
.category-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 18px; }
.category-grid label { display: flex; align-items: center; gap: 9px; min-height: 52px; padding: 12px; box-sizing: border-box; border: 1px solid var(--border-subtle); border-radius: 10px; cursor: pointer; color: var(--text-secondary); font-size: 17px; transition: background-color .18s, border-color .18s; }
.category-grid label.selected { color: var(--accent); border-color: var(--accent); background: var(--accent-soft); font-weight: 750; }
.category-grid input, .calendar-option input { width: 18px; height: 18px; flex: 0 0 auto; accent-color: var(--accent); }
.category-options:disabled label { cursor: default; }
.category-grid label:focus-within, .calendar-option:focus-within { outline: 2px solid var(--accent); outline-offset: 3px; }
.name-field { margin-top: 32px; }
.name-field > label { display: block; margin-bottom: 16px; }
.name-field :deep(.el-input__wrapper) { min-height: 54px; padding: 0 16px; }
.name-field :deep(.el-input__inner) { font-size: 18px; }
.field-error { font-size: 16px; color: var(--danger); margin: 10px 0 0; }
.calendar-option { display: flex; align-items: center; gap: 12px; min-height: 48px; margin-top: 20px; font-size: 17px; cursor: pointer; }
.archive-preview { min-width: 0; padding: 30px; background: var(--panel-tint); border-left: 1px solid var(--border-subtle); }
.archive-preview h2 { font-size: 23px; margin: 0 0 22px; }
.folder-trail { display: flex; flex-wrap: wrap; gap: 8px; font-size: 15px; color: var(--text-secondary); }
.folder-trail span:not(:last-child)::after { content: '/'; padding-left: 8px; color: var(--text-muted); }
.folder-trail span { overflow-wrap: anywhere; min-width: 0; }
.preview-name { display: block; font-size: 26px; line-height: 1.6; margin-top: 20px; overflow-wrap: anywhere; color: var(--accent); }
.archive-preview p { font-size: 17px; line-height: 1.85; color: var(--text-secondary); }
.dates-preview { margin-top: 30px; padding-top: 20px; border-top: 1px solid var(--border-subtle); }
.dates-preview h3 { font-size: 18px; margin: 0 0 14px; }
.dates-preview ul { padding: 0; margin: 0; list-style: none; }
.dates-preview li { display: flex; gap: 12px; margin-top: 12px; font-size: 16px; }
.dates-preview time { flex: 0 0 auto; color: var(--accent); }
.dates-preview span { min-width: 0; overflow-wrap: anywhere; }
.review-actions { display: flex; align-items: center; flex-wrap: wrap; justify-content: flex-end; gap: 14px; padding: 24px 30px; border-top: 1px solid var(--border-subtle); }
.review-actions > span { margin-right: auto; font-size: 16px; color: var(--text-secondary); }
.review-actions .el-button, .completion-actions .el-button, .review-error .el-button { min-height: 48px; margin-left: 0; font-size: 17px; }
.review-error { display: grid; gap: 12px; margin: 0 30px 24px; padding: 20px; background: #fbf1ef; border: 1px solid #e0b8b1; border-radius: 12px; overflow-wrap: anywhere; font-size: 16px; color: var(--danger); }
.review-error .el-button { justify-self: start; }
.review-complete { display: flex; align-items: center; flex-wrap: wrap; gap: 20px; padding: 28px; margin-top: 24px; border: 1px solid var(--accent-border); border-radius: 20px; background: var(--accent-soft); }
.review-complete > .el-icon { font-size: 38px; color: var(--accent); }
.review-complete > div:not(.completion-actions) { min-width: 0; flex: 1 1 300px; }
.review-complete h2 { margin: 0; font-size: 27px; }
.review-complete p { font-size: 16px; line-height: 1.7; overflow-wrap: anywhere; margin: 10px 0 0; color: var(--text-secondary); }
.completion-actions { display: flex; flex-wrap: wrap; gap: 12px; }
.category-history { border-bottom: 1px solid var(--border-subtle); margin-top: 28px; padding: 18px 8px; }
.category-history summary { cursor: pointer; font-weight: 750; font-size: 20px; }
.category-history p { font-size: 16px; color: var(--text-secondary); margin: 20px 0; }
.distribution-row { display: grid; grid-template-columns: 100px minmax(0, 1fr) 45px; gap: 16px; align-items: center; max-width: 680px; margin: 14px 0; font-size: 17px; }
.distribution-row > div { height: 10px; background: var(--accent-soft); border-radius: 5px; }
.distribution-row i { display: block; height: 100%; background: var(--accent); border-radius: inherit; }
@media (max-width: 1050px) { .review-layout { grid-template-columns: 1fr; } .archive-preview { border-left: 0; border-top: 1px solid var(--border-subtle); } }
@media (max-width: 600px) {
  .review-heading { padding: 14px 0 24px; } .review-heading > .el-icon { display: none; } .review-heading p { font-size: 18px; }
  .review-sheet { border-radius: 18px; } .original-file { padding: 22px 18px; flex-wrap: wrap; }
  .original-file strong { font-size: 18px; } .review-status { margin-left: 44px; }
  .review-fields, .archive-preview { padding: 24px 18px; } .category-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .review-actions { padding: 20px 18px; } .review-actions > span { flex-basis: 100%; }
  .review-actions .el-button { flex: 1; } .review-error { margin: 0 18px 20px; }
  .review-complete { padding: 22px 18px; gap: 14px; } .completion-actions { width: 100%; } .completion-actions .el-button { flex: 1 1 auto; }
}
</style>
