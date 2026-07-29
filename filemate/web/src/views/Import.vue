<template>
  <div class="import-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <h3>📤 导入文件</h3>
        </div>
      </template>

      <!-- 上传区域 -->
      <el-upload
        ref="uploadRef"
        class="upload-area"
        drag
        :auto-upload="false"
        :limit="10"
        :on-change="handleFileChange"
        :on-exceed="handleExceed"
        accept=".docx,.doc,.pdf,.pptx,.ppt"
        multiple
      >
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="upload-text">
          将文件拖到此处，或 <em>点击上传</em>
        </div>
        <template #tip>
          <div class="upload-tip">
            支持 .docx, .pdf, .pptx 格式，单次最多 10 个文件
          </div>
        </template>
      </el-upload>

      <!-- 文件列表 -->
      <div class="file-list" v-if="fileList.length > 0">
        <h4>待处理文件 ({{ fileList.length }})</h4>
        <el-table :data="fileList" stripe>
          <el-table-column prop="name" label="文件名" />
          <el-table-column prop="size" label="大小" width="120">
            <template #default="{ row }">
              {{ formatSize(row.size) }}
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="getStatusType(row.status)">
                {{ getStatusText(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'ready'"
                type="primary"
                size="small"
                @click="processFile(row)"
                :loading="row.loading"
              >
                处理
              </el-button>
              <el-button
                v-if="row.status === 'success'"
                size="small"
                @click="viewResult(row)"
              >
                查看结果
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 开始处理按钮 -->
      <div class="actions" v-if="fileList.length > 0">
        <el-button type="primary" size="large" @click="processAllFiles" :loading="processing">
          <el-icon><Download /></el-icon>
          全部处理
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { UploadFilled, Download } from '@element-plus/icons-vue'
import type { UploadFile } from 'element-plus'
import { uploadFile } from '../services/api'
import { useFileStore } from '../stores/fileStore'

interface FileItem {
  uid: number
  name: string
  size: number
  file: File
  status: 'ready' | 'processing' | 'success' | 'error'
  loading?: boolean
  sessionId?: string
}

const router = useRouter()
const fileStore = useFileStore()
const fileList = ref<FileItem[]>([])
const processing = ref(false)

function handleFileChange(_file: UploadFile, uploadFiles: UploadFile[]) {
  fileList.value = uploadFiles.map((f: any) => ({
    uid: f.uid,
    name: f.name || 'unknown',
    size: f.size || 0,
    file: f.raw as File,
    status: 'ready'
  }))
}

function handleExceed() {
  ElMessage.warning('最多上传 10 个文件')
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function getStatusType(status: string) {
  const map: Record<string, 'info' | 'warning' | 'success' | 'danger'> = {
    ready: 'info',
    processing: 'warning',
    success: 'success',
    error: 'danger'
  }
  return map[status] || 'info'
}

function getStatusText(status: string) {
  const map: Record<string, string> = {
    ready: '待处理',
    processing: '处理中',
    success: '已完成',
    error: '失败'
  }
  return map[status] || status
}

async function processFile(row: FileItem) {
  row.status = 'processing'
  row.loading = true

  try {
    const session = await uploadFile(row.file)
    row.status = 'success'
    row.sessionId = session.session_id
    fileStore.addFile(session)
    ElMessage.success(`文件 "${row.name}" 处理完成`)
  } catch (e: any) {
    row.status = 'error'
    ElMessage.error(`处理失败: ${e.message}`)
  } finally {
    row.loading = false
  }
}

async function processAllFiles() {
  processing.value = true

  for (const row of fileList.value) {
    if (row.status === 'ready') {
      await processFile(row)
    }
  }

  processing.value = false
  ElMessage.success('所有文件处理完成')
}

function viewResult(row: FileItem) {
  if (row.sessionId) {
    router.push(`/classification?session=${row.sessionId}`)
  }
}
</script>

<style scoped>
.import-page {
  max-width: 1000px;
  margin: 0 auto;
}

.card-header h3 {
  margin: 0;
}

.upload-area {
  margin: 20px 0;
}

.upload-icon {
  font-size: 48px;
  color: #409eff;
}

.upload-text {
  font-size: 16px;
}

.upload-text em {
  color: #409eff;
  font-style: normal;
}

.upload-tip {
  font-size: 12px;
  color: #888;
  margin-top: 8px;
}

.file-list {
  margin-top: 20px;
}

.file-list h4 {
  margin: 0 0 12px 0;
}

.actions {
  margin-top: 20px;
  text-align: center;
}
</style>