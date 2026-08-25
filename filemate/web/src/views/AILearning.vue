<template>
  <div class="ai-learning-page">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon class="title-icon"><ChatDotSquare /></el-icon>
        AI辅助学习
      </h1>
      <p class="page-subtitle">快来问问你的学习小助手吧</p>
    </div>

    <!-- API 配置（仅 AI 学习板块） -->
    <div class="api-config-section">
      <button class="config-toggle" @click="showConfig = !showConfig">
        <el-icon><Setting /></el-icon>
        <span>LLM 配置</span>
        <span v-if="!isApiKeyConfigured" class="config-badge">未配置</span>
        <span v-else class="config-badge config-badge--ok">已配置</span>
        <el-icon class="toggle-arrow" :class="{ expanded: showConfig }">
          <ArrowRight />
        </el-icon>
      </button>

      <el-collapse-transition>
        <div v-show="showConfig" class="config-panel">
          <div class="config-fields">
            <div class="config-field">
              <label>API Key</label>
              <el-input
                v-model="llmConfig.apiKey"
                type="password"
                placeholder="输入你的 API Key"
                show-password
              />
            </div>
            <div class="config-field">
              <label>Base URL</label>
              <el-input
                v-model="llmConfig.baseUrl"
                placeholder="请输入相应的 URL"
              />
            </div>
            <div class="config-field">
              <label>模型名</label>
              <el-input
                v-model="llmConfig.model"
                placeholder="请输入模型名"
              />
            </div>
          </div>
          <div class="config-actions">
            <el-button
              type="primary"
              size="small"
              :loading="isLoadingConfig"
              :disabled="isLoadingConfig"
              @click="saveConfig"
            >
              <el-icon><Check /></el-icon>
              保存配置
            </el-button>
            <span v-if="configSaved" class="config-success">已保存</span>
          </div>
        </div>
      </el-collapse-transition>
    </div>

    <!-- 模式选择 -->
    <div class="mode-selector" role="group" aria-label="学习模式">
      <button
        class="mode-btn"
        :class="{ active: mode === 'explore' }"
        @click="selectMode('explore')"
      >
        <el-icon><Compass /></el-icon>
        <span>探索全新领域</span>
      </button>
      <button
        class="mode-btn"
        :class="{ active: mode === 'reinforce' }"
        @click="selectMode('reinforce')"
      >
        <el-icon><Reading /></el-icon>
        <span>加强已有知识</span>
      </button>
    </div>

    <!-- 对话区域 -->
    <div class="chat-container" ref="chatContainer">
      <div v-if="!hasMessages" class="chat-placeholder">
        <el-icon class="placeholder-icon"><ChatLineRound /></el-icon>
        <p>选择学习模式，开始与 AI 助手对话</p>
        <p class="placeholder-hint">支持上传文件，AI 会基于文件内容或知识库回答</p>

        <!-- 未配置 API Key 的警告 -->
        <div v-if="!isApiKeyConfigured" class="api-warning">
          <el-icon><WarningFilled /></el-icon>
          <span>请先在下方「LLM 配置」中填入你的 API Key，否则无法调用 AI</span>
        </div>
      </div>

      <div
        v-for="(msg, idx) in displayedMessages"
        :key="msg.message_id || idx"
        class="message-row"
        :class="msg.role"
      >
        <div class="message-avatar">
          <el-icon v-if="msg.role === 'user'"><User /></el-icon>
          <el-icon v-else><MagicStick /></el-icon>
        </div>
        <div class="message-body">
          <div class="message-header">
            <span class="message-role">{{ msg.role === 'user' ? '你' : 'AI 助手' }}</span>
            <button
              v-if="msg.role === 'assistant'"
              class="msg-download-btn"
              @click="downloadMessage(msg)"
              title="下载此回复为 Markdown 文件"
            >
              <el-icon><Download /></el-icon>
            </button>
          </div>
          <div class="message-content" v-html="renderMarkdown(msg.content)"></div>

          <!-- 引用卡片 -->
          <div v-if="msg.citations && msg.citations.length" class="citations">
            <div class="citations-label">引用来源</div>
            <div
              v-for="(cit, ci) in msg.citations"
              :key="ci"
              class="citation-card"
            >
              <div class="citation-source">{{ cit.source_name }}</div>
              <div class="citation-excerpt">{{ cit.excerpt }}</div>
              <div class="citation-score">相关度: {{ cit.score }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 加载中 -->
      <div v-if="isLoading" class="message-row assistant">
        <div class="message-avatar">
          <el-icon><MagicStick /></el-icon>
        </div>
        <div class="message-body">
          <div class="typing-indicator">
            <span></span><span></span><span></span>
          </div>
        </div>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="input-area">
      <!-- 文件上传 -->
      <div class="file-upload-row">
        <el-upload
          :auto-upload="false"
          :show-file-list="false"
          :on-change="handleFileChange"
          accept=".pdf,.doc,.docx,.ppt,.pptx,.txt"
        >
          <el-button size="small" :disabled="!mode">
            <el-icon><Document /></el-icon>
            上传文件
          </el-button>
        </el-upload>
        <span v-if="selectedFile" class="file-name">
          {{ selectedFile.name }}
          <el-button
            type="text"
            size="small"
            @click.stop="clearFile"
          >移除</el-button>
        </span>
      </div>

      <!-- 输入框 + 发送 -->
      <div class="input-row">
        <el-input
          v-model="inputText"
          type="textarea"
          :rows="2"
          :placeholder="inputPlaceholder"
          :disabled="!mode || isLoading"
          @keydown.enter.exact.prevent="sendMessage"
        />
        <el-button
          type="primary"
          :disabled="!canSend"
          :loading="isLoading"
          @click="sendMessage"
        >
          <el-icon><Promotion /></el-icon>
          发送
        </el-button>
      </div>

      <!-- 总结对话 -->
      <div class="summary-row">
        <el-button
          :disabled="!hasMessages || isLoading"
          @click="generateSummary"
        >
          <el-icon><DocumentChecked /></el-icon>
          总结对话
        </el-button>
        <el-button
          :disabled="!hasMessages || isLoading"
          @click="clearConversation"
          type="default"
          size="default"
        >
          <el-icon><Delete /></el-icon>
          清空对话
        </el-button>
        <el-tooltip v-if="summaryResult" content="点击查看总结内容" placement="top">
          <span class="summary-success summary-link" @click="viewSummary">
            <el-icon><View /></el-icon>
            已生成：{{ summaryResult.title }}
          </span>
        </el-tooltip>
      </div>

      <!-- 总结内容对话框 -->
      <el-dialog
        v-model="summaryDialogVisible"
        :title="summaryResult?.title || '学习笔记'"
        width="70%"
        top="5vh"
        destroy-on-close
      >
        <div v-loading="summaryDialogLoading" class="summary-dialog-content">
          <div v-if="!summaryDialogLoading" class="markdown-body" v-html="renderMarkdown(summaryDialogContent)"></div>
        </div>
      </el-dialog>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ChatDotSquare,
  Compass,
  Reading,
  ChatLineRound,
  User,
  MagicStick,
  Document,
  Promotion,
  DocumentChecked,
  Setting,
  ArrowRight,
  Check,
  WarningFilled,
  View,
  Delete,
  Download
} from '@element-plus/icons-vue'
import {
  createAILearningSession,
  sendAILearningMessage,
  getAILearningSession,
  getAILearningSessions,
  summarizeAILearningSession,
  validateAILearningConfig,
  updateAILearningSettings,
  updateAILearningMode,
  getKnowledgeArtifact
} from '../services/api'
import type { AIMessage, AICitation } from '../types'

