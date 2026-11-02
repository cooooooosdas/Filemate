<template>
  <section class="action-paper action-preview" aria-labelledby="action-preview-heading">
    <h2 id="action-preview-heading">预览与保存</h2>
    <p v-if="state.dirty" class="action-status">有未保存的安排调整，请重新预览后确认。</p>
    <div v-if="state.pending" class="action-status" role="status"><h3>正在核对上次保存结果</h3><p>请求可能已保存。先按原请求编号查回执，不会自动重复提交。</p><p>安排日期：{{ state.pending.study_date }}</p><button type="button" :disabled="busy" @click="$emit('recover')">查找原请求回执</button><p v-if="state.pending.kind === 'confirm'">若回执暂未找到，可读取原目标并重新预览；确认仍沿用原请求编号。</p><button v-else-if="state.pending.operation_id" type="button" :disabled="busy" @click="$emit('previewUndo', state.pending.operation_id)">重新预览原撤销</button><details><summary>查看原请求编号</summary><code>{{ state.pending.request_key }}</code></details></div>
    <div v-if="state.preview"><p class="action-total">{{ state.preview.selected.length }} 项 · 预计 {{ state.preview.estimated_minutes }} 分钟</p><p>{{ state.preview.study_date }} · 保存前版本 {{ state.preview.day_revision }}</p><ul><li v-for="task in state.preview.selected" :key="task.task_id">{{ task.title }} · 预计 {{ task.estimated_minutes ?? '待核对' }} 分钟</li></ul>
      <p v-if="state.preview.changes.replaces_goal" class="action-status">确认后将更换今日优先目标，另一目标的原任务与完成记录保留。</p><p>本次新增 {{ changeCounts.added }} 项，移出 {{ changeCounts.removed }} 项；移出今日安排不会删除原任务。</p><details><summary>查看安排变更依据</summary><pre>{{ JSON.stringify(state.preview.changes, null, 2) }}</pre></details>
      <details v-if="state.preview.deferred_count"><summary>{{ state.preview.deferred_count }} 项未排入，查看原因</summary><p v-for="(count, reason) in state.preview.deferred_counts" :key="reason">{{ reasonText(String(reason)) }}：{{ count }} 项</p><p v-if="state.preview.deferred_truncated">原因明细已截断，仅显示已返回记录。</p><ul><li v-for="item in state.preview.deferred" :key="item.task_id">{{ taskTitle(item.task_id) }}：{{ reasonText(item.reason) }}{{ item.pinned ? '（已固定，仍受预算约束）' : '' }}</li></ul></details>
      <p class="action-help">只调整今日安排；原目标、原计划与完成记录保留。预览有效期最多 {{ state.preview.expires_in_seconds }} 秒。</p><button type="button" class="action-primary" :disabled="busy" @click="$emit('confirm')">确认保存此安排</button>
    </div>
    <p v-else-if="!state.pending">选好目标、范围与时间后预览。预览不会保存安排。</p>
    <div v-if="state.receipt" class="action-receipt" role="status"><h3>{{ state.receipt.status === 'undone' ? '撤销已保存' : '安排已保存' }}</h3><p>{{ state.receipt.study_date }} · 版本 {{ state.receipt.revision }}</p><p v-if="state.receipt.study_date !== state.day?.study_date">此回执属于历史日期，当前日期以服务器为准。</p><details><summary>查看保存回执</summary><code>{{ state.receipt.operation_id }}</code></details>
      <button v-if="canUndo" type="button" :disabled="busy" @click="$emit('previewUndo', state.receipt.operation_id)">预览撤销此调整</button>
    </div>
    <div v-if="state.undo_preview" class="action-status"><h3>确认撤销今日安排调整</h3><p>撤销 {{ state.undo_preview.study_date }} 的此项调整，恢复上一已保存安排。原领域完成记录不会重置。</p><p>当前安排版本 {{ state.undo_preview.day_revision }}。恢复后的数量以服务器结果为准。</p><button type="button" class="action-primary" :disabled="busy" @click="$emit('confirmUndo')">确认撤销此调整</button><button type="button" :disabled="busy" @click="$emit('cancelUndo')">取消撤销</button></div>
  </section>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import type { TodayState } from '../../types/today'
const props = defineProps<{ state: TodayState; busy: boolean }>()
defineEmits<{ confirm: []; recover: []; previewUndo: [id: string]; confirmUndo: []; cancelUndo: [] }>()
const canUndo = computed(() => props.state.receipt?.status === 'confirmed' && props.state.day?.latest_operation?.operation_id === props.state.receipt.operation_id && props.state.receipt.study_date === props.state.day.study_date && !props.state.pending)
const changeCounts = computed(() => { const previous = props.state.preview?.changes.previous_selected_ids; const before = new Set(Array.isArray(previous) ? previous.filter(id => typeof id === 'string') : []); const after = new Set(props.state.preview?.selected.map(task => task.task_id) ?? []); return { added: [...after].filter(id => !before.has(id)).length, removed: [...before].filter(id => !after.has(id)).length } })
const taskTitle = (id: string) => props.state.snapshot?.projection.tasks.find(task => task.task_id === id)?.title ?? '原候选任务'
const reasons: Record<string, string> = { budget: '超出可用时间', estimate_required: '请先补充预计时长', excluded: '本次已排除', limit: '达到20项上限', prerequisite_unavailable: '前置任务尚未完成或未排入', dependency_cycle: '前置关系存在循环，需先修正', paused: '原复习已暂停', pending_check: '原作答尚待核验', not_due: '复习尚未到期', archived: '原计划已归档' }
const reasonText = (reason: string) => reasons[reason] ?? '当前不符合安排条件，请查看原任务状态'
</script>
