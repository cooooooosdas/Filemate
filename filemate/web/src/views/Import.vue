<!--
  View: Import
  Design: Premium upload interface with drag-drop
  Animations: Drop zone interaction, progress animation, micro-feedback
-->
<template>
  <div class="import-page">
    <h2 class="page-title"><el-icon><Upload /></el-icon> 导入文件</h2>

    <!-- Upload Zone -->
    <label
      class="upload-zone"
      for="primary-file-upload"
      :class="{ 'is-dragover': isDragover, 'is-uploading': isUploading }"
      @dragover.prevent="handleDragover"
      @dragleave.prevent="handleDragleave"
      @drop.prevent="handleDrop"
    >
      <input
        id="primary-file-upload"
        ref="fileInput"
        name="course_files"
        type="file"
        :disabled="isUploading"
        multiple
        accept=".doc,.docx,.pdf,.ppt,.pptx,.txt,.jpg,.png"
        @change="handleFileSelect"
        hidden
      />

      <div v-if="!isUploading" class="upload-content">
        <div class="upload-icon-wrap">
          <div class="upload-icon">
            <el-icon size="48"><Upload /></el-icon>
          </div>
        </div>
        <h3>拖拽文件到这里</h3>
        <p>或点击选择文件</p>
        <div class="upload-formats">
          <span class="format-tag" v-for="fmt in formats" :key="fmt">{{ fmt }}</span>
        </div>
      </div>

      <!-- Uploading State -->
      <div v-else class="uploading-content">
        <div class="upload-progress-wrap">
          <el-progress
            type="circle"
            :percentage="uploadProgress"
            :width="140"
            :stroke-width="6"
            :color="progressColors"
          >
            <template #default>
              <div class="progress-inner">
                <span class="progress-value">{{ Math.round(uploadProgress) }}</span>
                <span class="progress-unit">%</span>
              </div>
            </template>
          </el-progress>
        </div>
        <h3>正在处理</h3>
        <p class="uploading-name">{{ uploadingFileName }}</p>
      </div>
    </label>

    <!-- Actions -->
    <div class="upload-actions">
      <button class="btn-primary" @click="triggerFileInput" :disabled="isUploading">
        <el-icon><FolderOpened /></el-icon>
        选择文件
      </button>
      <button class="btn-secondary" @click="uploadFromClipboard" :disabled="isUploading">
        <el-icon><Document /></el-icon>
        粘贴上传
      </button>
    </div>

    <!-- Queue -->
    <div v-if="uploadQueue.length > 0" class="queue-section">
      <div class="queue-header">
        <h3><el-icon><List /></el-icon> 上传队列</h3>
        <span class="queue-count">{{ uploadQueue.length }} 个文件</span>
      </div>

      <div class="queue-list">
        <div
          v-for="(item, index) in uploadQueue"
          :key="index"
          class="queue-item"
          :style="{ '--delay': index * 0.05 + 's' }"
          :class="{ 'animate-in': true }"
        >
          <div class="queue-icon">{{ getFileIcon(item.name) }}</div>
          <div class="queue-info">
            <div class="queue-name">{{ item.name }}</div>
            <div class="queue-size">{{ formatSize(item.size) }}</div>
          </div>
          <div class="queue-status">
            <span class="status-badge" :class="'status-' + item.status">
              {{ getStatusText(item.status) }}
            </span>
          </div>
          <div class="queue-actions">
            <button
              v-if="item.status === 'error'"
              class="action-btn"
              @click.stop="retryUpload(index)"
            >
              重试
            </button>
            <button
              v-if="item.status !== 'uploading'"
              class="action-btn delete"
              @click.stop="removeFromQueue(index)"
            >
              删除
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Tips -->
    <div class="tips-card">
      <div class="tips-icon">💡</div>
      <div class="tips-content">
        <h4>使用提示</h4>
        <ul>
          <li>支持批量上传多个文件</li>
          <li>上传后自动进行分类、命名和日程提取</li>
          <li>处理完成后可在"分类预览"查看结果</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload, FolderOpened, Document, List } from '@element-plus/icons-vue'
