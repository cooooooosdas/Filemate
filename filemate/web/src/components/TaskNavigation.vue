<template>
  <nav ref="root" class="context-navigation" aria-label="当前任务的相关功能">
    <span v-show="indicator.width" class="task-indicator" aria-hidden="true" :style="{
      width: `${indicator.width}px`, height: `${indicator.height}px`,
      transform: `translate(${indicator.x}px, ${indicator.y}px)`
    }" />
    <router-link v-for="item in items" :key="item.path" :to="item.path" :class="{ 'task-current': item.path === activePath }">
      <component :is="item.icon" :size="20" :stroke-width="1.8" aria-hidden="true" />
      <span>{{ item.title }}</span>
    </router-link>
  </nav>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch, type Component } from 'vue'
import { useRoute } from 'vue-router'

const props = defineProps<{ items: { path: string; title: string; icon: Component }[] }>()
const route = useRoute()
const root = ref<HTMLElement>()
const indicator = ref({ x: 0, y: 0, width: 0, height: 0 })
const activePath = computed(() => route.path === '/naming' ? '/classification' : route.path)
let observer: ResizeObserver | undefined
let disposed = false
function measure(): void {
  const current = root.value?.querySelector<HTMLElement>('.task-current')
  indicator.value = current
    ? { x: current.offsetLeft, y: current.offsetTop, width: current.offsetWidth, height: current.offsetHeight }
    : { x: 0, y: 0, width: 0, height: 0 }
}
watch(() => [activePath.value, props.items], async () => { await nextTick(); if (!disposed) measure() })
onMounted(() => {
  observer = new ResizeObserver(measure)
  if (root.value) observer.observe(root.value)
  measure()
})
onUnmounted(() => { disposed = true; observer?.disconnect() })
</script>

<style scoped>
.context-navigation { position:relative; isolation:isolate; display:flex; flex-wrap:wrap; gap:6px; margin:0 auto 24px; max-width:1360px; width:100%; padding:6px; border:1px solid var(--border-subtle); border-radius:16px; background:var(--bg-surface); }
.task-indicator { position:absolute; left:0; top:0; z-index:-1; background:var(--accent); border-radius:10px; box-shadow:0 3px 10px #2454d726; transition:transform var(--motion-panel),width var(--motion-panel),height var(--motion-panel); }
a { display:inline-flex; align-items:center; justify-content:center; gap:9px; min-height:46px; padding:8px 16px; border-radius:10px; color:var(--text-secondary); font-size:16px; text-decoration:none; transition:color var(--motion-fast),background var(--motion-fast); }
a:hover:not(.task-current) { background:var(--accent-soft); color:var(--accent); }
a.task-current { color:var(--hero-ink); }
svg { flex-shrink:0; }
@media(max-width:560px) { a { padding-inline:12px; } }
@media(prefers-reduced-motion:reduce) { .task-indicator,a { transition:none; } }
</style>
