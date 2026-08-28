<!--
  View: AI Tools
  Design: 综合AI学习工具箱
  功能：PDF摘要、知识卡生成、题目提取、笔记提取、AI问答
-->
<template>
  <div class="ai-tools-page">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon class="title-icon"><MagicStick /></el-icon>
        资料理解工作区
      </h1>
      <p class="page-subtitle">上传文档，AI 帮你搞定学习笔记、知识卡、练习题</p>
    </div>

    <div class="main-layout">
      <!-- 会话历史侧边栏 -->
      <aside class="session-sidebar" :class="{ collapsed: !sidebarOpen }">
        <div class="sidebar-header">
          <h3><el-icon><ChatDotSquare /></el-icon>历史会话</h3>
          <button class="sidebar-toggle" @click="sidebarOpen = !sidebarOpen" :aria-label="sidebarOpen ? '收起侧栏' : '展开侧栏'">
            <el-icon><ArrowLeft v-if="sidebarOpen" /><ArrowRight v-else /></el-icon>
          </button>
        </div>
        <div class="sidebar-actions" v-if="sidebarOpen">
          <button class="btn-new-chat" @click="startNewChat">
            <el-icon><Plus /></el-icon>新对话
          </button>
        </div>
        <div class="session-list" v-if="sidebarOpen">
          <div v-if="loadingSessions" class="sidebar-loading">加载中...</div>
          <div v-else-if="sessions.length === 0" class="sidebar-empty">暂无历史会话</div>
          <button
            v-for="session in sessions"
            :key="session.ctx_id"
            class="session-item"
            :class="{ active: currentCtxId === session.ctx_id }"
            @click="resumeSession(session)"
          >
            <div class="session-title">{{ session.title || '未命名对话' }}</div>
            <div class="session-meta">
              <span>{{ session.message_count }} 条消息</span>
              <span v-if="session.updated_at">{{ formatDate(session.updated_at) }}</span>
            </div>
          </button>
        </div>
      </aside>

      <!-- 主内容区 -->
      <div class="main-content">

    <!-- 功能选择标签 -->
    <div class="tool-tabs" role="tablist" aria-label="资料处理工具">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        class="tab-btn"
        role="tab"
        :aria-selected="activeTab === tab.id"
        :class="{ active: activeTab === tab.id }"
        @click="switchTab(tab.id)"
      >
        <el-icon class="tab-icon"><component :is="tab.icon" /></el-icon>
        <span class="tab-label">{{ tab.label }}</span>
      </button>
    </div>

    <!-- 上传区域 -->
    <label
      class="upload-zone"
      for="ai-document-upload"
      :class="{ 'is-dragover': isDragover }"
      @dragover.prevent="isDragover = true"
      @dragleave.prevent="isDragover = false"
      @drop.prevent="handleDrop"
    >
      <input
        id="ai-document-upload"
        name="ai_document"
        type="file"
        accept=".pdf,.doc,.docx,.ppt,.pptx,.txt"
        @change="handleFileSelect"
        hidden
      />

      <div class="upload-content">
        <div class="upload-icon">
          <el-icon><Document v-if="!selectedFile" /><CircleCheck v-else /></el-icon>
        </div>
        <p v-if="!selectedFile" class="upload-hint">
          点击或拖拽文件到这里
        </p>
        <p v-else class="upload-filename">
          {{ selectedFile.name }}
        </p>
        <p class="upload-formats">支持 PDF、DOC、DOCX、PPT、TXT</p>
      </div>
    </label>

    <!-- 功能配置 -->
    <div v-if="selectedFile" class="tool-config">
      <!-- 知识卡数量配置 -->
      <div v-if="activeTab === 'knowledge'" class="config-row">
        <label>卡片数量：</label>
        <input
          type="range"
          aria-label="卡片数量"
          v-model.number="config.numCards"
          min="5"
          max="30"
          step="5"
        />
        <span class="config-value">{{ config.numCards }} 张</span>
      </div>

      <!-- 题目数量和类型配置 -->
      <div v-if="activeTab === 'questions'" class="config-row">
        <label>题目数量：</label>
        <input
          type="range"
          aria-label="题目数量"
          v-model.number="config.numQuestions"
          min="5"
          max="20"
          step="5"
        />
        <span class="config-value">{{ config.numQuestions }} 道</span>
      </div>

      <!-- 笔记格式配置 -->
      <div v-if="activeTab === 'notes'" class="config-row">
        <label>笔记格式：</label>
        <select v-model="config.noteFormat" name="note_format" aria-label="笔记格式">
          <option value="outline">大纲</option>
          <option value="markdown">Markdown</option>
          <option value="mindmap">思维导图</option>
        </select>
      </div>
    </div>

    <!-- 执行按钮 -->
    <div v-if="selectedFile" class="action-row">
      <button
        class="btn-primary"
        :disabled="isProcessing || activeTab === 'chat'"
        @click="processFile"
      >
        <span v-if="isProcessing" class="spinner" aria-label="正在生成" />
        <span v-else>{{ actionButtonText }}</span>
      </button>
    </div>

    <!-- 处理结果 -->
    <div v-if="result" class="result-section">
      <!-- 摘要结果 -->
      <div v-if="activeTab === 'summary'" class="result-card summary-result">
        <div class="result-header">
          <h3><el-icon><Memo /></el-icon>资料摘要</h3>
          <button class="copy-btn" @click="copyToClipboard(result.summary)">
            <el-icon><CopyDocument /></el-icon>复制
          </button>
        </div>
        <div class="result-content">{{ result.summary }}</div>
      </div>

      <!-- 知识卡结果 -->
      <div v-else-if="activeTab === 'knowledge'" class="result-card cards-result">
        <div class="result-header">
          <h3><el-icon><Tickets /></el-icon>知识卡片</h3>
          <span class="card-count">{{ result.cards.length }} 张</span>
        </div>
        <div class="cards-grid">
          <div
            v-for="(card, idx) in result.cards"
            :key="idx"
            class="knowledge-card"
          >
            <div class="card-front">
              <span class="card-label">正面</span>
              {{ card.front }}
            </div>
            <div class="card-divider">↓</div>
            <div class="card-back">
              <span class="card-label">背面</span>
              {{ card.back }}
            </div>
          </div>
        </div>
        <div class="export-actions">
          <button class="btn-secondary" @click="exportCardsAsJson">
            <el-icon><Download /></el-icon>导出 JSON
          </button>
          <button class="btn-secondary" @click="exportCardsAsCsv">
            <el-icon><Download /></el-icon>导出 CSV
          </button>
        </div>
      </div>

      <!-- 题目结果 -->
      <div v-else-if="activeTab === 'questions'" class="result-card questions-result">
        <div class="result-header">
          <h3><el-icon><List /></el-icon>练习题目</h3>
          <span class="question-count">{{ result.questions.length }} 道</span>
        </div>
        <div class="questions-list">
          <div
            v-for="(q, idx) in result.questions"
            :key="idx"
            class="question-item"
          >
            <div class="question-type">{{ q.type }}</div>
            <div class="question-text">{{ q.question }}</div>
            <div v-if="q.options && q.options.length" class="question-options">
              <span
                v-for="(opt, oi) in q.options"
                :key="oi"
                class="option-tag"
              >{{ opt }}</span>
            </div>
            <div class="answer-entry">
              <input v-model="questionAnswers[idx]" :name="`question_answer_${idx}`" autocomplete="off" :aria-label="`第 ${Number(idx) + 1} 题答案`" placeholder="输入你的答案…" />
              <button class="btn-secondary" :disabled="!questionAnswers[idx]?.trim()" @click="submitAnswer(idx)">提交</button>
            </div>
            <div v-if="questionResults[idx]" class="question-answer" :class="{ incorrect: !questionResults[idx].is_correct }">
              {{ questionResults[idx].feedback }} · 参考答案：{{ questionResults[idx].reference_answer }}
            </div>
            <div v-if="questionResults[idx] && q.explanation" class="question-explanation">
              <span class="explain-label">解析：</span>{{ q.explanation }}
            </div>
          </div>
        </div>
      </div>

      <!-- 笔记结果 -->
      <div v-else-if="activeTab === 'notes'" class="result-card notes-result">
        <div class="result-header">
          <h3><el-icon><Notebook /></el-icon>结构化笔记</h3>
        </div>
        <div class="notes-content">
          <h4 v-if="result.notes.title">{{ result.notes.title }}</h4>
          <div
            v-for="(section, idx) in result.notes.sections"
            :key="idx"
            class="note-section"
          >
            <div class="section-title">{{ section.title }}</div>
            <div class="section-content">
              <template v-if="Array.isArray(section.content)">
                <p v-for="(item, i) in section.content" :key="i">{{ item }}</p>
              </template>
              <template v-else>
                {{ section.content }}
              </template>
            </div>
          </div>
        </div>
      </div>

      <!-- 问答结果 -->
      <div v-else-if="activeTab === 'chat'" class="result-card chat-result">
        <div class="chat-container">
          <div class="tutor-modes" role="group" aria-label="教学方式">
            <button v-for="mode in tutorModes" :key="mode.id" type="button" :class="{ active: chatMode === mode.id }" :aria-pressed="chatMode === mode.id" @click="chatMode = mode.id"><b>{{ mode.label }}</b><span>{{ mode.description }}</span></button>
          </div>
          <div class="chat-history">
            <div
              v-for="(msg, idx) in chatHistory"
              :key="idx"
              class="chat-message"
              :class="msg.role"
            >
              <span class="message-role">
                <el-icon><User v-if="msg.role === 'user'" /><Service v-else /></el-icon>
              </span>
              <div class="message-content">
                {{ msg.content }}
                <div v-if="msg.citations?.length" class="message-citations">
                  <div v-for="citation in msg.citations" :key="citation.id" class="citation-item">
                    <b>[引用{{ citation.id }}] {{ citation.source_name }}</b>
                    <span v-if="citation.page_number"> · 第 {{ citation.page_number }} 页</span>
                    <p v-if="citation.excerpt">{{ citation.excerpt }}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="chat-input-area">
            <input
              v-model="chatQuestion"
              type="text"
              name="document_question"
              autocomplete="off"
              aria-label="资料问答问题"
              :placeholder="chatPlaceholder"
              @keyup.enter="sendChatMessage"
              :disabled="isProcessing"
            />
            <button
              class="send-btn"
              @click="sendChatMessage"
              :disabled="!chatQuestion.trim() || isProcessing"
            >
              发送
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 问答模式切换按钮 -->
    <div v-if="result && result.ctx_id && activeTab !== 'chat'" class="switch-chat-mode">
      <button class="btn-chat" @click="switchToChatMode(result.ctx_id)">
        <el-icon><ChatDotRound /></el-icon>进入问答模式
      </button>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="error-toast" aria-live="polite">
      <el-icon><WarningFilled /></el-icon>{{ error }}
    </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  ChatDotRound,
  ChatDotSquare,
  CircleCheck,
  CopyDocument,
  Document,
  Download,
  List,
  MagicStick,
  Memo,
  Notebook,
  Plus,
  Service,
  Tickets,
  User,
  WarningFilled,
  ArrowLeft,
  ArrowRight
} from '@element-plus/icons-vue'
import {
  generateSummary,
  generateKnowledgeCards,
  extractQuestions,
  extractNotes,
  askAI,
  submitQuizAttempt,
  listAIContexts,
  getAIContext,
  type QuizAttemptResult,
  type KnowledgeCard,
  type AISessionSummary,
  type AIChatMessage
} from '../services/api'

