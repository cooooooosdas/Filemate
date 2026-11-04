<template>
  <section
    class="action-paper coach-workspace"
    aria-labelledby="coach-heading"
    :aria-busy="busy"
    @keydown.esc.prevent="close"
  >
    <header class="coach-heading">
      <div>
        <h2 id="coach-heading" ref="heading" tabindex="-1">把下一步想清楚</h2>
        <p>围绕当前目标，先核对依据，再决定是否采纳。</p>
      </div>
      <button type="button" @click="close">关闭教练</button>
    </header>
    <p v-if="loading || state?.phase === 'loading'" role="status">正在核对当前学习范围…</p>
    <p v-if="error || (state?.error && !shown)" role="alert" class="coach-notice">
      {{ error || state?.error }}
    </p>
    <div v-if="workspace && state && form && state.capabilities?.enabled" class="coach-layout">
      <section class="coach-question">
        <h3>这次想解决什么</h3>
        <p>
          本次可用时间：{{
            form.days
              .map((day) => `${day.study_date} · ${day.options.available_minutes}分钟`)
              .join('；')
          }}
        </p>
        <div class="coach-kinds" aria-label="学习请求">
          <button
            v-for="item in intents"
            :key="item.value"
            type="button"
            :disabled="blocked"
            :aria-pressed="form.intent === item.value"
            @click="chooseIntent(item.value)"
          >
            {{ item.label }}
          </button>
        </div>
        <label class="coach-question-label"
          >写下这次的问题<textarea
            :value="form.question"
            rows="3"
            maxlength="2000"
            :disabled="blocked"
            @input="edit({ ...form, question: ($event.target as HTMLTextAreaElement).value })"
          />
        </label>
        <div class="coach-actions">
          <button
            class="action-primary"
            type="button"
            :disabled="blocked || !form.question.trim()"
            @click="rules"
          >
            先用本地规则<ArrowRight :size="20" aria-hidden="true" /></button
          ><button type="button" :disabled="blocked || !form.question.trim()" @click="reviewModel">
            请模型补充建议</button
          ><button v-if="state.pending?.kind === 'request'" type="button" @click="workspace.cancel">
            取消本次生成
          </button>
        </div>
        <p v-if="state.phase === 'running'" role="status">
          正在生成本次建议，可取消。原学习记录保留。
        </p>
        <CoachEvidence
          v-if="client"
          :client="client"
          :input="form"
          :context="fresh ? state.context : null"
          :goal-type="goalType"
          :disabled="blocked"
          @update="edit"
        />
      </section>
      <section class="coach-reading" aria-live="polite">
        <template v-if="shown"
          ><h3 ref="readingHeading" tabindex="-1">{{ shown.model_status }}</h3>
          <p v-if="state.error" role="alert" class="coach-notice">{{ state.error }}</p>
          <RouterLink v-if="state.run?.safe_error_code === 'credentials_missing'" to="/trust"
            >设置模型服务<ArrowRight :size="20" aria-hidden="true"
          /></RouterLink>
          <p v-if="!shown.rule_days.some((day) => day.schedule.selected.length)">
            当前没有可安排的任务。可以补选训练依据，或调整当前目标的预算后再核对。
          </p>
          <section v-for="day in shown.rule_days" :key="day.study_date" class="coach-day">
            <h4>{{ day.study_date }}</h4>
            <p>预计 {{ day.schedule.estimated_minutes ?? '待核对' }} 分钟，是候选估时。</p>
            <ol>
              <li v-for="task in day.schedule.selected" :key="task.task_id">
                <strong>{{ task.title }}</strong>
                <p>{{ task.reason }} · {{ task.estimated_minutes ?? '待核对' }} 分钟</p>
              </li>
            </ol>
          </section>
          <details v-if="shown.methods.length">
            <summary>为什么这样练习</summary>
            <div v-for="(method, index) in shown.methods" :key="index">
              <h4>{{ method.label }}</h4>
              <p>{{ method.text }}</p>
            </div>
          </details>
          <p v-for="notice in shown.coverage_notices" :key="notice" class="coach-notice">
            {{ notice }}
          </p>
          <p v-if="!state.receipt">
            当前为候选建议，尚未写入学习计划。完成训练仍需回到原练习中执行。
          </p></template
        ><template v-else
          ><h3>建议会从这些记录出发</h3>
          <p>
            选择与目标有关的错题、知识点或训练反馈，再用本地规则生成。没有足够证据时会明确说明。
          </p>
          <p>选择模型补充后，先核对外发内容；点击本次授权后才发送。</p></template
        >
      </section>
    </div>
    <CoachProposal
      v-if="state && commands && (state.run || state.pending || state.receipt)"
      :state="state"
      :commands="commands"
      @edit="editProposal"
    />
    <section
      v-if="reviewing && state?.context && client && form"
      class="coach-consent"
      aria-labelledby="coach-consent-heading"
    >
      <h3 id="coach-consent-heading">核对后，只授权这一次</h3>
      <CoachEvidence
        :client="client"
        :input="form"
        :context="state.context"
        :disabled="blocked"
        external
      /><label class="coach-check"
        ><input v-model="allowOnce" type="checkbox" :disabled="blocked" /><span
          >允许将上方列出的本次内容发送给已配置的模型服务，用于补充学习建议。</span
        ></label
      ><button
        class="action-primary"
        type="button"
        :disabled="blocked || !allowOnce || !fresh"
        @click="enhance"
      >
        授权并生成这一次
      </button>
    </section>
  </section>
