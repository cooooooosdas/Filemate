<template>
  <div class="learning-workspace">
    <header class="workspace-heading"><div><h1>学习工作区</h1><p>让资料、思考和练习，停留在同一张书桌上。</p></div><router-link to="/goals">我的学习路径 <el-icon><ArrowRight /></el-icon></router-link></header>
    <div v-if="error" class="workspace-error" role="alert">{{ error }} <button type="button" @click="reload">重新读取</button></div>
    <nav class="mobile-panes" aria-label="切换学习面板"><button v-for="pane in panes" :key="pane.id" :aria-pressed="activePane === pane.id" @click="activePane = pane.id">{{ pane.label }}</button></nav>
    <div class="desk" :data-pane="activePane">
      <aside class="source-pane" aria-label="学习资料与会话">
        <div class="pane-heading"><h2>我的资料</h2><span>{{ sources.length }}</span></div>
        <button class="import-button" :disabled="busy" @click="fileInput?.click()"><el-icon><Plus /></el-icon>{{ importing ? '正在本地解析…' : '添加资料' }}</button>
        <input ref="fileInput" class="file-input" type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.txt" aria-label="上传学习资料" @change="importFile" />
        <label class="source-search"><el-icon><Search /></el-icon><input v-model="search" placeholder="查找资料" aria-label="查找学习资料" /></label>
        <p v-if="loadingSources" class="quiet" role="status">读取资料中…</p>
        <div v-else class="source-list"><button v-for="item in filteredSources" :key="item.source_id" :class="{ selected: source?.source_id === item.source_id }" :aria-pressed="source?.source_id === item.source_id" :disabled="busy" @click="navigateSource(item.source_id)"><el-icon><Document /></el-icon><span>{{ item.original_name }}<small>{{ item.text_length?.toLocaleString() || '—' }} 字</small></span></button><p v-if="!filteredSources.length" class="quiet">{{ search ? '没有匹配的资料' : '先添加一份课件或笔记。' }}</p></div>
        <template v-if="source"><div class="session-heading"><h2>这份资料的对话</h2><button :disabled="busy" aria-label="新建对话" @click="newSession"><el-icon><Plus /></el-icon></button></div><div class="session-list"><button v-for="session in sessions" :key="session.ctx_id" :disabled="busy" :aria-pressed="context?.ctx_id === session.ctx_id" @click="navigateSource(source.source_id, session.ctx_id)"><el-icon><ChatDotRound /></el-icon><span>{{ session.message_count ? `${session.message_count} 条消息` : '新对话' }}<small>{{ formatDate(session.updated_at || session.created_at) }}</small></span></button></div></template>
        <p class="local-note"><el-icon><FolderOpened /></el-icon>资料保存在本机<br />仅阅读和导入不调用模型</p>
      </aside>

      <section class="conversation-pane" aria-label="资料对话">
        <header class="conversation-heading"><div><small>{{ source ? '正在学习' : '从一份资料开始' }}</small><h2>{{ source?.original_name || '今天，想弄懂什么？' }}</h2></div><span v-if="context" class="saved-indicator">会话可恢复</span></header>
        <div v-if="loading" class="blank-state" role="status"><el-icon><Reading /></el-icon><h3>正在打开资料与学习记录…</h3></div>
        <div v-else-if="!source" class="blank-state"><el-icon><Reading /></el-icon><h3>把课件放进来，让学习接着发生。</h3><p>添加资料后即可读原文。需要讲解时再开启模型，也可以打开已有笔记和练习。</p><button class="primary" :disabled="busy" @click="fileInput?.click()">添加第一份资料</button><small>PDF / Word / PowerPoint / TXT · 最大 25 MB</small></div>
        <template v-else>
          <div ref="messageScroll" class="conversation-scroll" aria-live="polite">
            <div v-if="!context?.chat_history.length" class="conversation-intro"><span class="intro-line"></span><h3>不急着得到答案，<br />先找到你想理解的那一点。</h3><p>读原文、记笔记，或把卡住的概念交给我。回答会附上可核对的资料片段。</p><div class="starter-prompts"><button v-for="prompt in prompts" :key="prompt" @click="questionText = prompt; composer?.focus()">{{ prompt }}<el-icon><ArrowRight /></el-icon></button></div></div>
            <article v-for="(message, i) in context?.chat_history" :key="i" class="message" :class="message.role"><small>{{ message.role === 'user' ? '我' : 'FileMate' }}</small><p>{{ message.content }}</p><div v-if="message.citations?.length" class="citations"><button v-for="citation in message.citations" :key="citation.id" @click="showCitation(citation)"><el-icon><Document /></el-icon>引用 {{ citation.id }} · {{ citation.page_number ? `第 ${citation.page_number} 页` : '原文片段' }}</button></div></article>
            <p v-if="sending" class="pending" role="status">正在检索资料并组织回答…</p>
          </div>
          <div class="composer-area">
            <div class="mode-switch" aria-label="学习方式"><button v-for="mode in modes" :key="mode.id" :aria-pressed="chatMode === mode.id" :disabled="sending" @click="chatMode = mode.id">{{ mode.label }}</button></div>
            <form class="composer" @submit.prevent="send"><textarea ref="composer" v-model="questionText" rows="3" maxlength="4000" aria-label="向资料提问" :placeholder="modePlaceholder" :disabled="busy" @keydown.enter.ctrl.prevent="send" /><div><small>Ctrl + Enter 发送</small><button class="primary" :disabled="busy || !context || !questionText.trim() || !authorized" type="submit"><el-icon><Promotion /></el-icon>发送</button></div></form>
            <label class="model-consent"><input v-model="authorized" type="checkbox" :disabled="busy" />本次学习允许将资料片段和问题发送给已配置的模型</label>
            <p v-if="actionError" class="inline-error" role="alert">{{ actionError }}</p>
          </div>
        </template>
      </section>

      <aside class="resource-pane" aria-label="学习内容与原文">
        <nav class="resource-tabs" aria-label="阅读内容"><button :aria-pressed="resourceTab === 'artifacts'" @click="resourceTab = 'artifacts'">学习内容 <span>{{ artifacts.length }}</span></button><button :aria-pressed="resourceTab === 'source'" @click="resourceTab = 'source'">原文</button></nav>
        <div v-if="!source" class="resource-empty"><el-icon><Notebook /></el-icon><h3>把思考留在旁边</h3><p>笔记、卡片和练习会在这里打开，阅读时不必离开对话。</p></div>
        <div v-if="source" v-show="resourceTab === 'source'" ref="sourceReader" class="source-reader"><div v-if="citation" class="citation-focus"><button aria-label="关闭引用片段" @click="citation = null">关闭片段</button><strong>引用 {{ citation.id }} · {{ citation.source_name }}</strong><p>{{ citation.excerpt }}</p></div><h3>解析正文</h3><small>按文件解析顺序展示；图片与复杂排版可能不保留。</small><pre>{{ source.raw_text }}</pre></div>
        <div v-if="source" v-show="resourceTab === 'artifacts'" class="artifact-workbench">
          <div class="generation-controls"><label>添加学习内容<select v-model="generationKind" :disabled="busy"><option value="notes">结构化笔记</option><option value="knowledge_cards">知识卡</option><option value="questions">练习题</option><option value="summary">摘要</option></select></label><label v-if="generationKind === 'questions' || generationKind === 'knowledge_cards'">最多生成<select v-model.number="count" :disabled="busy"><option :value="5">5</option><option :value="10">10</option></select></label><button :disabled="busy || !authorized" @click="generate">{{ generating ? '生成中…' : '生成' }}</button></div>
          <p v-if="!authorized" class="generation-note">先在对话框下方确认模型使用，再生成新内容。</p>
          <p v-if="generationError" role="alert" class="inline-error">{{ generationError }} <button :disabled="busy || !authorized" @click="generate">重试</button></p>
          <p v-if="generating" class="generation-note" role="status">正在生成，完成后会自动保存到这份资料。无需重复上传。</p>
          <label v-if="artifacts.length" class="artifact-picker">已保存的内容<select v-model="activeArtifactId"><option v-for="item in artifacts" :key="item.artifact_id" :value="item.artifact_id">{{ item.title }} · {{ formatDate(item.created_at) }}</option></select></label>
          <KeepAlive><LearningArtifact v-if="activeArtifact" :key="activeArtifact.artifact_id" :artifact="activeArtifact" /></KeepAlive>
          <div v-if="!activeArtifact" class="resource-empty"><el-icon><Notebook /></el-icon><h3>还没有学习内容</h3><p>先整理一份笔记，再用卡片回忆、用练习检验。不必一次做完。</p></div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, ChatDotRound, Document, FolderOpened, Notebook, Plus, Promotion, Reading, Search } from '@element-plus/icons-vue'
