<template>
  <component :is="panel" v-if="panel" :backend-connected="backendConnected" :active="active" />
  <section v-else-if="failed" class="settings-load-state" role="alert">
    <strong>模型设置暂时无法打开</strong>
    <p>网络恢复后，请重新加载页面再打开设置。未保存的输入将清除，已保存的密钥仍在当前存储空间。</p>
    <el-button @click="reopen">重新加载页面</el-button>
  </section>
  <p v-else class="settings-load-state" role="status">正在加载模型设置…</p>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, shallowRef, type Component } from 'vue'

defineProps<{ backendConnected: boolean | null; active: boolean }>()
const panel = shallowRef<Component>()
const failed = ref(false)
let disposed = false
let loading = false
function reopen(): void {
  if (window.dispatchEvent(new Event('filemate:before-refresh', { cancelable: true }))) window.location.reload()
}
async function load(): Promise<void> {
  if (loading) return
  loading = true
  failed.value = false
  try {
    const module = await import('./LLMSettingsPanel.vue')
    if (!disposed) panel.value = module.default
  } catch {
    if (!disposed) failed.value = true
  } finally { loading = false }
}
onMounted(() => { void load() })
onUnmounted(() => { disposed = true })
</script>

<style scoped>
.settings-load-state { padding:24px 4px; color:var(--text-secondary); font-size:16px; line-height:1.7; }
.settings-load-state strong { color:var(--text-primary); font-size:18px; }
.settings-load-state p { margin:10px 0 18px; }
</style>
