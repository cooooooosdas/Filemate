<template>
  <main class="action-workspace" :aria-busy="state.phase === 'loading' || busy">
    <header class="action-heading workspace-refined-heading"><span class="workspace-heading-icon" aria-hidden="true"><Calendar :size="27" /></span><div><h1>今日行动</h1><p>{{ presentation?.goal_title ?? '先选一个目标，再决定今天的一步。' }}</p><p v-if="state.snapshot" class="action-meta">{{ state.snapshot.snapshot.study_date }} · {{ presentation?.scope_label }}</p></div><button v-if="trialEnabled && state.snapshot" ref="weeklyTrigger" type="button" :disabled="busy || reading || coachOpen || weeklyOpen" @click="weeklyOpen = true">本周复盘</button><button type="button" :disabled="busy || reading || coachOpen || weeklyOpen" @click="refresh">{{ reading ? '正在读取…' : '刷新真实记录' }}</button></header>
    <WeeklyReflection v-if="weeklyOpen && state.snapshot && state.identity" ref="weeklyPanel" :scope="state.snapshot.snapshot.scope" :identity="state.identity" :bundle="state.snapshot" @close="closeWeekly" @coach="coachFromReflection" />
    <CoachPanel v-if="coachOpen && coachInput && state.identity" ref="coachPanel" :input="coachInput" :identity="state.identity" :goal-type="coachGoalType" :refresh="workspace.refresh" @close="closeCoach" @busy="coachBusy = $event" />
    <div v-if="state.error" role="alert" class="action-alert"><p>{{ state.error }}</p><button v-if="['expired', 'error'].includes(state.phase)" type="button" @click="initialize">重新读取当前账号</button></div>
    <p v-if="state.phase === 'loading'" role="status">正在读取当前账号与已保存安排…</p>
    <template v-if="state.phase === 'ready' && state.identity">
      <div class="action-layout" :class="{ 'is-unconfigured': !state.snapshot }" :inert="coachOpen || weeklyOpen || undefined">
        <section v-if="state.snapshot && presentation" class="action-paper action-next" aria-labelledby="next-action-heading"><p class="action-eyebrow">接下来做什么</p><template v-if="presentation.next_task"><h2 id="next-action-heading">{{ presentation.next_task.title }}</h2><p>{{ presentation.next_task.reason }}</p><p class="action-meta">预计 {{ presentation.next_task.estimated_minutes ?? '待核对' }} 分钟，并非实际学习时长</p><RouterLink v-if="nextDestination?.primary && canOpen(nextDestination.primary.path)" class="action-primary" :to="nextDestination.primary">{{ nextDestination.primary.label }}<ArrowRight :size="20" aria-hidden="true" /></RouterLink><p v-else>{{ nextDestination?.primary ? '对应功能当前关闭，可调整安排或查看来源。' : nextDestination?.notice }}</p></template><template v-else><h2 id="next-action-heading">给今天留出一段时间</h2><p>预览候选、核对依据，确认后再从原任务开始。</p><button type="button" @click="startEditing">调整本次安排<ArrowRight :size="20" aria-hidden="true" /></button></template><p v-if="state.day?.stale_refs.length" class="action-status">原安排有失效记录。原数据保留，请刷新后重新预览。</p></section>
        <section v-else class="action-paper action-next action-intro"><span class="action-intro-icon" aria-hidden="true"><Calendar :size="32" /></span><h2>让今天，有一个清楚的开始。</h2><p>选好目标，再安排你愿意投入的时间。</p><ol class="action-onboarding"><li><strong>选择目标</strong><span>明确这次要学什么</span></li><li><strong>安排时间</strong><span>根据可用时间挑选任务</span></li><li><strong>预览后确认</strong><span>核对依据，再保存安排</span></li></ol><RouterLink to="/goals" class="action-link">还没有目标？先创建目标<ArrowRight :size="20" aria-hidden="true" /></RouterLink></section>
        <div class="action-settings"><TodayScope :client="client" :identity="state.identity" :active="state.snapshot?.snapshot.scope ?? null" :title="presentation?.goal_title ?? ''" :busy="busy || reading" @scope="selectScope" />
          <section v-if="state.draft && state.snapshot" class="action-paper action-budget" aria-labelledby="action-budget-heading"><h2 id="action-budget-heading">今天愿意投入多久</h2><label class="action-budget-label">可用时间（分钟）<input :value="state.draft.options.available_minutes" type="number" min="0" max="1440" step="1" :disabled="busy || reading" @change="setBudget(($event.target as HTMLInputElement).valueAsNumber)"></label><p class="action-help">0分钟也可预览，不能把预计时长当作实际学习时间。</p><button v-if="coachEnabled" ref="coachTrigger" type="button" :disabled="busy || reading" @click="openCoach()">请教学习教练<ArrowRight :size="20" aria-hidden="true" /></button>
            <div class="action-mode-buttons" aria-label="学习场景"><button v-for="item in modes" :key="item.value" type="button" :aria-pressed="mode === item.value" :disabled="busy || !allowedModes.includes(item.value)" @click="setMode(item.value)">{{ item.label }}</button></div><p v-if="!allowedModes.includes('exam')" class="action-help">当前未选有有效日期的考试目标，考前冲刺暂不可选。</p><p class="action-help">{{ modeDescription }}</p>
            <button type="button" class="action-primary" :disabled="busy || reading" @click="preview">{{ state.write_status === 'previewing' ? '正在预览…' : '预览本次安排' }}<ArrowRight :size="20" aria-hidden="true" /></button><button v-if="!editing" type="button" :disabled="busy" @click="startEditing">调整顺序与时长</button>
          </section>
          <TodayPreview v-if="state.snapshot || state.pending || state.receipt" :state="state" :busy="busy || reading" @confirm="commands.confirm" @recover="commands.recover" @preview-undo="commands.previewUndo" @confirm-undo="commands.confirmUndo" @cancel-undo="commands.invalidate" />
          <TodayFeedback v-if="state.snapshot && presentation" :bundle="state.snapshot" :presentation="presentation" />
        </div>
        <div v-if="state.snapshot && state.draft" class="action-main">
          <p v-if="state.day?.scope && state.day.scope.goal_id !== state.snapshot.snapshot.scope.goal_id" class="action-status">已保存安排属于另一个目标。当前读取不会修改它；确认新预览后才更换今日优先目标。</p>
          <TodayTasks :tasks="editing ? pendingTasks : savedTasks" :bundle="state.snapshot" :options="editing ? state.draft.options : undefined" :editable="editing" :busy="busy || reading" :can-open="canOpen" @options="setOptions" />
          <button v-if="editing && savedTasks.length && !state.dirty" type="button" @click="editing = false">返回已保存安排</button>
        </div>
      </div>
    </template>
  </main>
