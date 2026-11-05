<template>
  <section class="privacy-boundary" aria-label="资料保存与外发说明">
    <template v-if="boundary">
      <strong>{{ boundary.storage_location === 'server' ? '网站资料保存在服务器' : '资料保存在服务运行设备' }}</strong>
      <details><summary>查看完整说明</summary><div class="privacy-details"><p v-for="(fact, index) in facts" :key="index">{{ fact }}</p><p>单份资料最多 25 MB。</p><p>在可信与隐私页导出、删除或恢复资料。</p><p>下载的备份与第三方留存需另行处理。</p></div></details>
    </template>
    <p v-else role="status">{{ error || '正在确认当前服务的数据保存位置…' }}</p><button v-if="error" type="button" @click="load">重试读取说明</button>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getPrivacyBoundary, type PrivacyBoundary } from '../services/api'
const emit = defineEmits<{ ready: [boolean] }>()
const boundary = ref<PrivacyBoundary | null>(null), error = ref('')
const facts = computed(() => boundary.value ? [boundary.value.storage_notice, boundary.value.model_notice, boundary.value.retention_notice, boundary.value.key_notice, boundary.value.camera_notice, boundary.value.speech_notice].flatMap(text => text.split(/(?<=[。；;，：])/u).filter(Boolean)) : [])
async function load() { error.value = ''; emit('ready', false); try { boundary.value = await getPrivacyBoundary(); emit('ready', true) } catch { boundary.value = null; error.value = '未能确认数据保存位置，请先连接服务并重试。' } }
onMounted(load)
</script>
<style scoped>
.privacy-boundary{display:flex;flex-wrap:wrap;align-items:center;gap:4px 18px;padding:12px 16px;margin:0 0 18px;border:1px solid var(--border-strong);border-radius:10px;background:var(--accent-soft);font-size:16px;line-height:1.7;overflow-wrap:anywhere}.privacy-boundary strong{font-size:16px}.privacy-boundary p{margin:8px 0 0}.privacy-boundary details{flex:1;min-width:140px}.privacy-boundary details[open]{flex-basis:100%}.privacy-boundary summary{cursor:pointer;min-height:44px;display:list-item;align-content:center;color:var(--accent);width:fit-content}.privacy-boundary button{min-height:44px;font-size:16px}.privacy-details{max-width:720px}
</style>