// 标签页配置
const tabs = [
  { id: 'summary', label: '资料摘要', icon: Memo },
  { id: 'knowledge', label: '知识卡', icon: Tickets },
  { id: 'questions', label: '题目提取', icon: List },
  { id: 'notes', label: '笔记提取', icon: Notebook },
  { id: 'chat', label: '资料问答', icon: ChatDotRound }
]

const activeTab = ref('summary')
const switchTab = (tabId: string) => {
  if (tabId === activeTab.value) return
  if (tabId === 'chat' && result.value?.ctx_id) {
    activeTab.value = 'chat'
    return
  }
  if (tabId === 'chat') {
    ElMessage.warning('请先选择摘要/知识卡/笔记/题目处理文件，再从结果页点击「进入问答模式」')
    return
  }
  activeTab.value = tabId
  result.value = null
  error.value = ''
  chatHistory.value = []
  questionAnswers.value = {}
  questionResults.value = {}
}
const selectedFile = ref<File | null>(null)
const isDragover = ref(false)
const isProcessing = ref(false)
const result = ref<any>(null)
const error = ref('')
const chatQuestion = ref('')
const chatHistory = ref<AIChatMessage[]>([])
const chatMode = ref<'answer' | 'socratic' | 'feynman'>('answer')
const tutorModes = [
  { id: 'answer' as const, label: '证据问答', description: '结论与引用' },
  { id: 'socratic' as const, label: '苏格拉底', description: '追问引导思考' },
  { id: 'feynman' as const, label: '费曼训练', description: '讲给 AI 听' }
]
const chatPlaceholder = computed(() => ({
  answer: '输入问题，AI 基于资料回答…',
  socratic: '输入你卡住的问题，导师会逐步追问…',
  feynman: '用自己的话解释一个概念，AI 帮你查漏补缺…'
}[chatMode.value]))
const questionAnswers = ref<Record<string, string>>({})
const questionResults = ref<Record<string, QuizAttemptResult>>({})