import LearningArtifact from '../components/LearningArtifact.vue'
import { askAI, createSourceContext, generateSourceArtifact, getAIContext, getKnowledgeArtifacts, getKnowledgeSources, getLearningSource, importLearningSource, listAIContexts, type AICitation, type AIContextDetail, type AISessionSummary, type KnowledgeArtifact, type KnowledgeSource, type KnowledgeSourceDetail, type WorkspaceArtifactKind } from '../services/api'

const route = useRoute(); const router = useRouter()
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
const generationKind = ref<WorkspaceArtifactKind>('notes'); const count = ref(5)
const chatMode = ref<'answer' | 'socratic' | 'feynman'>('answer')
const modes = [{ id: 'answer' as const, label: '直接讲解' }, { id: 'socratic' as const, label: '引导我思考' }, { id: 'feynman' as const, label: '听我讲一遍' }]
const modePlaceholder = computed(() => ({ answer: '这份资料里，有什么想问的？', socratic: '告诉我你卡在哪，我用追问帮你理清。', feynman: '试着用自己的话解释一个概念，我来帮你找遗漏。' }[chatMode.value]))
const prompts = ['请解释这份资料的核心概念。', '这些知识可以用来解决什么问题？', '我想检验自己的理解，从哪里开始？']
let epoch = 0
const message = (cause: unknown) => cause instanceof Error ? cause.message : '操作失败，请重试'
function formatDate(value?: string) { return value ? new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '' }
async function loadSources() { loadingSources.value = true; try { sources.value = await getKnowledgeSources(200) } finally { loadingSources.value = false } }
async function navigateSource(id: string, ctx?: string) { await router.push({ path: '/ai-tools', query: { source: id, ...(ctx ? { ctx } : {}) } }); activePane.value = 'chat' }
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
    activeArtifactId.value = contents[0]?.artifact_id || ''
    if (!history.some(item => item.ctx_id === active.ctx_id)) {
      const updatedSessions = await listAIContexts(id)
      if (token !== epoch) return
      sessions.value = updatedSessions
    }
    if (token !== epoch) return
    // 已加载的 source / ctx 由监听器去重，只更新可恢复地址。
    if (route.query.ctx !== active.ctx_id || route.query.source !== id) {
      await router.replace({ path: '/ai-tools', query: { source: id, ctx: active.ctx_id } })
    }
    await scrollBottom()
  } catch (cause) { if (token === epoch) error.value = message(cause) }
  finally { if (token === epoch) loading.value = false }
}
async function reload() { try { error.value = ''; await loadSources(); await openRoute() } catch (cause) { error.value = message(cause) } }
async function importFile(event: Event) {
  const input = event.target as HTMLInputElement; const file = input.files?.[0]; input.value = ''
  if (!file || busy.value) return
  if (file.size > 25 * 1024 * 1024) { error.value = '文件不能超过 25 MB'; return }
  importing.value = true; error.value = ''
  try { const imported = await importLearningSource(file); await loadSources(); await navigateSource(imported.source_id) }
  catch (cause) { error.value = message(cause) }
  finally { importing.value = false }
}
async function newSession() {
  if (!source.value || busy.value) return
  loading.value = true
  try { const active = await createSourceContext(source.value.source_id); await navigateSource(source.value.source_id, active.ctx_id) }
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
  try { const artifact = await generateSourceArtifact(id, generationKind.value, count.value); if (token !== epoch) return; artifacts.value.unshift(artifact); activeArtifactId.value = artifact.artifact_id; resourceTab.value = 'artifacts'; activePane.value = 'resources' }
  catch (cause) { if (token === epoch) generationError.value = message(cause) }
  finally { generating.value = false }
}
async function showCitation(item: AICitation) {
  citation.value = item; resourceTab.value = 'source'; activePane.value = 'resources'
  await nextTick()
  sourceReader.value?.scrollTo({ top: 0 })
}
watch(() => [route.query.source, route.query.ctx], () => {
  if (source.value?.source_id === route.query.source && context.value?.ctx_id === route.query.ctx) return
  void openRoute()
})
onMounted(reload)
onUnmounted(() => { epoch++ })
</script>

