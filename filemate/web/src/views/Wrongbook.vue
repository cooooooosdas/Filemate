<template>
  <main v-if="normalized.blocked || normalizeError" class="route-location">
    <h1>无法定位这道题</h1><p role="alert">{{ normalizeError || normalized.notice }}</p>
    <RouterLink to="/wrongbook">返回错题目录</RouterLink><RouterLink to="/today">返回今日行动</RouterLink>
  </main>
  <p v-else-if="normalizing" role="status" class="route-location">正在定位原错题…</p>
  <template v-else>
    <aside v-if="reference.present" class="route-location">
      <RouterLink to="/today">返回今日行动</RouterLink>
      <p v-if="!v2">当前为旧版错题目录，精准定位需启用新版复盘。原链接参数已保留，请在目录中选择原题。</p>
    </aside>
    <component :is="Workspace" />
  </template>
</template>
<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { normalizeWrongbookQuery, readRouteReference } from '../today/navigation'
const route = useRoute(), router = useRouter(), v2 = import.meta.env.VITE_ENABLE_WRONGBOOK_V2 === 'true'
const Workspace = defineAsyncComponent(v2
  ? () => import('../components/wrongbook/ReviewWorkspace.vue')
  : () => import('../components/wrongbook/LegacyWrongbook.vue'))
const normalized = computed(() => normalizeWrongbookQuery(route.query, v2))
const reference = computed(() => readRouteReference(route.query, v2 ? 'focus' : 'wrong_id'))
const normalizing = ref(false), normalizeError = ref('')
let epoch = 0
watch(normalized, async value => {
  const ticket = ++epoch
  normalizeError.value = ''; normalizing.value = value.changed && !value.blocked
  if (!normalizing.value) return
  try { await router.replace({ path: '/wrongbook', query: value.query }) }
  catch { if (ticket === epoch) { normalizing.value = false; normalizeError.value = '无法更新错题链接，请返回目录重新选择。' } }
}, { immediate: true })
onBeforeUnmount(() => { epoch++ })
</script>
<style scoped>
.route-location { padding:16px; font-size:17px; line-height:1.7; overflow-wrap:anywhere; }
.route-location a { display:inline-flex; align-items:center; min-height:44px; margin-right:20px; color:var(--accent); }
</style>
