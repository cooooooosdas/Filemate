<template>
  <div class="naming-page">
    <WorkflowSteps :current="3" />
    <DataState v-if="loading" loading />
    <DataState v-else-if="loadError" :error="loadError" @retry="loadRequestedSession" />
    <DataState v-else-if="!currentFile" empty>
      <el-icon class="empty-icon"><Edit /></el-icon>
      <strong>还没有待确认的命名</strong>
      <span>从导入资料开始，核对分类后会进入命名确认。</span>
      <el-button type="primary" @click="router.push('/import')">去导入资料</el-button>
    </DataState>

    <template v-else>
      <el-card>
        <template #header>
          <h3><el-icon><Edit /></el-icon> 命名预览</h3>
        </template>

        <el-row :gutter="20">
          <el-col :span="12" :xs="24">
            <el-card shadow="hover">
              <template #header>原始文件名</template>
              <div class="filename">{{ currentFile.source_path.split(/[/\\]/).pop() }}</div>
            </el-card>
          </el-col>

          <el-col :span="12" :xs="24">
            <el-card shadow="hover">
              <template #header>建议文件名</template>
              <div class="filename suggested">{{ currentFile.suggested_name }}</div>
            </el-card>
          </el-col>
        </el-row>

        <el-card style="margin-top: 20px">
          <template #header>修改文件名</template>
          <label class="field-label" for="suggested-name">最终文件名</label>
          <el-input id="suggested-name" v-model="editedName" placeholder="输入新文件名" />
          <div class="form-actions">
            <el-button @click="goBackToClassification">返回分类</el-button>
            <el-button
              type="primary"
              :disabled="!editedName.trim() || completed"
              @click="confirmName"
              :loading="confirming"
            >
              {{ completed ? '已完成归档' : '确认命名并归档' }}
            </el-button>
          </div>
        </el-card>

        <el-alert
          v-if="completed"
          class="completion-alert"
          title="资料已完成可信归档"
          type="success"
          :closable="false"
          show-icon
        >
          <p>{{ destination || '归档记录已保存，可在处理记录中查看。' }}</p>
          <div class="completion-actions">
            <el-button v-if="currentFile.milestones.length" @click="goToSchedule">查看学习日程</el-button>
            <el-button type="primary" @click="router.push('/history')">查看处理记录</el-button>
          </div>
        </el-alert>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Edit } from '@element-plus/icons-vue'
import { confirmSession, getSession } from '../services/api'
import { useFileStore } from '../stores/fileStore'
import DataState from '../components/DataState.vue'
import WorkflowSteps from '../components/WorkflowSteps.vue'

const route = useRoute()
const router = useRouter()
const fileStore = useFileStore()
const currentFile = computed(() => fileStore.currentFile)
const editedName = ref('')
const confirming = ref(false)
const loading = ref(false)
const loadError = ref('')
const completed = ref(false)
const destination = ref('')

watch(currentFile, (file) => {
  if (file) {
    editedName.value = file.suggested_name
    completed.value = file.status === 'confirmed'
    destination.value = file.execution?.dest_path || ''
  }
}, { immediate: true })

onMounted(loadRequestedSession)

async function loadRequestedSession() {
  const sessionId = route.query.session as string | undefined
  if (!sessionId) {
    fileStore.setCurrentFile(null)
    return
  }
  loading.value = true
  loadError.value = ''
  fileStore.setCurrentFile(null)
  try {
    const session = await getSession(sessionId)
    fileStore.setCurrentFile(session)
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '命名结果加载失败'
  } finally {
    loading.value = false
  }
}

function goBackToClassification() {
  if (!currentFile.value) return
  router.push({ path: '/classification', query: { session: currentFile.value.session_id } })
}

function goToSchedule() {
  if (!currentFile.value) return
  router.push({ path: '/schedule', query: { session: currentFile.value.session_id } })
}

async function confirmName() {
  if (!currentFile.value || !editedName.value) return

  confirming.value = true
  try {
    const result = await confirmSession(currentFile.value.session_id, {
      accepted: true,
      edits: { suggested_name: editedName.value }
    })

    if (result.ok) {
      const refreshed = await getSession(currentFile.value.session_id)
      fileStore.setCurrentFile(refreshed)
      const destinationPath = result.execution?.dest_path
      completed.value = true
      destination.value = destinationPath || ''
      ElMessage.success(
        destinationPath ? `已归档到 ${destinationPath}` : '命名已确认并完成归档'
      )
    } else {
      ElMessage.error(result.error || '确认失败')
    }
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    confirming.value = false
  }
}
</script>

<style scoped>
.naming-page {
  max-width: 1000px;
  margin: 0 auto;
}

.filename {
  font-size: 16px;
  font-family: var(--font-mono);
  padding: 12px;
  overflow-wrap: anywhere;
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
}

.filename.suggested {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: bold;
}

.field-label {
  display: block;
  margin-bottom: 8px;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 700;
}

.form-actions,
.completion-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 14px;
}

.completion-alert {
  margin-top: 20px;
}

.completion-alert p {
  margin: 8px 0 0;
  overflow-wrap: anywhere;
}

.empty-icon {
  color: var(--accent);
  font-size: 34px;
}

@media (max-width: 560px) {
  .form-actions,
  .completion-actions {
    align-items: stretch;
    flex-direction: column-reverse;
  }

  .form-actions .el-button,
  .completion-actions .el-button {
    width: 100%;
    margin: 0;
  }
}
</style>
