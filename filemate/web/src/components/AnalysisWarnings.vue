<template>
  <aside v-if="warnings.length" class="analysis-warnings" role="status">
    <strong><IconInfoCircle :size="21" aria-hidden="true" />本次处理范围</strong>
    <p v-for="message in warnings" :key="message">{{ message }}</p>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { IconInfoCircle } from '@tabler/icons-vue'

const props = defineProps<{ messages?: unknown }>()
const warnings = computed(() => Array.isArray(props.messages)
  ? props.messages.filter((message): message is string => typeof message === 'string' && Boolean(message.trim()))
  : [])
</script>

<style scoped>
.analysis-warnings { padding: 16px 20px; margin: 16px 0; border: 1px solid var(--accent-border); border-radius: 12px; background: var(--bg-elevated); color: var(--text-primary); }
strong { display: flex; align-items: center; gap: 8px; font-size: 17px; line-height: 1.5; }
p { margin: 8px 0 0; font-size: 16px; line-height: 1.7; overflow-wrap: anywhere; }
</style>
