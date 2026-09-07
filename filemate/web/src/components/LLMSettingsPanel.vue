<template>
  <section class="model-settings" aria-labelledby="model-settings-title">
    <header class="model-settings-head">
      <div>
        <span class="eyebrow">自带密钥</span>
        <h3 id="model-settings-title">DeepSeek 模型服务</h3>
        <p>填写你自己的 API 密钥，FileMate 的生成、问答与面试能力即可使用。</p>
      </div>
      <span class="model-status" :class="statusClass">
        <i aria-hidden="true" />{{ statusLabel }}
      </span>
    </header>

    <dl class="model-meta">
      <div><dt>服务商</dt><dd>{{ status?.provider || 'DeepSeek' }}</dd></div>
      <div><dt>模型</dt><dd>{{ status?.model || 'deepseek-v4-flash' }}</dd></div>
      <div><dt>保存位置</dt><dd>{{ storageLabel }}</dd></div>
    </dl>

    <label class="credential-field">
      <span>DeepSeek API 密钥</span>
      <el-input
        v-model="apiKey"
        type="password"
        show-password
        clearable
        autocomplete="new-password"
        placeholder="粘贴你的 API 密钥"
        :disabled="!backendConnected || saving || !canSave"
        @keyup.enter="saveCredential"
      />
    </label>

    <p class="privacy-note">
      密钥不会写入浏览器、数据库或日志，只保存在当前 Windows 用户的系统凭据库；仅在你主动使用在线模型功能时发送给 DeepSeek 官方接口。
    </p>

    <div class="model-actions">
      <el-button
        type="primary"
        :loading="saving"
        :disabled="!backendConnected || !canSave || !apiKey.trim()"
        @click="saveCredential"
      >
        保存本机密钥
      </el-button>
      <el-button
        :disabled="!backendConnected || saving || status?.source !== 'secure_store'"
        @click="removeCredential"
      >
        移除本机密钥
      </el-button>
      <el-button text :loading="loading" :disabled="!backendConnected" @click="loadStatus">
        刷新状态
      </el-button>
    </div>

    <p v-if="!backendConnected" class="model-message warning" role="status">请先连接本地服务，再配置模型密钥。</p>
    <p v-else-if="errorMessage" class="model-message error" role="alert">{{ errorMessage }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getLLMSettings,
  removeLLMApiKey,
  saveLLMApiKey,
  type LLMSettingsStatus
} from '../services/api'

const props = defineProps<{ backendConnected: boolean | null }>()

const status = ref<LLMSettingsStatus | null>(null)
const apiKey = ref('')
const loading = ref(false)
const saving = ref(false)
const errorMessage = ref('')

const canSave = computed(() => status.value?.secure_storage_available !== false)
const statusClass = computed(() => status.value?.configured ? 'ready' : 'pending')
const statusLabel = computed(() => {
  if (loading.value) return '正在读取'
  return status.value?.configured ? '已配置' : '待配置'
})
const storageLabel = computed(() => {
  if (status.value?.source === 'secure_store') return 'Windows 安全凭据库'
  if (status.value?.source === 'environment') return '部署环境变量'
  if (status.value && !status.value.secure_storage_available) return '当前系统不可用'
  return '尚未保存'
})

async function loadStatus(): Promise<void> {
  if (!props.backendConnected) return
  loading.value = true
  errorMessage.value = ''
  try {
    status.value = await getLLMSettings()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '模型设置读取失败'
  } finally {
    loading.value = false
  }
}

async function saveCredential(): Promise<void> {
  const value = apiKey.value.trim()
  if (!value || saving.value || !canSave.value) return
  saving.value = true
  errorMessage.value = ''
  try {
    status.value = await saveLLMApiKey(value)
    apiKey.value = ''
    ElMessage.success('DeepSeek 密钥已安全保存并立即生效')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '模型密钥保存失败'
  } finally {
    saving.value = false
  }
}

async function removeCredential(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '移除后，需要在线模型的功能将暂停，其他本地功能不受影响。',
      '移除本机密钥',
      { confirmButtonText: '确认移除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  saving.value = true
  errorMessage.value = ''
  try {
    status.value = await removeLLMApiKey()
    apiKey.value = ''
    ElMessage.success('本机密钥已移除')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '模型密钥移除失败'
  } finally {
    saving.value = false
  }
}

watch(
  () => props.backendConnected,
  connected => { if (connected) void loadStatus() },
  { immediate: true }
)
</script>

<style scoped>
.model-settings {
  margin-top: 18px;
  padding: 18px;
  background: #f3f8f4;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-panel);
}

.model-settings-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.eyebrow {
  color: var(--accent);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

h3 {
  margin: 5px 0 4px;
  font-size: 17px;
}

.model-settings-head p,
.privacy-note {
  margin: 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.65;
}

.model-status {
  min-height: 30px;
  padding: 0 10px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  flex: 0 0 auto;
  color: var(--warning);
  background: #fff8eb;
  border: 1px solid #ead5ad;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 700;
}

.model-status i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

.model-status.ready {
  color: var(--accent);
  background: var(--accent-soft);
  border-color: var(--accent-border);
}

.model-meta {
  margin: 16px 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  border-block: 1px solid var(--border-subtle);
}

.model-meta > div {
  min-width: 0;
  padding: 12px 10px;
}

.model-meta > div + div {
  border-left: 1px solid var(--border-subtle);
}

.model-meta dt {
  color: var(--text-muted);
  font-size: 11px;
}

.model-meta dd {
  margin: 4px 0 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.credential-field {
  display: grid;
  gap: 8px;
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 650;
}

.privacy-note {
  margin-top: 10px;
}

.model-actions {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.model-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.model-message {
  margin: 12px 0 0;
  font-size: 12px;
}

.model-message.warning { color: var(--warning); }
.model-message.error { color: var(--danger); }

@media (max-width: 560px) {
  .model-settings { padding: 14px; }
  .model-settings-head { display: grid; }
  .model-status { justify-self: start; }
  .model-meta { grid-template-columns: 1fr; }
  .model-meta > div + div { border-left: 0; border-top: 1px solid var(--border-subtle); }
}
</style>