// 会话侧边栏
const sidebarOpen = ref(true)
const sessions = ref<AISessionSummary[]>([])
const loadingSessions = ref(false)
const currentCtxId = ref<string | null>(null)

const loadSessions = async () => {
  loadingSessions.value = true
  try {
    sessions.value = await listAIContexts(undefined, 50)
  } catch (e: any) {
    ElMessage.error(e.message || '加载会话列表失败')
  } finally {
    loadingSessions.value = false
  }
}

const resumeSession = async (session: AISessionSummary) => {
  currentCtxId.value = session.ctx_id
  try {
    const ctx = await getAIContext(session.ctx_id)
    chatHistory.value = ctx.chat_history || []
    result.value = { ctx_id: session.ctx_id, source_id: session.source_id }
    activeTab.value = 'chat'
  } catch (e: any) {
    ElMessage.error(e.message || '加载会话失败')
  }
}

const startNewChat = () => {
  currentCtxId.value = null
  chatHistory.value = []
  result.value = null
  activeTab.value = 'summary'
  ElMessage.info('请先选择文件并处理，再进入问答模式')
}

const formatDate = (iso: string) => {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  const days = Math.floor(diff / 86400000)
  if (days === 0) return '今天'
  if (days === 1) return '昨天'
  if (days < 7) return `${days} 天前`
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

// 配置
const config = ref({
  numCards: 10,
  numQuestions: 10,
  noteFormat: 'outline'
})

// 计算操作按钮文字
const actionButtonText = computed(() => {
  if (isProcessing.value) return '处理中...'
  const texts: Record<string, string> = {
    summary: '生成摘要',
    knowledge: '生成知识卡',
    questions: '提取题目',
    notes: '提取笔记',
    chat: '开始问答'
  }
  return texts[activeTab.value] || '执行'
})

// 处理文件选择
const handleFileSelect = (e: Event) => {
  const input = e.target as HTMLInputElement
  if (input.files && input.files[0]) {
    selectedFile.value = input.files[0]
    result.value = null
    error.value = ''
    chatHistory.value = []
    questionAnswers.value = {}
    questionResults.value = {}
  }
}

// 处理拖放
const handleDrop = (e: DragEvent) => {
  isDragover.value = false
  const files = e.dataTransfer?.files
  if (files && files[0]) {
    selectedFile.value = files[0]
    result.value = null
    error.value = ''
    chatHistory.value = []
    questionAnswers.value = {}
    questionResults.value = {}
  }
}

// 处理文件
const processFile = async () => {
  if (!selectedFile.value) return

  isProcessing.value = true
  error.value = ''
  result.value = null

  try {
    switch (activeTab.value) {
      case 'summary':
        result.value = await generateSummary(selectedFile.value, 500)
        break
      case 'knowledge':
        result.value = await generateKnowledgeCards(
          selectedFile.value,
          config.value.numCards,
          'front_back'
        )
        break
      case 'questions':
        result.value = await extractQuestions(
          selectedFile.value,
          undefined,
          config.value.numQuestions
        )
        break
      case 'notes':
        result.value = await extractNotes(
          selectedFile.value,
          config.value.noteFormat
        )
        break
      case 'chat':
        error.value = '请先选择摘要/知识卡/笔记/题目处理文件，再从结果页点击「进入问答模式」'
        break
      default:
        error.value = '未知功能'
    }
  } catch (e: any) {
    error.value = e.message || '处理失败'
    ElMessage.error(error.value)
  } finally {
    isProcessing.value = false
    if (!error.value && result.value?.ctx_id) {
      loadSessions()
    }
  }
}

// 切换到问答模式
const switchToChatMode = (ctxId: string) => {
  activeTab.value = 'chat'
  currentCtxId.value = ctxId
  chatHistory.value = []
  if (result.value) {
    result.value = { ctx_id: ctxId }
  }
}

// 发送问答消息
const sendChatMessage = async () => {
  if (!chatQuestion.value.trim() || !result.value?.ctx_id) return

  const question = chatQuestion.value.trim()
  chatQuestion.value = ''
  isProcessing.value = true

  // 添加用户问题到历史
  chatHistory.value.push({ role: 'user', content: question })

  try {
    const response = await askAI(
      result.value.ctx_id,
      question,
      chatHistory.value.slice(0, -1),
      chatMode.value
    )
    chatHistory.value.push({
      role: 'assistant',
      content: response.answer,
      citations: response.citations
    })
    await loadSessions()
  } catch (e: any) {
    ElMessage.error(e.message || '问答失败')
  } finally {
    isProcessing.value = false
  }
}

const submitAnswer = async (index: string | number) => {
  if (!result.value?.artifact_id || !questionAnswers.value[index]?.trim()) return
  try {
    questionResults.value[index] = await submitQuizAttempt(
      result.value.artifact_id,
      Number(index),
      questionAnswers.value[index]
    )
    ElMessage[questionResults.value[index].is_correct ? 'success' : 'warning'](
      questionResults.value[index].feedback
    )
  } catch (e: any) {
    ElMessage.error(e.message || '提交答案失败')
  }
}

// 复制到剪贴板
const copyToClipboard = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

// 导出为 JSON
const exportCardsAsJson = () => {
  if (!result.value?.cards) return
  const json = JSON.stringify(result.value.cards, null, 2)
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'knowledge_cards.json'
  link.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出 JSON')
}

// 导出为 CSV
const exportCardsAsCsv = () => {
  if (!result.value?.cards) return
  const cards = result.value.cards as KnowledgeCard[]
  const csv = 'front,back\n' + cards.map(c =>
    `"${c.front.replace(/"/g, '""')}","${c.back.replace(/"/g, '""')}"`
  ).join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'knowledge_cards.csv'
  link.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出 CSV')
}

onMounted(() => {
  loadSessions()
})
</script>

<style scoped>
.ai-tools-page {
  --bg-card: var(--bg-surface);
  --border-subtle: #d7e3d9;
  --border-default: #bfd0c3;
  --text-primary: #183229;
  --text-secondary: #4d655b;
  --text-muted: #6d8077;

  max-width: 1000px;
  margin: 0 auto;
  padding: 24px;
}

.page-header {
  text-align: left;
  margin-bottom: 32px;
}

.page-title {
  font-size: 28px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.title-icon {
  margin-right: 8px;
}

.page-subtitle {
  font-size: 15px;
  color: var(--text-muted);
  margin: 0;
}

/* 标签页 */
.tool-tabs {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: color 0.2s, background-color 0.2s, border-color 0.2s;
}

.tab-btn:hover {
  border-color: var(--accent-border);
}

.tab-btn.active {
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--accent);
}

.tab-icon {
  font-size: 18px;
}

/* 上传区域 */
.upload-zone {
  background: var(--bg-card);
  border: 2px dashed var(--border-default);
  border-radius: 16px;
  padding: 40px;
  text-align: center;
  cursor: pointer;
  transition: background-color 0.3s, border-color 0.3s;
  margin-bottom: 20px;
}

.upload-zone:hover {
  border-color: var(--accent-border);
  background: var(--accent-soft);
}

.upload-zone.is-dragover {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.upload-icon {
  font-size: 40px;
  margin-bottom: 12px;
}

.upload-hint {
  font-size: 16px;
  color: var(--text-secondary);
  margin: 0 0 8px;
}

.upload-filename {
  font-size: 16px;
  color: #a5b4fc;
  font-weight: 500;
  margin: 0 0 8px;
}

.upload-formats {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

/* 功能配置 */
.tool-config {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 16px 20px;
  margin-bottom: 20px;
}

.config-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.config-row label {
  font-size: 14px;
  color: var(--text-secondary);
}

.config-row input[type="range"] {
  flex: 1;
  max-width: 200px;
}

.config-row select {
  padding: 6px 12px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
}

.config-value {
  font-size: 14px;
  color: #a5b4fc;
  min-width: 60px;
}

/* 操作按钮 */
.action-row {
  text-align: center;
  margin-bottom: 24px;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 14px 40px;
  background: var(--accent);
  border: none;
  border-radius: 12px;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s, box-shadow 0.2s, transform 0.2s;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  background: var(--accent-hover);
  box-shadow: 0 6px 18px rgba(47, 125, 85, 0.16);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 结果区域 */
.result-section {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 16px;
  padding: 24px;
  max-height: 600px;
  overflow-y: auto;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.result-header h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.copy-btn {
  padding: 6px 12px;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
}

.copy-btn:hover {
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-primary);
}

.result-content {
  font-size: 15px;
  line-height: 1.8;
  color: var(--text-secondary);
  white-space: pre-wrap;
}

/* 知识卡 */
.card-count {
  font-size: 13px;
  color: var(--text-muted);
}

.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.knowledge-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 16px;
}

.card-label {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.knowledge-card .card-front {
  font-size: 14px;
  color: var(--text-primary);
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--border-subtle);
}

.card-divider {
  text-align: center;
  color: var(--text-muted);
  font-size: 12px;
  margin: 4px 0;
}

.knowledge-card .card-back {
  font-size: 13px;
  color: var(--text-secondary);
}

.export-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.btn-secondary {
  padding: 8px 16px;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
}

.btn-secondary:hover {
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
}

/* 题目 */
.question-count {
  font-size: 13px;
  color: var(--text-muted);
}

.questions-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.question-item {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 16px;
}

.question-type {
  font-size: 11px;
  color: #a5b4fc;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.question-text {
  font-size: 14px;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.question-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.option-tag {
  padding: 4px 10px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.question-answer {
  font-size: 13px;
  color: #4ade80;
  margin-bottom: 4px;
}

.question-answer.incorrect { color: #b45309; }
.answer-entry { display: flex; gap: 8px; margin: 12px 0; }
.answer-entry input { flex: 1; padding: 9px 12px; border: 1px solid var(--border-default); border-radius: 8px; background: var(--bg-elevated); color: var(--text-primary); }

.answer-label {
  color: var(--text-muted);
}

.question-explanation {
  font-size: 12px;
  color: var(--text-muted);
}

.explain-label {
  color: var(--text-muted);
}

/* 笔记 */
.notes-content h4 {
  font-size: 18px;
  color: var(--text-primary);
  margin: 0 0 16px;
}

.note-section {
  margin-bottom: 16px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #a5b4fc;
  margin-bottom: 8px;
}

.section-content {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.7;
}

.section-content p {
  margin: 0 0 8px;
}

/* 问答 */
.chat-container {
  display: flex;
  flex-direction: column;
  height: 400px;
}

.chat-history {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 12px;
  margin-bottom: 12px;
}

.chat-message {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
  max-width: 80%;
}

.chat-message.user {
  margin-left: auto;
  flex-direction: row-reverse;
}

.message-role {
  font-size: 16px;
}

.message-content {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
}

.message-citations {
  display: grid;
  gap: 8px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border-subtle);
  font-size: 12px;
  color: var(--text-muted);
}

.citation-item p {
  margin: 4px 0 0;
}

.chat-message.user .message-content {
  color: var(--text-primary);
}

.chat-input-area {
  display: flex;
  gap: 8px;
}

.chat-input-area input {
  flex: 1;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  color: var(--text-primary);
  font-size: 14px;
}

.chat-input-area input:focus {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-color: var(--accent);
}

.send-btn {
  padding: 12px 24px;
  background: var(--accent);
  border: none;
  border-radius: 10px;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.send-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 切换问答模式 */
.switch-chat-mode {
  text-align: center;
  margin-top: 16px;
}

.btn-chat {
  padding: 12px 24px;
  background: transparent;
  border: 1px solid var(--accent-border);
  border-radius: 10px;
  color: var(--accent);
  font-size: 14px;
  cursor: pointer;
}

.btn-chat:hover {
  background: var(--accent-soft);
}

/* 错误提示 */
.error-toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  padding: 12px 24px;
  background: rgba(239, 68, 68, 0.9);
  border-radius: 10px;
  color: #fff;
  font-size: 14px;
}
.tutor-modes{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:10px;border-bottom:1px solid var(--border-subtle);background:var(--bg-base)}.tutor-modes button{display:flex;align-items:flex-start;flex-direction:column;gap:3px;padding:10px 12px;border:1px solid var(--border-subtle);border-radius:9px;background:var(--bg-surface);color:var(--text-secondary);text-align:left;cursor:pointer}.tutor-modes button.active{border-color:var(--accent);background:var(--accent-soft);color:var(--accent)}.tutor-modes b{font-size:13px}.tutor-modes span{font-size:11px;color:var(--text-muted)}@media(max-width:560px){.tutor-modes{grid-template-columns:1fr}.tutor-modes button{flex-direction:row;align-items:center;justify-content:space-between}}

/* 移动端（375px）适配 */
@media (max-width: 640px) {
  .tab-btn {
    min-height: 44px;
    padding: 10px 14px;
  }

  .upload-zone {
    padding: 24px 16px;
  }

  .config-row {
    flex-wrap: wrap;
  }

  .config-row input[type="range"] {
    min-width: 160px;
  }

  .result-section {
    padding: 16px;
  }

  .result-header {
    flex-wrap: wrap;
    gap: 8px;
  }

  .btn-primary,
  .btn-chat,
  .send-btn {
    width: 100%;
    justify-content: center;
  }

  .export-actions {
    flex-wrap: wrap;
  }

  .export-actions .btn-secondary {
    flex: 1;
    min-width: 44px;
  }

  .chat-message {
    max-width: 92%;
  }
}

</style>

<style scoped>
/* 浅色自然绿主题覆盖 */
.tab-btn:hover,
.upload-zone:hover,
.upload-zone.is-dragover,
.chat-input:focus {
  border-color: var(--accent);
}

.tab-btn.active,
.upload-zone.is-dragover,
.btn-chat:hover {
  color: var(--accent);
  background: var(--accent-soft);
  border-color: var(--accent-border);
}

.upload-text,
.char-count,
.question-type,
.answer-label,
.btn-chat {
  color: var(--accent);
}

.btn-primary,
.send-btn {
  color: #ffffff;
  background: var(--accent);
  box-shadow: none;
}

.btn-primary:hover:not(:disabled),
.send-btn:hover:not(:disabled) {
  background: var(--accent-hover);
  box-shadow: none;
  transform: none;
}

.char-count,
.knowledge-card,
.question-item,
.copy-btn:hover,
.btn-secondary:hover,
.chat-input-area input,
.option-item {
  background: var(--bg-elevated);
}

.chat-input-area input:focus {
  border-color: var(--accent);
}

.result-header h3,
.copy-btn,
.btn-secondary,
.btn-chat,
.error-toast {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

/* 会话侧边栏 */
.main-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.session-sidebar {
  width: 260px;
  flex-shrink: 0;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 12px;
  transition: width 0.2s, padding 0.2s, opacity 0.2s;
  overflow: hidden;
}

.session-sidebar.collapsed {
  width: 44px;
  padding: 8px;
  opacity: 0.7;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.sidebar-header h3 {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
}

.sidebar-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  flex-shrink: 0;
}

.sidebar-toggle:hover {
  background: var(--accent-soft);
  color: var(--accent);
}

.sidebar-actions {
  margin-bottom: 8px;
}

.btn-new-chat {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  width: 100%;
  padding: 8px;
  border: 1px dashed var(--border-default);
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
}

.btn-new-chat:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-soft);
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 60vh;
  overflow-y: auto;
}

.session-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  text-align: left;
  transition: background 0.15s, border-color 0.15s;
}

.session-item:hover {
  background: var(--accent-soft);
  border-color: var(--border-subtle);
}

.session-item.active {
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--accent);
}

.session-title {
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-item.active .session-title {
  color: var(--accent);
}

.session-meta {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: var(--text-muted);
}

.sidebar-loading,
.sidebar-empty {
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
  padding: 20px 8px;
}

.main-content {
  flex: 1;
  min-width: 0;
}

@media (max-width: 768px) {
  .main-layout {
    flex-direction: column;
  }

  .session-sidebar {
    width: 100%;
    max-height: 200px;
  }

  .session-sidebar.collapsed {
    width: 100%;
    max-height: 44px;
  }

  .session-list {
    max-height: 140px;
    flex-direction: row;
    flex-wrap: wrap;
  }

  .session-item {
    min-width: 140px;
    flex: 1;
  }
}
</style>
