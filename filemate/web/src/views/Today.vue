<template>
  <div class="today-page">
    <header class="hero">
      <div>
        <p class="eyebrow">DAILY LEARNING QUEUE</p>
        <h1>今天，只完成最重要的学习任务</h1>
        <p>根据计划日期、考试紧迫度和错题次数自动排序，完成后立即更新本地成长记录。</p>
      </div>
      <button type="button" :disabled="loading" @click="load">{{ loading ? '刷新中…' : '刷新队列' }}</button>
    </header>

    <div v-if="loading" class="state" aria-live="polite">正在计算今日学习顺序…</div>
    <DataState v-else-if="error" :error="error" @retry="load" />
    <template v-else-if="data">
      <section class="summary" aria-label="今日学习概览">
        <article><span>推荐任务</span><strong>{{ data.items.length }}</strong><small>按薄弱程度排序</small></article>
        <article><span>预计用时</span><strong>{{ data.recommended_minutes }}</strong><small>分钟</small></article>
        <article><span>进行中计划</span><strong>{{ data.active_plan_count }}</strong><small>可跨重启继续</small></article>
        <article><span>待复习错题</span><strong>{{ data.pending_wrong_count }}</strong><small>连续答对两次掌握</small></article>
      </section>

      <section v-if="data.items.length" class="queue">
        <div class="section-head"><div><p class="eyebrow">RECOMMENDED ORDER</p><h2>今日执行顺序</h2></div><span>{{ formatDate(data.date) }}</span></div>
        <article v-for="(item, index) in data.items" :key="item.item_id" class="task-card" :class="item.priority">
          <div class="order">{{ String(index + 1).padStart(2, '0') }}</div>
          <div class="task-main">
            <div class="task-meta"><span>{{ item.kind === 'plan_day' ? '计划任务' : '错题复习' }}</span><em>{{ item.duration_minutes }} 分钟</em><b v-if="item.priority === 'high'">优先</b></div>
            <h3>{{ item.title }}</h3>
            <p>{{ item.reason }}</p>
            <ul v-if="item.tasks?.length"><li v-for="task in item.tasks" :key="task">{{ task }}</li></ul>
            <p v-if="item.explanation" class="hint">复习提示：{{ item.explanation }}</p>
            <div v-if="item.kind === 'wrong_question'" class="retry">
              <label><span class="sr-only">重新回答这道错题</span><input v-model="answers[item.item_id]" :name="`today_${item.wrong_id}`" autocomplete="off" placeholder="先回忆，再输入答案…" @keyup.enter="retry(item)" /></label>
              <button type="button" :disabled="!answers[item.item_id]?.trim() || working.has(item.item_id)" @click="retry(item)">提交答案</button>
            </div>
            <p v-if="results[item.item_id]" class="feedback">{{ results[item.item_id] }}</p>
          </div>
          <div class="task-action">
            <button v-if="item.kind === 'plan_day'" type="button" :disabled="working.has(item.item_id)" @click="completePlan(item)">{{ working.has(item.item_id) ? '保存中…' : '完成任务' }}</button>
            <router-link v-else :to="item.route">完整复盘</router-link>
          </div>
        </article>
      </section>

      <section v-else class="empty">
        <span>✓</span><h2>今天的队列已经清空</h2><p>可以添加新的课程资料，或者创建下一份考试计划。</p>
        <div><router-link to="/ai-tools">理解新资料</router-link><router-link class="secondary" to="/study-plan">创建学习计划</router-link></div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getTodayReview,
  submitQuizAttempt,
  updateStudyPlanDay,
  type TodayReview,
  type TodayReviewItem
} from '../services/api'
import DataState from '../components/DataState.vue'

const data = ref<TodayReview | null>(null)
const loading = ref(true)
const error = ref('')
const answers = ref<Record<string, string>>({})
const results = ref<Record<string, string>>({})
const working = ref<Set<string>>(new Set())

const setWorking = (itemId: string, active: boolean) => {
  const next = new Set(working.value)
  active ? next.add(itemId) : next.delete(itemId)
  working.value = next
}

const load = async () => {
  loading.value = true
  error.value = ''
  try { data.value = await getTodayReview() }
  catch (e: any) { error.value = e?.message || '今日学习队列加载失败'; ElMessage.error(error.value) }
  finally { loading.value = false }
}

const completePlan = async (item: TodayReviewItem) => {
  if (!item.plan_id || item.day_index === undefined) return
  setWorking(item.item_id, true)
  try {
    await updateStudyPlanDay(item.plan_id, item.day_index, true)
    ElMessage.success('今日计划已完成，成长数据已更新')
    await load()
  } catch (error: any) {
    ElMessage.error(error.message || '完成状态保存失败')
  } finally { setWorking(item.item_id, false) }
}

