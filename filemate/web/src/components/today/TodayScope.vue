<template>
  <section class="action-paper action-scope" aria-labelledby="action-scope-heading">
    <h2 id="action-scope-heading">为哪个目标行动</h2>
    <form class="action-search" @submit.prevent="findGoals(0)"><label>查找目标<input v-model="query" maxlength="120" type="search" placeholder="输入目标名称" :disabled="busy"></label><button type="submit" :disabled="busy || searching">查找</button></form>
    <label>今日优先目标<select v-model="goalId" :disabled="busy" @change="chooseGoal"><option value="">请选择目标</option><option v-if="savedChoice && !choices.some(goal => goal.goal_id === savedChoice!.goal_id)" :value="savedChoice.goal_id">{{ savedChoice.title }}</option><option v-for="goal in choices" :key="goal.goal_id" :value="goal.goal_id" :disabled="!goal.valid">{{ goal.title }}{{ goal.valid ? '' : '（记录需修复）' }}</option></select></label>
    <p v-if="choice?.deadline" class="action-meta">目标截止：{{ choice.deadline }}</p><div class="action-controls"><button :disabled="busy || searching || offset === 0" type="button" @click="findGoals(Math.max(0, offset - 30))">上一页目标</button><span>{{ total ? `${offset + 1}—${Math.min(offset + 30, total)} / ${total}` : '暂无目标' }}</span><button :disabled="busy || searching || offset + 30 >= total" type="button" @click="findGoals(offset + 30)">下一页目标</button></div>
    <RouterLink class="action-link" to="/goals">创建或查看目标</RouterLink>
    <details class="action-range" :open="!!courseId"><summary>选择课程与资料范围</summary>
      <form class="action-search" @submit.prevent="findCourses(0)"><label>查找课程<input v-model="courseQuery" maxlength="120" type="search" placeholder="输入课程名称" :disabled="busy"></label><button type="submit" :disabled="busy || coursesLoading">查找课程</button></form>
      <label>关联课程<select v-model="courseId" :disabled="busy" @change="chooseCourse(false)"><option value="">仅目标关联资料</option><option v-if="course && !courses.some(item => item.course_id === course!.course_id)" :value="course.course_id">{{ course.name }}</option><option v-for="item in courses" :key="item.course_id" :value="item.course_id">{{ item.name }}</option></select></label>
      <div class="action-controls"><button type="button" :disabled="busy || coursesLoading || !courseOffset" @click="findCourses(courseOffset - 30)">上一页课程</button><button type="button" :disabled="busy || coursesLoading || courseOffset + 30 >= courseTotal" @click="findCourses(courseOffset + 30)">下一页课程</button></div>
      <p v-if="courseLoading" role="status">正在读取所选课程的资料目录…</p><button v-if="courseId && courseError" type="button" :disabled="busy || courseLoading" @click="chooseCourse(true)">重新读取所选课程</button>
      <fieldset v-if="courseId && course"><legend>只读取勾选的资料（最多20份）</legend><label v-for="source in course.sources?.filter(source => source.active !== 0)" :key="source.source_id" class="action-check"><input v-model="sourceIds" type="checkbox" :value="source.source_id" :disabled="busy || !sourceIds.includes(source.source_id) && sourceIds.length >= 20"><span>{{ source.original_name }}</span></label><p v-if="!course.sources?.some(source => source.active !== 0)">本课程没有可选资料，仍可读取目标任务。</p></fieldset>
      <p v-else-if="choice?.source_id">范围仅为此目标明确关联的一份资料，不读取其他资料。</p><p v-else>此目标未关联资料。仅查看目标任务，不汇总全部资料库。</p>
    </details>
    <p v-if="catalogError" role="alert">{{ catalogError }}</p><p v-if="courseError" role="alert">{{ courseError }}</p>
    <button type="button" class="action-primary" :disabled="busy || !choice?.valid || courseLoading || !!courseId && !course || !!courseId && !!course?.sources?.some(source => source.active !== 0) && !sourceIds.length" @click="readScope">读取所选范围</button>
    <p class="action-help">每次只服务一个明确目标。读取与预览不保存安排。</p>
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { GoalChoice, OrchestratorClient, ScopeRequest } from '../../types/orchestrator'
import type { GraphCourse } from '../../types/courseGraph'
import { getGraphCourse, listGraphCourses } from '../../services/api'
const props = defineProps<{ client: OrchestratorClient; identity: string; active: ScopeRequest | null; title: string; busy: boolean }>()
const emit = defineEmits<{ scope: [value: ScopeRequest] }>()
const query = ref(''), choices = ref<GoalChoice[]>([]), savedChoice = ref<GoalChoice | null>(null), total = ref(0), offset = ref(0), searching = ref(false), catalogError = ref('')
const goalId = ref(''), courseId = ref(''), sourceIds = ref<string[]>([]), courses = ref<GraphCourse[]>([]), course = ref<GraphCourse | null>(null), courseQuery = ref(''), courseOffset = ref(0), courseTotal = ref(0), coursesLoading = ref(false), courseLoading = ref(false), courseError = ref('')
const choice = computed(() => choices.value.find(goal => goal.goal_id === goalId.value) ?? (savedChoice.value?.goal_id === goalId.value ? savedChoice.value : null))
let goalEpoch = 0, courseEpoch = 0, listEpoch = 0, disposed = false
async function findGoals(page: number) {
  const ticket = ++goalEpoch; searching.value = true; catalogError.value = ''
  try { const data = await props.client.getOrchestratorGoalOptions({ q: query.value, offset: page }); if (disposed || ticket !== goalEpoch) return; if (!Array.isArray(data.items) || data.items.length > 30) throw new Error(); choices.value = data.items; total.value = data.total; offset.value = data.offset }
  catch { if (!disposed && ticket === goalEpoch) catalogError.value = '目标目录暂时无法读取，请重新查找。' }
  finally { if (!disposed && ticket === goalEpoch) searching.value = false }
}
async function findCourses(page: number) {
  const ticket = ++listEpoch; coursesLoading.value = true
  try { const data = await listGraphCourses(courseQuery.value, page); if (!disposed && ticket === listEpoch) { courses.value = data.items; courseOffset.value = data.offset; courseTotal.value = data.total } }
  catch { if (!disposed && ticket === listEpoch) courseError.value = '课程目录暂不可用，可重试或选择仅目标关联资料。' }
  finally { if (!disposed && ticket === listEpoch) coursesLoading.value = false }
}
function chooseGoal() { savedChoice.value = choice.value; if (!courseId.value) sourceIds.value = choice.value?.source_id ? [choice.value.source_id] : [] }
async function chooseCourse(keepSources: boolean) {
  const ticket = ++courseEpoch, selected = courseId.value; course.value = null; courseError.value = ''; courseLoading.value = false
  if (!keepSources) sourceIds.value = []
  if (!selected) { if (!keepSources || !sourceIds.value.length) sourceIds.value = choice.value?.source_id ? [choice.value.source_id] : []; return }
  courseLoading.value = true
  try { const data = await getGraphCourse(selected); if (!disposed && ticket === courseEpoch && data.course_id === selected) course.value = data }
  catch { if (!disposed && ticket === courseEpoch) courseError.value = '所选课程无法读取，请重新选择或重试。' }
  finally { if (!disposed && ticket === courseEpoch) courseLoading.value = false }
}
function readScope() { if (choice.value?.valid) emit('scope', { goal_id: goalId.value, course_id: courseId.value || null, source_ids: [...sourceIds.value] }) }
watch(() => JSON.stringify([props.identity, props.active]), () => {
  if (!props.active) return
  goalId.value = props.active?.goal_id ?? ''; courseId.value = props.active?.course_id ?? ''; sourceIds.value = [...props.active?.source_ids ?? []]
  if (goalId.value) savedChoice.value = { goal_id: goalId.value, title: props.title, goal_type: null, deadline: null, source_id: null, valid: true }
  else savedChoice.value = null
  void chooseCourse(true)
}, { immediate: true })
watch(() => props.title, title => { if (goalId.value !== props.active?.goal_id) return; if (savedChoice.value) savedChoice.value.title = title; choices.value = choices.value.map(goal => goal.goal_id === goalId.value ? { ...goal, title } : goal) })
onMounted(() => { void findGoals(0); void findCourses(0) })
onBeforeUnmount(() => { disposed = true; goalEpoch++; courseEpoch++; listEpoch++ })
</script>
