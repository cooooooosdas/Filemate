<template>
  <div class="goal-planner-page">
    <header class="goal-hero">
      <div>
        <h1>目标反推</h1>
        <p class="lead">写下想完成的事，结合已有资料和练习记录，安排下一步。</p>
      </div>
    </header>

    <section class="create-panel">
      <div class="section-heading">
        <div><h2>新建目标</h2></div>
        <p>设好截止日期，选上相关资料。</p>
      </div>
      <div class="goal-form">
        <label class="title-field">
          <span>目标名称</span>
          <input v-model.trim="form.title" name="goal_title" maxlength="160" placeholder="例如：准备好下周的竞赛答辩" />
        </label>
        <label>
          <span>目标类型</span>
          <select v-model="form.goal_type" name="goal_type">
            <option value="competition">竞赛答辩</option>
            <option value="exam">课程考试</option>
            <option value="job">求职面试</option>
            <option value="postgraduate">保研复试</option>
            <option value="custom">自定义目标</option>
          </select>
        </label>
        <label>
          <span>截止日期</span>
          <input v-model="form.deadline" name="goal_deadline" type="date" :min="today" />
        </label>
        <label>
          <span>目标分数 <i>可选</i></span>
          <input v-model.number="form.target_score" name="target_score" type="number" min="0" max="100" placeholder="80" />
        </label>
        <label class="source-field">
          <span>目标依据资料 <i>可选</i></span>
          <select v-model="form.source_id" name="goal_source">
            <option value="">不指定资料</option>
            <option v-for="source in sources" :key="source.source_id" :value="source.source_id">{{ source.original_name }}</option>
          </select>
        </label>
        <button type="button" class="create-button" :disabled="creating || !canCreate" @click="createGoal">
          {{ creating ? '正在读取本地记录…' : '安排下一步' }}
        </button>
      </div>
    </section>

    <DataState v-if="error" :error="error" @retry="load" />
    <div v-else-if="loading" class="loading-state" aria-live="polite">正在读取目标和学习记录…</div>

    <template v-else-if="activeGoal">
      <section class="goal-toolbar">
        <div>
          <span class="goal-type">{{ goalTypeLabel(activeGoal.goal_type) }}</span>
          <h2>{{ activeGoal.title }}</h2>
          <p>截止 {{ formatDate(activeGoal.deadline) }}<template v-if="activeGoal.source_name"> · 依据《{{ activeGoal.source_name }}》</template></p>
        </div>
        <div class="toolbar-actions">
          <label v-if="goals.length > 1">
            <span>历史目标</span>
            <select v-model="activeGoalId" name="goal_history">
              <option v-for="goal in goals" :key="goal.goal_id" :value="goal.goal_id">{{ goal.title }}</option>
            </select>
          </label>
          <button type="button" :disabled="replanning" @click="replan">
            {{ replanning ? '重新读取中…' : '根据最新进度重排' }}
          </button>
        </div>
      </section>

      <LearningPath :goal="activeGoal" :updating-task="updatingTask" @toggle="toggleTask" />

      <section class="evidence-layout">
        <article class="evidence-panel">
          <div class="section-heading compact">
            <div><span>02</span><h2>现有学习记录</h2></div>
            <b :class="activeGoal.evidence_status">{{ activeGoal.evidence_status === 'ready' ? '记录充足' : '记录较少 · 待评测' }}</b>
          </div>
          <div class="metric-grid">
            <div><strong>{{ activeGoal.evidence_snapshot.source_count }}</strong><span>本地资料</span></div>
            <div><strong>{{ activeGoal.evidence_snapshot.quiz_attempt_count }}</strong><span>练习作答</span></div>
            <div><strong>{{ activeGoal.evidence_snapshot.pending_wrong_count }}</strong><span>待复习错题</span></div>
            <div><strong>{{ activeGoal.evidence_snapshot.interview_count }}</strong><span>模拟面试</span></div>
          </div>
          <p class="evidence-note">这里只汇总已保存到本机的行为记录。样本不足时不会生成掌握度、趋势或虚假准确率。</p>
        </article>

        <article class="gap-panel">
          <div class="section-heading compact">
            <div><span>03</span><h2>能力差距诊断</h2></div>
            <b>{{ openGapCount }} 项待提升</b>
          </div>
          <div class="gap-list">
            <article v-for="gap in activeGoal.gaps" :key="gap.name" :class="gap.status">
              <span class="gap-status">{{ gap.status === 'ready' ? '已具备' : '待提升' }}</span>
              <div class="gap-copy">
                <strong>{{ gap.name }}</strong>
                <p><span>{{ gap.current }}</span><i aria-hidden="true">→</i><span>{{ gap.target }}</span></p>
                <small>{{ gap.evidence }}</small>
              </div>
            </article>
          </div>
        </article>
      </section>

      <section class="tasks-panel">
        <div class="section-heading compact">
          <div><span>04</span><h2>下一步行动</h2></div>
          <b>{{ completedCount }}/{{ activeGoal.tasks.length }} 已完成</b>
        </div>
        <div class="progress" role="progressbar" :aria-valuenow="completionRate" aria-valuemin="0" aria-valuemax="100">
          <span :style="{ width: `${completionRate}%` }" />
        </div>
        <div class="task-list">
          <article v-for="(task, index) in activeGoal.tasks" :key="task.task_id" :class="{ completed: task.status === 'completed' }">
            <button type="button" class="task-check" :aria-label="task.status === 'completed' ? '标记为未完成' : '标记为已完成'" :disabled="updatingTask === task.task_id" @click="toggleTask(task)">
              {{ task.status === 'completed' ? '✓' : String(index + 1).padStart(2, '0') }}
            </button>
            <div class="task-copy"><strong>{{ task.title }}</strong><p>{{ task.reason }}</p></div>
            <time :datetime="task.due_date">{{ formatDate(task.due_date) }} 前</time>
            <button type="button" class="task-link" @click="router.push(task.route === '/ai-tools' && activeGoal.source_id ? { path: task.route, query: { source: activeGoal.source_id } } : task.route)">去完成</button>
          </article>
        </div>
      </section>
    </template>

    <section v-else class="empty-state">
      <span>从终点开始</span>
      <h2>还没有目标反推记录</h2>
      <p>填写上方目标后，系统会用你已有的真实学习行为生成第一版行动路径。</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import DataState from '../components/DataState.vue'
