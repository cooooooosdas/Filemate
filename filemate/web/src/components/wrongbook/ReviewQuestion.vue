<template>
  <section class="review-question" aria-label="当前复习问题">
    <p class="question-kind">{{ shown.type === 'choice' ? '选择题' : shown.type === 'fill' ? '填空题' : shown.type === 'code' ? '代码题' : '简答题' }}</p>
    <h2 tabindex="-1">{{ shown.stem || '题目内容不可用' }}</h2>
    <pre v-if="shown.code" class="code-block">{{ shown.code }}</pre>
    <fieldset v-if="shown.options.length" :disabled="locked"><legend>选择你的回答</legend>
      <label v-for="option in shown.options" :key="option.key" class="review-option"><input type="radio" :name="`review-${identity}`" :value="option.key" :checked="s.answer === option.key" @change="submission.setAnswer(option.key)" /><b>{{ option.key }}</b><span>{{ option.text }}</span></label>
    </fieldset>
    <label v-else class="answer-field">你的回答<textarea :value="s.answer" :disabled="locked" rows="5" maxlength="10000" placeholder="先独立作答，再核对依据" @input="submission.setAnswer(($event.target as HTMLTextAreaElement).value)" /></label>
    <p v-if="readonly" class="review-notice">{{ readonlyReason || '当前为只读记录，可查看证据，不能提交作答。' }}</p>
    <div v-else class="review-actions">
      <button class="primary" :disabled="locked || !s.answer.trim()" @click="submit('answer')">{{ s.busy ? '正在保存…' : '提交回答' }}</button>
      <button v-if="allowAssistance !== false" :disabled="locked" @click="submit('dont_know')">暂时不会</button>
      <button v-if="allowAssistance !== false && !s.receipt && !s.answerRevealed" :disabled="s.busy || s.uncertain" @click="submission.revealAnswer()"><View :size="19" />查看答案</button>
    </div>
    <p v-if="s.error" ref="errorFocus" role="alert" tabindex="-1" class="review-error">{{ s.error }}</p>
    <div v-if="s.uncertain" class="review-actions"><button :disabled="s.busy" @click="submission.recover()">查询保存回执</button><button :disabled="s.busy || s.stale" @click="submit('answer')">原样重试</button></div>
    <p v-if="s.answerRevealed && !s.receipt" class="review-notice">已查看参考，本次将记为辅助练习，不计独立验证。</p>
    <section v-if="s.receipt" class="review-receipt" role="status"><h3>{{ reviewResultLabel(s.receipt) }}</h3><p>{{ s.receipt.feedback }}</p><p>{{ s.receipt.eligible ? '本次计入合格验证。' : '本次已保存；是否计入合格验证由真实作答与复习时间共同决定。' }}</p></section>
    <section v-if="s.answerRevealed || s.receipt" class="review-reference"><h3>参考与解析</h3><p class="preserve">{{ shown.reference || s.receipt?.reference_answer || '暂无参考答案' }}</p><p class="preserve">{{ shown.explanation }}</p></section>
  </section>
</template>
<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { View } from '../../icons'
import { presentReviewQuestion, reviewResultLabel } from '../../wrongbook/presentation'
import type { createReviewSubmission } from '../../wrongbook/submission'
const props = withDefaults(defineProps<{ question: Record<string, unknown>; identity: string; submission: ReturnType<typeof createReviewSubmission>; readonly?: boolean; readonlyReason?: string; allowAssistance?: boolean }>(), { allowAssistance: true })
const emit = defineEmits<{ saved: [] }>()
const s = computed(() => props.submission.state)
const errorFocus = ref<HTMLElement | null>(null)
watch(() => s.value.error, async value => { if (value) { await nextTick(); errorFocus.value?.focus() } })
const shown = computed(() => presentReviewQuestion(props.question))
const locked = computed(() => !!props.readonly || s.value.busy || s.value.stale || !!s.value.receipt || s.value.uncertain)
async function submit(action: 'answer' | 'dont_know') { if (await props.submission.submit(action)) emit('saved') }
</script>
