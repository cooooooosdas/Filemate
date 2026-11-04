<template>
  <section class="coach-proposal" aria-labelledby="coach-proposal-heading">
    <h3 id="coach-proposal-heading" ref="heading" tabindex="-1">
      {{ state.receipt ? '已保存的安排' : '把建议变成可执行安排' }}
    </h3>
    <div v-if="state.pending" class="coach-notice" role="status">
      <p>原请求结果尚待核验。请查询原编号，避免重复保存。</p>
      <button type="button" :disabled="state.phase === 'loading'" @click="commands.recover">
        查询原请求结果
      </button>
    </div>
    <template v-if="state.receipt"
      ><p role="status">
        {{ state.receipt.study_dates.join('、') }} ·
        {{ state.receipt.status === 'undone' ? '已整体撤销' : '已保存' }}
      </p>
      <p>今日与未来日期分别保存；原今日行动草稿保留。任务完成记录仍以原功能为准。</p>
      <RouterLink
        v-if="state.receipt.plan_id && state.receipt.status === 'confirmed'"
        :to="{ path: '/study-plan', query: { plan: state.receipt.plan_id } }"
        >打开已保存短计划<ArrowRight :size="20" aria-hidden="true" /></RouterLink
      ><button
        v-if="state.receipt.status === 'confirmed'"
        type="button"
        :disabled="blocked"
        @click="commands.previewUndo(state.receipt.operation_id)"
      >
        预览整体撤销
      </button></template
    >
    <template v-else-if="draft && state.run?.status === 'ready'">
      <p>调整只在本页生效。先预览实际影响，再确认保存；不会改写旧计划或完成记录。</p>
      <fieldset
        v-for="(day, index) in draft.days"
        :key="index"
        class="coach-edit-day"
        :disabled="blocked"
      >
        <legend>第 {{ index + 1 }} 个学习日</legend>
        <div class="coach-day-inputs">
          <label
            >安排日期<input
              type="date"
              :value="day.study_date"
              :min="today"
              :max="lastDay"
              @change="changeDate(index, ($event.target as HTMLInputElement).value)" /></label
          ><label
            >可用分钟<input
              type="number"
              min="0"
              max="1440"
              :value="day.options.available_minutes"
              @change="budget(index, ($event.target as HTMLInputElement).valueAsNumber)" /></label
          ><button v-if="draft.days.length > 1" type="button" @click="removeDay(index)">
            移除这一天
          </button>
        </div>
        <ol class="coach-edit-tasks">
          <li v-for="(task, position) in rows(index)" :key="task.task_id">
            <strong>{{ task.title }}</strong>
            <p>{{ task.reason }}</p>
            <div class="coach-task-actions">
              <label
                >预计分钟<input
                  type="number"
                  min="1"
                  max="240"
                  :value="minutes(index, task.task_id, task.estimated_minutes)"
                  @change="
                    duration(index, task.task_id, ($event.target as HTMLInputElement).valueAsNumber)
                  " /></label
              ><button
                type="button"
                :disabled="position === 0"
                :aria-label="`上移：${task.title}`"
                @click="move(index, task.task_id, -1)"
              >
                上移</button
              ><button
                type="button"
                :disabled="position === rows(index).length - 1"
                :aria-label="`下移：${task.title}`"
                @click="move(index, task.task_id, 1)"
              >
                下移</button
              ><button
                type="button"
                :aria-pressed="day.options.excluded_ids?.includes(task.task_id) ?? false"
                @click="exclude(index, task.task_id)"
              >
                {{
                  day.options.excluded_ids?.includes(task.task_id) ? '重新纳入' : '本次排除'
                }}</button
              ><button
                v-if="!isNew(task.task_id)"
                type="button"
                :aria-pressed="day.options.pinned_ids?.includes(task.task_id) ?? false"
                @click="pin(index, task.task_id)"
              >
                {{ day.options.pinned_ids?.includes(task.task_id) ? '取消固定' : '固定顺序' }}
              </button>
            </div>
          </li>
        </ol>
      </fieldset>
      <button v-if="draft.days.length < 7" type="button" :disabled="blocked" @click="addDay">
        增加未来学习日
      </button>
      <fieldset v-if="overlaps.length" :disabled="blocked" class="coach-edit-day">
        <legend>核对可能重复的原计划</legend>
        <label v-for="overlap in overlaps" :key="overlap.original_task_id"
          >{{ originalTitle(overlap.original_task_id)
          }}<select
            :value="
              draft.overlap_choices.find((c) => c.original_task_id === overlap.original_task_id)
                ?.keep ?? ''
            "
            @change="
              overlapChoice(overlap.original_task_id, ($event.target as HTMLSelectElement).value)
            "
          >
            <option value="">两者分别保留</option>
            <option value="original">保留原计划，不新增本批短任务</option>
            <option value="proposed">采用短任务，本次不安排原计划</option>
          </select></label
        >
      </fieldset>
      <div class="coach-actions">
        <button class="action-primary" type="button" :disabled="blocked" @click="preview">
          预览保存影响<ArrowRight :size="20" aria-hidden="true" />
        </button>
      </div>
      <section
        v-if="state.preview"
        class="coach-confirmation"
        aria-labelledby="coach-confirm-heading"
      >
        <h4 id="coach-confirm-heading" ref="confirmationHeading" tabindex="-1">
          核对这次将保存什么
        </h4>
        <p>
          新增 {{ state.preview.changes.new_study_plans }} 个短计划，保存
          {{ state.preview.changes.daily_schedules }} 天安排。全部确认成功后才生效。
        </p>
        <div v-for="day in state.preview.changes.days ?? []" :key="day.study_date">
          <h4>{{ day.study_date }}{{ day.study_date === today ? ' · 今天' : ' · 未来安排' }}</h4>
          <p>
            {{ day.replaces_existing_schedule ? '替换该日安排配置' : '新增该日安排' }}；保留已完成
            {{ day.completed_count }} 项、固定 {{ day.pinned_count }} 项；待安排
            {{ day.selected_count }} 项，预计 {{ day.estimated_minutes }} 分钟；延期／未纳入
            {{ day.deferred_count }} 项。
          </p>
          <ol>
            <li v-for="task in day.selected" :key="task.task_id">
              {{ task.title }} · {{ task.estimated_minutes }} 分钟
            </li>
          </ol>
        </div>
        <button class="action-primary" type="button" :disabled="blocked" @click="confirm">
          确认保存这些日期的安排
        </button>
      </section>
    </template>
    <section v-if="state.undo_preview" class="coach-confirmation">
      <h4>确认整体撤销</h4>
      <p>
        恢复
        {{
          Object.keys(state.undo_preview.day_revisions).join('、')
        }}
        的原安排，归档本批新短计划。已有任务一旦开始或进度变化，服务器将整体拒绝撤销。
      </p>
      <button type="button" :disabled="blocked" @click="commands.confirmUndo">确认整体撤销</button
      ><button type="button" :disabled="blocked" @click="commands.invalidate">保留当前安排</button>
    </section>
    <details v-if="state.receipt?.status === 'confirmed' && targets.length">
      <summary>返回原功能训练</summary>
      <p>此处不标记完成。打开原记录执行，回来重新读取真实记录。</p>
      <ul>
        <li v-for="target in targets" :key="JSON.stringify(target)">
          <RouterLink :to="{ path: target.path, query: target.query }">{{
            target.label
          }}</RouterLink>
        </li>
      </ul>
    </details>
  </section>
