<template>
  <section class="review-session-planner" aria-labelledby="session-plan-title">
    <header class="review-header"><div><h2 id="session-plan-title">这次，留多少时间复习？</h2><p>按当前已应用的筛选挑选到期题，最多20题。</p></div><button @click="$emit('close')">收起预览</button></header>
    <form class="review-actions" @submit.prevent="preview">
      <label>可用时间（分钟）<input v-model.number="minutes" type="number" inputmode="numeric" min="0" max="1440" step="1" /></label>
      <label>每题预估（分钟）<input v-model.number="perQuestion" type="number" inputmode="numeric" min="1" max="60" step="1" /></label>
      <button class="primary" :disabled="s.loading || s.checking">{{ s.loading ? '正在挑选…' : '预览本次题目' }}</button>
    </form>
    <p v-if="s.error" class="review-error" role="alert">{{ s.error }}</p>
    <div v-if="s.preview" aria-live="polite">
      <p class="session-plan-summary"><b>{{ s.preview.selected_count }} 题 · 约 {{ s.preview.estimated_minutes }} 分钟</b><span>符合条件 {{ s.preview.eligible_count }} 题，本次延后 {{ s.preview.deferred_count }} 题</span></p>
      <p>{{ s.preview.estimate_note }}</p><p v-if="s.preview.warning" class="review-notice">{{ s.preview.warning }}</p>
      <ol v-if="s.preview.items.length" class="session-plan-list"><li v-for="item in s.preview.items" :key="item.ref.wrong_id"><strong>{{ item.stem }}</strong><span>{{ item.priority.reason }} · 预估 {{ item.estimated_minutes }} 分钟</span></li></ol>
      <p v-else>当前预算与筛选下没有可安排的到期题。可调整时间或回到目录修改筛选。</p>
      <button class="primary" :disabled="!s.preview.items.length || s.loading || s.checking" @click="start">{{ s.checking ? '正在核验题目…' : '核验并开始本次复习' }}</button>
      <p class="review-meta">预览与开始不会创建长期计划或作答。题目变化时会要求重新预览。</p>
    </div>
  </section>
</template>
<script setup lang="ts">
import { ref, reactive, watch, onBeforeUnmount } from 'vue'
import * as api from '../../services/review-api'
import { createReviewSessionController } from '../../wrongbook/session-state'
import type { ReviewFilter, ReviewSessionReady } from '../../types/wrongbook'
const props = defineProps<{ filters: ReviewFilter; scope: string | null }>()
const emit = defineEmits<{ ready: [result: ReviewSessionReady]; close: [] }>()
const minutes = ref(20), perQuestion = ref(4)
const c = createReviewSessionController(api, value => reactive(value) as typeof value), s = c.state
watch([minutes, perQuestion, () => props.filters, () => props.scope], () => c.invalidate(), { deep: true, flush: 'sync' })
async function preview() { await c.load(props.filters, minutes.value, perQuestion.value) }
async function start() { const result = await c.check(); if (result) emit('ready', result) }
onBeforeUnmount(() => c.dispose())
defineExpose({ invalidate: c.invalidate })
</script>
