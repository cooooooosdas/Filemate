<template>
  <div class="naming-page">
    <el-alert
      title="请先在导入页面上传文件"
      type="info"
      :closable="false"
      v-if="!currentFile"
    />

    <template v-else>
      <el-card>
        <template #header>
          <h3><el-icon><Edit /></el-icon> 命名预览</h3>
        </template>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-card shadow="hover">
              <template #header>原始文件名</template>
              <div class="filename">{{ currentFile.source_path.split(/[/\\]/).pop() }}</div>
            </el-card>
          </el-col>

          <el-col :span="12">
            <el-card shadow="hover">
              <template #header>建议文件名</template>
              <div class="filename suggested">{{ currentFile.suggested_name }}</div>
            </el-card>
          </el-col>
        </el-row>

        <el-card style="margin-top: 20px">
          <template #header>修改文件名</template>
          <el-input v-model="editedName" placeholder="输入新文件名" />
          <el-button type="primary" style="margin-top: 12px" @click="confirmName" :loading="confirming">
            确认命名
          </el-button>
        </el-card>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Edit } from '@element-plus/icons-vue'
import { confirmSession, getSession } from '../services/api'
import { useFileStore } from '../stores/fileStore'

const fileStore = useFileStore()
const currentFile = computed(() => fileStore.currentFile)
const editedName = ref('')
const confirming = ref(false)

watch(currentFile, (file) => {
  if (file) {
    editedName.value = file.suggested_name
  }
})

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
      const destination = result.execution?.dest_path
      ElMessage.success(
        destination ? `已归档到 ${destination}` : '命名已确认并完成归档'
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
  font-family: monospace;
  padding: 8px;
  background: #f5f7fa;
  border-radius: 4px;
}

.filename.suggested {
  background: #e6f7ff;
  color: #1890ff;
  font-weight: bold;
}
</style>
