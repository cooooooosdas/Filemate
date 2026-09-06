<template>
  <article class="learning-artifact">
    <header><div><small>{{ label }}</small><h3>{{ artifact.title }}</h3></div><button type="button" @click="download">导出</button></header>
    <p v-if="artifact.metadata?.source_truncated" class="notice">本次内容依据资料前 {{ artifact.metadata.input_characters }} 字生成，未覆盖全文。</p>
    <template v-if="artifact.artifact_type === 'knowledge_cards' && cards.length">
      <div class="pager"><span>知识卡 {{ index + 1 }} / {{ cards.length }}</span><div><button :disabled="index === 0" aria-label="上一张卡片" @click="move(-1)">上一张</button><button :disabled="index === cards.length - 1" aria-label="下一张卡片" @click="move(1)">下一张</button></div></div>
      <button class="flashcard" type="button" :aria-expanded="revealed" @click="revealed = !revealed">
        <small>{{ revealed ? '参考解释' : '先回忆，再翻面' }}</small><p>{{ revealed ? cards[index]?.back : cards[index]?.front }}</p><span>{{ revealed ? '返回问题' : '点击查看解释' }}</span>
      </button>
      <p class="muted">翻面用于自主回忆，不会据此推断掌握度。</p>
    </template>
    <template v-else-if="artifact.artifact_type === 'questions' && questions.length">
      <div class="pager"><span>练习 {{ index + 1 }} / {{ questions.length }}</span><div><button :disabled="index === 0" @click="move(-1)">上一题</button><button :disabled="index === questions.length - 1" @click="move(1)">下一题</button></div></div>
      <h4>{{ question?.stem || question?.question }}</h4>
      <fieldset v-if="options.length"><legend class="sr-only">选择答案</legend><label v-for="option in options" :key="option.key" class="choice"><input v-model="answers[index]" type="radio" :name="`answer-${artifact.artifact_id}-${index}`" :value="option.key" :disabled="Boolean(results[index]) || saving" /><span>{{ option.text }}</span></label></fieldset>
      <textarea v-else v-model="answers[index]" rows="4" aria-label="练习答案" placeholder="写下你的回答…" :disabled="Boolean(results[index]) || saving" />
      <button v-if="!results[index]" class="primary" :disabled="!answers[index]?.trim() || saving" @click="submit">{{ saving ? '正在保存作答…' : '提交答案' }}</button>
      <div v-else class="answer-feedback" role="status"><strong>{{ results[index]?.is_correct ? '回答正确' : '已记录到错题本' }}</strong><p>{{ results[index]?.feedback }}</p><p>参考答案：{{ results[index]?.reference_answer }}</p><p>{{ question?.analysis || question?.explanation }}</p><router-link v-if="!results[index]?.is_correct" to="/wrongbook">前往复盘</router-link></div>
      <p class="muted">作答会保存；此处的本轮答题标记不会跨页面保留。</p>
    </template>
    <div v-else-if="artifact.artifact_type === 'notes' && sections.length" class="note-content"><section v-for="(section, i) in sections" :key="i"><h4>{{ section.title }}</h4><p>{{ section.content }}</p></section></div>
    <p v-else class="read-content">{{ typeof artifact.content === 'string' ? artifact.content : JSON.stringify(artifact.content, null, 2) }}</p>
    <p v-if="error" role="alert" class="error">{{ error }} 请重试。</p>
  </article>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { submitQuizAttempt, type KnowledgeArtifact, type QuizAttemptResult } from '../services/api'