</template>
<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  shallowRef,
  watch,
} from 'vue'
import { ArrowRight } from '../../icons'
import { loadLearningCoachClient } from '../../services/api'
import { coachError, createCoachWorkspace } from '../../today/coach-state'
import { presentCoach } from '../../today/coach-presentation'
import { createCoachCommands } from '../../today/coach-commands'
import type { CoachDraft } from '../../types/learning-coach'
import type { CoachInput, CoachIntent, LearningCoachClient } from '../../types/learning-coach'
import CoachEvidence from './CoachEvidence.vue'
import CoachProposal from './CoachProposal.vue'

const props = defineProps<{
  input: CoachInput
  identity: string | null
  goalType?: string | null
  refresh: () => Promise<void>
}>()
const emit = defineEmits<{ close: []; busy: [value: boolean] }>()
const workspace = shallowRef<ReturnType<typeof createCoachWorkspace> | null>(null)
const client = shallowRef<LearningCoachClient | null>(null)
const commands = shallowRef<ReturnType<typeof createCoachCommands> | null>(null)
const form = ref<CoachInput | null>(JSON.parse(JSON.stringify(props.input))),
  loading = ref(true),
  error = ref(''),
  reviewing = ref(false),
  allowOnce = ref(false),
  heading = ref<HTMLElement | null>(null),
  readingHeading = ref<HTMLElement | null>(null)
