<template>
  <div class="import-page">
    <header class="intake-heading"><div><p class="eyebrow">资料入口</p><h1>放进资料，<span>接着学。</span></h1><p>选择这份资料的下一步，其他操作留在学习中完成。</p></div><router-link to="/knowledge">打开已有资料 <el-icon><ArrowRight /></el-icon></router-link></header>
    <div class="intake-layout">
      <section class="intake-main" aria-label="添加资料">
        <PrivacyBoundaryNotice @ready="boundaryReady = $event" />
        <div class="purpose-options" aria-label="资料用途">
          <button v-for="option in purposes" :key="option.id" :aria-pressed="intent === option.id" :disabled="hasPending" @click="chooseIntent(option.id)"><el-icon><component :is="option.icon" /></el-icon><span><strong>{{ option.title }}</strong><small>{{ option.description }}</small></span><span class="selection-dot" aria-hidden="true" /></button>
        </div>
        <label v-if="intent === 'archive'" class="archive-consent"><input v-model="archiveConsent" type="checkbox" :disabled="hasPending" /><span>允许将资料内容发送给已配置的模型，生成分类、文件名与日程建议。</span></label>
        <section class="upload-zone" :class="{ 'is-dragover': isDragover, 'is-uploading': isUploading }" aria-label="文件投放区" @dragover.prevent="isDragover = true" @dragleave.prevent="isDragover = false" @drop.prevent="handleDrop">
          <input id="primary-file-upload" ref="fileInput" name="course_files" type="file" :disabled="!canUpload" multiple :accept="acceptedExtensions" @change="handleFileSelect" hidden />
          <div class="paper-stack" aria-hidden="true"><span /><span /><div><el-icon><DocumentAdd /></el-icon></div></div>
          <h2>{{ isUploading ? '资料正在就位' : '把课件或笔记放到这里' }}</h2>
          <p>{{ isUploading ? uploadingFileName : '拖入文件，或从设备中选择。每份最多 25 MB。' }}</p>
          <button class="btn-primary" type="button" :disabled="!canUpload" @click="fileInput?.click()"><el-icon><Plus /></el-icon>{{ isUploading ? '正在处理…' : '选择资料' }}</button>
          <p class="format-note">{{ intent === 'study' ? 'PDF · Word · PPT · 文本 · Markdown · 代码' : 'PDF · Word · PPT · TXT' }}</p>
          <p v-if="intent === 'archive' && !archiveConsent" class="consent-hint">先确认模型授权，即可添加。</p>
        </section>
        <section v-if="uploadQueue.length" class="queue-section" aria-label="资料处理结果" aria-live="polite">
          <div class="queue-heading"><h2>{{ isUploading ? '正在处理资料' : '这次添加的资料' }}</h2><span>{{ completedCount }} / {{ uploadQueue.length }} 份就绪</span></div>
          <p v-if="failedCount" class="queue-error" role="alert">{{ failedCount }} 份未完成，可用原文件重试。<button :disabled="isUploading" @click="retryAllFailed">重试未完成资料</button></p>
          <article v-for="(item, index) in uploadQueue" :key="item.id" class="queue-item">
            <span class="file-mark" aria-hidden="true"><el-icon><Document /></el-icon></span><div class="queue-info"><strong>{{ item.name }}</strong><p>{{ formatSize(item.size) }} · {{ statusText[item.status] }}</p><p v-if="item.error" class="queue-error">{{ item.error }}</p></div>
            <router-link v-if="item.source" class="next-action" :to="{ path: '/ai-tools', query: { source: item.source.source_id } }">开始学习 <el-icon><ArrowRight /></el-icon></router-link>
            <button v-else-if="item.session" class="next-action" @click="reviewResult(item.session)">核对并归档 <el-icon><ArrowRight /></el-icon></button>
            <button v-if="item.status === 'error'" :disabled="isUploading" @click="retryUpload(index)">重试</button><button v-if="item.status !== 'uploading' && item.status !== 'pending'" class="dismiss" :disabled="isUploading" :aria-label="`移除列表中的 ${item.name}`" @click="uploadQueue.splice(index, 1)"><el-icon><Close /></el-icon></button>
          </article>
        </section>
      </section>
      <aside class="next-step" aria-label="下一步指引"><span class="guide-label">{{ intent === 'study' ? '从阅读到理解' : '从散乱到有序' }}</span><h2>{{ intent === 'study' ? '一份资料，一条学习路径。' : '先核对，再放到正确的位置。' }}</h2><ol><li v-for="(step, index) in currentSteps" :key="step.title"><span>{{ index + 1 }}</span><div><strong>{{ step.title }}</strong><p>{{ step.description }}</p></div></li></ol><p class="boundary-note"><el-icon><Lock /></el-icon>{{ intent === 'study' ? '导入与阅读不调用模型。讲解、笔记与练习由你在学习时授权。' : '生成建议后集中核对。归档前可预览，确认后执行，执行后可撤销。' }}</p></aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowRight, Close, Document, DocumentAdd, FolderOpened, Lock, Plus, Reading } from '../icons'
