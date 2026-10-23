<template>
  <section class="cl-section" aria-label="审核练习草稿">
    <h3>从原文创建练习</h3><p>先核对问题和出处，再保存为正式题集。本地模式只做术语填空。</p>
    <fieldset :disabled="busy"><legend>生成方式</legend><label><input v-model="mode" type="radio" value="local" />本地基础练习</label><label><input v-model="mode" type="radio" value="llm" />模型生成</label></fieldset>
    <label>题目数量 <input v-model.number="count" type="number" min="1" max="5" /></label>
    <label v-if="mode === 'llm'">难度 <select v-model="difficulty"><option value="simple">基础</option><option value="standard">标准</option><option value="advanced">进阶</option></select></label>
    <label v-if="mode === 'llm'"><input v-model="consent" type="checkbox" />同意本次将相关课程原文发送给已配置的模型</label>
    <button :disabled="busy || (mode === 'llm' && !consent)" @click="generate">{{ work?.status === 'failed' ? '重新生成' : '生成待审核练习' }}</button>
    <template v-if="work">
      <p role="status">{{ work.stale ? '课程或学习记录已更新，请重新生成。' : labels[work.status] || work.status }}<span v-if="work.error_code"> · {{ work.error_code }}</span></p>
      <p class="cw-caption">工作编号 {{ work.work_id }}</p>
      <button v-if="['running', 'ready', 'interrupted'].includes(work.status)" :disabled="busy" @click="$emit('cancel')">取消这份草稿</button>
      <button :disabled="busy" @click="$emit('recover', work.work_id)">重新读取已存结果</button>
      <template v-if="work.status === 'ready' && !work.stale">
        <article v-for="(q, index) in edited" :key="index" class="cw-quote">
          <label><input type="checkbox" :checked="accepted.has(index)" :disabled="busy" @change="toggle(index)" />接受第 {{ index + 1 }} 题</label>
          <label>题干<textarea :value="q.stem || q.question" :disabled="busy" maxlength="4000" @input="edit(index, 'stem', ($event.target as HTMLTextAreaElement).value)" /></label>
          <p v-for="option in q.options" :key="option">{{ option }}</p>
          <label>参考答案<input :value="q.answer" :disabled="busy" maxlength="4000" @input="edit(index, 'answer', ($event.target as HTMLInputElement).value)" /></label>
          <details><summary>核对原文</summary><blockquote v-for="quote in work.payload.quotes?.filter(r => q.citation_ids?.includes(r.evidence_id))" :key="quote.evidence_id">{{ quote.quote }}</blockquote></details>
        </article>
        <button :disabled="busy || accepted.size === 0" @click="$emit('review')">预览选中题目</button>
        <div v-if="preview" class="cl-confirm"><p>将新增 {{ preview.accepted_count }} 道正式题目，并关联当前知识点。</p><button class="cw-primary" :disabled="busy" @click="$emit('confirm')">确认保存题集</button></div>
      </template>
    </template>
    <p v-if="receipt" role="status">题集已保存。在“选择题目”中打开，即可开始真实练习。</p>
  </section>
</template>
<script setup lang="ts">
import { ref, shallowRef, toRaw, watch } from 'vue'
import type { LearningPreview, LearningQuestion, LearningReceipt, LearningWork, PracticeDecision, PracticeOptions } from '../../types/courseLearning'
const props = defineProps<{ work: LearningWork | null; preview: LearningPreview | null; receipt: LearningReceipt | null; busy: boolean }>()
const emit = defineEmits<{ generate: [options: PracticeOptions]; decisions: [items: PracticeDecision[]]; review: []; confirm: []; cancel: []; recover: [id: string] }>()
const mode = ref<'local' | 'llm'>('local'), consent = ref(false), count = ref(1), difficulty = ref<PracticeOptions['difficulty']>('simple')
const edited = shallowRef<LearningQuestion[]>([]), accepted = shallowRef(new Set<number>())
const labels: Record<string, string> = { running: '正在生成', ready: '等待人工审核', failed: '生成失败，没有保存为正式题目', cancelled: '已取消', interrupted: '工作已中断', confirmed: '已保存题集' }
let initializedWork = ''
watch(() => [props.work?.work_id, props.work?.status], ([id]) => {
  if (id !== initializedWork) { edited.value = []; accepted.value = new Set(); consent.value = false; initializedWork = '' }
  if (id && props.work?.status === 'ready' && initializedWork !== id) {
    edited.value = structuredClone(toRaw(props.work.payload.questions || [])); accepted.value = new Set(); initializedWork = id
  }
}, { immediate: true })
function publish() { emit('decisions', edited.value.map((q, index) => ({ index, verdict: accepted.value.has(index) ? 'accept' : 'reject', ...(accepted.value.has(index) ? { question: q } : {}) }))) }
function toggle(index: number) { const next = new Set(accepted.value); if (next.has(index)) next.delete(index); else next.add(index); accepted.value = next; publish() }
function edit(index: number, key: 'stem' | 'answer', value: string) { edited.value = edited.value.map((q, i) => i === index ? { ...q, [key]: value } : q); publish() }
function generate() { emit('generate', { mode: mode.value, count: count.value, difficulty: difficulty.value, allow_external_model: consent.value }) }
</script>
