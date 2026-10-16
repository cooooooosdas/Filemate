<template>
  <div class="today-page ppt-surface">
    <header class="hero">
      <div>
        <h1>今日学习</h1>
        <p>{{ todayLabel }} · 从已有记录继续学</p>
      </div>
      <button type="button" :disabled="loading" @click="load">{{ loading ? '刷新中…' : '刷新队列' }}</button>
    </header>

    <div v-if="loading" class="state" aria-live="polite">正在计算今日学习顺序…</div>
    <DataState v-else-if="error" :error="error" @retry="load" />
    <template v-else-if="data">
      <div class="today-layout">
        <div class="today-main">
          <section class="day-welcome" aria-label="开始今天的学习">
            <div><h2>留一点时间，<br />把今天学扎实。</h2><p>{{ data.items.length ? `已为你排好 ${data.items.length} 项任务，预计 ${data.recommended_minutes} 分钟。` : '从一份资料、一场复习开始，按自己的节奏来。' }}</p><a v-if="data.items.length" href="#today-queue" @click.prevent="focusQueue">从第一项开始<ArrowRight :size="20" aria-hidden="true" /></a></div>
            <StudyMotif class="day-motif" />
          </section>
      <section v-if="data.items.length" id="today-queue" ref="queueRoot" tabindex="-1" class="queue">
        <div class="section-head"><h2>今日执行顺序</h2><span>{{ formatDate(data.date) }}</span></div>
        <article v-for="(item, index) in data.items" :key="item.item_id" class="task-card" :class="item.priority">
          <div class="order">{{ String(index + 1).padStart(2, '0') }}</div>
          <div class="task-main">
            <div class="task-meta"><span>{{ item.kind === 'plan_day' ? '计划任务' : '错题复习' }}</span><em>{{ item.duration_minutes }} 分钟</em><b v-if="item.priority === 'high'">优先</b></div>
            <div class="reorder-actions" aria-label="调整任务顺序"><button type="button" :disabled="index === 0 || savingPreferences" :aria-label="`上移：${item.title}`" @click="moveTask(index, -1)">上移</button><button type="button" :disabled="index === data.items.length - 1 || savingPreferences" :aria-label="`下移：${item.title}`" @click="moveTask(index, 1)">下移</button></div>
            <h3>{{ item.title }}</h3>
            <p>{{ item.reason }}</p>
            <ul v-if="item.tasks?.length"><li v-for="task in item.tasks" :key="task">{{ task }}</li></ul>
            <p v-if="item.explanation && results[item.item_id]" class="hint">复习提示：{{ item.explanation }}</p>
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
        <span><el-icon><CircleCheckFilled /></el-icon></span><h2>{{ data.deferred_count ? '当前时长排不下待办任务' : '今天没有待完成的任务' }}</h2><p>{{ data.deferred_count ? '增加可用时长，或从计划和错题本选择一项开始。' : '可以读一份新资料，或者为下次考试安排计划。' }}</p>
        <div v-if="data.deferred_count"><router-link to="/wrongbook">打开错题本</router-link><router-link class="secondary" to="/study-plan">打开学习计划</router-link></div>
        <div v-else><router-link to="/ai-tools">理解新资料</router-link><router-link class="secondary" to="/study-plan">创建学习计划</router-link></div>
      </section>
        </div>
        <aside class="today-aside" aria-label="今日安排与时间">
          <section class="summary" aria-label="今日学习概览">
            <article><span class="summary-icon"><Notebook :size="25" /></span><div><span>今日任务</span><strong>{{ data.items.length }}<small> 项</small></strong><p>按计划与错题记录安排</p></div></article>
            <article class="review-stat"><span class="summary-icon"><Clock :size="25" /></span><div><span>待复习错题</span><strong>{{ data.pending_wrong_count }}<small> 题</small></strong><p>连续答对两次标记掌握</p></div></article>
            <article><span class="summary-icon"><Reading :size="25" /></span><div><span>进行中计划</span><strong>{{ data.active_plan_count }}<small> 个</small></strong><p>已完成的进度自动保留</p></div></article>
          </section>
      <section class="coach-controls" aria-label="今日学习安排">
        <div><h2>今天有多少时间？</h2><p>调整可用时长，任务会按预算重新安排。</p></div>
        <form @submit.prevent="saveBudget">
          <label for="available-minutes">可用时长</label>
          <input id="available-minutes" v-model.number="availableInput" type="number" min="10" max="240" step="5" :disabled="savingPreferences" />
          <span>分钟</span>
          <button type="submit" :disabled="savingPreferences || availableInput === data.available_minutes">{{ savingPreferences ? '保存中…' : '重新安排' }}</button>
        </form>
        <p v-if="data.deferred_count" class="deferred-note">另有 {{ data.deferred_count }} 项在 {{ data.available_minutes }} 分钟预算外，可调整时长后重新安排。</p>
      </section>

      <CompanionCard
        v-if="companionEvent"
        class="today-companion"
        compact
        :mood="companionEvent.mood"
        :title="companionEvent.title"
        :message="companionEvent.message"
        :evidence="companionEvent.evidence"
        :route="companionEvent.route"
        :action-label="companionEvent.actionLabel"
      />
        </aside>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheckFilled } from '@element-plus/icons-vue'