</template>
<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { ArrowRight } from '../../icons'
import { resolveCoachAction } from '../../today/navigation'
import { appendCoachDay, type createCoachCommands } from '../../today/coach-commands'
import type { CoachDraft, CoachState } from '../../types/learning-coach'
const props = defineProps<{ state: CoachState; commands: ReturnType<typeof createCoachCommands> }>()
const emit = defineEmits<{ edit: [draft: CoachDraft] }>()
const heading = ref<HTMLElement | null>(null),
  confirmationHeading = ref<HTMLElement | null>(null)
const draft = computed(() => props.state.draft),
  blocked = computed(
    () => !!props.state.pending || ['loading', 'running', 'expired'].includes(props.state.phase),
  )
const today = computed(
  () =>
    props.state.context?.snapshot.study_date ??
    props.state.preview?.issued_study_date ??
    new Date(Date.now() + 8 * 3600000).toISOString().slice(0, 10),
)
const shift = (date: string, amount: number) =>
  new Date(Date.parse(`${date}T00:00:00Z`) + amount * 86400000).toISOString().slice(0, 10)
const lastDay = computed(() => shift(today.value, 6))
const newPool = computed(() => props.state.run?.proposal?.new_actions ?? [])
const targets = computed(() =>
  (draft.value?.new_actions ?? []).flatMap((action) => {
    const target = resolveCoachAction(action)
    return target ? [target] : []
  }),
)
const overlaps = computed(
  () => (props.state.preview?.changes.possible_overlaps ?? []) as { original_task_id: string }[],
)
const isNew = (id: string) => newPool.value.some((a) => a.action_key === id)
function rows(index: number) {
  const source = props.state.run?.proposal?.days[index]?.schedule
  const registry = new Map(
    (props.state.context?.projection.tasks ?? []).map((task) => [task.task_id, task]),
  )
  const tasks = [
    ...(source?.selected ?? []),
    ...(source?.deferred ?? []).flatMap((ref) => {
      const task = registry.get(ref.task_id)
      return task ? [task] : []
    }),
  ].slice(0, 30)
  const order = draft.value?.days[index]?.options.item_order ?? []
  return tasks.sort((a, b) => {
    const ai = order.indexOf(a.task_id),
      bi = order.indexOf(b.task_id)
    return (ai < 0 ? 999 : ai) - (bi < 0 ? 999 : bi)
  })
}
function update(edit: (value: CoachDraft) => void) {
  if (!draft.value || blocked.value) return
  const value = JSON.parse(JSON.stringify(draft.value)) as CoachDraft
  edit(value)
  value.days.sort((a, b) => a.study_date.localeCompare(b.study_date))
  emit('edit', value)
}
function budget(index: number, value: number) {
  if (Number.isInteger(value) && value >= 0 && value <= 1440)
    update((d) => {
      d.days[index]!.options.available_minutes = value
    })
}
function changeDate(index: number, value: string) {
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(value) ||
    value < today.value ||
    value > lastDay.value ||
    draft.value?.days.some((d, i) => i !== index && d.study_date === value)
  )
    return
  update((d) => {
    const old = d.days[index]!.study_date
    d.days[index]!.study_date = value
    for (const action of d.new_actions) if (action.study_date === old) action.study_date = value
  })
}
function minutes(index: number, id: string, fallback: number | null) {
  return (
    draft.value?.new_actions.find((a) => a.action_key === id)?.minutes ??
    draft.value?.days[index]?.options.minute_overrides?.[id] ??
    fallback
  )
}
function duration(index: number, id: string, value: number) {
  if (!Number.isInteger(value) || value < 1 || value > 240) return
  update((d) => {
    const action = d.new_actions.find((a) => a.action_key === id)
    if (action) action.minutes = value
    else if (!isNew(id)) {
      const options = d.days[index]!.options
      options.minute_overrides = { ...options.minute_overrides, [id]: value }
    }
  })
}
function move(index: number, id: string, delta: number) {
  const ids = rows(index).map((t) => t.task_id),
    position = ids.indexOf(id),
    next = position + delta
  if (next < 0 || next >= ids.length) return
  ;[ids[position], ids[next]] = [ids[next]!, ids[position]!]
  update((d) => {
    d.days[index]!.options.item_order = ids
  })
}
function pin(index: number, id: string) {
  update((d) => {
    const options = d.days[index]!.options,
      pins = new Set(options.pinned_ids)
    if (pins.has(id)) pins.delete(id)
    else pins.add(id)
    options.pinned_ids = [...pins]
    options.item_order = rows(index).map((t) => t.task_id)
  })
}
function exclude(index: number, id: string) {
  update((d) => {
    const day = d.days[index]!,
      excluded = new Set(day.options.excluded_ids)
    if (excluded.has(id)) {
      excluded.delete(id)
      const action = newPool.value.find((a) => a.action_key === id)
      if (action && !d.new_actions.some((a) => a.action_key === id))
        d.new_actions.push({ ...action, study_date: day.study_date })
    } else {
      excluded.add(id)
      d.new_actions = d.new_actions.filter((a) => a.action_key !== id)
      day.options.pinned_ids = day.options.pinned_ids?.filter((key) => key !== id)
    }
    day.options.excluded_ids = [...excluded]
  })
}
function addDay() {
  if (draft.value && !blocked.value) emit('edit', appendCoachDay(draft.value, today.value))
}
function removeDay(index: number) {
  update((d) => {
    const [removed] = d.days.splice(index, 1)
    d.new_actions = d.new_actions.filter((a) => a.study_date !== removed!.study_date)
  })
}
function originalTitle(id: string) {
  return (
    props.state.context?.projection.tasks.find((t) => t.task_id === id)?.title ?? '可能重复的原计划'
  )
}
function overlapChoice(id: string, value: string) {
  update((d) => {
    d.overlap_choices = d.overlap_choices.filter((c) => c.original_task_id !== id)
    if (value === 'original' || value === 'proposed')
      d.overlap_choices.push({ original_task_id: id, keep: value })
  })
}
async function preview() {
  if (!draft.value) return
  await props.commands.preview(draft.value)
  await nextTick()
  confirmationHeading.value?.focus()
  confirmationHeading.value?.scrollIntoView({ block: 'start' })
}
async function confirm() {
  await props.commands.confirm()
  await nextTick()
  heading.value?.focus()
  heading.value?.scrollIntoView({ block: 'start' })
}
</script>
