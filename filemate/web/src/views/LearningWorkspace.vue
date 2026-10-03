<template>
  <div class="learning-workspace">
    <header class="workspace-heading"><div><h1>把知识，<span>读明白。</span></h1><p>一份资料，串起讲解、笔记与练习。</p></div><router-link to="/goals">我的学习路径 <el-icon><ArrowRight /></el-icon></router-link></header>
    <div v-if="error" class="workspace-error" role="alert">{{ error }} <button type="button" @click="reload">重新读取</button></div>
    <nav class="mobile-panes" aria-label="切换学习面板"><button v-for="pane in panes" :key="pane.id" :aria-pressed="activePane === pane.id" @click="switchPane(pane.id)">{{ pane.label }}</button></nav>
    <label v-if="source" class="model-consent"><input v-model="authorized" type="checkbox" :disabled="busy" /><span>允许本次学习将资料片段和问题发送给已配置的模型</span></label>
    <div class="desk" :data-pane="activePane">
      <aside class="source-pane" aria-label="学习资料与会话">
        <div class="pane-heading"><h2>我的资料</h2><span>{{ sources.length }}</span></div>
        <button class="import-button" :disabled="busy" @click="fileInput?.click()"><el-icon><Plus /></el-icon>{{ importing ? '正在解析资料…' : '添加资料' }}</button>
        <input ref="fileInput" class="file-input" type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.txt,.md,.markdown,.c,.cpp,.h,.hpp,.py,.java,.js,.ts" aria-label="上传学习资料" @change="importFile" />
        <label class="source-search"><el-icon><Search /></el-icon><input v-model="search" placeholder="查找资料" aria-label="查找学习资料" /></label>
        <p v-if="loadingSources" class="quiet" role="status">读取资料中…</p>
        <div v-else class="source-list"><button v-for="item in filteredSources" :key="item.source_id" :class="{ selected: source?.source_id === item.source_id }" :aria-pressed="source?.source_id === item.source_id" :disabled="busy" @click="navigateSource(item.source_id)"><el-icon><Document /></el-icon><span>{{ item.original_name }}<small>{{ item.text_length?.toLocaleString() || '—' }} 字</small></span></button><p v-if="!filteredSources.length" class="quiet">{{ search ? '没有匹配的资料' : '先添加一份课件或笔记。' }}</p></div>
        <template v-if="source"><div class="session-heading"><h2>这份资料的对话</h2><button :disabled="busy" aria-label="新建对话" @click="newSession"><el-icon><Plus /></el-icon></button></div><div class="session-list"><button v-for="session in sessions" :key="session.ctx_id" :disabled="busy" :aria-pressed="context?.ctx_id === session.ctx_id" @click="navigateSource(source.source_id, session.ctx_id)"><el-icon><ChatDotRound /></el-icon><span>{{ session.message_count ? `${session.message_count} 条消息` : '新对话' }}<small>{{ formatDate(session.updated_at || session.created_at) }}</small></span></button></div></template>
        <p class="local-note"><el-icon><FolderOpened /></el-icon>资料保存在当前学习空间<br />阅读与导入不调用模型</p>
      </aside>

      <section class="conversation-pane" aria-label="资料对话">
        <header class="conversation-heading"><div><small>{{ source ? '正在学习' : '从一份资料开始' }}</small><h2>{{ source?.original_name || '今天，想弄懂什么？' }}</h2></div><span v-if="context" class="saved-indicator">会话可恢复</span></header>
        <div v-if="loading" class="blank-state" role="status"><el-icon><Reading /></el-icon><h3>正在打开资料与学习记录…</h3></div>
        <div v-else-if="!source" class="blank-state"><el-icon><Reading /></el-icon><h3>把课件放进来，让学习接着发生。</h3><p>添加资料后即可读原文。需要讲解时再开启模型，也可以打开已有笔记和练习。</p><button class="primary" :disabled="busy" @click="fileInput?.click()">添加第一份资料</button><small>课件、Markdown、代码笔记 · 最大 25 MB</small></div>
        <template v-else>
          <div ref="messageScroll" class="conversation-scroll" aria-live="polite">
            <div v-if="!context?.chat_history.length" class="conversation-intro"><span class="intro-line"></span><h3>不急着得到答案，<br />先找到你想理解的那一点。</h3><p>读原文、记笔记，或把卡住的概念交给我。回答会附上可核对的资料片段。</p><div class="starter-prompts"><button v-for="prompt in prompts" :key="prompt" @click="questionText = prompt; composer?.focus()">{{ prompt }}<el-icon><ArrowRight /></el-icon></button></div></div>
            <article v-for="(message, i) in context?.chat_history" :key="i" class="message" :class="message.role"><small>{{ message.role === 'user' ? '我' : 'FileMate' }}</small><p>{{ message.content }}</p><div v-if="message.citations?.length" class="citations"><button v-for="citation in message.citations" :key="citation.id" @click="showCitation(citation)"><el-icon><Document /></el-icon>引用 {{ citation.id }} · {{ citation.page_number ? `第 ${citation.page_number} 页` : '原文片段' }}</button></div><router-link v-if="digitalHumanEnabled && message.role === 'assistant'" class="speak-answer" :to="{ path: '/digital-human', query: { ctx: context?.ctx_id, message: i } }"><el-icon><Microphone /></el-icon>让 AI 导师讲解</router-link></article>
            <p v-if="sending" class="pending" role="status">正在检索资料并组织回答…</p>
          </div>
          <div class="composer-area">
            <div class="mode-switch" aria-label="学习方式"><button v-for="mode in modes" :key="mode.id" :aria-pressed="chatMode === mode.id" :disabled="sending" @click="chatMode = mode.id">{{ mode.label }}</button></div>
            <form class="composer" @submit.prevent="send"><textarea ref="composer" v-model="questionText" rows="3" maxlength="4000" aria-label="向资料提问" :placeholder="modePlaceholder" :disabled="busy" @keydown.enter.ctrl.prevent="send" /><div><small>Ctrl + Enter 发送</small><button class="primary" :disabled="busy || !context || !questionText.trim() || !authorized" type="submit"><el-icon><Promotion /></el-icon>发送</button></div></form>
            <p v-if="actionError" class="inline-error" role="alert">{{ actionError }}</p>
          </div>
        </template>
      </section>

      <aside class="resource-pane" aria-label="学习内容与原文">
        <nav class="resource-tabs" aria-label="阅读内容"><button :aria-pressed="resourceTab === 'artifacts'" @click="resourceTab = 'artifacts'">学习内容 <span>{{ artifacts.length }}</span></button><button :aria-pressed="resourceTab === 'source'" @click="resourceTab = 'source'">原文</button></nav>
        <div v-if="!source" class="resource-empty"><el-icon><Notebook /></el-icon><h3>把思考留在旁边</h3><p>笔记、卡片和练习会在这里打开，阅读时不必离开对话。</p></div>
        <div v-if="source" v-show="resourceTab === 'source'" ref="sourceReader" class="source-reader"><div v-if="citation" class="citation-focus"><button aria-label="关闭引用片段" @click="citation = null">关闭片段</button><strong>引用 {{ citation.id }} · {{ citation.source_name }}</strong><p>{{ citation.excerpt }}</p></div><h3>解析正文</h3><small>按文件解析顺序展示；图片与复杂排版可能不保留。</small><pre>{{ source.raw_text }}</pre></div>
        <div v-if="source" v-show="resourceTab === 'artifacts'" class="artifact-workbench">
          <div v-if="artifacts.length && !creatingContent" class="reading-toolbar"><strong>继续读，接着想。</strong><button @click="creatingContent = true"><el-icon aria-hidden="true"><Plus /></el-icon>创建学习内容</button></div>
          <section v-if="creatingContent || !artifacts.length" class="generation-controls" aria-label="创建学习内容">
            <div class="creator-heading"><h2>把资料变成<span>下一步。</span></h2><button v-if="artifacts.length" :disabled="busy" @click="creatingContent = false">返回阅读</button></div>
            <div class="generation-kinds"><button v-for="task in generationTasks" :key="task.id" :aria-pressed="generationKind === task.id" :disabled="busy" @click="generationKind = task.id"><el-icon aria-hidden="true"><component :is="task.icon" /></el-icon>{{ task.label }}</button></div>
            <p class="task-purpose">{{ generationTask.description }}</p>
            <div class="generation-submit">
              <fieldset v-if="generationKind === 'questions' || generationKind === 'knowledge_cards'" :disabled="busy" class="generation-count"><legend>最多生成</legend><label v-for="limit in [5, 10]" :key="limit"><input v-model="count" type="radio" name="generation-count" :value="limit" />{{ limit }}{{ generationKind === 'questions' ? '题' : '张' }}</label></fieldset>
              <button class="primary" :disabled="busy || !authorized" @click="generate">{{ generating ? '正在生成…' : `生成${generationTask.label}` }}<el-icon v-if="!generating" aria-hidden="true"><ArrowRight /></el-icon></button>
            </div>
            <p v-if="!authorized" class="generation-note">勾选上方模型授权后，即可生成。</p>
          </section>
          <p v-if="generationError" role="alert" class="inline-error">{{ generationError }} <button :disabled="busy || !authorized" @click="generate">重试</button></p>
          <p v-if="generating" class="generation-note" role="status">正在生成，完成后会自动保存到这份资料。无需重复上传。</p>
          <section v-if="artifacts.length" class="saved-contents" aria-label="已保存的学习内容"><h2>接着学</h2><div class="artifact-picker"><button v-for="item in artifacts" :key="item.artifact_id" :aria-pressed="activeArtifactId === item.artifact_id" :title="item.title" @click="selectArtifact(item.artifact_id)"><span>{{ artifactLabel(item.artifact_type) }}</span><strong>{{ item.title }}</strong><time>{{ formatDate(item.created_at) }}</time></button></div></section>
          <KeepAlive><LearningArtifact v-if="activeArtifact" :key="activeArtifact.artifact_id" :artifact="activeArtifact" /></KeepAlive>
          <div v-if="!activeArtifact" class="resource-empty"><el-icon><Notebook /></el-icon><h3>还没有学习内容</h3><p>先整理一份笔记，再用卡片回忆、用练习检验。不必一次做完。</p></div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight, ChatDotRound, Collection, Document, FolderOpened, Microphone, Notebook, Plus, Promotion, Reading, Search, Tickets } from '@element-plus/icons-vue'