</template>
<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ArrowRight, Calendar } from '../../icons'
import { getGraphCourse, listGraphCourses } from '../../services/api'
import { getOrchestratorBrowserScope } from '../../services/orchestrator-api'
import type { OrchestratorCapabilities, OrchestratorClient, ScheduleOptions, ScopeRequest } from '../../types/orchestrator'
import type { CoachInput } from '../../types/learning-coach'
import type { TodayMode, TodayStorage } from '../../types/today'
import { availableTools } from '../../navigation/catalog'
import { createTodayWorkspace } from '../../today/workspace-state'
import { createTodayCommands } from '../../today/command-state'
import { createTodayPreferences, createTodayStorage } from '../../today/preferences'
import { presentToday } from '../../today/presentation'
import { resolveTodayTask, todayTargetAvailable } from '../../today/navigation'
import { todayModes } from '../../today/entry-state'
import TodayScope from './TodayScope.vue'
import TodayTasks from './TodayTasks.vue'
import TodayPreview from './TodayPreview.vue'
import TodayFeedback from './TodayFeedback.vue'
import '../../today/today.css'
const props = defineProps<{ client: OrchestratorClient; capabilities: OrchestratorCapabilities }>()
function browserStorage(area: 'localStorage' | 'sessionStorage'): TodayStorage { return { getItem: key => window[area].getItem(key), setItem: (key, value) => window[area].setItem(key, value), removeItem: key => window[area].removeItem(key) } }
const storage = createTodayStorage(browserStorage('localStorage'), browserStorage('sessionStorage'))
const workspace = createTodayWorkspace({ client: props.client, getCourseBrowserScope: getOrchestratorBrowserScope, getGraphCourse, listGraphCourses }, storage, Date.now, value => reactive(value))
const state = workspace.state, commands = createTodayCommands(props.client, state, storage, workspace.refresh)
const editing = ref(true), reading = ref(false), mode = ref<TodayMode>('daily')
const coachEnabled = import.meta.env.VITE_ENABLE_LEARNING_COACH === 'true'
const trialEnabled = import.meta.env.VITE_ENABLE_TRIAL_WORKSPACE === 'true'
const weeklyOpen = ref(false), weeklyTrigger = ref<HTMLElement | null>(null), weeklyPanel = ref<{ needsLeaveConfirmation(): boolean; invalidate(): void } | null>(null)
const WeeklyReflection = defineAsyncComponent(() => import('./WeeklyReflection.vue'))
async function closeWeekly() { weeklyOpen.value = false; await nextTick(); weeklyTrigger.value?.focus() }
function coachFromReflection(value: { record_id: string; notes: string }) { if (!coachEnabled) { state.error = '当前版本的学习教练暂未启用，复盘已保存。'; return }; weeklyOpen.value = false; openCoach(value) }
const coachOpen = ref(false), coachBusy = ref(false), coachInput = ref<CoachInput | null>(null), coachTrigger = ref<HTMLElement | null>(null)
const coachPanel = ref<{ needsLeaveConfirmation(): boolean; invalidate(): void } | null>(null)
const CoachPanel = defineAsyncComponent({ loader: () => import('./CoachPanel.vue'), timeout: 15000, onError(_error, _retry, fail) { coachOpen.value = false; state.error = '教练界面暂时无法加载，请保留原安排并重新打开。'; fail() } })
const coachGoalType = computed(() => (state.snapshot?.snapshot.facts.goal as { goal_type?: string } | undefined)?.goal_type ?? null)
function openCoach(reflection?: { record_id: string; notes: string }) { if (coachOpen.value || !state.snapshot || !state.draft) return; coachInput.value = JSON.parse(JSON.stringify({ scope: state.snapshot.snapshot.scope, selection: { interview_ids: [], submission_ids: [], concept_ids: [], wrong_ids: [], feedback_refs: [], position_id: null, requirement_indices: [] }, reflection_id: reflection?.record_id ?? null, intent: reflection ? 'next_step' : 'budget', question: reflection?.notes ?? `我今天只有${state.draft.options.available_minutes}分钟，先做什么？`, days: [{ study_date: state.snapshot.snapshot.study_date, options: state.draft.options }] })) as CoachInput; coachOpen.value = true }
async function closeCoach() { coachOpen.value = false; coachInput.value = null; coachBusy.value = false; await nextTick(); coachTrigger.value?.focus() }
const busy = computed(() => coachBusy.value || ['previewing', 'confirming', 'undoing'].includes(state.write_status))
const presentation = computed(() => state.snapshot ? presentToday(state.snapshot, state.day) : null)
const nextDestination = computed(() => state.snapshot && presentation.value?.next_task ? resolveTodayTask(presentation.value.next_task, state.snapshot) : null)
const pendingTasks = computed(() => state.snapshot?.projection.tasks.filter(task => task.status === 'pending') ?? [])
const scopeKey = (scope: ScopeRequest) => JSON.stringify([scope.goal_id, scope.course_id ?? null, [...scope.source_ids ?? []].sort()])
const savedTasks = computed(() => {
  if (!state.snapshot || !state.day?.scope || scopeKey(state.day.scope) !== scopeKey(state.snapshot.snapshot.scope)) return []
  return state.day.selected.flatMap(saved => { const current = pendingTasks.value.find(task => task.task_id === saved.task_id && task.eligibility === 'eligible'); return current ? [{ ...current, estimated_minutes: saved.estimated_minutes, estimate_source: saved.estimate_source }] : [] })
})
const paths = new Set(availableTools(import.meta.env).map(tool => tool.path)), canOpen = (path: string) => todayTargetAvailable(path, paths, import.meta.env.VITE_ENABLE_COURSE_GRAPH === 'true')
const modes: { value: TodayMode; label: string }[] = [{ value: 'daily', label: '日常学习' }, { value: 'exam', label: '考前冲刺' }, { value: 'project', label: '项目／能力训练' }]
const allowedModes = computed(() => todayModes(state.snapshot?.snapshot.facts.goal, state.snapshot?.snapshot.study_date ?? ''))
const modeDescription = computed(() => mode.value === 'exam' ? '围绕当前考试目标行动，完成后回原题验证。' : mode.value === 'project' ? '围绕当前目标执行训练，选题与评价仍在原功能完成。' : '按自己的可用时间，逐项完成有依据的任务。')
let preferences: ReturnType<typeof createTodayPreferences> | null = null, disposed = false
watch(() => state.identity, identity => { preferences?.clearMemory(); preferences = identity ? createTodayPreferences(storage, identity) : null; mode.value = preferences?.read().mode ?? 'daily' })
watch(allowedModes, values => { if (!values.includes(mode.value)) mode.value = 'daily' })
watch(() => state.write_status, value => { if (value === 'saved' && !state.dirty) editing.value = false })
function setMode(value: TodayMode) { if (allowedModes.value.includes(value)) { mode.value = value; preferences?.write({ mode: value, last_goal_id: state.snapshot?.snapshot.scope.goal_id ?? null }) } }
function setOptions(value: ScheduleOptions) { try { commands.invalidate(); workspace.setOptions(value); editing.value = true } catch (error) { state.error = error instanceof Error ? error.message : '调整无效，请核对输入。' } }
function setBudget(value: number) { if (state.draft) setOptions({ ...state.draft.options, available_minutes: value }) }
function startEditing() { editing.value = true }
async function selectScope(scope: ScopeRequest) { if (state.dirty && !window.confirm('当前安排调整尚未保存。要放弃草稿并读取另一范围吗？')) return; commands.invalidate(); reading.value = true; try { await workspace.selectScope(scope); if (!disposed && state.snapshot) { editing.value = true; preferences?.write({ mode: mode.value, last_goal_id: scope.goal_id }) } } finally { if (!disposed) reading.value = false } }
async function initialize() { reading.value = true; try { await workspace.initialize(props.capabilities); if (!disposed && state.identity) await commands.recover() } finally { if (!disposed) reading.value = false } }
async function refresh() { if (busy.value || reading.value) return; commands.invalidate(); reading.value = true; try { await workspace.refresh() } finally { if (!disposed) reading.value = false } }
async function preview() { await commands.preview() }
function invalidate() { weeklyPanel.value?.invalidate(); weeklyOpen.value = false; coachPanel.value?.invalidate(); coachOpen.value = false; coachInput.value = null; coachBusy.value = false; commands.invalidate(); workspace.resetIdentity() }
async function visible() { if (document.visibilityState !== 'visible' || await commands.checkDayBoundary()) return; if (document.visibilityState === 'visible' && !busy.value && !reading.value && !state.dirty && !state.preview && !state.undo_preview && state.phase === 'ready') void refresh() }
let dayTimer: ReturnType<typeof setTimeout>
function scheduleDayCheck() { dayTimer = setTimeout(async () => { await commands.checkDayBoundary(); if (!disposed) scheduleDayCheck() }, 86400000 - (Date.now() + 28800000) % 86400000 + 10) }
function unload(event: BeforeUnloadEvent) { if (state.dirty || state.pending || busy.value || (coachPanel.value?.needsLeaveConfirmation() || weeklyPanel.value?.needsLeaveConfirmation())) { event.preventDefault(); event.returnValue = '' } }
onBeforeRouteLeave(() => !(state.dirty || state.pending || busy.value || (coachPanel.value?.needsLeaveConfirmation() || weeklyPanel.value?.needsLeaveConfirmation())) || window.confirm(state.pending || busy.value ? '保存结果尚待核验，原请求编号会保留。确认离开今日行动吗？' : '当前安排或教练候选内容尚未保存，确认离开吗？'))
onMounted(() => { void initialize(); scheduleDayCheck(); document.addEventListener('visibilitychange', visible); window.addEventListener('filemate:review-changed', visible); window.addEventListener('filemate:today-invalidated', invalidate); window.addEventListener('beforeunload', unload) })
onBeforeUnmount(() => { disposed = true; clearTimeout(dayTimer); commands.dispose(); workspace.dispose(); preferences?.clearMemory(); document.removeEventListener('visibilitychange', visible); window.removeEventListener('filemate:review-changed', visible); window.removeEventListener('filemate:today-invalidated', invalidate); window.removeEventListener('beforeunload', unload) })
</script>
