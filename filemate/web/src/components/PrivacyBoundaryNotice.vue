<template>
  <section class="privacy-boundary" aria-label="资料保存与外发说明">
    <template v-if="boundary">
      <strong>{{ boundary.storage_location === 'server' ? '网站资料保存在服务器' : '资料保存在服务运行设备' }}</strong>
      <p>{{ boundary.storage_notice }}。</p><p>{{ boundary.model_notice }}</p><p>{{ boundary.retention_notice }}</p>
      <details><summary>查看密钥、摄像头与语音边界</summary><p>{{ boundary.key_notice }}</p><p>{{ boundary.camera_notice }}</p><p>{{ boundary.speech_notice }}</p><p>可在可信与隐私页导出、删除或恢复资料。自己下载的备份与第三方留存需另行处理。</p></details>
    </template>
    <p v-else role="status">{{ error || '正在确认当前服务的数据保存位置…' }}</p><button v-if="error" type="button" @click="load">重试读取说明</button>
  </section>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getPrivacyBoundary, type PrivacyBoundary } from '../services/api'
const emit = defineEmits<{ ready: [boolean] }>()
const boundary = ref<PrivacyBoundary | null>(null), error = ref('')
async function load() { error.value = ''; emit('ready', false); try { boundary.value = await getPrivacyBoundary(); emit('ready', true) } catch { boundary.value = null; error.value = '未能确认数据保存位置，请先连接服务并重试。' } }
onMounted(load)
</script>
<style scoped>.privacy-boundary{padding:20px;margin:0 0 22px;border:1px solid var(--accent-border);border-radius:14px;background:var(--accent-soft);font-size:16px;line-height:1.7;overflow-wrap:anywhere}.privacy-boundary strong{font-size:20px}.privacy-boundary p{margin:8px 0 0}.privacy-boundary summary{cursor:pointer;min-height:44px;display:flex;align-items:center;color:var(--accent)}.privacy-boundary button{min-height:44px;font-size:16px}</style>
