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

      <el-table :data="history" v-loading="loading" stripe>
        <el-table-column prop="session_id" label="ID" width="100" />
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
        <el-table-column prop="created_at" label="创建时间" width="180" />
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

const router = useRouter()
const fileStore = useFileStore()
const history = ref<HistoryItem[]>([])
const loading = ref(false)
const undoingId = ref('')

onMounted(() => {
  loadHistory()
})

async function loadHistory() {
  loading.value = true
  try {
    history.value = await getHistory(undefined, 50)
  } catch (e: any) {
    ElMessage.error(`加载失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}

function getFileName(path: string): string {
  return path.split(/[/\\]/).pop() || path
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

/* 表格样式统一为暗色主题 */
:deep(.el-table) {
  --el-table-bg-color: #16161e;
  --el-table-tr-bg-color: #16161e;
  --el-table-header-bg-color: #1a1a24;
  --el-table-row-hover-bg-color: rgba(16, 185, 129, 0.08);
  --el-table-border-color: rgba(255, 255, 255, 0.06);
  --el-table-text-color: #a1a1aa;
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
  background: #1a1a24 !important;
  border-bottom-color: rgba(255, 255, 255, 0.06);
}

:deep(.el-table__body tr:hover > td.el-table__cell) {
  background: rgba(16, 185, 129, 0.08) !important;
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
</style>
