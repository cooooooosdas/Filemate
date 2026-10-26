<template>
  <aside class="review-catalog" aria-label="错题目录">
    <div class="catalog-heading"><h2>题目目录</h2><span>{{ total }} 道</span></div>
    <p v-if="loading" role="status">正在读取目录…</p>
    <div v-else-if="error" role="alert"><p>{{ error }}</p><button @click="$emit('reload')">重试目录</button></div>
    <p v-else-if="!items.length">当前筛选没有题目。调整筛选，或从课程练习开始。</p>
    <ol v-else class="review-list"><li v-for="(item, i) in items" :key="item.wrong_id"><button :aria-current="selected === item.wrong_id ? 'true' : undefined" @click="$emit('select', item.wrong_id)"><span class="list-number">{{ offset + i + 1 }}</span><span class="list-copy"><strong>{{ item.stem || '题目待修复' }}</strong><span>{{ reviewStateLabel(item) }} · 错误 {{ item.error_count }} 次</span><span>{{ item.source_name || '未关联资料' }}</span></span></button></li></ol>
    <nav class="review-pages" aria-label="错题分页"><button :disabled="loading || offset === 0" @click="$emit('page', Math.max(0, offset - 30))">上一页</button><span>{{ total ? Math.floor(offset / 30) + 1 : 0 }} / {{ Math.ceil(total / 30) }}</span><button :disabled="loading || !hasMore" @click="$emit('page', offset + 30)">下一页</button></nav>
  </aside>
</template>
<script setup lang="ts">
import type { ReviewListItem } from '../../types/wrongbook'
import { reviewStateLabel } from '../../wrongbook/presentation'
defineProps<{ items: ReviewListItem[]; selected: string; total: number; offset: number; hasMore: boolean; loading: boolean; error: string }>()
defineEmits<{ select: [id: string]; page: [offset: number]; reload: [] }>()
</script>
