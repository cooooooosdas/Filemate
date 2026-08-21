<template>
  <div class="wrongbook-page" aria-live="polite">
    <header>
      <div><p class="eyebrow">LEARNING LOOP</p><h1>错题复盘</h1><p>答错自动收录，连续答对两次后移入已掌握。</p></div>
      <button class="filter" @click="showMastered = !showMastered; load()">{{ showMastered ? '查看待复习' : '查看已掌握' }}</button>
    </header>
    <div v-if="loading" class="empty">正在加载…</div>
    <DataState v-else-if="error" :error="error" @retry="load" />
    <div v-else-if="!items.length" class="empty">{{ showMastered ? '暂无已掌握题目' : '暂无错题，继续保持' }}</div>
    <article v-for="item in items" :key="item.wrong_id" class="wrong-card">
      <div class="meta"><span>{{ item.question.type }}</span><span>错误 {{ item.error_count }} 次</span><span>复习 {{ item.review_count }} 次</span><span>{{ reviewLabel(item) }}</span></div>
      <h2>{{ item.question.question }}</h2>
      <p v-if="item.question.explanation">{{ item.question.explanation }}</p>
      <small>最近答案：{{ item.latest_answer || '未填写' }}</small>
      <div v-if="!showMastered" class="retry">
        <input v-model="answers[item.wrong_id]" :name="`retry_${item.wrong_id}`" autocomplete="off" :aria-label="`重新回答：${item.question.question}`" placeholder="重新作答…" @keyup.enter="retry(item)" />
        <button :disabled="!answers[item.wrong_id]?.trim()" @click="retry(item)">提交复习</button>
      </div>
      <p v-if="results[item.wrong_id]" class="result">{{ results[item.wrong_id] }}</p>
    </article>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getWrongbook, submitQuizAttempt, type WrongQuestion } from '../services/api'
import DataState from '../components/DataState.vue'

const items = ref<WrongQuestion[]>([])
const loading = ref(true)
const error = ref('')
const showMastered = ref(false)
const answers = ref<Record<string, string>>({})
const results = ref<Record<string, string>>({})
const load = async () => {
  loading.value = true
  error.value = ''
  try { items.value = await getWrongbook(showMastered.value) }
  catch (e: any) { error.value = e?.message || '加载失败'; ElMessage.error(error.value) }
  finally { loading.value = false }
}
onMounted(load)
const retry = async (item: WrongQuestion) => {
  const answer = answers.value[item.wrong_id]?.trim()
  if (!answer) return
  try {
    const result = await submitQuizAttempt(item.artifact_id, item.question_index, answer)
    results.value[item.wrong_id] = `${result.feedback}（相似度 ${Math.round(result.score * 100)}%）`
    if (result.is_correct) await load()
  } catch (error: any) { ElMessage.error(error.message || '提交失败') }
}
const reviewLabel = (item: WrongQuestion) => {
  if (item.mastered) return '已掌握'
  const next = new Date(item.next_review_at)
  if (Number.isNaN(next.getTime()) || next <= new Date()) return '现在到期'
  return `${new Intl.DateTimeFormat('zh-CN',{month:'short',day:'numeric'}).format(next)}复习`
}
</script>

<style scoped>
.wrongbook-page { max-width: 980px; margin: 0 auto; padding: 28px; color: var(--text-primary); }
header { display: flex; justify-content: space-between; gap: 24px; align-items: end; margin-bottom: 28px; }
h1 { margin: 3px 0 8px; font-size: 30px; } header p { margin: 0; color: var(--text-secondary); }
.eyebrow { color: var(--accent); font-size: 12px; font-weight: 700; letter-spacing: .12em; }
.filter { border: 1px solid var(--accent-border); background: var(--accent-soft); color: var(--accent); padding: 10px 16px; border-radius: 10px; cursor: pointer; }
.wrong-card { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 14px; padding: 20px; margin-bottom: 14px; }
.wrong-card h2 { font-size: 17px; margin: 12px 0; }.wrong-card p,.wrong-card small { color: var(--text-secondary); }
.meta { display: flex; gap: 8px; flex-wrap: wrap; }.meta span { background: var(--accent-soft); color: var(--accent); padding: 4px 9px; border-radius: 999px; font-size: 12px; }
.empty { padding: 70px; text-align: center; background: var(--bg-surface); border: 1px dashed var(--border-default); border-radius: 14px; color: var(--text-muted); }
.retry { display: flex; gap: 8px; margin-top: 14px; }.retry input { flex: 1; border: 1px solid var(--border-default); border-radius: 9px; padding: 10px 12px; background: var(--bg-elevated); }.retry button { border: 0; border-radius: 9px; padding: 10px 14px; color: #fff; background: var(--accent); }.retry button:disabled { opacity: .45; }.result { color: var(--accent) !important; font-weight: 600; }
@media (max-width: 640px) { header { align-items: start; flex-direction: column; }.wrongbook-page { padding: 18px; } }
</style>