// ──────────────────────────────────────────
// 状态
// ──────────────────────────────────────────

const mode = ref<'explore' | 'reinforce'>('explore')
const sessionId = ref<string | null>(null)
const messages = ref<AIMessage[]>([])
const inputText = ref('')
const isLoading = ref(false)
const selectedFile = ref<File | null>(null)
const fileText = ref('')
const summaryResult = ref<{ title: string; artifact_id: string } | null>(null)
const summaryDialogVisible = ref(false)
const summaryDialogContent = ref('')
const summaryDialogLoading = ref(false)
const chatContainer = ref<HTMLElement | null>(null)
const router = useRouter()

// LLM 配置（仅 AI 学习板块使用）
const llmConfig = ref({
  apiKey: '',
  baseUrl: '',
  model: '',
})
const showConfig = ref(false)
const configSaved = ref(false)
const isLoadingConfig = ref(false)

// ──────────────────────────────────────────
// 计算属性
// ──────────────────────────────────────────

const hasMessages = computed(() => displayedMessages.value.length > 0)

const displayedMessages = computed(() => {
  return messages.value.filter(m => (m as any).mode === mode.value || !(m as any).mode)
})

const isApiKeyConfigured = computed(() => !!llmConfig.value.apiKey.trim())

const canSend = computed(() => {
  return !!mode.value && !!inputText.value.trim() && !isLoading.value && isApiKeyConfigured.value
})

