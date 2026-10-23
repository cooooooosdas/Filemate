<template>
  <section class="cw-source-panel" aria-label="原文引用定位">
    <p v-if="loading" role="status">正在核对当前来源与引文…</p>
    <template v-else-if="citation">
      <p class="cw-kicker">原文定位 · 已核对当前版本</p><h2>{{ citation.original_name }}</h2>
      <p v-if="citation.page">第 {{ citation.page }} 页</p>
      <p class="cw-original"><span>{{ citation.before }}</span><mark>{{ citation.quote }}</mark><span>{{ citation.after }}</span></p>
      <router-link class="cw-source-link" :to="{ path: '/ai-tools', query: { source: citation.source_id } }">打开资料问答<IconArrowUpRight :size="20" aria-hidden="true" /></router-link>
    </template>
    <div v-else role="alert"><h2>这段原文暂时不可用</h2><p>{{ error || '来源可能已变化、移出或撤销，请刷新后核对。' }}</p><button @click="$emit('retry')">重新核验</button></div>
    <button @click="$emit('closed')">返回知识点</button>
  </section>
</template>
<script setup lang="ts">
import { IconArrowUpRight } from '@tabler/icons-vue'
import type { WorkspaceCitation } from '../../types/courseWorkspace'
defineProps<{ citation: WorkspaceCitation | null; loading: boolean; error: string }>()
defineEmits<{ retry: []; closed: [] }>()
</script>