import LearningPath from '../components/LearningPath.vue'
import {
  createReverseGoal,
  getKnowledgeSources,
  getReverseGoals,
  replanReverseGoal,
  updateReverseGoalTask,
  type KnowledgeSource,
  type ReverseGoalPlan,
  type ReverseGoalTask,
  type ReverseGoalType
} from '../services/api'

const isoDate = (value: Date) => {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const router = useRouter()
const today = isoDate(new Date())
const defaultDeadline = new Date()
defaultDeadline.setDate(defaultDeadline.getDate() + 30)
const loading = ref(true)
const creating = ref(false)
const replanning = ref(false)
const updatingTask = ref('')
const error = ref('')
const sources = ref<KnowledgeSource[]>([])
const goals = ref<ReverseGoalPlan[]>([])
const activeGoalId = ref('')
const form = ref<{ title: string; goal_type: ReverseGoalType; deadline: string; target_score: number | null; source_id: string }>({
  title: '',
  goal_type: 'competition',
  deadline: isoDate(defaultDeadline),
  target_score: null,
  source_id: ''
})

const activeGoal = computed(() => goals.value.find(goal => goal.goal_id === activeGoalId.value) || null)
const canCreate = computed(() => form.value.title.length >= 2 && form.value.deadline >= today)
const completedCount = computed(() => activeGoal.value?.tasks.filter(task => task.status === 'completed').length || 0)
const completionRate = computed(() => activeGoal.value?.tasks.length ? Math.round(completedCount.value / activeGoal.value.tasks.length * 100) : 0)
const openGapCount = computed(() => activeGoal.value?.gaps.filter(gap => gap.status === 'gap').length || 0)

const formatDate = (value: string) => new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric' }).format(new Date(`${value}T00:00:00`))
const goalTypeLabel = (type: ReverseGoalType) => ({ exam: '课程考试', competition: '竞赛答辩', job: '求职面试', postgraduate: '保研复试', custom: '自定义目标' }[type])

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const [sourceList, goalList] = await Promise.all([getKnowledgeSources(), getReverseGoals()])
    sources.value = sourceList
    goals.value = goalList
    if (!activeGoalId.value || !goalList.some(goal => goal.goal_id === activeGoalId.value)) activeGoalId.value = goalList[0]?.goal_id || ''
  } catch (cause: any) {
    error.value = cause?.message || '目标与证据加载失败'
  } finally {
    loading.value = false
  }
}