const props = defineProps<{ artifact: KnowledgeArtifact }>()
const index = ref(0)
const revealed = ref(false)
const answers = ref<Record<number, string>>({})
const results = ref<Record<number, QuizAttemptResult>>({})
const saving = ref(false)
const error = ref('')
const label = computed(() => ({ summary: '摘要', notes: '结构化笔记', knowledge_cards: '主动回忆', questions: '随堂练习' }[props.artifact.artifact_type] || '学习内容'))
const cards = computed(() => Array.isArray(props.artifact.content) ? props.artifact.content : [])
const questions = cards
const question = computed(() => questions.value[index.value])
const sections = computed(() => Array.isArray(props.artifact.content?.sections) ? props.artifact.content.sections : [])
const options = computed(() => {
  const items = question.value?.options
  if (Array.isArray(items)) return items.map((text, i) => ({ key: String.fromCharCode(65 + i), text: String(text) }))
  if (items && typeof items === 'object') return Object.entries(items).map(([key, value]) => ({ key, text: `${key}. ${value}` }))
  return []
})
watch(() => props.artifact.artifact_id, () => { index.value = 0; revealed.value = false; answers.value = {}; results.value = {}; error.value = '' })
function move(offset: number) { index.value += offset; revealed.value = false; error.value = '' }
async function submit() {
  if (saving.value || !answers.value[index.value]?.trim()) return
  const targetId = props.artifact.artifact_id
  const targetIndex = index.value
  saving.value = true; error.value = ''
  try {
    const result = await submitQuizAttempt(targetId, targetIndex, answers.value[targetIndex]!)
    if (props.artifact.artifact_id === targetId) results.value[targetIndex] = result
  } catch (cause) { if (props.artifact.artifact_id === targetId) error.value = cause instanceof Error ? cause.message : '提交失败' }
  finally { saving.value = false }
}
function download() {
  const text = typeof props.artifact.content === 'string' ? props.artifact.content : JSON.stringify(props.artifact.content, null, 2)
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
  const link = document.createElement('a'); link.href = url
  link.download = `${props.artifact.title.replace(/[<>:"/\\|?*]/g, '_')}.txt`; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
</script>

<style scoped>
.learning-artifact{color:var(--text-primary);min-width:0}.learning-artifact header{display:flex;gap:12px;align-items:start;justify-content:space-between;padding-bottom:22px;border-bottom:1px solid var(--border-color,#d7e3d9)}h3{font-size:18px;line-height:1.6;margin:6px 0 0;overflow-wrap:anywhere}small,.muted{color:#566e60;font-size:12px;line-height:1.7}button{min-height:44px;padding:8px 12px;background:white;border:1px solid #d7e3d9;border-radius:8px;color:inherit;cursor:pointer}button:disabled{opacity:.5;cursor:default}button:focus-visible,textarea:focus-visible{outline:2px solid #2f7d55;outline-offset:3px}.pager{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:8px;margin:20px 0;font-size:13px}.pager>div{display:flex;gap:6px}.flashcard{width:100%;min-height:260px;background:#f0f5ef;text-align:left;padding:26px;display:flex;flex-direction:column;justify-content:space-between;animation:reveal .2s ease}.flashcard p{font-size:19px;line-height:1.9;white-space:pre-wrap;overflow-wrap:anywhere}.flashcard span{font-size:12px;color:#2f7d55}.primary{background:#2f7d55;color:white;margin-top:16px}h4{font-size:16px;line-height:1.8}.read-content,.note-content p{white-space:pre-wrap;line-height:1.95;font-size:14px;overflow-wrap:anywhere}.note-content section{padding:8px 0}.choice{display:flex;gap:10px;padding:13px 10px;border-bottom:1px solid #e3eae3;line-height:1.6;cursor:pointer}.choice input{accent-color:#2f7d55}fieldset{border:0;padding:0;min-width:0}textarea{width:100%;box-sizing:border-box;padding:12px;border:1px solid #d7e3d9;border-radius:8px;font:inherit;resize:vertical}.answer-feedback{padding:18px;background:#f0f5ef;margin-top:18px;line-height:1.8;font-size:14px;overflow-wrap:anywhere}.notice{padding:12px;background:#fff8e8;color:#77581d;font-size:12px}.error{color:#a13939}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}@keyframes reveal{from{opacity:.5;transform:translateY(4px)}to{opacity:1;transform:none}}@media(prefers-reduced-motion:reduce){.flashcard{animation:none}}
</style>