import { importLearningSource, uploadFile, type KnowledgeSourceDetail } from '../services/api'
import { useFileStore } from '../stores/fileStore'
import type { ProcessingSession } from '../types'
import PrivacyBoundaryNotice from '../components/PrivacyBoundaryNotice.vue'

type Intent = 'study' | 'archive'
type QueueItem = { id: number; file: File; name: string; size: number; intent: Intent; status: 'pending' | 'uploading' | 'success' | 'error'; error?: string; source?: KnowledgeSourceDetail; session?: ProcessingSession }
const route = useRoute(), router = useRouter(), fileStore = useFileStore()
const intent = computed<Intent>(() => route.query.intent === 'archive' ? 'archive' : 'study')
const purposes = [{ id: 'study' as const, title: '阅读与学习', description: '读原文，继续讲解、笔记与练习', icon: Reading }, { id: 'archive' as const, title: '整理与归档', description: '核对分类、名称和日程，一次确认', icon: FolderOpened }]
const studySteps = [{ title: '添加一份资料', description: '解析正文，保存到你的学习空间。' }, { title: '打开资料，开始理解', description: '读原文，带着问题获得讲解与引用。' }, { title: '留下笔记，练习巩固', description: '学习结果自动保存，下次接着学。' }]
const archiveSteps = [{ title: '添加待整理文件', description: '模型生成分类、命名与日程建议。' }, { title: '在一屏中集中核对', description: '修改建议，预览目标位置与操作。' }, { title: '确认归档', description: '执行记录可查看，也可以撤销。' }]
const currentSteps = computed(() => intent.value === 'study' ? studySteps : archiveSteps)
const fileInput = ref<HTMLInputElement>(), isDragover = ref(false), isUploading = ref(false), uploadingFileName = ref(''), archiveConsent = ref(false)
const uploadQueue = ref<QueueItem[]>([])
const boundaryReady = ref(false)
watch(intent, () => { archiveConsent.value = false })
const hasPending = computed(() => isUploading.value || uploadQueue.value.some(item => item.status === 'pending'))
const canUpload = computed(() => boundaryReady.value && !hasPending.value && (intent.value === 'study' || archiveConsent.value))
const acceptedExtensions = computed(() => '.doc,.docx,.pdf,.ppt,.pptx,.txt' + (intent.value === 'study' ? ',.md,.markdown,.c,.cpp,.h,.hpp,.py,.java,.js,.ts' : ''))
const failedCount = computed(() => uploadQueue.value.filter(item => item.status === 'error').length)
const completedCount = computed(() => uploadQueue.value.filter(item => item.status === 'success').length)
const statusText = { pending: '等待处理', uploading: '正在解析', success: '已就绪', error: '未完成' }
let nextId = 0
function chooseIntent(value: Intent) { if (!hasPending.value) { archiveConsent.value = false; void router.replace({ path: '/import', query: { intent: value } }) } }
function handleFileSelect(event: Event) { const input = event.target as HTMLInputElement; addToQueue(Array.from(input.files || [])); input.value = '' }
function handleDrop(event: DragEvent) { isDragover.value = false; addToQueue(Array.from(event.dataTransfer?.files || [])) }
function addToQueue(files: File[]) {
  if (!canUpload.value) { ElMessage.info(!boundaryReady.value ? '请先读取数据保存说明并连接服务。' : hasPending.value ? '请等当前资料处理完成。' : '请先确认模型授权。'); return }
  const allowed = new Set(acceptedExtensions.value.split(','))
  for (const file of files) {
    const extension = `.${file.name.split('.').pop()?.toLowerCase() || ''}`
    if (!allowed.has(extension)) { ElMessage.warning(`“${file.name}”格式不支持`); continue }
    if (!file.size || file.size > 25 * 1024 * 1024) { ElMessage.warning(`“${file.name}”为空或超过 25 MB`); continue }
    uploadQueue.value.push({ id: ++nextId, file, name: file.name, size: file.size, intent: intent.value, status: 'pending' })
  }
  void processQueue()
}
async function processQueue(): Promise<void> {
  if (isUploading.value) return
  isUploading.value = true
  try {
    for (const item of uploadQueue.value) {
      if (item.status !== 'pending') continue
      item.status = 'uploading'; uploadingFileName.value = item.name
      try {
        if (item.intent === 'study') item.source = await importLearningSource(item.file)
        else { item.session = await uploadFile(item.file); fileStore.updateFile(item.session); fileStore.setCurrentFile(item.session) }
        item.status = 'success'
      } catch (cause) { item.status = 'error'; item.error = cause instanceof Error ? cause.message : '处理失败，请重试' }
    }
  } finally { isUploading.value = false; uploadingFileName.value = '' }
}
function retryUpload(index: number) {
  const item = uploadQueue.value[index]
  if (!item || hasPending.value || (item.intent === 'archive' && !archiveConsent.value)) { ElMessage.info('归档资料重试前请重新确认模型授权。'); return }
  item.status = 'pending'; item.error = undefined; void processQueue()
}
function retryAllFailed() {
  if (hasPending.value) return
  const eligible = uploadQueue.value.filter(item => item.status === 'error' && (item.intent === 'study' || archiveConsent.value))
  if (!eligible.length) { ElMessage.info('归档资料重试前请重新确认模型授权。'); return }
  eligible.forEach(item => { item.status = 'pending'; item.error = undefined }); void processQueue()
}
function reviewResult(session: ProcessingSession) { fileStore.setCurrentFile(session); void router.push({ path: '/classification', query: { session: session.session_id } }) }
function formatSize(bytes: number) { return bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB` }
function allowLeaving() { if (!hasPending.value) return true; ElMessage.info('资料仍在处理中，完成后即可切换。'); return false }
function guardRefresh(event: Event) { if (hasPending.value) { event.preventDefault(); ElMessage.info('请等资料处理完成后再刷新。') } }
function guardUnload(event: BeforeUnloadEvent) { if (hasPending.value) { event.preventDefault(); event.returnValue = '' } }
onBeforeRouteLeave(allowLeaving)
onBeforeRouteUpdate(allowLeaving)
onMounted(() => { window.addEventListener('filemate:before-refresh', guardRefresh); window.addEventListener('beforeunload', guardUnload) })
onUnmounted(() => { window.removeEventListener('filemate:before-refresh', guardRefresh); window.removeEventListener('beforeunload', guardUnload) })
</script>

<style scoped>
.import-page { max-width:1180px; margin:0 auto; }
.intake-heading { display:flex; align-items:end; justify-content:space-between; gap:24px; margin:10px 0 36px; }
.eyebrow,.guide-label { margin:0 0 16px; font-size:16px; font-weight:600; color:var(--accent); }
.intake-heading h1 { margin:0 0 16px; font-size:clamp(34px,4vw,52px); line-height:1.2; letter-spacing:-.04em; }.intake-heading h1 span { color:var(--accent); }
.intake-heading p:not(.eyebrow) { font-size:18px; line-height:1.7; color:var(--text-secondary); margin:0; }
.intake-heading a { display:inline-flex; align-items:center; gap:8px; min-height:44px; flex-shrink:0; font-size:16px; color:var(--accent); text-decoration:none; }
.intake-layout { display:grid; grid-template-columns:minmax(0,1.7fr) minmax(260px,1fr); gap:28px; align-items:start; }
.intake-main { min-width:0; }.purpose-options { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:20px; }
.purpose-options button { display:flex; align-items:center; gap:12px; text-align:left; padding:20px 16px; min-width:0; border:1px solid var(--border-strong); background:var(--bg-surface); border-radius:14px; color:var(--text-primary); cursor:pointer; transition:border-color .18s,background .18s; }
.purpose-options button[aria-pressed=true] { border-color:var(--accent); background:var(--accent-soft); }.purpose-options .el-icon { font-size:24px; color:var(--accent); flex-shrink:0; }.purpose-options strong { display:block; font-size:18px; }.purpose-options small { display:block; margin-top:8px; font-size:14px; line-height:1.6; color:var(--text-secondary); }.selection-dot { width:16px; height:16px; border:1px solid var(--border-strong); border-radius:50%; margin-left:auto; flex-shrink:0; }.purpose-options button[aria-pressed=true] .selection-dot { background:var(--accent); border:4px solid var(--bg-surface); outline:1px solid var(--accent); }
.upload-zone { position:relative; display:flex; flex-direction:column; align-items:center; overflow:hidden; padding:48px 28px 32px; border:1px dashed var(--accent-border); border-radius:20px; text-align:center; background:radial-gradient(ellipse at top,#e4edff 0,transparent 65%),var(--bg-surface); transition:background .2s,border-color .2s; }.upload-zone.is-dragover { border:2px solid var(--accent); background:var(--accent-soft); }
.paper-stack { position:relative; width:90px; height:90px; margin-bottom:26px; }.paper-stack>span,.paper-stack>div { position:absolute; inset:0; border-radius:14px; border:1px solid var(--accent-border); background:#edf3ff; transform:rotate(-12deg) translate(-7px,4px); transition:transform .22s; }.paper-stack>span:nth-child(2) { transform:rotate(10deg) translate(8px,3px); background:#dae8ff; }.paper-stack>div { display:grid; place-items:center; background:var(--bg-surface); transform:none; color:var(--accent); font-size:40px; }.upload-zone:hover .paper-stack>span { transform:rotate(-18deg) translate(-12px,4px); }.upload-zone:hover .paper-stack>span:nth-child(2) { transform:rotate(16deg) translate(12px,3px); }
.upload-zone h2 { font-size:24px; line-height:1.5; margin:0 0 12px; }.upload-zone p { font-size:16px; line-height:1.7; margin:0 0 24px; overflow-wrap:anywhere; max-width:100%; color:var(--text-secondary); }.upload-zone .format-note { margin:20px 0 0; font-size:14px; }.upload-zone .consent-hint { margin:12px 0 0; color:var(--accent); }
.btn-primary,.next-action { display:inline-flex; align-items:center; justify-content:center; gap:10px; border:0; border-radius:10px; background:var(--accent); color:#fff; padding:0 24px; min-height:52px; font-size:18px; font-weight:600; cursor:pointer; text-decoration:none; }.btn-primary:hover,.next-action:hover { background:var(--accent-hover); }button:disabled { opacity:.55; cursor:not-allowed; }
.next-step { background:#152e63; color:#edf4ff; padding:32px 28px; border-radius:20px; }.guide-label { display:block; color:#c3d6f9; }.next-step h2 { white-space:pre-line; font-size:30px; line-height:1.45; margin:0 0 32px; letter-spacing:-.03em; }.next-step ol { list-style:none; margin:0; padding:0; }.next-step li { display:flex; gap:16px; margin-bottom:28px; }.next-step li>span { flex:0 0 32px; height:32px; border:1px solid #728cbd; border-radius:50%; display:grid; place-items:center; font-size:16px; }.next-step strong { font-size:18px; line-height:1.6; }.next-step p { margin:6px 0 0; color:#c3d6f9; font-size:16px; line-height:1.7; }.next-step .boundary-note { border-top:1px solid #496493; padding-top:22px; font-size:14px; }.boundary-note .el-icon { margin-right:6px; vertical-align:middle; }
.archive-consent { display:flex; align-items:start; gap:12px; padding:16px; margin:0 0 16px; background:var(--accent-soft); border-radius:10px; font-size:16px; line-height:1.6; color:var(--text-secondary); }.archive-consent input { width:18px; height:18px; margin:4px 0 0; flex-shrink:0; accent-color:var(--accent); }
.queue-section { margin-top:28px; }.queue-heading { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:14px; }.queue-heading h2 { margin:0; font-size:22px; }.queue-heading>span { font-size:14px; color:var(--text-secondary); }.queue-item { display:flex; align-items:center; gap:14px; padding:18px 0; border-top:1px solid var(--border-default); }.file-mark { color:var(--accent); font-size:24px; }.queue-info { flex:1; min-width:0; }.queue-info strong { font-size:17px; overflow-wrap:anywhere; }.queue-info p { margin:8px 0 0; color:var(--text-secondary); font-size:14px; line-height:1.5; }.queue-item .next-action { min-height:44px; padding:0 14px; font-size:16px; flex-shrink:0; }.queue-item>button:not(.next-action),.queue-error button { min-height:44px; background:transparent; color:var(--accent); border:0; cursor:pointer; font-size:16px; }.queue-item .dismiss { width:44px; padding:0; flex-shrink:0; }.queue-error,.queue-info .queue-error { color:#a32b39; font-size:16px; line-height:1.6; }
@media(max-width:1100px) { .intake-layout { grid-template-columns:1fr; }.next-step ol { display:grid; grid-template-columns:repeat(3,1fr); gap:24px; }.next-step h2 { white-space:normal; }.next-step li { margin:0; }.next-step .boundary-note { margin-top:24px; } }
@media(max-width:620px) { .intake-heading { flex-direction:column; align-items:start; gap:10px; margin-bottom:24px; }.purpose-options { grid-template-columns:1fr; }.purpose-options button { padding:16px; }.next-step { padding:28px 22px; }.next-step ol { grid-template-columns:1fr; gap:24px; }.upload-zone { padding:32px 18px; }.upload-zone h2 { font-size:22px; }.queue-item { flex-wrap:wrap; }.queue-info { flex-basis:calc(100% - 60px); }.queue-item .next-action { margin-left:38px; } }
@media(prefers-reduced-motion:reduce) { .paper-stack>span,.paper-stack>div,.purpose-options button,.upload-zone { transition:none; } }
</style>