<style scoped>
.learning-workspace{color:#183229;max-width:1680px;margin:0 auto;padding:8px 10px 28px}.workspace-heading{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:22px}.workspace-heading h1{font-size:26px;margin:0 0 8px;font-weight:650;letter-spacing:-.5px}.workspace-heading p{margin:0;color:#566e60;font-size:14px}.workspace-heading a{display:flex;align-items:center;gap:8px;color:#2f7d55;text-decoration:none;font-size:13px;white-space:nowrap;min-height:44px}.desk{display:grid;grid-template-columns:210px minmax(280px,1fr) minmax(310px,.9fr);border:1px solid #d7e3d9;border-radius:14px;overflow:hidden;background:#fff;min-height:680px;height:calc(100dvh - 212px);max-height:1050px}.source-pane{background:#f0f5ef;border-right:1px solid #d7e3d9;padding:20px 12px;overflow:auto;display:flex;flex-direction:column;gap:14px;min-width:0}.pane-heading,.session-heading{display:flex;align-items:center;justify-content:space-between;padding:0 6px}.pane-heading h2,.session-heading h2{font-size:13px;margin:0;font-weight:650}.pane-heading span{font-size:12px;color:#566e60}.session-heading{border-top:1px solid #d7e3d9;padding-top:15px}.learning-workspace button{font:inherit;color:inherit;cursor:pointer;min-height:44px;border:1px solid #d7e3d9;background:white;border-radius:8px;padding:8px 12px}.learning-workspace button:disabled{opacity:.5;cursor:default}.learning-workspace button:focus-visible,.learning-workspace input:focus-visible,.learning-workspace textarea:focus-visible,.learning-workspace select:focus-visible,.learning-workspace a:focus-visible{outline:2px solid #2f7d55;outline-offset:2px}.learning-workspace .primary{background:#2f7d55;color:white;border-color:#2f7d55;display:inline-flex;align-items:center;justify-content:center;gap:8px}.import-button{display:flex;justify-content:center;gap:8px;align-items:center;width:100%;font-size:13px!important}.file-input{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none}.source-search{display:flex;align-items:center;padding:0 10px;background:#e7eee6;border-radius:8px;gap:7px;color:#566e60}.source-search input{border:0;background:transparent;width:100%;min-width:0;min-height:44px;font:inherit;font-size:12px;outline-offset:-2px}.source-list,.session-list{display:flex;flex-direction:column;gap:4px}.source-list button,.session-list button{display:flex;align-items:start;gap:9px;text-align:left;background:transparent;border-color:transparent;font-size:12px;line-height:1.7;padding:10px 8px}.source-list button>span,.session-list button>span{min-width:0;overflow-wrap:anywhere}.source-list .el-icon,.session-list .el-icon{font-size:17px;flex-shrink:0;margin-top:3px}.source-list button.selected,.session-list button[aria-pressed=true]{background:#fff;border-color:#c7d9cb}.source-list small,.session-list small{display:block;font-size:10px;color:#566e60;margin-top:2px}.session-heading button{border:0;background:none;padding:5px;width:44px}.local-note{margin-top:auto;padding:20px 6px 0;font-size:11px;line-height:1.9;color:#566e60}.local-note .el-icon{margin-right:5px}.quiet{font-size:12px;line-height:1.8;color:#566e60;padding:0 6px}.conversation-pane{display:flex;flex-direction:column;min-width:0;min-height:0}.conversation-heading{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:22px 26px;border-bottom:1px solid #e6ece5}.conversation-heading small{font-size:11px;color:#566e60}.conversation-heading h2{font-size:15px;margin:7px 0 0;line-height:1.6;overflow-wrap:anywhere}.saved-indicator{font-size:10px;white-space:nowrap;color:#2f7d55}.conversation-scroll{flex:1;overflow:auto;padding:26px;min-height:100px}.conversation-intro{padding:28px 0}.intro-line{display:block;width:36px;height:3px;background:#3f805c;margin-bottom:25px}.conversation-intro h3{font-size:25px;line-height:1.6;letter-spacing:-.5px;font-weight:550;margin:0 0 20px}.conversation-intro p{font-size:13px;color:#566e60;line-height:1.9;margin-bottom:28px}.starter-prompts{display:flex;flex-direction:column;gap:7px}.starter-prompts button{text-align:left;font-size:12px!important;display:flex;align-items:center;justify-content:space-between;gap:12px;border:0!important;background:#f5f7f2!important}.message{padding:0 0 28px;font-size:14px;line-height:1.95}.message small{font-size:11px;color:#2f7d55;font-weight:650}.message p{margin:6px 0;white-space:pre-wrap;overflow-wrap:anywhere}.message.user{background:#f0f5ef;padding:14px 18px;margin-bottom:24px;border-radius:10px}.citations{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}.citations button{font-size:11px!important;display:flex;align-items:center;gap:5px}.composer-area{border-top:1px solid #e6ece5;padding:16px 22px 20px;background:#fff}.mode-switch{display:flex;gap:5px;margin-bottom:10px;flex-wrap:wrap}.mode-switch button{border-color:transparent;min-height:36px;font-size:11px;padding:5px 9px}.mode-switch button[aria-pressed=true]{background:#eaf2e8;color:#286243}.composer{border:1px solid #c6d8c9;border-radius:10px;padding:12px}.composer textarea{border:0;width:100%;resize:vertical;min-height:66px;max-height:180px;box-sizing:border-box;font:inherit;font-size:13px;line-height:1.8;color:inherit}.composer>div{display:flex;align-items:center;justify-content:space-between;gap:8px}.composer small{font-size:10px;color:#566e60}.composer button{font-size:12px}.model-consent{display:flex;gap:7px;align-items:flex-start;font-size:10px;line-height:1.8;color:#566e60;margin-top:12px;cursor:pointer}.model-consent input{accent-color:#2f7d55;margin:3px 0 0}.resource-pane{background:#fbfcf9;border-left:1px solid #d7e3d9;display:flex;flex-direction:column;min-height:0;min-width:0}.resource-tabs{display:flex;gap:15px;padding:15px 20px 0;border-bottom:1px solid #d7e3d9}.resource-tabs button{border:0;border-bottom:2px solid transparent;background:none;border-radius:0;font-size:13px;padding:8px 0 16px}.resource-tabs button[aria-pressed=true]{border-bottom-color:#2f7d55;color:#2f7d55}.resource-tabs span{font-size:10px;margin-left:5px}.artifact-workbench,.source-reader{padding:20px;overflow:auto;flex:1;min-height:0}.generation-controls{display:flex;gap:8px;align-items:end}.generation-controls label{min-width:0;flex:1;font-size:11px;color:#566e60}.generation-controls select,.artifact-picker select{width:100%;min-width:0;min-height:44px;border:1px solid #d7e3d9;border-radius:8px;background:white;color:#183229;padding:8px;font:inherit;font-size:12px;margin-top:6px}.generation-controls label:nth-child(2){flex:0 0 56px}.generation-controls button{font-size:12px}.generation-note{font-size:11px;line-height:1.8;color:#566e60;margin:12px 0 22px}.artifact-picker{display:block;margin:18px 0 26px;font-size:11px;color:#566e60}.resource-empty,.blank-state{display:flex;flex-direction:column;align-items:flex-start;justify-content:center;padding:45px 28px;line-height:1.9;color:#566e60;flex:1}.resource-empty>.el-icon,.blank-state>.el-icon{font-size:32px;color:#3f805c;margin-bottom:15px}.resource-empty h3,.blank-state h3{font-size:19px;line-height:1.8;color:#183229;font-weight:550;margin:0 0 14px}.resource-empty p,.blank-state p{font-size:13px;margin:0 0 20px}.blank-state small{font-size:11px;margin-top:16px}.source-reader pre{font-family:inherit;font-size:13px;line-height:2;white-space:pre-wrap;overflow-wrap:anywhere}.source-reader h3{font-size:16px}.source-reader small{color:#566e60;font-size:11px}.citation-focus{padding:16px;background:#eaf2e8;border-left:3px solid #2f7d55;line-height:1.9;font-size:13px}.citation-focus button{display:block;font-size:11px;margin-bottom:12px}.citation-focus p{white-space:pre-wrap}.pending{color:#566e60;font-size:13px}.workspace-error,.inline-error{color:#9a3333;background:#fcf0ed;padding:12px;font-size:12px;line-height:1.8}.workspace-error{margin-bottom:15px}.mobile-panes{display:none}
@media(min-width:1500px){.desk{grid-template-columns:225px minmax(340px,1.05fr) minmax(380px,1fr)}}
@media(max-width:1200px){.desk{grid-template-columns:170px minmax(260px,1fr) minmax(270px,.9fr)}.conversation-heading,.conversation-scroll{padding:18px}.composer-area{padding:12px}.artifact-workbench,.source-reader{padding:14px}.conversation-intro h3{font-size:22px}.saved-indicator{display:none}}
@media(max-width:1000px){.mobile-panes{display:flex;gap:6px;margin-bottom:12px}.mobile-panes button{flex:1;font-size:13px}.mobile-panes button[aria-pressed=true]{background:#2f7d55;color:white}.desk{display:block;height:calc(100dvh - 245px);min-height:620px}.desk>.source-pane,.desk>.conversation-pane,.desk>.resource-pane{display:none;height:100%;box-sizing:border-box;border:0}.desk[data-pane=sources]>.source-pane{display:flex}.desk[data-pane=chat]>.conversation-pane{display:flex}.desk[data-pane=resources]>.resource-pane{display:flex}.source-list button{font-size:14px}.source-list small{font-size:12px}.workspace-heading{align-items:start}.workspace-heading h1{font-size:23px}.workspace-heading p{font-size:12px}.workspace-heading>a{font-size:11px}.conversation-intro{max-width:560px}.resource-empty{justify-content:flex-start;padding-top:50px}}
@media(max-width:480px){.learning-workspace{padding:4px 0 20px}.workspace-heading{flex-direction:column;gap:4px;margin-bottom:10px}.workspace-heading a{min-height:36px}.desk{min-height:620px}.conversation-heading{padding:16px}.conversation-scroll{padding:20px}.conversation-intro h3{font-size:24px}.resource-tabs{padding-left:15px}}
</style>