import { uploadFile } from '../services/api'

const fileInput = ref<HTMLInputElement>()
const isDragover = ref(false)
const isUploading = ref(false)
const uploadProgress = ref(0)
const uploadingFileName = ref('')

const uploadQueue = ref<Array<{
  file: File
  name: string
  size: number
  status: 'pending' | 'uploading' | 'success' | 'error'
  error?: string
}>>([])

const formats = ['DOC', 'DOCX', 'PDF', 'PPT', 'PPTX', 'TXT', 'JPG', 'PNG']

const progressColors = [
  { color: '#10b981', percentage: 20 },
  { color: '#059669', percentage: 40 },
  { color: '#34d399', percentage: 60 },
  { color: '#6ee7b7', percentage: 80 },
  { color: '#22c55e', percentage: 100 }
]

const triggerFileInput = () => {
  fileInput.value?.click()
}

const handleDragover = () => {
  isDragover.value = true
}

const handleDragleave = () => {
  isDragover.value = false
}

const handleDrop = (e: DragEvent) => {
  isDragover.value = false
  const files = Array.from(e.dataTransfer?.files || [])
  if (files.length > 0) {
    addToQueue(files)
  }
}

const handleFileSelect = (e: Event) => {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files || [])
  if (files.length > 0) {
    addToQueue(files)
  }
  input.value = ''
}

const addToQueue = (files: File[]) => {
  for (const file of files) {
    uploadQueue.value.push({
      file,
      name: file.name,
      size: file.size,
      status: 'pending'
    })
  }
  processQueue()
}

const processQueue = async () => {
  const pending = uploadQueue.value.find(q => q.status === 'pending')
  if (!pending || isUploading.value) return

  isUploading.value = true
  uploadProgress.value = 0
  uploadingFileName.value = pending.name
  pending.status = 'uploading'

  try {
    const progressInterval = setInterval(() => {
      if (uploadProgress.value < 90) {
        uploadProgress.value += Math.random() * 18
      }
    }, 180)

    await uploadFile(pending.file)

    clearInterval(progressInterval)
    uploadProgress.value = 100
    pending.status = 'success'

    ElMessage.success(`文件 "${pending.name}" 处理完成！`)

    setTimeout(() => {
      isUploading.value = false
      uploadProgress.value = 0
      processQueue()
    }, 1200)
  } catch (e: any) {
    pending.status = 'error'
    pending.error = e.message || '处理失败'
    ElMessage.error(`文件 "${pending.name}" 处理失败`)
    isUploading.value = false
    uploadProgress.value = 0
    processQueue()
  }
}

const retryUpload = (index: number) => {
  const item = uploadQueue.value[index]
  item.status = 'pending'
  item.error = undefined
  processQueue()
}

const removeFromQueue = (index: number) => {
  uploadQueue.value.splice(index, 1)
}

const uploadFromClipboard = async () => {
  try {
    const items = await navigator.clipboard.read()
    if (items.length === 0) {
      ElMessage.warning('剪贴板为空')
      return
    }

    const files: File[] = []
    for (const item of items) {
      for (const type of item.types) {
        if (type.startsWith('image/') || type.includes('pdf')) {
          const blob = await item.getType(type)
          const file = new File([blob], `clipboard_${Date.now()}.${type.split('/')[1]}`, { type })
          files.push(file)
        }
      }
    }

    if (files.length > 0) {
      addToQueue(files)
    } else {
      ElMessage.warning('剪贴板中没有支持的文件')
    }
  } catch (e) {
    ElMessage.error('读取剪贴板失败')
  }
}

const getFileIcon = (name: string) => {
  const ext = name.split('.').pop()?.toLowerCase() || ''
  const icons: Record<string, string> = {
    doc: '📄', docx: '📄', pdf: '📕', ppt: '📊', pptx: '📊',
    txt: '📝', jpg: '🖼️', png: '🖼️', gif: '🖼️'
  }
  return icons[ext] || '📁'
}

const formatSize = (bytes: number) => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

const getStatusText = (status: string) => {
  const texts: Record<string, string> = {
    pending: '等待中',
    uploading: '上传中',
    success: '已完成',
    error: '失败'
  }
  return texts[status] || status
}
</script>

