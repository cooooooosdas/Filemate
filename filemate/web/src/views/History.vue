<template>
  <div class="history-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <h3><el-icon><Document /></el-icon> 历史记录</h3>
          <el-button @click="loadHistory" :loading="loading">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <DataState v-if="error" :error="error" @retry="loadHistory" />
      <DataState v-else-if="!loading && history.length === 0" empty>
        <el-icon class="history-empty-icon"><Document /></el-icon>
        <strong>还没有处理记录</strong>
        <span>导入并确认第一份资料后，执行与撤销记录会显示在这里。</span>
        <el-button type="primary" @click="router.push('/import?intent=archive')">导入第一份资料</el-button>
      </DataState>

      <div v-else class="history-table">
        <el-table :data="history" v-loading="loading" stripe>
          <el-table-column label="记录编号" width="120">
            <template #default="{ row }">
              <span class="table-id" :title="row.session_id">{{ shortId(row.session_id) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="文件" min-width="200">
            <template #default="{ row }">
              {{ getFileName(row.execution?.dest_path || row.source_path) }}
            </template>
          </el-table-column>
          <el-table-column prop="category" label="分类" width="100">
            <template #default="{ row }">
              <el-tag :type="getCategoryType(row.category)" size="small">
                {{ row.category || '待确认' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="suggested_name" label="建议名" min-width="200" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="getStatusType(row.status)" size="small">
                {{ getStatusText(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="170">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="210" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" size="small" @click="viewDetail(row)">
                查看
              </el-button>
              <el-button
                v-if="row.can_undo"
                type="warning"
                size="small"
                :loading="undoingId === row.session_id"
                @click="undoExecution(row)"
              >
                撤销
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 移动端卡片列表（<768px 显示） -->
      <div v-if="!error && (loading || history.length)" class="history-cards" v-loading="loading">
        <p v-if="!loading && history.length === 0" class="cards-empty">暂无处理记录</p>
        <article v-for="row in history" :key="row.session_id" class="history-card">
          <div class="card-top">
            <div class="card-file">
              <strong class="card-filename">{{ getFileName(row.execution?.dest_path || row.source_path) }}</strong>
              <span class="card-suggest">{{ row.suggested_name }}</span>
            </div>
            <div class="card-tags">
              <el-tag :type="getCategoryType(row.category)" size="small">
                {{ row.category || '待确认' }}
              </el-tag>
              <el-tag :type="getStatusType(row.status)" size="small">
                {{ getStatusText(row.status) }}
              </el-tag>
            </div>
          </div>
          <div class="card-meta">
            <span class="card-id" :title="row.session_id">编号 {{ shortId(row.session_id) }}</span>
            <span class="card-date">{{ formatDate(row.created_at) }}</span>
          </div>
          <div class="card-actions">
            <el-button type="primary" size="small" @click="viewDetail(row)">查看</el-button>
            <el-button
              v-if="row.can_undo"
              type="warning"
              size="small"
              :loading="undoingId === row.session_id"
              @click="undoExecution(row)"
            >
              撤销
            </el-button>
          </div>
        </article>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, Document } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getHistory, getSession, undoSession } from '../services/api'
import { useFileStore } from '../stores/fileStore'
import type { HistoryItem } from '../types'
import DataState from '../components/DataState.vue'

const router = useRouter()
const fileStore = useFileStore()
const history = ref<HistoryItem[]>([])
const loading = ref(false)
const undoingId = ref('')
const error = ref('')

onMounted(() => {
  loadHistory()
})

async function loadHistory() {
  loading.value = true
  error.value = ''
  try {
    history.value = await getHistory(undefined, 50)
  } catch (e: any) {
    error.value = e?.message || '处理记录加载失败'
    ElMessage.error(`加载失败: ${error.value}`)
  } finally {
    loading.value = false
  }
}

function getFileName(path: string): string {
  return path.split(/[/\\]/).pop() || path
}

function shortId(id: string): string {
  return id.length > 10 ? `${id.slice(0, 8)}…` : id
}

function formatDate(value: string): string {
  if (!value) return '时间未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value.replace('T', ' ').slice(0, 16)
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  }).format(date)
}

function getCategoryType(category: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, '' | 'success' | 'warning' | 'danger' | 'info'> = {
    课件: 'info',
    作业: 'warning',
    竞赛通知: 'success',
    考试通知: 'danger',
    参考资料: 'info',
    大创通知: 'warning',
    待确认: ''
  }
  return map[category] || ''
}

function getStatusType(status: string): 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
    pending: 'info',
    processing: 'warning',
    done: 'success',
    confirmed: 'success',
    skipped: 'info',
    expired: 'warning',
    failed: 'danger'
  }
  return map[status] || 'info'
}

function getStatusText(status: string): string {
  const map: Record<string, string> = {
    pending: '待处理',
    processing: '处理中',
    done: '已完成',
    confirmed: '已确认',
    skipped: '已跳过',
    expired: '已过期',
    failed: '失败'
  }
  return map[status] || status
}

async function viewDetail(row: HistoryItem) {
  try {
    const session = await getSession(row.session_id)
    fileStore.setCurrentFile(session)
    router.push(`/classification?session=${row.session_id}`)
  } catch (e: any) {
    ElMessage.error(`加载详情失败: ${e.message}`)
  }
}

async function undoExecution(row: HistoryItem) {
  try {
    await ElMessageBox.confirm(
      `将文件恢复到原位置：${row.source_path}`,
      '确认撤销归档',
      {
        confirmButtonText: '撤销归档',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    undoingId.value = row.session_id
    await undoSession(row.session_id)
    ElMessage.success('已恢复原文件并撤销日历写入')
    await loadHistory()
  } catch (e: any) {
    if (e !== 'cancel' && e !== 'close') {
      ElMessage.error(`撤销失败: ${e.message || e}`)
    }
  } finally {
    undoingId.value = ''
  }
}
</script>

<style scoped>
.history-page {
  max-width: 1200px;
  margin: 0 auto;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header h3 {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.table-id {
  font-family: var(--font-mono);
  color: var(--text-muted);
}

:deep(.el-table) {
  --el-table-bg-color: var(--bg-surface);
  --el-table-tr-bg-color: var(--bg-surface);
  --el-table-header-bg-color: var(--bg-elevated);
  --el-table-row-hover-bg-color: var(--bg-hover);
  --el-table-border-color: var(--border-subtle);
  --el-table-text-color: var(--text-secondary);
  --el-table-header-text-color: #71717a;
}

:deep(.el-table__row--striped) {
  background: rgba(255, 255, 255, 0.02) !important;
}

:deep(.el-table__row--striped td) {
  background: transparent !important;
}

:deep(.el-table td.el-table__cell) {
  background: transparent;
  border-bottom-color: rgba(255, 255, 255, 0.04);
}

:deep(.el-table th.el-table__cell) {
  background: var(--bg-elevated) !important;
  border-bottom-color: var(--border-subtle);
}

:deep(.el-table__body tr:hover > td.el-table__cell) {
  background: var(--bg-hover) !important;
}

.history-empty-icon {
  color: var(--accent);
  font-size: 34px;
}

/* 分页样式 */
:deep(.el-pagination) {
  --el-pagination-bg-color: transparent;
  --el-pagination-text-color: var(--text-muted);
  --el-pagination-button-bg-color: var(--bg-elevated);
  --el-pagination-hover-color: var(--accent);
}
</style>

<style scoped>
:deep(.el-table) {
  --el-table-bg-color: var(--bg-surface);
  --el-table-tr-bg-color: var(--bg-surface);
  --el-table-header-bg-color: var(--bg-elevated);
  --el-table-border-color: var(--border-subtle);
  --el-table-text-color: var(--text-secondary);
  --el-table-header-text-color: var(--text-muted);
}

:deep(.el-table__body tr:hover > td.el-table__cell) {
  background: var(--accent-soft) !important;
}

:deep(.el-table th.el-table__cell) {
  background: var(--bg-elevated) !important;
  border-bottom-color: var(--border-subtle);
}

:deep(.el-table__row--striped) {
  background: var(--bg-base) !important;
}

/* 移动端卡片列表：桌面隐藏，<768px 显示 */
.history-cards {
  display: none;
}

.history-card {
  padding: 14px;
  margin-bottom: 10px;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-panel);
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.card-file {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.card-filename {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  word-break: break-all;
}

.card-suggest {
  font-size: 12px;
  color: var(--text-muted);
  word-break: break-all;
}

.card-tags {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.card-meta {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border-subtle);
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: var(--text-muted);
  font-size: 12px;
}

.card-id {
  font-family: var(--font-mono);
}

.card-date {
  white-space: nowrap;
}

.card-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}

.cards-empty {
  padding: 24px 0;
  text-align: center;
  color: var(--text-muted);
}

@media (max-width: 767px) {
  .history-table {
    display: none;
  }

  .history-cards {
    display: block;
  }

  .history-card .el-button {
    min-width: 88px;
  }

  .card-meta {
    align-items: flex-start;
    flex-direction: column;
    gap: 5px;
  }
}
</style>