async function createGoal(): Promise<void> {
  if (!canCreate.value) return
  creating.value = true
  try {
    const goal = await createReverseGoal({
      ...form.value,
      target_score: form.value.target_score || null,
      source_id: form.value.source_id || null
    })
    goals.value = [goal, ...goals.value]
    activeGoalId.value = goal.goal_id
    ElMessage.success('已依据本地证据生成反推路径')
  } catch (cause: any) {
    ElMessage.error(cause?.message || '目标反推失败')
  } finally {
    creating.value = false
  }
}

async function toggleTask(task: ReverseGoalTask): Promise<void> {
  if (!activeGoal.value) return
  updatingTask.value = task.task_id
  try {
    const goal = await updateReverseGoalTask(activeGoal.value.goal_id, task.task_id, task.status !== 'completed')
    replaceGoal(goal)
  } catch (cause: any) {
    ElMessage.error(cause?.message || '任务状态保存失败')
  } finally {
    updatingTask.value = ''
  }
}

async function replan(): Promise<void> {
  if (!activeGoal.value) return
  replanning.value = true
  try {
    const goal = await replanReverseGoal(activeGoal.value.goal_id)
    replaceGoal(goal)
    ElMessage.success('已读取最新证据并保留已完成任务')
  } catch (cause: any) {
    ElMessage.error(cause?.message || '重新规划失败')
  } finally {
    replanning.value = false
  }
}

function replaceGoal(goal: ReverseGoalPlan): void {
  const index = goals.value.findIndex(item => item.goal_id === goal.goal_id)
  if (index >= 0) goals.value.splice(index, 1, goal)
  else goals.value.unshift(goal)
}

onMounted(load)
</script>