<style scoped>
/* ═══════════════════════════════════════════════════════
   Design Tokens
   ═══════════════════════════════════════════════════════ */
.import-page {
  --bg-card: var(--bg-surface);
  --border-subtle: #d7e3d9;
  --border-default: #bfd0c3;

  --text-primary: #183229;
  --text-secondary: #4d655b;
  --text-muted: #6d8077;

  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 20px;

  --transition-fast: 0.15s cubic-bezier(0.4, 0, 0.2, 1);
  --transition-smooth: 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  max-width: 900px;
  margin: 0 auto;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 24px;
  animation: fadeDown 0.4s ease-out;
}

@keyframes fadeDown {
  from {
    opacity: 0;
    transform: translateY(-12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ═══════════════════════════════════════════════════════
   Upload Zone with Micro-interactions
   ═══════════════════════════════════════════════════════ */
.upload-zone {
  background: var(--bg-card);
  border: 2px dashed var(--border-default);
  border-radius: var(--radius-xl);
  padding: 56px 32px;
  text-align: center;
  cursor: pointer;
  transition:
    border-color var(--transition-smooth),
    background var(--transition-smooth),
    transform var(--transition-fast);
  min-height: 280px;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.5s ease-out 0.1s backwards;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.upload-zone:hover {
  border-color: rgba(16, 185, 129, 0.35);
  background: rgba(16, 185, 129, 0.02);
}

.upload-zone:hover .upload-icon {
  transform: scale(1.05);
}

.upload-zone.is-dragover {
  border-color: #10b981;
  background: rgba(16, 185, 129, 0.06);
  border-style: solid;
  transform: scale(1.01);
}

.upload-zone.is-uploading {
  cursor: default;
  pointer-events: none;
}

.upload-content {
  pointer-events: none;
}

.upload-icon-wrap {
  position: relative;
  display: inline-block;
  margin-bottom: 16px;
}

.upload-icon {
  width: 72px;
  height: 72px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-soft);
  border: 1px solid var(--accent-border);
  border-radius: 14px;
  color: var(--accent);
}

.upload-content h3 {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.upload-content p {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0 0 20px;
}

.upload-formats {
  display: flex;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
}

.format-tag {
  font-size: 11px;
  padding: 4px 12px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  color: var(--text-muted);
  letter-spacing: 0.02em;
  transition: color var(--transition-fast), background-color var(--transition-fast), border-color var(--transition-fast);
}

.format-tag:hover {
  background: rgba(99, 102, 241, 0.1);
  border-color: rgba(99, 102, 241, 0.2);
  color: #6ee7b7;
}

/* Uploading State */
.uploading-content {
  pointer-events: none;
}

.upload-progress-wrap {
  margin-bottom: 20px;
  animation: progressFadeIn 0.3s ease-out;
}

@keyframes progressFadeIn {
  from {
    opacity: 0;
    transform: scale(0.9);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.progress-inner {
  display: flex;
  align-items: baseline;
  justify-content: center;
}

.progress-value {
  font-size: 36px;
  font-weight: 700;
  color: var(--text-primary);
}

.progress-unit {
  font-size: 16px;
  color: var(--text-muted);
  margin-left: 2px;
}

.uploading-content h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.uploading-name {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin: 0 auto;
  animation: textFadeIn 0.3s ease-out 0.2s backwards;
}

@keyframes textFadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* ═══════════════════════════════════════════════════════
   Actions
   ═══════════════════════════════════════════════════════ */
.upload-actions {
  margin-top: 24px;
  display: flex;
  justify-content: center;
  gap: 14px;
  animation: fadeUp 0.4s ease-out 0.2s backwards;
}

@keyframes fadeUp {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 14px 32px;
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  border: none;
  border-radius: var(--radius-md);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition:
    transform var(--transition-fast),
    box-shadow var(--transition-fast),
    background var(--transition-fast);
  box-shadow: 0 4px 16px rgba(16, 185, 129, 0.3);
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 24px rgba(16, 185, 129, 0.4);
}

.btn-primary:active:not(:disabled) {
  transform: scale(0.97) translateY(1px);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 14px 32px;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition:
    background var(--transition-fast),
    border-color var(--transition-fast),
    color var(--transition-fast),
    transform var(--transition-fast);
}

.btn-secondary:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.15);
  color: var(--text-primary);
}

.btn-secondary:active:not(:disabled) {
  transform: scale(0.98);
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ═══════════════════════════════════════════════════════
   Queue with Stagger Animation
   ═══════════════════════════════════════════════════════ */
.queue-section {
  margin-top: 32px;
}

.queue-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.queue-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.queue-count {
  font-size: 13px;
  color: var(--text-muted);
}

.queue-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.queue-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  transition:
    background var(--transition-fast),
    border-color var(--transition-fast),
    transform var(--transition-fast);
  animation: slideIn 0.3s ease-out backwards;
  animation-delay: var(--delay, 0s);
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateX(-12px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.queue-item:hover {
  background: rgba(255, 255, 255, 0.02);
}

.queue-item .queue-icon {
  font-size: 24px;
}

.queue-item .queue-info {
  flex: 1;
  min-width: 0;
}

.queue-item .queue-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.queue-item .queue-size {
  font-size: 12px;
  color: var(--text-muted);
}

.queue-status {
  min-width: 80px;
}

.status-badge {
  display: inline-block;
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-muted);
}

.status-badge.status-pending {
  background: rgba(251, 191, 36, 0.1);
  color: #fbbf24;
}

.status-badge.status-uploading {
  background: rgba(99, 102, 241, 0.1);
  color: #6ee7b7;
}

.status-badge.status-success {
  background: rgba(34, 197, 94, 0.1);
  color: #4ade80;
}

.status-badge.status-error {
  background: rgba(239, 68, 68, 0.1);
  color: #f87171;
}

.queue-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  font-size: 12px;
  padding: 6px 12px;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  cursor: pointer;
  transition:
    background var(--transition-fast),
    color var(--transition-fast),
    transform var(--transition-fast);
}

.action-btn:hover {
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
}

.action-btn:active {
  transform: scale(0.95);
}

.action-btn.delete:hover {
  border-color: rgba(239, 68, 68, 0.3);
  color: #f87171;
}

/* ═══════════════════════════════════════════════════════
   Tips
   ═══════════════════════════════════════════════════════ */
.tips-card {
  margin-top: 32px;
  display: flex;
  gap: 16px;
  padding: 20px 24px;
  background: rgba(99, 102, 241, 0.04);
  border: 1px solid rgba(99, 102, 241, 0.12);
  border-radius: var(--radius-md);
  animation: fadeUp 0.4s ease-out 0.3s backwards;
}

.tips-icon {
  font-size: 20px;
}

.tips-content h4 {
  font-size: 14px;
  font-weight: 600;
  color: #6ee7b7;
  margin: 0 0 8px;
}

.tips-content ul {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.8;
}

.tips-content li {
  margin: 0;
}

/* Responsive */
@media (max-width: 640px) {
  .upload-zone {
    padding: 40px 20px;
  }

  .upload-actions {
    flex-direction: column;
  }

  .btn-primary,
  .btn-secondary {
    width: 100%;
    justify-content: center;
  }
}
</style>

<style scoped>
/* 浅色自然绿主题覆盖 */
.upload-zone.is-dragover {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.upload-icon,
.format-tag:hover,
.status-badge.status-uploading,
.tip-card h4 {
  color: var(--accent);
}

.upload-icon-bg,
.format-tag:hover,
.status-badge.status-uploading,
.tip-card {
  background: var(--accent-soft);
  border-color: var(--accent-border);
}

.btn-primary {
  color: #ffffff;
  background: var(--accent);
  box-shadow: none;
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-hover);
  box-shadow: 0 8px 18px rgba(47, 125, 85, 0.16);
}

.format-tag,
.queue-item:hover,
.file-icon,
.action-btn:hover,
.btn-secondary:hover:not(:disabled) {
  background: var(--bg-elevated);
  border-color: var(--border-strong);
}
</style>