import LearningArtifact from '../components/LearningArtifact.vue'
import { askAI, createSourceContext, generateSourceArtifact, getAIContext, getKnowledgeArtifacts, getKnowledgeSources, getLearningSource, importLearningSource, listAIContexts, type AICitation, type AIContextDetail, type AISessionSummary, type KnowledgeArtifact, type KnowledgeSource, type KnowledgeSourceDetail, type WorkspaceArtifactKind } from '../services/api'

const route = useRoute(); const router = useRouter()
const digitalHumanEnabled = import.meta.env.VITE_ENABLE_DIGITAL_HUMAN !== 'false'
const sources = ref<KnowledgeSource[]>([]); const source = ref<KnowledgeSourceDetail | null>(null)
const sessions = ref<AISessionSummary[]>([]); const context = ref<AIContextDetail | null>(null)
const artifacts = ref<KnowledgeArtifact[]>([]); const activeArtifactId = ref('')
const activeArtifact = computed(() => artifacts.value.find(item => item.artifact_id === activeArtifactId.value))
const search = ref(''); const filteredSources = computed(() => sources.value.filter(item => item.original_name.toLocaleLowerCase().includes(search.value.toLocaleLowerCase())))
const loadingSources = ref(false); const loading = ref(false); const importing = ref(false); const sending = ref(false); const generating = ref(false)
const busy = computed(() => loading.value || importing.value || sending.value || generating.value)
const error = ref(''); const actionError = ref(''); const generationError = ref(''); const authorized = ref(false)
const fileInput = ref<HTMLInputElement>(); const composer = ref<HTMLTextAreaElement>(); const messageScroll = ref<HTMLDivElement>()
const sourceReader = ref<HTMLDivElement>()
const questionText = ref(''); const resourceTab = ref<'artifacts' | 'source'>('artifacts'); const citation = ref<AICitation | null>(null)
const activePane = ref('chat'); const panes = [{ id: 'sources', label: '资料' }, { id: 'chat', label: '对话' }, { id: 'resources', label: '学习内容' }]
function switchPane(id: string): void {
  activePane.value = id
  if (id === 'resources') resourceTab.value = 'artifacts'
}
const generationKind = ref<WorkspaceArtifactKind>('notes'); const count = ref(5)
const creatingContent = ref(true)
const generationTasks = [
  { id: 'notes' as const, label: '笔记', description: '把重点理成层次，留下一份可反复阅读的笔记。', icon: Notebook },
  { id: 'knowledge_cards' as const, label: '卡片', description: '先回忆，再翻面。用问题把知识留得更牢。', icon: Collection },
  { id: 'questions' as const, label: '练习', description: '逐题作答，保存结果，再到错题本继续复盘。', icon: Tickets },
  { id: 'summary' as const, label: '摘要', description: '先抓住主线，再回到原文核对细节。', icon: Document },
]
const generationTask = computed(() => generationTasks.find(task => task.id === generationKind.value)!)
function artifactLabel(kind: string): string { return generationTasks.find(task => task.id === kind)?.label || '学习内容' }
async function selectArtifact(id: string): Promise<void> {
  if (!artifacts.value.some(item => item.artifact_id === id)) return
  creatingContent.value = false
  activeArtifactId.value = id; resourceTab.value = 'artifacts'; activePane.value = 'resources'
  await router.replace({ path: '/ai-tools', query: { ...route.query, artifact: id } })
}
const chatMode = ref<'answer' | 'socratic' | 'feynman'>('answer')
const modes = [{ id: 'answer' as const, label: '直接讲解' }, { id: 'socratic' as const, label: '引导我思考' }, { id: 'feynman' as const, label: '听我讲一遍' }]
const modePlaceholder = computed(() => ({ answer: '这份资料里，有什么想问的？', socratic: '告诉我你卡在哪，我用追问帮你理清。', feynman: '试着用自己的话解释一个概念，我来帮你找遗漏。' }[chatMode.value]))
const prompts = ['请解释这份资料的核心概念。', '这些知识可以用来解决什么问题？', '我想检验自己的理解，从哪里开始？']
let epoch = 0
let internalNavigation = false
const message = (cause: unknown) => cause instanceof Error ? cause.message : '操作失败，请重试'
function formatDate(value?: string) { return value ? new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '' }
async function loadSources() { loadingSources.value = true; try { sources.value = await getKnowledgeSources(200) } finally { loadingSources.value = false } }
async function allowLeaving(): Promise<boolean> {
  if (busy.value) { ElMessage.info('请等当前学习操作完成后再切换。'); return false }
  if (!questionText.value.trim()) return true
  try {
    await ElMessageBox.confirm('输入的问题尚未发送。', '切换学习内容？', {
      confirmButtonText: '舍弃问题并切换', cancelButtonText: '继续编辑', type: 'warning',
    })
    return true
  } catch { return false }
}
async function navigateSource(id: string, ctx?: string, approved = false) {
  if (!approved && !await allowLeaving()) return
  internalNavigation = true
  try { await router.push({ path: '/ai-tools', query: { source: id, ...(ctx ? { ctx } : {}) } }); activePane.value = 'chat' }
  finally { internalNavigation = false }
}
function guardRefresh(event: Event): void {
  if (!busy.value && !questionText.value.trim()) return
  event.preventDefault()
  ElMessage.info(busy.value ? '请等当前学习操作完成后再刷新。' : '问题尚未发送，请先发送或清空后再刷新。')
}
function guardUnload(event: BeforeUnloadEvent): void {
  if (busy.value || questionText.value.trim()) { event.preventDefault(); event.returnValue = '' }
}
onBeforeRouteLeave(allowLeaving)
onBeforeRouteUpdate(to => {
  if (internalNavigation || (to.query.source === source.value?.source_id && to.query.ctx === context.value?.ctx_id)) return true
  return allowLeaving()
})
async function openRoute() {
  const token = ++epoch
  loading.value = true; error.value = ''; actionError.value = ''; generationError.value = ''; authorized.value = false
  source.value = null; context.value = null; artifacts.value = []; sessions.value = []; citation.value = null; questionText.value = ''
  let id = typeof route.query.source === 'string' ? route.query.source : ''
  const ctxId = typeof route.query.ctx === 'string' ? route.query.ctx : ''
  try {
    const restored = ctxId ? await getAIContext(ctxId) : null
    if (!id) id = restored?.source_id || ''
    if (!id) return
    const [detail, contents, history] = await Promise.all([getLearningSource(id), getKnowledgeArtifacts(id), listAIContexts(id)])
    if (token !== epoch) return
    if (restored && restored.source_id !== id) throw new Error('会话不属于这份资料，请从左侧重新打开。')
    const active = restored || (history[0] ? await getAIContext(history[0].ctx_id) : await createSourceContext(id))
    if (token !== epoch) return
    source.value = detail; artifacts.value = contents; sessions.value = history; context.value = active
    creatingContent.value = contents.length === 0
    const requestedArtifact = typeof route.query.artifact === 'string' ? route.query.artifact : ''
    activeArtifactId.value = contents.find(item => item.artifact_id === requestedArtifact)?.artifact_id || contents[0]?.artifact_id || ''
    if (requestedArtifact && activeArtifactId.value === requestedArtifact) {
      resourceTab.value = 'artifacts'; activePane.value = 'resources'
    }
    if (!history.some(item => item.ctx_id === active.ctx_id)) {
      const updatedSessions = await listAIContexts(id)
      if (token !== epoch) return
      sessions.value = updatedSessions
    }
    if (token !== epoch) return
    // 已加载的 source / ctx 由监听器去重，只更新可恢复地址。
    if (route.query.ctx !== active.ctx_id || route.query.source !== id) {
      await router.replace({ path: '/ai-tools', query: { source: id, ctx: active.ctx_id, ...(requestedArtifact ? { artifact: requestedArtifact } : {}) } })
    }
    await scrollBottom()
  } catch (cause) { if (token === epoch) error.value = message(cause) }
  finally { if (token === epoch) loading.value = false }
}
async function reload() { if (!await allowLeaving()) return; try { error.value = ''; await loadSources(); await openRoute() } catch (cause) { error.value = message(cause) } }
async function importFile(event: Event) {
  const input = event.target as HTMLInputElement; const file = input.files?.[0]; input.value = ''
  if (!file || busy.value) return
  if (file.size > 25 * 1024 * 1024) { error.value = '文件不能超过 25 MB'; return }
  if (!await allowLeaving()) return
  importing.value = true; error.value = ''
  try { const imported = await importLearningSource(file); await loadSources(); await navigateSource(imported.source_id, undefined, true) }
  catch (cause) { error.value = message(cause) }
  finally { importing.value = false }
}
async function newSession() {
  if (!source.value || busy.value) return
  if (!await allowLeaving()) return
  loading.value = true
  try { const active = await createSourceContext(source.value.source_id); await navigateSource(source.value.source_id, active.ctx_id, true) }
  catch (cause) { error.value = message(cause) }
  finally { loading.value = false }
}
async function scrollBottom() { await nextTick(); messageScroll.value?.scrollTo({ top: messageScroll.value.scrollHeight }) }
async function send() {
  if (!context.value || busy.value || !authorized.value || !questionText.value.trim()) return
  const token = epoch; const ctx = context.value; const question = questionText.value.trim()
  sending.value = true; actionError.value = ''
  try {
    const result = await askAI(ctx.ctx_id, question, undefined, chatMode.value)
    if (token !== epoch) return
    // 问答接口只返回最近十条消息，不能因此截断当前已打开的完整历史。
    ctx.chat_history.push({ role: 'user', content: question }, { role: 'assistant', content: result.answer, citations: result.citations })
    questionText.value = ''
    const updatedSessions = await listAIContexts(source.value!.source_id)
    if (token !== epoch) return
    sessions.value = updatedSessions; await scrollBottom()
  } catch (cause) { if (token === epoch) actionError.value = `${message(cause)}。问题已保留，可再次发送。` }
  finally { sending.value = false }
}
async function generate() {
  if (!source.value || busy.value || !authorized.value) return
  const token = epoch; const id = source.value.source_id
  generating.value = true; generationError.value = ''
  try { const artifact = await generateSourceArtifact(id, generationKind.value, count.value); if (token !== epoch) return; artifacts.value.unshift(artifact); await selectArtifact(artifact.artifact_id) }
  catch (cause) { if (token === epoch) generationError.value = message(cause) }
  finally { generating.value = false }
}
async function showCitation(item: AICitation) {
  citation.value = item; resourceTab.value = 'source'; activePane.value = 'resources'
  await nextTick()
  sourceReader.value?.scrollTo({ top: 0 })
}
watch(() => [route.query.source, route.query.ctx, route.query.artifact], () => {
  if (source.value?.source_id === route.query.source && context.value?.ctx_id === route.query.ctx) {
    const requested = typeof route.query.artifact === 'string' ? route.query.artifact : ''
    if (requested && artifacts.value.some(item => item.artifact_id === requested)) {
      activeArtifactId.value = requested; resourceTab.value = 'artifacts'; activePane.value = 'resources'
    }
    return
  }
  void openRoute()
})
onMounted(() => { void reload(); window.addEventListener('filemate:before-refresh', guardRefresh); window.addEventListener('beforeunload', guardUnload) })
onUnmounted(() => { epoch++; window.removeEventListener('filemate:before-refresh', guardRefresh); window.removeEventListener('beforeunload', guardUnload) })
</script>