<style scoped>
.goal-planner-page { max-width: 1480px; margin: 0 auto; padding: 12px 18px 64px; color: var(--text-primary); }
.goal-hero { position: relative; display: grid; grid-template-columns: minmax(0, 1fr) 210px; gap: 40px; align-items: center; min-height: 270px; padding: 44px 50px; overflow: hidden; border: 1px solid rgba(31, 111, 235, .16); border-radius: 32px; background: linear-gradient(115deg, #f6fbff 0%, #edf7ff 52%, #effaf6 100%); box-shadow: 0 24px 60px rgba(30, 73, 120, .08); }
.goal-hero::before { content: ''; position: absolute; width: 460px; height: 460px; right: -170px; top: -270px; border: 70px solid rgba(37, 99, 235, .07); border-radius: 50%; }
.goal-hero::after { content: ''; position: absolute; left: 48px; bottom: 0; width: 42%; height: 4px; background: linear-gradient(90deg, #2563eb, #43aa8b, transparent); }
.eyebrow { margin: 0 0 12px; color: #2468d7; font-size: 12px; font-weight: 800; letter-spacing: .14em; }
.goal-hero h1 { max-width: 850px; margin: 0 0 16px; font-size: clamp(34px, 4.5vw, 62px); line-height: 1.07; letter-spacing: -.055em; }
.goal-hero h1 em { color: #247f75; font-style: normal; }
.lead { max-width: 760px; margin: 0; color: var(--text-secondary); font-size: 16px; line-height: 1.8; }
.evidence-seal { z-index: 1; display: grid; place-content: center; width: 176px; aspect-ratio: 1; justify-self: end; text-align: center; border: 1px solid rgba(36, 127, 117, .35); border-radius: 50%; background: rgba(255,255,255,.75); box-shadow: inset 0 0 0 10px rgba(36,127,117,.05), 0 16px 40px rgba(36,127,117,.1); }
.evidence-seal span, .evidence-seal small { color: #4c7771; font-size: 10px; letter-spacing: .1em; }
.evidence-seal strong { margin: 6px 0; color: #176d64; font-size: 25px; }
.create-panel, .evidence-panel, .gap-panel, .tasks-panel { margin-top: 22px; padding: 28px; border: 1px solid #e0e9ef; border-radius: 24px; background: rgba(255,255,255,.94); box-shadow: 0 14px 38px rgba(31,67,95,.055); }
.section-heading { display: flex; justify-content: space-between; gap: 24px; align-items: center; margin-bottom: 22px; }
.section-heading > div { display: flex; align-items: center; gap: 12px; }
.section-heading > div > span { color: #2b72df; font-weight: 850; }
.section-heading h2 { margin: 0; font-size: 22px; }
.section-heading p { margin: 0; color: var(--text-secondary); }
.section-heading.compact { margin-bottom: 18px; }
.section-heading b { padding: 7px 11px; border-radius: 99px; background: #edf5fb; color: #47718f; font-size: 12px; }
.section-heading b.ready { background: #e9f7f1; color: #176d54; }
.section-heading b.insufficient { background: #fff4db; color: #8a6013; }
.goal-form { display: grid; grid-template-columns: minmax(200px, 1.4fr) repeat(3, minmax(145px, .6fr)); gap: 16px; align-items: end; }
.goal-form label, .toolbar-actions label { display: grid; gap: 7px; color: #4c6577; font-size: 13px; font-weight: 700; }
.goal-form label span i { color: #8296a5; font-style: normal; font-weight: 500; }
.goal-form input, .goal-form select, .toolbar-actions select { width: 100%; height: 44px; padding: 0 13px; border: 1px solid #cfdde6; border-radius: 11px; background: #fbfdff; color: var(--text-primary); outline: none; box-sizing: border-box; }
.goal-form input:focus, .goal-form select:focus, .toolbar-actions select:focus { border-color: #2b72df; box-shadow: 0 0 0 3px rgba(43,114,223,.1); }
.source-field { grid-column: span 2; }
.create-button, .toolbar-actions button { min-height: 44px; padding: 0 20px; border: 0; border-radius: 11px; background: #175fba; color: white; font-weight: 750; cursor: pointer; }
button:disabled { cursor: not-allowed; opacity: .55; }
.loading-state, .empty-state { margin-top: 22px; padding: 70px 24px; text-align: center; border: 1px dashed #cbdce7; border-radius: 24px; color: var(--text-secondary); background: #f9fcfe; }
.empty-state span { color: #247f75; font-size: 12px; font-weight: 800; letter-spacing: .12em; }
.empty-state h2 { margin: 10px 0; color: var(--text-primary); }
.empty-state p { margin: 0; }
.goal-toolbar { display: flex; justify-content: space-between; gap: 24px; align-items: end; margin-top: 34px; padding: 0 4px; }
.goal-toolbar h2 { margin: 8px 0 4px; font-size: 30px; letter-spacing: -.03em; }
.goal-toolbar p { margin: 0; color: var(--text-secondary); }
.goal-type { color: #247f75; font-size: 12px; font-weight: 800; letter-spacing: .12em; }
.toolbar-actions { display: flex; gap: 12px; align-items: end; }
.toolbar-actions label { min-width: 190px; }
.backcast-rail { display: grid; grid-template-columns: repeat(6, 1fr); margin-top: 20px; overflow: hidden; border: 1px solid #dce8ef; border-radius: 20px; background: #f8fbfd; }
.backcast-rail article { position: relative; min-width: 0; padding: 18px 16px; border-right: 1px solid #dce8ef; }
.backcast-rail article:last-child { border-right: 0; }
.backcast-rail article.current { background: #eaf6f3; }
.backcast-rail article > span { color: #8aa1b1; font-size: 11px; font-weight: 800; }
.backcast-rail article div { display: grid; gap: 5px; margin-top: 7px; }
.backcast-rail strong { font-size: 14px; }
.backcast-rail small { overflow: hidden; color: var(--text-secondary); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.evidence-layout { display: grid; grid-template-columns: minmax(320px, .78fr) minmax(500px, 1.22fr); gap: 22px; }
.metric-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.metric-grid div { display: grid; gap: 3px; padding: 18px; border-radius: 15px; background: #f2f7fa; }
.metric-grid strong { color: #175fba; font-size: 30px; }
.metric-grid span { color: #657d8d; font-size: 12px; }
.evidence-note { margin: 16px 0 0; color: #69808f; font-size: 12px; line-height: 1.7; }
.gap-list { display: grid; gap: 10px; }
.gap-list > article { display: grid; grid-template-columns: 60px 1fr; gap: 14px; padding: 14px; border-left: 3px solid #d49b32; border-radius: 11px; background: #fffaf0; }
.gap-list > article.ready { border-left-color: #36a383; background: #f2faf7; }
.gap-status { align-self: start; padding: 5px 7px; text-align: center; border-radius: 7px; background: rgba(212,155,50,.12); color: #8a6013; font-size: 11px; font-weight: 750; }
.ready .gap-status { background: rgba(54,163,131,.12); color: #176d54; }
.gap-copy strong { font-size: 14px; }
.gap-copy p { display: flex; gap: 9px; align-items: center; margin: 6px 0; color: #38556a; font-size: 13px; }
.gap-copy p i { color: #87a0b1; font-style: normal; }
.gap-copy small { color: #738895; line-height: 1.45; }
.tasks-panel { margin-top: 22px; }
.progress { height: 6px; margin-bottom: 14px; overflow: hidden; border-radius: 99px; background: #e9f0f4; }
.progress span { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #2873de, #36a383); transition: width .3s ease; }
.task-list { display: grid; gap: 8px; }
.task-list article { display: grid; grid-template-columns: 46px minmax(0, 1fr) 100px 84px; gap: 14px; align-items: center; padding: 13px; border: 1px solid #e2ebf0; border-radius: 14px; transition: transform .2s ease, border-color .2s ease; }
.task-list article:hover { transform: translateX(3px); border-color: #b8d2e4; }
.task-list article.completed { background: #f5faf7; }
.task-check { width: 40px; height: 40px; border: 1px solid #b9cedd; border-radius: 12px; background: white; color: #47718f; font-size: 12px; font-weight: 800; cursor: pointer; }
.completed .task-check { border-color: #36a383; background: #36a383; color: white; }
.task-copy strong { font-size: 14px; }
.task-copy p { margin: 4px 0 0; color: var(--text-secondary); font-size: 12px; }
.task-list time { color: #607887; font-size: 12px; }
.task-link { padding: 8px 10px; border: 1px solid #bcd2e1; border-radius: 9px; background: white; color: #175fba; font-weight: 700; cursor: pointer; }
@media (max-width: 1080px) {
  .goal-form { grid-template-columns: repeat(2, 1fr); }
  .title-field, .source-field { grid-column: span 2; }
  .backcast-rail { grid-template-columns: repeat(3, 1fr); }
  .backcast-rail article:nth-child(3) { border-right: 0; }
  .evidence-layout { grid-template-columns: 1fr; }
}
@media (max-width: 720px) {
  .goal-planner-page { padding-inline: 4px; }
  .goal-hero { grid-template-columns: 1fr; padding: 30px 24px; }
  .evidence-seal { display: none; }
  .goal-form { grid-template-columns: 1fr; }
  .title-field, .source-field { grid-column: span 1; }
  .goal-toolbar, .section-heading { align-items: flex-start; flex-direction: column; }
  .toolbar-actions { width: 100%; flex-direction: column; align-items: stretch; }
  .backcast-rail { grid-template-columns: repeat(2, 1fr); }
  .backcast-rail article:nth-child(3) { border-right: 1px solid #dce8ef; }
  .backcast-rail article:nth-child(even) { border-right: 0; }
  .task-list article { grid-template-columns: 44px 1fr; }
  .task-list time, .task-link { grid-column: 2; }
}
</style>