import { ArrowRight, Clock, Notebook, Reading } from '../icons'
import StudyMotif from '../components/StudyMotif.vue'
import {
  getTodayReview,
  saveTodayReviewPreferences,
  submitQuizAttempt,
  updateStudyPlanDay,
  type TodayReview,
  type TodayReviewItem
} from '../services/api'
import CompanionCard from '../components/CompanionCard.vue'
import DataState from '../components/DataState.vue'
import {
  publishCompanionEvent,
  type CompanionEvent
} from '../composables/useCompanion'

const todayLabel = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(new Date())
const queueRoot = ref<HTMLElement | null>(null)
function focusQueue(): void {
  queueRoot.value?.scrollIntoView({ block: 'start', behavior: 'auto' })
  queueRoot.value?.focus({ preventScroll: true })
}
const data = ref<TodayReview | null>(null)
const loading = ref(true)
const error = ref('')
const answers = ref<Record<string, string>>({})
const results = ref<Record<string, string>>({})
const working = ref<Set<string>>(new Set())
const companionEvent = ref<CompanionEvent | null>(null)
const availableInput = ref(60)
const savingPreferences = ref(false)

const setWorking = (itemId: string, active: boolean) => {
  const next = new Set(working.value)
  active ? next.add(itemId) : next.delete(itemId)
  working.value = next
}

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    data.value = await getTodayReview()
    availableInput.value = data.value.available_minutes
  }
  catch (e: any) { error.value = e?.message || '今日学习队列加载失败'; ElMessage.error(error.value) }
  finally { loading.value = false }
}

const saveBudget = async () => {
  if (!data.value || savingPreferences.value) return
  if (!Number.isInteger(availableInput.value) || availableInput.value < 10 || availableInput.value > 240) {
    ElMessage.warning('可用时长须为 10 至 240 分钟的整数')
    return
  }
  savingPreferences.value = true
  try {
    data.value = await saveTodayReviewPreferences(availableInput.value, data.value.item_order)
  } catch (e: any) { ElMessage.error(e?.message || '今日安排保存失败') }
  finally { savingPreferences.value = false }
}

const moveTask = async (index: number, direction: -1 | 1) => {
  if (!data.value || savingPreferences.value) return
  const next = [...data.value.items]
  const target = index + direction
  if (target < 0 || target >= next.length) return
  ;[next[index], next[target]] = [next[target], next[index]]
  const selectedIds = new Set(next.map(item => item.item_id))
  const itemOrder = [
    ...next.map(item => item.item_id),
    ...data.value.item_order.filter(id => !selectedIds.has(id))
  ]
  savingPreferences.value = true
  try {
    data.value = await saveTodayReviewPreferences(data.value.available_minutes, itemOrder)
    availableInput.value = data.value.available_minutes
  } catch (e: any) { ElMessage.error(e?.message || '任务顺序保存失败') }
  finally { savingPreferences.value = false }
}