<style scoped>
.learning-workspace { color: var(--text-primary); max-width: 1600px; margin: 0 auto; padding: 8px 0 28px; }
.workspace-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 20px; padding: 24px 28px; margin-bottom: 24px; border-radius: 22px; background: var(--panel-tint); border: 1px solid var(--border-subtle); }
.workspace-heading h1 { font-size: clamp(36px, 4vw, 48px); line-height: 1.25; margin: 0 0 16px; font-weight: 750; letter-spacing: -.04em; }
.workspace-heading h1 span { color: var(--accent); }
.workspace-heading p { margin: 0; color: var(--text-secondary); font-size: 19px; }
.workspace-heading a { display: inline-flex; align-items: center; gap: 12px; color: var(--accent); text-decoration: none; font-size: 17px; min-height: 48px; }
.mobile-panes { display: flex; gap: 12px; margin-bottom: 18px; }
.learning-workspace button { font: inherit; font-size: 17px; color: inherit; cursor: pointer; min-height: 48px; border: 1px solid var(--border-subtle); background: var(--bg-reading); border-radius: 10px; padding: 10px 16px; transition: background-color .18s, border-color .18s; }
.learning-workspace button:disabled { opacity: .5; cursor: default; }
.learning-workspace button:focus-visible, .learning-workspace input:focus-visible, .learning-workspace textarea:focus-visible, .learning-workspace a:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.mobile-panes button { min-width: 130px; font-size: 18px; min-height: 54px; }
.mobile-panes button[aria-pressed=true] { background: var(--accent); color: white; border-color: var(--accent); font-weight: 750; }
.learning-workspace .primary { background: var(--accent); color: white; border-color: var(--accent); display: inline-flex; align-items: center; justify-content: center; gap: 12px; }
.model-consent { display: flex; align-items: flex-start; gap: 12px; font-size: 17px; line-height: 1.7; padding: 14px 18px; background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 12px; color: var(--text-secondary); margin: 0 0 20px; cursor: pointer; }
.model-consent input { width: 19px; height: 19px; flex: 0 0 auto; accent-color: var(--accent); margin: 4px 0 0; }
.desk { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr); border: 1px solid var(--border-subtle); border-radius: 22px; overflow: hidden; background: var(--bg-reading); min-height: 740px; height: clamp(740px, calc(100dvh - 285px), 1050px); }
.desk[data-pane=resources] { grid-template-columns: minmax(0, .85fr) minmax(0, 1.15fr); }
.desk > * { animation: pane-in .22s ease-out; }
.source-pane { display: none; padding: 30px; overflow: auto; background: var(--panel-tint); gap: 22px; min-width: 0; }
.desk[data-pane=sources] { grid-template-columns: 1fr; }
.desk[data-pane=sources] > .source-pane { display: flex; flex-direction: column; }
.desk[data-pane=sources] > .conversation-pane, .desk[data-pane=sources] > .resource-pane { display: none; }
.pane-heading, .session-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.pane-heading h2, .session-heading h2 { font-size: 26px; margin: 0; font-weight: 750; }
.pane-heading span { font-size: 20px; color: var(--accent); }
.session-heading { border-top: 1px solid var(--border-subtle); padding-top: 26px; }
.import-button { display: inline-flex; align-items: center; justify-content: center; gap: 12px; align-self: flex-start; color: var(--accent) !important; }
.file-input { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
.source-search { display: flex; align-items: center; padding: 0 16px; background: var(--bg-reading); border: 1px solid var(--border-subtle); border-radius: 10px; gap: 12px; color: var(--text-secondary); max-width: 650px; }
.source-search input { border: 0; background: transparent; width: 100%; min-width: 0; min-height: 52px; font: inherit; font-size: 18px; outline-offset: -2px; }
.source-list, .session-list { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.source-list button, .session-list button { display: flex; align-items: flex-start; gap: 14px; text-align: left; background: var(--bg-surface); font-size: 18px; line-height: 1.7; padding: 20px; }
.source-list button > span, .session-list button > span { min-width: 0; overflow-wrap: anywhere; }
.source-list .el-icon, .session-list .el-icon { font-size: 24px; flex-shrink: 0; margin-top: 4px; color: var(--accent); }
.source-list button.selected, .session-list button[aria-pressed=true] { background: var(--accent-soft); border-color: var(--accent); }
.source-list small, .session-list small { display: block; font-size: 15px; color: var(--text-secondary); margin-top: 8px; }
.local-note { margin: auto 0 0; padding-top: 10px; font-size: 16px; line-height: 1.8; color: var(--text-secondary); }
.local-note .el-icon { margin-right: 8px; }
.quiet { font-size: 18px; line-height: 1.8; color: var(--text-secondary); }
.conversation-pane { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
.conversation-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 24px; border-bottom: 1px solid var(--border-subtle); }
.conversation-heading small { font-size: 15px; color: var(--text-secondary); }
.conversation-heading h2 { font-size: 23px; margin: 8px 0 0; line-height: 1.5; overflow-wrap: anywhere; }
.saved-indicator { font-size: 14px; color: var(--accent); white-space: nowrap; }
.conversation-scroll { flex: 1; overflow: auto; padding: 26px; min-height: 160px; }
.conversation-intro { padding: 10px 0; }
.intro-line { display: block; width: 50px; height: 4px; background: var(--accent); margin-bottom: 22px; }
.conversation-intro h3 { font-size: 29px; line-height: 1.55; letter-spacing: -.035em; font-weight: 650; margin: 0 0 20px; }
.conversation-intro p { font-size: 18px; color: var(--text-secondary); line-height: 1.9; margin: 0 0 26px; }
.starter-prompts { display: flex; flex-direction: column; gap: 12px; }
.starter-prompts button { text-align: left; display: flex; align-items: center; justify-content: space-between; gap: 12px; background: var(--bg-base); line-height: 1.6; }
.message { padding: 0 0 28px; font-size: 18px; line-height: 1.95; }
.message small { font-size: 15px; color: var(--accent); font-weight: 750; }
.message p { margin: 8px 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.message.user { background: var(--accent-soft); padding: 18px; margin-bottom: 26px; border-radius: 14px; }
.citations { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
.citations button { font-size: 15px; display: inline-flex; align-items: center; gap: 8px; }
.composer-area { border-top: 1px solid var(--border-subtle); padding: 18px 24px 24px; background: var(--bg-reading); }
.mode-switch { display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
.mode-switch button { font-size: 16px; padding: 8px 12px; }
.mode-switch button[aria-pressed=true] { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
.composer { border: 1px solid var(--border-strong); border-radius: 12px; padding: 16px; }
.composer textarea { border: 0; width: 100%; resize: vertical; min-height: 85px; max-height: 180px; box-sizing: border-box; font: inherit; font-size: 18px; line-height: 1.8; color: inherit; }
.composer > div { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.composer small { font-size: 14px; color: var(--text-secondary); }
.resource-pane { background: var(--bg-reading); border-left: 1px solid var(--border-subtle); display: flex; flex-direction: column; min-height: 0; min-width: 0; }
.resource-tabs { display: flex; gap: 22px; padding: 16px 24px 0; border-bottom: 1px solid var(--border-subtle); }
.resource-tabs button { border: 0; border-bottom: 3px solid transparent; background: none; border-radius: 0; font-size: 19px; padding: 10px 0 16px; }
.resource-tabs button[aria-pressed=true] { border-bottom-color: var(--accent); color: var(--accent); font-weight: 750; }
.resource-tabs span { font-size: 15px; margin-left: 8px; }
.artifact-workbench, .source-reader { padding: 24px; overflow: auto; flex: 1; min-height: 0; }
.generation-controls { padding-bottom: 26px; margin-bottom: 24px; border-bottom: 1px solid var(--border-subtle); }
.reading-toolbar, .creator-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 14px; margin-bottom: 22px; }
.reading-toolbar strong { font-size: 22px; }
.reading-toolbar button { display: inline-flex; align-items: center; gap: 10px; color: var(--accent); }
.creator-heading h2 { margin: 0 !important; }
.creator-heading button { font-size: 16px; }
.generation-controls h2, .saved-contents h2 { font-size: 25px; letter-spacing: -.025em; margin: 0 0 18px; }
.generation-controls h2 span { color: var(--accent); }
.generation-kinds { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.generation-kinds button { display: flex; align-items: center; justify-content: center; gap: 10px; min-width: 0; font-size: 18px; min-height: 54px; padding: 10px; }
.generation-kinds button[aria-pressed=true] { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); font-weight: 750; }
.task-purpose { font-size: 17px; color: var(--text-secondary); line-height: 1.8; margin: 18px 0; }
.generation-submit { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 18px; }
.generation-submit .primary { min-height: 52px; }
.generation-count { display: flex; gap: 12px; padding: 0; margin: 0; border: 0; min-width: 0; }
.generation-count legend { font-size: 15px; color: var(--text-secondary); margin-bottom: 8px; }
.generation-count label { display: flex; align-items: center; gap: 8px; font-size: 17px; min-height: 44px; cursor: pointer; }
.generation-count input { accent-color: var(--accent); width: 18px; height: 18px; margin: 0; }
.generation-note { font-size: 16px; line-height: 1.8; color: var(--text-secondary); margin: 18px 0 0; }
.saved-contents { margin-bottom: 30px; }
.artifact-picker { display: flex; gap: 12px; overflow-x: auto; padding: 4px 3px 12px; }
.artifact-picker button { flex: 0 0 190px; max-width: 85%; text-align: left; padding: 12px 14px; line-height: 1.6; }
.artifact-picker button[aria-pressed=true] { background: var(--accent-soft); border-color: var(--accent); }
.artifact-picker strong { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; overflow-wrap: anywhere; font-size: 18px; margin: 6px 0; }
.artifact-picker span, .artifact-picker time { font-size: 14px; color: var(--text-secondary); }
.resource-empty, .blank-state { display: flex; flex-direction: column; align-items: flex-start; justify-content: center; padding: 34px 28px; line-height: 1.85; color: var(--text-secondary); flex: 1; }
.resource-empty > .el-icon, .blank-state > .el-icon { font-size: 44px; color: var(--accent); margin-bottom: 22px; }
.resource-empty h3, .blank-state h3 { font-size: 28px; line-height: 1.6; color: var(--text-primary); font-weight: 650; margin: 0 0 18px; }
.resource-empty p, .blank-state p { font-size: 18px; margin: 0 0 24px; }
.blank-state small { font-size: 15px; margin-top: 20px; }
.source-reader pre { font-family: inherit; font-size: 18px; line-height: 2; white-space: pre-wrap; overflow-wrap: anywhere; }
.source-reader h3 { font-size: 25px; margin: 0 0 14px; }
.source-reader small { color: var(--text-secondary); font-size: 15px; }
.citation-focus { padding: 20px; margin-bottom: 24px; background: var(--accent-soft); border-left: 3px solid var(--accent); line-height: 1.9; font-size: 18px; }
.citation-focus button { display: block; font-size: 16px; margin-bottom: 14px; }
.citation-focus p { white-space: pre-wrap; overflow-wrap: anywhere; }
.pending { color: var(--text-secondary); font-size: 17px; }
.workspace-error, .inline-error { color: #9a3333; background: #fcf0ed; padding: 16px; font-size: 17px; line-height: 1.8; overflow-wrap: anywhere; }
.workspace-error { margin-bottom: 18px; }
.speak-answer { display: inline-flex; align-items: center; gap: 10px; min-height: 48px; margin-top: 12px; padding: 0 16px; border: 1px solid var(--border-strong); border-radius: 10px; color: var(--accent); text-decoration: none; font-size: 16px; font-weight: 650; }
.speak-answer:hover { background: var(--accent-soft); }
@keyframes pane-in { from { opacity: .4; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@media (max-width: 1200px) { .generation-kinds { grid-template-columns: repeat(2, minmax(0, 1fr)); } .saved-indicator { display: none; } .source-list, .session-list { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 1050px) {
  .desk, .desk[data-pane=resources] { display: block; height: clamp(760px, calc(100dvh - 285px), 1050px); }
  .desk > .source-pane, .desk > .conversation-pane, .desk > .resource-pane { display: none; height: 100%; box-sizing: border-box; border: 0; }
  .desk[data-pane=sources] > .source-pane, .desk[data-pane=chat] > .conversation-pane, .desk[data-pane=resources] > .resource-pane { display: flex; }
  .generation-kinds { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
@media (max-width: 600px) {
  .workspace-heading { padding: 24px 20px; gap: 12px; } .workspace-heading p { font-size: 18px; }
  .mobile-panes { gap: 8px; } .mobile-panes button { min-width: 0; flex: 1; padding: 10px 8px; font-size: 17px; }
  .model-consent { font-size: 16px; padding: 14px; } .desk { border-radius: 18px; }
  .source-pane, .conversation-heading, .conversation-scroll, .artifact-workbench, .source-reader, .composer-area { padding: 22px 18px; }
  .source-list, .session-list { grid-template-columns: 1fr; } .conversation-intro h3 { font-size: 27px; }
  .generation-kinds { grid-template-columns: repeat(2, minmax(0, 1fr)); } .resource-tabs { padding: 14px 18px 0; }
  .generation-submit .primary { width: 100%; } .resource-empty, .blank-state { padding: 26px 20px; }
  .mode-switch { gap: 6px; } .mode-switch button { font-size: 15px; padding: 8px 10px; }
}
@media (prefers-reduced-motion: reduce) { .desk > * { animation: none; } }
</style>
