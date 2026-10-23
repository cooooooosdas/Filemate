<template>
  <section class="cw-outline" aria-label="知识点大纲">
    <p class="cw-caption">按资料所属章节整理 · {{ page?.total ?? 0 }} 个知识点，融合成员只计一次</p>
    <p v-if="page?.chapter_groups_truncated" class="cw-status">本页章节信息较多，部分路径未加载。点击章节标题可核对完整归属。</p>
    <div v-if="page?.items.length"><section v-for="section in sections" :key="section.id" class="cw-outline-chapter"><h3><button :aria-label="`查看章节：${section.title}`" @click="$emit('openChapter', section.id)">{{ section.title }}</button></h3><p v-if="section.incomplete" class="cw-caption">点击章节标题读取完整路径</p><ol class="cw-node-list">
      <li v-for="node in section.nodes" :key="node.id"><button :aria-pressed="selectedId === node.id" @click="$emit('select', node.id)">
        <span><strong>{{ node.label }}</strong><small>{{ node.source_count ? `${node.source_count} 份有效来源` : '无有效来源' }}<span v-if="node.chapter_ids.length > 1"> · 多章节归属（{{ node.chapter_ids.length }}）</span></small></span><IconChevronRight :size="21" aria-hidden="true" />
      </button></li>
    </ol></section></div>
    <div v-else class="cw-empty"><IconBook2 :size="42" aria-hidden="true" /><h3>这里还没有知识点</h3><p>可清除范围条件，或在“整理课程”中核对资料。</p></div>
    <nav v-if="page && page.total > page.limit" class="cw-pagination" aria-label="知识点分页">
      <button :disabled="loading || page.offset === 0" @click="$emit('page', Math.max(0, page.offset-page.limit))">上一页</button>
      <span>{{ Math.floor(page.offset/page.limit)+1 }} / {{ Math.ceil(page.total/page.limit) }}</span>
      <button :disabled="loading || page.offset+page.limit >= page.total" @click="$emit('page', page.offset+page.limit)">下一页</button>
    </nav>
  </section>
</template>
<script setup lang="ts">
import { IconBook2, IconChevronRight } from '@tabler/icons-vue'
import { computed } from 'vue'
import type { WorkspaceConceptPage } from '../../types/courseWorkspace'
import { groupWorkspaceOutline } from '../../course-graph/workspace-hierarchy'
const props = defineProps<{ page: WorkspaceConceptPage | null; selectedId: string; loading: boolean }>()
const sections = computed(() => groupWorkspaceOutline(props.page))
defineEmits<{ select: [id: string]; page: [offset: number]; openChapter: [id: string] }>()
</script>