const completePlan = async (item: TodayReviewItem) => {
  if (!item.plan_id || item.day_index === undefined) return
  setWorking(item.item_id, true)
  try {
    await updateStudyPlanDay(item.plan_id, item.day_index, true)
    ElMessage.success('今日计划已完成，成长数据已更新')
    companionEvent.value = publishCompanionEvent({
      mood: 'happy',
      title: '今天的学习任务完成啦',
      message: '这次完成已经进入你的成长记录，休息一下再继续也没关系。',
      evidence: `依据：已完成“${item.title}”`,
      route: '/growth',
      actionLabel: '看看成长变化'
    })
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
    const result = await submitQuizAttempt(item.artifact_id, item.question_index, answer, item.question_snapshot)
    results.value[item.item_id] = `${result.feedback}（匹配度 ${Math.round(result.score * 100)}%）`
    companionEvent.value = publishCompanionEvent({
      mood: result.is_correct ? 'wink' : 'encouraging',
      title: result.is_correct ? '这道题已经重新拿下' : '错题正在变成下一次的得分点',
      message: result.is_correct
        ? '继续保持，连续答对后系统会把它标记为已掌握。'
        : '先对照解析找出错因，再用自己的话回答一次。',
      evidence: `依据：本次作答匹配度 ${Math.round(result.score * 100)}%`,
      route: '/wrongbook',
      actionLabel: '查看错题证据'
    })
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
.today-page { max-width: 1320px; margin: 0 auto; color: var(--text-primary); }
.hero { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-bottom: 26px; }
.hero h1 { margin: 0 0 8px; font-size: var(--type-title); letter-spacing: -.03em; line-height: 1.2; }
.hero p { margin: 0; color: var(--text-secondary); font-size: 17px; }
.hero > button { min-height: 44px; padding: 10px 16px; border: 1px solid var(--border-subtle); border-radius: 10px; color: var(--text-secondary); background: var(--bg-surface); }
.today-layout { display: grid; grid-template-columns: minmax(0, 1fr) 310px; gap: 28px; align-items: start; }
.today-main, .today-aside { min-width: 0; }
.today-aside { display: grid; gap: 22px; }
.day-welcome { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 248px; padding: 32px; border-radius: 16px; background: linear-gradient(115deg, #e0eeff, #cbdfff); overflow: hidden; }
.day-welcome > div { position: relative; flex: 1; min-width: 0; }
.day-welcome h2 { margin: 0 0 16px; font-size: clamp(26px, 2.8vw, 36px); line-height: 1.4; letter-spacing: -.03em; }
.day-welcome p { max-width: 30ch; margin: 0; color: #405573; font-size: 17px; line-height: 1.8; }
.day-welcome a { display: inline-flex; align-items: center; gap: 10px; min-height: 44px; margin-top: 14px; color: #1c42ad; text-decoration: none; font-size: 17px; font-weight: 600; }
.day-motif { width: 210px; max-width: 43%; flex-shrink: 0; }
.summary { display: grid; gap: 16px; }
.summary article { display: flex; gap: 18px; padding: 24px; border-radius: 16px; background: #fff; }
.summary article.review-stat { background: #fff5eb; }
.summary-icon { display: grid; place-items: center; width: 48px; height: 48px; flex-shrink: 0; color: var(--accent); background: #e5efff; border-radius: 12px; }
.review-stat .summary-icon { color: #96551b; background: #ffe5c9; }
.summary article > div { min-width: 0; }
.summary article > div > span { font-size: 18px; font-weight: 600; }
.summary strong { display: block; margin-top: 8px; color: var(--accent); font-size: 38px; line-height: 1.1; font-weight: 650; }
.review-stat strong { color: #96551b; }
.summary small { font-size: 17px; color: var(--text-primary); font-weight: 400; }
.summary p { margin: 10px 0 0; font-size: 15px; color: var(--text-secondary); line-height: 1.6; }
.coach-controls { padding: 24px; background: #fff; border-radius: 16px; }
.coach-controls h2 { margin: 0 0 10px; font-size: 21px; }
.coach-controls p { margin: 0; color: var(--text-secondary); font-size: 16px; line-height: 1.7; }
.coach-controls form { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 18px; font-size: 16px; }
.coach-controls form label { width: 100%; }
.coach-controls input { width: 85px; min-height: 46px; padding: 10px; background: var(--bg-elevated); color: var(--text-primary); border: 1px solid var(--border-default); border-radius: 9px; }
.coach-controls button { width: 100%; min-height: 46px; margin-top: 4px; background: var(--accent); color: #fff; border: 0; border-radius: 9px; }
.coach-controls .deferred-note { margin-top: 12px; color: var(--warning); }
.queue { margin-top: 26px; padding: 26px; background: #fff; border-radius: 16px; scroll-margin-top: 20px; }
.section-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; padding-bottom: 20px; }
.section-head h2 { margin: 0; font-size: 24px; }
.section-head > span { color: var(--text-secondary); font-size: 15px; }
.task-card { display: grid; grid-template-columns: 42px minmax(0, 1fr); gap: 16px; padding: 24px 0; border-top: 1px solid var(--border-subtle); }
.task-card:last-child { padding-bottom: 0; }
.order { display: grid; place-items: center; width: 40px; height: 44px; border-radius: 10px; background: var(--accent-soft); color: var(--accent); font-weight: 600; }
.task-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; font-size: 15px; color: var(--text-secondary); }
.task-meta em { font-style: normal; }
.task-meta b { color: var(--warning); font-weight: 600; }
.task-main { min-width: 0; }
.task-main h3 { margin: 12px 0 8px; font-size: 21px; line-height: 1.5; overflow-wrap: anywhere; }
.task-main > p { margin: 0; font-size: 16px; line-height: 1.7; color: var(--text-secondary); }
.task-main ul { margin: 12px 0 0; padding-left: 20px; color: var(--text-secondary); font-size: 16px; line-height: 1.8; }
.reorder-actions { display: flex; gap: 8px; float: right; }
.reorder-actions button { min-width: 44px; min-height: 44px; border: 0; border-radius: 8px; color: var(--text-secondary); background: var(--bg-elevated); font-size: 15px; }
.task-action { grid-column: 2; }
.task-action button, .task-action a, .retry button { display: inline-flex; align-items: center; justify-content: center; min-height: 46px; padding: 10px 18px; border: 0; border-radius: 10px; background: var(--accent); color: #fff; text-decoration: none; font-size: 17px; }
.retry { display: flex; gap: 10px; margin-top: 18px; }
.retry label { flex: 1; min-width: 0; }
.retry input { width: 100%; min-height: 46px; padding: 10px 12px; background: var(--bg-elevated); border: 1px solid var(--border-default); border-radius: 10px; color: var(--text-primary); }
.feedback, .hint { margin-top: 12px !important; color: var(--accent) !important; }
.empty { margin-top: 26px; padding: 48px 28px; border-radius: 16px; background: #fff; text-align: center; }
.empty > span { color: var(--accent); font-size: 30px; }
.empty h2 { margin: 16px 0 10px; font-size: 24px; }
.empty p { color: var(--text-secondary); line-height: 1.8; }
.empty > div { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; margin-top: 20px; }
.empty a { display: inline-flex; align-items: center; min-height: 46px; padding: 10px 16px; border-radius: 10px; background: var(--accent); color: #fff; text-decoration: none; }
.empty a.secondary { background: var(--accent-soft); color: var(--accent); }
.state { padding: 80px 20px; text-align: center; color: var(--text-secondary); }
button:disabled { opacity: .5; cursor: default; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
@media(max-width: 1180px) { .today-layout { grid-template-columns: minmax(0,1fr) 280px; gap: 20px; } .day-welcome { padding: 26px; } .day-motif { width: 160px; } .summary article { padding: 20px; gap: 12px; } }
@media(max-width: 1050px) { .today-layout { grid-template-columns: 1fr; } .today-aside { grid-template-columns: 1fr 1fr; } .summary { grid-template-columns: repeat(3,minmax(0,1fr)); grid-column: 1 / -1; } .summary article { flex-direction: column; } .coach-controls { grid-column: 1 / -1; } .coach-controls form { flex-wrap: nowrap; } .coach-controls form label, .coach-controls button { width: auto; } .coach-controls button { margin: 0; } .day-motif { width: 240px; } }
@media(max-width: 600px) { .hero { align-items: start; gap: 14px; } .hero h1 { font-size: 30px; } .hero p { font-size: 15px; line-height: 1.7; } .hero > button { flex-shrink: 0; font-size: 15px; padding-inline: 10px; } .day-welcome { padding: 26px 22px; min-height: 215px; } .day-welcome h2 { font-size: 27px; } .day-motif { display: none; } .day-welcome p { max-width: none; } .summary { grid-template-columns: 1fr; gap: 12px; } .summary article { flex-direction: row; } .today-aside { grid-template-columns: 1fr; } .coach-controls form { flex-wrap: wrap; } .coach-controls form label { width: 100%; } .queue { padding: 22px 18px; } .task-card { grid-template-columns: 1fr; } .order { display: none; } .task-action { grid-column: auto; } .retry { flex-direction: column; } .reorder-actions { float: none; margin-top: 10px; } .coach-controls { padding: 22px; } }
</style>
