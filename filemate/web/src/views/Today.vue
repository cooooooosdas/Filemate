<template>
  <div class="today-shell">
  <component v-if="entry.view === 'legacy'" :is="Legacy" />
  <component v-else-if="entry.view === 'workspace' && client && capabilities" :is="Workspace" :client="client" :capabilities="capabilities" />
  <main v-else class="today-entry" aria-live="polite"><h1>今日行动</h1><p v-if="entry.view === 'loading'">正在核对服务与账号…</p><template v-else><p role="alert">{{ entry.message }}</p><button type="button" @click="load">重新连接</button><RouterLink to="/trust">打开连接与账号设置</RouterLink></template></main>
  </div>
</template>
<script setup lang="ts">
import { computed, defineAsyncComponent, defineComponent, h, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { loadOrchestratorClient } from '../services/api'
import type { OrchestratorCapabilities, OrchestratorClient } from '../types/orchestrator'
import { resolveTodayEntry } from '../today/entry-state'
const ModuleError = defineComponent({ inheritAttrs: false, setup: () => () => h('main', { class: 'today-entry' }, [h('h1', '今日行动'), h('p', { role: 'alert' }, '页面模块未能加载，请恢复连接后重新加载。原数据与已保存安排保留。'), h('button', { type: 'button', onClick: () => window.location.reload() }, '重新加载页面')]) })
const Legacy = defineAsyncComponent({ loader: () => import('./LegacyToday.vue'), errorComponent: ModuleError })
const Workspace = defineAsyncComponent({ loader: () => import('../components/today/TodayWorkspace.vue'), errorComponent: ModuleError })
const client = shallowRef<OrchestratorClient | null>(null), capabilities = shallowRef<OrchestratorCapabilities | null>(null), error = ref<unknown>(null)
const entry = computed(() => resolveTodayEntry(capabilities.value, error.value))
let generation = 0, disposed = false
async function load() { const ticket = ++generation; capabilities.value = null; error.value = null; try { const port = await loadOrchestratorClient(); const caps = await port.getOrchestratorCapabilities(); if (!disposed && ticket === generation) { client.value = port; capabilities.value = caps } } catch (cause) { if (!disposed && ticket === generation) error.value = cause } }
onMounted(load)
onBeforeUnmount(() => { disposed = true; generation++ })
</script>
<style scoped>.today-entry{padding:32px;font-size:18px;overflow-wrap:anywhere}.today-entry h1{font-size:36px}.today-entry a,.today-entry button{display:inline-flex;align-items:center;min-height:44px;margin:12px 16px 0 0}.today-entry a{color:var(--accent)}</style>
