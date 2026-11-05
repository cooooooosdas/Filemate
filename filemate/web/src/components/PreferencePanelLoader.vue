<template>
  <component :is="panel" v-if="panel" v-bind="$attrs" />
  <section v-else-if="failed" role="alert"><p>设置面板暂时无法加载。</p><button type="button" @click="load">重新加载面板</button></section>
  <p v-else role="status">正在加载设置…</p>
</template>
<script setup lang="ts">
import { onMounted, onUnmounted, ref, shallowRef, type Component } from 'vue'
defineOptions({ inheritAttrs: false })
const props = defineProps<{ kind: 'appearance' | 'downloads' | 'preferences' }>()
const panel = shallowRef<Component>(), failed = ref(false)
let disposed = false, loading = false
async function load() {
  if (loading) return
  loading = true; failed.value = false
  try { const result = props.kind === 'preferences' ? await import('./PreferenceContent.vue') : props.kind === 'appearance' ? await import('./AppearanceSettings.vue') : await import('./DownloadSettings.vue'); if (!disposed) panel.value = result.default }
  catch { if (!disposed) failed.value = true }
  finally { loading = false }
}
onMounted(load)
onUnmounted(() => { disposed = true })
</script>
