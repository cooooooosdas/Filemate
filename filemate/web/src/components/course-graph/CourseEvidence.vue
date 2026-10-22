<template>
  <section class="cw-evidence" aria-label="知识点详情与来源">
    <template v-if="detail">
      <p class="cw-kicker">知识点 · 来源核对</p><h2>{{ detail.node.label }}</h2>
      <p v-if="detail.node.aliases.length" class="cw-caption">亦见：{{ detail.node.aliases.map(a => a.label).join('、') }}</p>
      <p>{{ detail.node.source_count ? `${detail.node.source_count} 份当前有效资料` : '无有效来源，原学习历史保留' }}</p>
      <h3>资料证据</h3>
      <article v-for="ref in detail.source_refs" :key="ref.evidence_id" class="cw-quote">
        <p class="cw-source-name"><IconFileText :size="20" aria-hidden="true" />{{ ref.original_name }}<span v-if="ref.page"> · 第{{ ref.page }}页</span></p>
        <blockquote>{{ ref.excerpt }}</blockquote>
        <button v-if="canOpen" :id="`${anchor}-${ref.evidence_id}`" @click="$emit('openCitation', ref.evidence_id, `${anchor}-${ref.evidence_id}`)">定位原文<IconArrowUpRight :size="19" aria-hidden="true" /></button>
      </article>
      <p v-if="!detail.source_refs.length" class="cw-caption">当前没有可核对的引用。可在整理课程中更新资料。</p>
      <nav v-if="detail.total_refs > detail.limit" class="cw-pagination" aria-label="原文引用分页"><button :disabled="detail.offset === 0" @click="$emit('page', Math.max(0, detail.offset-detail.limit))">前一页</button><span>{{ detail.offset+1 }}–{{ Math.min(detail.total_refs, detail.offset+detail.limit) }} / {{ detail.total_refs }}</span><button :disabled="detail.offset+detail.limit >= detail.total_refs" @click="$emit('page', detail.offset+detail.limit)">后一页</button></nav>
      <div class="cw-learning-empty"><h3>个人学习记录</h3><p>尚未建立学习记录关联。</p><p class="cw-caption">资料引用说明知识来自哪里；练习与复习记录需另行明确关联。</p></div>
    </template>
    <div v-else class="cw-empty"><IconBookmark :size="38" aria-hidden="true" /><h3>先选一个知识点</h3><p>在图谱或大纲中点选，核对它的来源与原句。</p></div>
  </section>
</template>
<script setup lang="ts">
import { useId } from 'vue'
import { IconArrowUpRight, IconBookmark, IconFileText } from '@tabler/icons-vue'
import type { WorkspaceDetail } from '../../types/courseWorkspace'
const anchor = `citation-${useId()}`
withDefaults(defineProps<{ detail: WorkspaceDetail | null; canOpen?: boolean }>(), { canOpen: false })
defineEmits<{ openCitation: [id: string, trigger: string]; openManager: []; page: [offset: number] }>()
</script>
