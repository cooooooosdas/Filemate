<template>
  <section class="cl-section" aria-label="课程学习路径">
    <h3>把下一步排进日程</h3><p>依据当前知识点、真实错答与有效前置关系，只新增计划。</p>
    <label>这次想达成什么<input :value="options.goal" maxlength="500" :disabled="busy" @input="change({ goal: ($event.target as HTMLInputElement).value })" /></label>
    <div class="cl-fields"><label>安排天数<input :value="options.days" type="number" min="1" max="7" :disabled="busy" @input="change({ days: Number(($event.target as HTMLInputElement).value) })" /></label><label>每天分钟<input :value="options.daily_minutes" type="number" min="5" max="180" :disabled="busy" @input="change({ daily_minutes: Number(($event.target as HTMLInputElement).value) })" /></label></div>
    <label>关联已有目标（可选）<select :value="options.goal_id || ''" :disabled="busy" @change="change({ goal_id: ($event.target as HTMLSelectElement).value || null })"><option value="">本次自定目标</option><option v-for="goal in goals" :key="goal.artifact_id" :value="goal.artifact_id">{{ goal.title }}</option></select></label>
    <button :disabled="busy || !options.goal.trim()" @click="$emit('preview')">预览学习路径</button>
    <div v-if="preview" class="cl-confirm"><ol class="cl-tasks"><li v-for="task in preview.tasks" :key="task.day_index"><strong>第 {{ task.day_index + 1 }} 天 · {{ task.label }}</strong><p>{{ kinds[task.kind] || task.kind }} · {{ task.duration_minutes }} 分钟</p><p>{{ task.reason }}</p></li></ol><p v-if="preview.scope_expanded_count">包含 {{ preview.scope_expanded_count }} 个有效前置概念。</p><p v-if="preview.omitted_count">还有 {{ preview.omitted_count }} 项未排入本次日程。</p><p v-if="preview.unsupported_count">{{ preview.unsupported_count }} 个概念无有效来源，未参与推荐。</p><p v-if="preview.outside_scope_prerequisite_count" role="status">另有 {{ preview.outside_scope_prerequisite_count }} 个前置知识位于所选章节之外，未排入本次计划：{{ preview.outside_scope_prerequisites.map(item => item.label).join("、") }}。可扩大章节范围后重新预览。</p><button class="cw-primary" :disabled="busy" @click="$emit('confirm')">确认新增计划</button></div>
    <p v-if="receipt" role="status">学习计划已保存。<RouterLink :to="`/study-plan?plan=${receipt.plan_id}`">打开这份计划</RouterLink> · <RouterLink to="/today">今日学习</RouterLink></p>
  </section>
</template>
<script setup lang="ts">
import type { LearningReceipt, PathOptions, PathPreview } from '../../types/courseLearning'
defineProps<{ options: PathOptions; preview: PathPreview | null; receipt: LearningReceipt | null; busy: boolean; goals: { artifact_id: string; title: string }[] }>()
const emit = defineEmits<{ options: [value: Partial<PathOptions>]; preview: []; confirm: [] }>()
const change = (value: Partial<PathOptions>) => emit('options', value)
const kinds: Record<string, string> = { read: '核对原文', practice: '专项练习', review: '复习错题' }
</script>