const inputPlaceholder = computed(() => {
  if (!mode.value) return '请先选择学习模式'
  if (mode.value === 'explore') return '输入你想学习的主题或问题...'
  return '输入你想巩固的问题或知识点...'
})

// 面板展开时重置 loading，避免卡死
watch(showConfig, (open) => {
  if (open) isLoadingConfig.value = false
})

// ──────────────────────────────────────────
// 方法
// ──────────────────────────────────────────

async function selectMode(m: 'explore' | 'reinforce') {
  if (mode.value === m) return
  mode.value = m
  // 持久化模式切换
  if (sessionId.value) {
    try {
      await updateAILearningMode(sessionId.value, m)
    } catch {
      // 静默失败，本地状态已更新
    }
  }
  // 重新加载当前模式的消息
  await loadMessagesForMode(m)
}

async function loadConfig() {
  if (!sessionId.value) return
  try {
    const detail = await getAILearningSession(sessionId.value)
    llmConfig.value.apiKey = detail.user_api_key || ''
    llmConfig.value.baseUrl = detail.llm_base_url || 'https://api.stepfun.com/step_plan/v1'
    llmConfig.value.model = detail.llm_model || 'step-explore'
  } catch {
    // ignore
  }
}

async function saveConfig() {
  if (!sessionId.value) return

  // 如果 API Key 为空，直接报错
  if (!llmConfig.value.apiKey.trim()) {
    ElMessage.error('请填写 API Key')
    return
  }

  isLoadingConfig.value = true
  const loadingMsg = ElMessage({
    message: '正在检测 API 连通性...',
    type: 'warning',
    duration: 0,
  })
  const startTime = Date.now()
  try {
    // 1. 先验证 API 是否可用
    await validateAILearningConfig(sessionId.value, {
      userApiKey: llmConfig.value.apiKey,
      llmBaseUrl: llmConfig.value.baseUrl,
      llmModel: llmConfig.value.model,
    })

    // 保证 loading 提示至少显示 1.5 秒
    const elapsed = Date.now() - startTime
    if (elapsed < 1500) {
      await new Promise(r => setTimeout(r, 1500 - elapsed))
    }
    loadingMsg.close()

    // 2. 验证通过，保存配置
    await updateAILearningSettings(sessionId.value, {
      userApiKey: llmConfig.value.apiKey,
      llmBaseUrl: llmConfig.value.baseUrl,
      llmModel: llmConfig.value.model,
    })

    // 3. 成功：折叠面板 + 绿色提示
    showConfig.value = false
    ElMessage.success('配置成功')
  } catch (err: any) {
    const elapsed = Date.now() - startTime
    if (elapsed < 1500) {
      await new Promise(r => setTimeout(r, 1500 - elapsed))
    }
    loadingMsg.close()
    // 失败：红色提示 + 面板保持展开
    const msg = err.message || ''
    if (msg.includes('异常') || msg.includes('验证') || msg.includes('信息')) {
      ElMessage.error('配置失败，API信息异常')
    } else {
      ElMessage.error(msg || '配置失败，请检查后重试')
    }
  } finally {
    isLoadingConfig.value = false
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  })
}