const retry = async (item: TodayReviewItem) => {
  const answer = answers.value[item.item_id]?.trim()
  if (!answer || !item.artifact_id || item.question_index === undefined) return
  setWorking(item.item_id, true)
  try {
    const result = await submitQuizAttempt(item.artifact_id, item.question_index, answer)
    results.value[item.item_id] = `${result.feedback}（匹配度 ${Math.round(result.score * 100)}%）`
    answers.value[item.item_id] = ''
    await load()
  } catch (error: any) {
    ElMessage.error(error.message || '答案提交失败')
  } finally { setWorking(item.item_id, false) }
}

const formatDate = (value: string) => new Intl.DateTimeFormat('zh-CN', {
  month: 'long', day: 'numeric', weekday: 'long'
}).format(new Date(`${value}T00:00:00`))

onMounted(load)
</script>

<style scoped>
.today-page{max-width:1120px;margin:0 auto;padding:28px;color:var(--text-primary)}.hero{display:flex;justify-content:space-between;align-items:end;gap:32px;margin-bottom:24px}.hero h1{max-width:760px;margin:6px 0 10px;font-size:clamp(30px,4.5vw,48px);line-height:1.08;letter-spacing:-.04em}.hero p{max-width:760px;margin:0;color:var(--text-secondary);line-height:1.7}.hero>button{padding:10px 15px;border:1px solid var(--accent-border);border-radius:9px;background:var(--accent-soft);color:var(--accent);font-weight:700;cursor:pointer}.hero>button:disabled{opacity:.5}.eyebrow{color:var(--accent)!important;font-size:11px!important;font-weight:800;letter-spacing:.14em}.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.summary article,.queue,.empty{border:1px solid var(--border-subtle);border-radius:16px;background:var(--bg-surface)}.summary article{display:flex;flex-direction:column;padding:18px}.summary span,.summary small{color:var(--text-secondary);font-size:12px}.summary strong{margin:8px 0 3px;font-size:30px}.queue{margin-top:16px;padding:22px}.section-head{display:flex;justify-content:space-between;align-items:end;margin-bottom:16px}.section-head h2{margin:4px 0 0;font-size:21px}.section-head>span{color:var(--text-muted);font-size:13px}.task-card{display:grid;grid-template-columns:48px 1fr auto;gap:16px;padding:18px 0;border-top:1px solid var(--border-subtle)}.order{width:42px;height:42px;display:grid;place-items:center;border-radius:12px;background:var(--accent-soft);color:var(--accent);font-weight:800}.task-card.high .order{background:#fff0df;color:#9a5713}.task-meta{display:flex;align-items:center;gap:8px;font-size:11px}.task-meta span{color:var(--accent);font-weight:800}.task-meta em{font-style:normal;color:var(--text-muted)}.task-meta b{padding:3px 7px;border-radius:999px;background:#fff0df;color:#9a5713}.task-main h3{margin:7px 0;font-size:17px}.task-main>p{margin:0;color:var(--text-secondary);font-size:13px}.task-main ul{margin:10px 0 0;padding-left:18px;color:var(--text-secondary);font-size:13px;line-height:1.7}.hint{margin-top:10px!important;padding:9px 11px;border-radius:8px;background:var(--bg-base)}.task-action{display:flex;align-items:center}.task-action button,.task-action a{display:inline-flex;padding:9px 13px;border:1px solid var(--accent-border);border-radius:8px;background:var(--accent);color:white;text-decoration:none;font-weight:700;cursor:pointer}.task-action button:disabled{opacity:.5}.retry{display:flex;gap:8px;margin-top:12px}.retry label{flex:1}.retry input{width:100%;box-sizing:border-box;padding:10px 11px;border:1px solid var(--border-default);border-radius:8px;background:var(--bg-base);color:var(--text-primary)}.retry button{padding:9px 12px;border:0;border-radius:8px;background:var(--accent);color:#fff;font-weight:700}.retry button:disabled{opacity:.45}.feedback{margin-top:9px!important;color:var(--accent)!important;font-weight:700}.empty{display:flex;align-items:center;flex-direction:column;padding:70px 24px;text-align:center}.empty>span{width:54px;height:54px;display:grid;place-items:center;border-radius:50%;background:var(--accent-soft);color:var(--accent);font-size:26px}.empty h2{margin:16px 0 8px}.empty p{margin:0;color:var(--text-muted)}.empty div{display:flex;gap:9px;margin-top:20px}.empty a{padding:10px 14px;border-radius:9px;background:var(--accent);color:white;text-decoration:none}.empty a.secondary{border:1px solid var(--accent-border);background:transparent;color:var(--accent)}.state{padding:90px;text-align:center;color:var(--text-muted)}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}@media(max-width:820px){.summary{grid-template-columns:1fr 1fr}.task-card{grid-template-columns:42px 1fr}.task-action{grid-column:2}}@media(max-width:560px){.today-page{padding:16px}.hero{align-items:flex-start;flex-direction:column}.summary{grid-template-columns:1fr 1fr}.queue{padding:16px}.task-card{grid-template-columns:1fr}.order{display:none}.task-action{grid-column:auto}.retry{flex-direction:column}}@media(max-width:380px){.summary{grid-template-columns:1fr}}
</style>