let disposed = false
const state = computed(() => workspace.value?.state)
const busy = computed(
  () => loading.value || state.value?.phase === 'loading' || state.value?.phase === 'running',
)
const blocked = computed(() => busy.value || !!state.value?.pending)
const fresh = computed(
  () =>
    !!state.value?.context &&
    JSON.stringify(form.value) === JSON.stringify(state.value.context.input),
)
const shown = computed(() => (state.value?.run ? presentCoach(state.value.run) : null))
const intents: { value: CoachIntent; label: string }[] = [
  { value: 'budget', label: '安排有限时间' },
  { value: 'exam', label: '准备考试' },
  { value: 'error_cause', label: '复盘最近错题' },
  { value: 'tomorrow', label: '调整明天' },
  { value: 'next_step', label: '决定下一步' },
]
function edit(value: CoachInput) {
  commands.value?.invalidate()
  form.value = JSON.parse(JSON.stringify(value))
  reviewing.value = false
  allowOnce.value = false
  if (state.value) {
    state.value.input = JSON.parse(JSON.stringify(value))
    state.value.preview = null
    state.value.dirty = true
  }
}
function editProposal(value: CoachDraft) {
  commands.value?.invalidate()
  if (state.value && !state.value.pending) {
    state.value.draft = value
    state.value.dirty = true
  }
}
function chooseIntent(value: CoachIntent) {
  if (!form.value) return
  const date = state.value?.context?.snapshot.study_date ?? props.input.days[0]!.study_date
  const day =
    value === 'tomorrow'
      ? new Date(Date.parse(`${date}T00:00:00Z`) + 86400000).toISOString().slice(0, 10)
      : date
  const questions: Record<CoachIntent, string> = {
    budget: `我今天只有${form.value.days[0]!.options.available_minutes}分钟，先做什么？`,
    exam: '为当前考试目标，哪些内容值得优先复习？',
    error_cause: '根据我选中的作答和确认的错因，下一步怎么练习？',
    tomorrow: '帮我调整明天的任务，保留当前学习目标。',
    next_step: '根据已有完成记录，下一步应该做什么？',
  }
  edit({
    ...form.value,
    intent: value,
    question: questions[value],
    days: [{ study_date: day, options: form.value.days[0]!.options }],
  })
}
async function read() {
  if (!workspace.value || !form.value) return false
  await workspace.value.readContext(form.value)
  if (disposed) return false
  if (state.value?.context) form.value = JSON.parse(JSON.stringify(state.value.context.input))
  return state.value?.phase === 'ready' && !!state.value.context
}
async function showOutput() {
  await nextTick()
  if (!disposed && state.value?.run) {
    readingHeading.value?.focus()
    readingHeading.value?.scrollIntoView({ block: 'start', behavior: 'auto' })
  }
}
async function rules() {
  reviewing.value = false
  allowOnce.value = false
  if (await read()) {
    await workspace.value?.submit('rule')
    await showOutput()
  }
}
async function reviewModel() {
  allowOnce.value = false
  reviewing.value = await read()
}
async function enhance() {
  if (!allowOnce.value || !fresh.value) return
  allowOnce.value = false
  await workspace.value?.submit('llm')
  await showOutput()
}
function needsLeaveConfirmation() {
  return !!(state.value?.dirty || state.value?.pending || state.value?.run)
}
function close() {
  if (needsLeaveConfirmation() && !window.confirm('当前教练输入与候选建议尚在本页。确认关闭吗？'))
    return
  workspace.value?.close()
  form.value = null
  emit('close')
}
function invalidate() {
  commands.value?.invalidate()
  workspace.value?.invalidate()
  form.value = null
  allowOnce.value = false
  reviewing.value = false
}
function evidenceChanged() {
  commands.value?.invalidate()
  allowOnce.value = false
  reviewing.value = false
  if (state.value && !state.value.pending)
    state.value.error = '训练记录可能已变化，请重新读取依据并预览。'
}
function visible() {
  if (document.visibilityState === 'visible') evidenceChanged()
}
defineExpose({ needsLeaveConfirmation, invalidate })
watch(busy, (value) => emit('busy', value), { immediate: true })
watch(() => props.identity, invalidate)
watch(
  () => state.value?.phase,
  (phase) => {
    if (phase === 'expired') {
      form.value = null
      allowOnce.value = false
      reviewing.value = false
    }
  },
)
onMounted(async () => {
  try {
    const api = await loadLearningCoachClient()
    if (disposed) return
    client.value = api
    workspace.value = createCoachWorkspace(api, {
      identity: () => props.identity,
      wrap: (value) => reactive(value),
      beforeRequest: (locator) => commands.value!.trackRequest(locator),
      afterRequest: (run) => commands.value!.settleRequest(run),
      requestFailed: (error, locator) => commands.value!.rejectRequest(error, locator),
    })
    commands.value = createCoachCommands(api, {
      state: workspace.value.state,
      storage: {
        getItem: (key) => window.sessionStorage.getItem(key),
        setItem: (key, value) => window.sessionStorage.setItem(key, value),
        removeItem: (key) => window.sessionStorage.removeItem(key),
      },
      refresh: props.refresh,
    })
    await workspace.value.open(props.input)
    if (!disposed && state.value?.input) {
      form.value = JSON.parse(JSON.stringify(state.value.input))
      await commands.value.recover()
    }
  } catch (e) {
    if (!disposed) error.value = coachError(e)
  } finally {
    if (!disposed) {
      loading.value = false
      await nextTick()
      heading.value?.focus()
    }
  }
})
onBeforeUnmount(() => {
  disposed = true
  workspace.value?.close()
  form.value = null
  client.value = null
  emit('busy', false)
})
onMounted(() => {
  window.addEventListener('filemate:review-changed', evidenceChanged)
  document.addEventListener('visibilitychange', visible)
})
onBeforeUnmount(() => {
  commands.value?.invalidate()
  window.removeEventListener('filemate:review-changed', evidenceChanged)
  document.removeEventListener('visibilitychange', visible)
})
</script>
