<template>
  <section class="action-paper action-tasks" aria-labelledby="action-tasks-heading">
    <div class="action-section-head"><h2 id="action-tasks-heading">{{ editable ? '调整候选顺序' : '今天的行动顺序' }}</h2><span>{{ tasks.length }} 项{{ editable ? '候选' : '已保存' }}</span></div>
    <p v-if="!tasks.length">{{ editable ? '所选范围没有可安排任务，可先创建学习目标或原计划。' : '还没有保存今天的安排。选好范围与时间，再预览确认。' }}</p>
    <p v-if="editable" class="action-help">调整只保存为草稿。固定任务也受时间预算限制，排除仅影响本次安排。</p>
    <ol class="action-list">
      <li v-for="(task, index) in ordered" :key="task.task_id" :class="{ 'is-excluded': options?.excluded_ids?.includes(task.task_id) }">
        <span class="action-order" aria-hidden="true">{{ index + 1 }}</span>
        <div class="action-task-content"><h3>{{ task.title }}</h3><p>{{ task.reason }}</p>
          <p class="action-meta">{{ kindLabel(task.kind) }} · 预计 {{ task.estimated_minutes ?? '待核对' }} 分钟<span v-if="task.due_date"> · 截止 {{ task.due_date }}</span></p>
          <p class="action-meta">{{ estimateLabel(task.estimate_source) }}，并非实际学习时长</p>
          <div v-if="editable && options" class="action-controls">
            <button type="button" :disabled="busy || index === 0" :aria-label="`上移：${task.title}`" @click="move(index, -1)">上移</button>
            <button type="button" :disabled="busy || index === ordered.length - 1" :aria-label="`下移：${task.title}`" @click="move(index, 1)">下移</button>
            <button type="button" :disabled="busy || !options.pinned_ids?.includes(task.task_id) && (options.pinned_ids?.length ?? 0) >= 20" :aria-pressed="options.pinned_ids?.includes(task.task_id) || false" :aria-label="`固定：${task.title}`" @click="toggle(task.task_id, 'pin')">{{ options.pinned_ids?.includes(task.task_id) ? '取消固定' : '固定' }}</button>
            <button type="button" :disabled="busy" :aria-pressed="options.excluded_ids?.includes(task.task_id) || false" :aria-label="`排除：${task.title}`" @click="toggle(task.task_id, 'exclude')">{{ options.excluded_ids?.includes(task.task_id) ? '恢复候选' : '本次排除' }}</button>
            <label class="action-minutes">预计分钟<input :value="options.minute_overrides?.[task.task_id] ?? task.estimated_minutes ?? ''" :aria-label="`预计分钟：${task.title}`" type="number" min="1" max="240" step="1" :disabled="busy" @change="minutes(task.task_id, ($event.target as HTMLInputElement).valueAsNumber)"></label>
          </div>
          <div class="action-controls"><RouterLink v-if="destination(task).primary && canOpen(destination(task).primary!.path)" class="action-link" :to="destination(task).primary!">{{ destination(task).primary!.label }}</RouterLink><p v-else class="action-help">{{ destination(task).primary ? '该功能当前关闭，可先查看对应资料或调整安排。' : destination(task).notice }}</p>
            <RouterLink v-for="link in destination(task).related.filter(link => canOpen(link.path))" :key="link.path + JSON.stringify(link.query)" :to="link">{{ link.label }}</RouterLink></div>
          <details><summary>查看任务依据与原记录</summary><p>规则版本：{{ task.rule_version }} · 原领域状态：{{ task.status }}</p><pre>{{ evidence(task) }}</pre></details>
        </div>
      </li>
    </ol>
  </section>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import type { OrchestratorSnapshot, ScheduleOptions, TaskView } from '../../types/orchestrator'
import { resolveTodayTask } from '../../today/navigation'
const props = defineProps<{ tasks: TaskView[]; bundle: OrchestratorSnapshot; options?: ScheduleOptions; editable?: boolean; busy?: boolean; canOpen: (path: string) => boolean }>()
const emit = defineEmits<{ options: [value: ScheduleOptions] }>()
const ordered = computed(() => { const byId = new Map(props.tasks.map(task => [task.task_id, task])); const ids = props.options?.item_order ?? []; return [...ids.flatMap(id => byId.has(id) ? [byId.get(id)!] : []), ...props.tasks.filter(task => !ids.includes(task.task_id))] })
const destination = (task: TaskView) => resolveTodayTask(task, props.bundle)
const kinds: Record<string, string> = { review: '错题复练', goal: '目标任务', plan: '学习计划', semester: '学期任务' }
const kindLabel = (kind: string) => kinds[kind] ?? '原任务'
const estimates: Record<string, string> = { rule_default: '规则默认估计', domain_estimate: '原任务的预计时长', user_estimate: '你填写的预计时长' }
const estimateLabel = (source: string | null) => source ? estimates[source] ?? '原记录的预计时长' : '尚无可靠时长估计'
const evidence = (task: TaskView) => JSON.stringify({ evidence: task.evidence_refs, origins: task.origin_refs, completion: task.completion_ref }, null, 2).slice(0, 6000)
function copyOptions(): ScheduleOptions { return { ...props.options!, item_order: ordered.value.map(task => task.task_id), pinned_ids: [...props.options?.pinned_ids ?? []], excluded_ids: [...props.options?.excluded_ids ?? []], minute_overrides: { ...props.options?.minute_overrides } } }
function move(index: number, delta: number) { const next = copyOptions(), ids = next.item_order!; [ids[index], ids[index + delta]] = [ids[index + delta]!, ids[index]!]; emit('options', next) }
function toggle(id: string, kind: 'pin' | 'exclude') { const next = copyOptions(), field = kind === 'pin' ? 'pinned_ids' : 'excluded_ids', other = kind === 'pin' ? 'excluded_ids' : 'pinned_ids'; next[field] = next[field]!.includes(id) ? next[field]!.filter(value => value !== id) : [...next[field]!, id]; next[other] = next[other]!.filter(value => value !== id); emit('options', next) }
function minutes(id: string, value: number) { const next = copyOptions(); next.minute_overrides![id] = value; emit('options', next) }
</script>