async function loadMessagesForMode(m: 'explore' | 'reinforce') {
  if (!sessionId.value) return
  try {
    const detail = await getAILearningSession(sessionId.value)
    const allMessages = detail.messages || []
    // 按模式过滤：只显示当前模式的消息
    messages.value = allMessages.filter((msg: any) => {
      // 旧消息没有 mode 字段时，归入当前模式（向后兼容）
      if (!msg.mode) return true
      return msg.mode === m
    })
    await scrollToBottom()
  } catch {
    // ignore
  }
}

async function clearConversation() {
  if (!sessionId.value || !hasMessages.value) return
  try {
    await ElMessageBox.confirm(
      `确定要清空「${mode.value === 'explore' ? '探索全新领域' : '加强已有知识'}」的对话内容吗？`,
      '确认清除',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    messages.value = []
    ElMessage.success('对话已清空')
  } catch {
    // 用户取消
  }
}

async function downloadMessage(msg: any) {
  if (!msg || !msg.content) return
  try {
    const timestamp = msg.created_at
      ? new Date(msg.created_at).toISOString().slice(0, 19).replace(/[T:]/g, '-')
      : Date.now()
    const title = msg.content.slice(0, 30).replace(/[^\w一-鿿-]/g, '').trim() || 'AI回复'
    const filename = `AI回复_${title}_${timestamp}.md`

    const mdContent = `# AI 助手回复

> 时间：${msg.created_at || '未知'}
> 会话：${sessionId.value || '未知'}

---

${msg.content}
`

    const blob = new Blob([mdContent], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('文件已下载')
  } catch (err: any) {
    ElMessage.error(err.message || '下载失败')
  }
}

async function sendMessage() {
  if (!canSend.value || !sessionId.value) return

  // 先保存当前配置
  if (llmConfig.value.apiKey && !configSaved.value) {
    try {
      await updateAILearningSettings(sessionId.value, {
        userApiKey: llmConfig.value.apiKey,
        llmBaseUrl: llmConfig.value.baseUrl,
        llmModel: llmConfig.value.model,
      })
    } catch {
      // 静默失败，后端会 fallback
    }
  }

  const text = inputText.value.trim()
  inputText.value = ''
  isLoading.value = true
  scrollToBottom()

  try {
    const reply = await sendAILearningMessage(sessionId.value, {
      content: text,
      fileText: fileText.value || undefined,
    })

    messages.value.push({
      message_id: `user_${Date.now()}`,
      session_id: sessionId.value,
      role: 'user',
      content: text,
      citations: [],
      created_at: new Date().toISOString(),
      mode: mode.value,
    })
    messages.value.push({
      message_id: reply.message_id,
      session_id: sessionId.value,
      role: 'assistant',
      content: reply.content || '抱歉，AI 未返回有效回复，请重试。',
      citations: reply.citations as AICitation[],
      created_at: new Date().toISOString(),
      mode: mode.value,
    })
    clearFile()
  } catch (err: any) {
    ElMessage.error(err.message || '发送消息失败')
  } finally {
    isLoading.value = false
    scrollToBottom()
  }
}

async function generateSummary() {
  if (!sessionId.value || isLoading.value) return
  isLoading.value = true
  try {
    const result = await summarizeAILearningSession(sessionId.value)
    summaryResult.value = {
      title: result.title,
      artifact_id: result.artifact_id,
    }
    ElMessage.success(`总结已保存：${result.title}，即将跳转到知识库...`)
    // 延迟跳转，让用户看到成功提示
    setTimeout(() => {
      router.push('/knowledge')
    }, 1500)
  } catch (err: any) {
    ElMessage.error(err.message || '生成总结失败')
  } finally {
    isLoading.value = false
  }
}

async function viewSummary() {
  if (!summaryResult.value?.artifact_id) return
  summaryDialogLoading.value = true
  summaryDialogVisible.value = true
  summaryDialogContent.value = ''
  try {
    const artifact = await getKnowledgeArtifact(summaryResult.value.artifact_id)
    summaryDialogContent.value = artifact.content || '（无内容）'
  } catch (err: any) {
    summaryDialogContent.value = `加载失败：${err.message || '未知错误'}`
  } finally {
    summaryDialogLoading.value = false
  }
}

// 文件上传处理
function handleFileChange(file: any) {
  if (!file) return
  selectedFile.value = file.raw
  const reader = new FileReader()
  reader.onload = () => {
    fileText.value = reader.result as string
  }
  reader.readAsText(file.raw)
}

function clearFile() {
  selectedFile.value = null
  fileText.value = ''
}

// Markdown 渲染（支持代码块、表格、数学公式）
function renderMarkdown(text: string): string {
  if (!text) return ''
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // 数学公式占位（避免 markdown 解析器破坏公式内容）
  const mathBlocks: Array<{ placeholder: string; expr: string }> = []
  const mathInlines: Array<{ placeholder: string; expr: string }> = []
  let blockIdx = 0
  let inlineIdx = 0

  // 块级公式 $$...$$
  html = html.replace(/\$\$([\s\S]+?)\$\$/g, (_, expr) => {
    const placeholder = `%%MATH_BLOCK_${blockIdx++}%%`
    mathBlocks.push({ placeholder, expr: expr.trim() })
    return placeholder
  })

  // 行内公式 $...$
  html = html.replace(/(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)/g, (_, expr) => {
    const placeholder = `%%MATH_INLINE_${inlineIdx++}%%`
    mathInlines.push({ placeholder, expr: expr.trim() })
    return placeholder
  })

  // 代码块（必须在行内元素之前处理）
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const langLabel = lang ? ` class="language-${lang}"` : ''
    return `<pre><code${langLabel}>${code.trim()}</code></pre>`
  })

  // 表格
  html = html.replace(/^(.+?)\n[ \t]*\|[-| ]+\|[ \t]*\n([\s\S]+?)(?=\n\n|\n*$)/gm, (_match: string, headerRow: string, bodyRows: string) => {
    const headers = headerRow.split('|').map(h => h.trim()).filter(h => h.length > 0)
    const rows = bodyRows.trim().split('\n')
    let table = '<table><thead><tr>' + headers.map(h => `<th>${h}</th>`).join('') + '</tr></thead><tbody>'
    for (const row of rows) {
      const cells = row.split('|').map(c => c.trim()).filter(c => c.length > 0)
      if (cells.length) {
        table += '<tr>' + cells.map(c => `<td>${c}</td>`).join('') + '</tr>'
      }
    }
    return table + '</tbody></table>'
  })

  // 标题
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>')
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>')

  // 引用
  html = html.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>')
  html = html.replace(/^(<blockquote>.+<\/blockquote>\n?)+/g, (match) => {
    return match.replace(/<\/blockquote>\n<blockquote>/g, '<br>')
  })

  // 分隔线
  html = html.replace(/^---$/gm, '<hr>')

  // 加粗和斜体
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')

  // 删除线
  html = html.replace(/~~(.+?)~~/g, '<del>$1</del>')

  // 行内代码
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')

  // 无序列表
  html = html.replace(/^[ \t]*[-*] (.+)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>.+<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`)

  // 有序列表
  html = html.replace(/^[ \t]*\d+\. (.+)$/gm, '<li>$1</li>')

  // 段落（双换行）
  html = html.replace(/\n{2,}/g, '</p><p>')

  // 单换行转 <br>
  html = html.replace(/\n/g, '<br>')

  // 恢复数学公式
  for (const { placeholder, expr } of mathBlocks) {
    html = html.replace(placeholder, `<div class="math-block">$$${expr}$$</div>`)
  }
  for (const { placeholder, expr } of mathInlines) {
    html = html.replace(placeholder, `<span class="math-inline">$${expr}$</span>`)
  }

  return `<p>${html}</p>`
}

// KaTeX 数学公式渲染
let katexReady: Promise<void> | null = null

function initKatex(): Promise<void> {
  if (katexReady) return katexReady
  if ((window as any).katex) {
    katexReady = Promise.resolve()
    return katexReady
  }
  katexReady = new Promise<void>((resolve) => {
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css'
    document.head.appendChild(link)
    const script = document.createElement('script')
    script.src = 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js'
    script.onload = () => {
      renderChatMath()
      resolve()
    }
    script.onerror = () => {
      console.warn('KaTeX 加载失败，公式将显示原始文本')
      resolve()
    }
    document.head.appendChild(script)
  })
  return katexReady
}

function renderChatMath() {
  const katex = (window as any).katex
  if (!katex) return
  const container = chatContainer.value
  if (!container) return

  // 只渲染对话区域内的公式（不渲染对话框等）
  container.querySelectorAll('.math-block').forEach((el: any) => {
    try {
      const expr = el.textContent?.replace(/\$\$/g, '').trim() || ''
      katex.render(expr, el, { displayMode: true, throwOnError: false })
    } catch { /* 渲染失败保留原文 */ }
  })
  container.querySelectorAll('.math-inline').forEach((el: any) => {
    try {
      const expr = el.textContent?.replace(/\$/g, '').trim() || ''
      katex.render(expr, el, { displayMode: false, throwOnError: false })
    } catch { /* 渲染失败保留原文 */ }
  })
}

// 监听消息变化，渲染公式
watch([displayedMessages, mode], () => {
  if (displayedMessages.value.length > 0) {
    nextTick(() => {
      initKatex().then(() => renderChatMath())
    })
  }
})

// ──────────────────────────────────────────
// 生命周期
// ──────────────────────────────────────────

onMounted(async () => {
  try {
    // 优先加载最近的会话（API 配置和对话历史都在服务端）
    const sessions = await getAILearningSessions(1)
    if (sessions.length > 0) {
      const latest = sessions[0]
      sessionId.value = latest.session_id
      mode.value = latest.mode
      await loadConfig()
      // 加载对话历史（按模式过滤）
      const detail = await getAILearningSession(latest.session_id)
      if (detail.messages && detail.messages.length) {
        messages.value = detail.messages
          .filter((m: any) => !m.mode || m.mode === latest.mode)
          .map((m: any) => ({
            message_id: m.message_id,
            session_id: m.session_id,
            role: m.role as 'user' | 'assistant',
            content: m.content,
            citations: m.citations || [],
            created_at: m.created_at,
            mode: m.mode,
          }))
      }
    } else {
      // 没有历史会话，创建新的
      const resp = await createAILearningSession({
        mode: 'explore',
        userApiKey: '',
        llmBaseUrl: '',
        llmModel: '',
      })
      sessionId.value = resp.session_id
      mode.value = resp.mode
      await loadConfig()
    }
    // 未配置 API Key 时自动展开配置面板
    if (!llmConfig.value.apiKey) {
      showConfig.value = true
    }
  } catch (err: any) {
    ElMessage.error(err.message || '初始化学习会话失败')
  }
})
</script>

<style scoped>
.ai-learning-page {
  --bg-card: var(--bg-surface, #f7faf8);
  --border-subtle: #d7e3d9;
  --border-default: #bfd0c3;
  --text-primary: #183229;
  --text-secondary: #4d655b;
  --text-muted: #6d8077;
  --accent: #5b8a72;

  max-width: 900px;
  margin: 0 auto;
  padding: 24px;
}

.page-header {
  margin-bottom: 24px;
}

.page-title {
  font-size: 26px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 6px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-icon {
  color: var(--accent);
}

.page-subtitle {
  font-size: 15px;
  color: var(--text-muted);
  margin: 0;
}

/* API 配置 */
.api-config-section {
  margin-bottom: 16px;
}

.config-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  width: 100%;
}

.config-toggle:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.config-badge {
  margin-left: 6px;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
}

.config-badge:not(.config-badge--ok) {
  background: #fef0f0;
  color: #c0392b;
}

.config-badge--ok {
  background: #e8f5e9;
  color: #2e7d32;
}

.toggle-arrow {
  margin-left: auto;
  transition: transform 0.3s;
}

.toggle-arrow.expanded {
  transform: rotate(90deg);
}

.config-panel {
  padding: 14px;
  background: #fff;
  border: 1px solid var(--border-subtle);
  border-top: none;
  border-radius: 0 0 12px 12px;
  margin-top: -1px;
}

.config-fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 12px;
}

.config-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.config-field label {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
}

.config-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.config-success {
  font-size: 13px;
  color: var(--accent);
}

/* 未配置 API Key 警告 */
.api-warning {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 20px;
  padding: 10px 16px;
  background: #fef0f0;
  border: 1px solid #f5c6cb;
  border-radius: 10px;
  color: #c0392b;
  font-size: 13px;
}

.api-warning .el-icon {
  font-size: 18px;
  flex-shrink: 0;
}

/* 模式选择 */
.mode-selector {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.mode-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 20px;
  background: var(--bg-card);
  border: 2px solid var(--border-subtle);
  border-radius: 14px;
  color: var(--text-secondary);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.mode-btn:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}

.mode-btn.active {
  background: rgba(91, 138, 114, 0.12);
  border-color: var(--accent);
  color: var(--accent);
  font-weight: 600;
}

.mode-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 对话区域 */
.chat-container {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 16px;
  min-height: 400px;
  max-height: 520px;
  overflow-y: auto;
  padding: 20px;
  margin-bottom: 16px;
}

.chat-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 340px;
  color: var(--text-muted);
  text-align: center;
}

.placeholder-icon {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.placeholder-hint {
  font-size: 13px;
  margin-top: 8px;
  opacity: 0.7;
}

/* 消息 */
.message-row {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.message-row.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 18px;
}

.message-row.user .message-avatar {
  background: #d7e3d9;
  color: var(--text-primary);
}

.message-row.assistant .message-avatar {
  background: rgba(91, 138, 114, 0.15);
  color: var(--accent);
}

.message-body {
  max-width: 75%;
}

.message-role {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.message-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.msg-download-btn {
  display: none;
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 6px;
  color: var(--text-muted);
  font-size: 14px;
  border-radius: 4px;
  transition: all 0.2s;
}

.message-row:hover .msg-download-btn {
  display: inline-flex;
  align-items: center;
}

.msg-download-btn:hover {
  color: #409eff;
  background: rgba(64, 158, 255, 0.08);
}

.message-row.user .message-role {
  text-align: right;
}

.message-content {
  background: #fff;
  border: 1px solid var(--border-subtle);
  border-radius: 14px;
  padding: 12px 16px;
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary);
  word-break: break-word;
}

.message-row.user .message-content {
  background: rgba(91, 138, 114, 0.08);
  border-color: rgba(91, 138, 114, 0.2);
}

.message-content :deep(pre) {
  background: #f0f4f2;
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
  font-size: 13px;
}

.message-content :deep(code) {
  background: #f0f4f2;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
}

.message-content :deep(strong) {
  color: var(--text-primary);
}

/* 引用卡片 */
.citations {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.citations-label {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
}

.citation-card {
  background: rgba(91, 138, 114, 0.05);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 13px;
}

.citation-source {
  font-weight: 600;
  color: var(--accent);
  margin-bottom: 4px;
}

.citation-excerpt {
  color: var(--text-secondary);
  line-height: 1.5;
  margin-bottom: 4px;
}

.citation-score {
  font-size: 12px;
  color: var(--text-muted);
}

/* 输入中动画 */
.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 12px 16px;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  background: var(--accent);
  border-radius: 50%;
  animation: bounce 1.2s infinite;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-6px); opacity: 1; }
}

/* 输入区域 */
.input-area {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.file-upload-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.file-name {
  font-size: 13px;
  color: var(--text-secondary);
}

.input-row {
  display: flex;
  gap: 10px;
}

.input-row .el-input {
  flex: 1;
}

.input-row .el-button {
  align-self: flex-end;
}

.summary-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.summary-success {
  font-size: 13px;
  color: var(--accent);
}

.summary-link {
  cursor: pointer;
  transition: opacity 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.summary-link:hover {
  opacity: 0.8;
  text-decoration: underline;
}

.summary-dialog-content {
  max-height: 70vh;
  overflow-y: auto;
  padding: 8px 0;
}

.markdown-body {
  line-height: 1.8;
  color: #333;
}

.markdown-body pre {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 8px 0;
}

.markdown-body code {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Courier New', monospace;
  font-size: 0.9em;
}

.markdown-body strong {
  color: #000;
  font-weight: 600;
}

/* 数学公式渲染 */
.math-block {
  display: block;
  text-align: center;
  margin: 12px 0;
  padding: 12px;
  background: var(--bg-card);
  border-radius: 8px;
  overflow-x: auto;
}

.math-inline {
  display: inline;
}

/* Markdown 内容样式 */
.message-content p {
  margin: 0 0 8px 0;
}

.message-content p:last-child {
  margin-bottom: 0;
}

.message-content h1,
.message-content h2,
.message-content h3,
.message-content h4 {
  margin: 12px 0 6px 0;
  font-weight: 600;
  color: var(--text-primary);
}

.message-content h1 { font-size: 1.2em; }
.message-content h2 { font-size: 1.1em; }
.message-content h3 { font-size: 1.05em; }

.message-content ul,
.message-content ol {
  margin: 6px 0;
  padding-left: 20px;
}

.message-content li {
  margin: 2px 0;
}

.message-content blockquote {
  margin: 8px 0;
  padding: 8px 12px;
  border-left: 3px solid var(--accent);
  background: rgba(91, 138, 114, 0.06);
  border-radius: 0 6px 6px 0;
  color: var(--text-secondary);
}

.message-content hr {
  border: none;
  border-top: 1px solid var(--border-subtle);
  margin: 12px 0;
}

.message-content table {
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 0.9em;
  width: 100%;
}

.message-content th,
.message-content td {
  border: 1px solid var(--border-subtle);
  padding: 6px 10px;
  text-align: left;
}

.message-content th {
  background: var(--bg-card);
  font-weight: 600;
}

.message-content code {
  background: rgba(91, 138, 114, 0.08);
  padding: 1px 5px;
  border-radius: 3px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 0.88em;
  color: var(--accent);
}

.message-content pre {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 8px 0;
  font-size: 0.85em;
  line-height: 1.6;
}

.message-content pre code {
  background: none;
  padding: 0;
  color: inherit;
  font-size: inherit;
}

/* 响应式 */
@media (max-width: 768px) {
  .ai-learning-page {
    padding: 16px;
  }

  .mode-selector {
    flex-direction: column;
  }

  .message-body {
    max-width: 85%;
  }

  .chat-container {
    min-height: 300px;
    max-height: 400px;
  }
}
</style>
