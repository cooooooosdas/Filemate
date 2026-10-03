<template>
  <section class="career-plans panel" aria-labelledby="career-plans-title">
    <header><div><p class="eyebrow">实际作答 · 下一步学习</p><h2 id="career-plans-title">岗位学习计划</h2></div><button :disabled="loading || busy || locked" @click="load">刷新岗位计划</button></header>
    <p>先核对建议和原记录，再保存到学习计划。每天建议30分钟，最多安排7项；新建议另存，已有计划与进度保留。</p>
    <p v-if="loading" role="status">正在读取岗位学习计划…</p>
    <p v-if="error" role="alert">{{ error }} <button :disabled="loading || busy || locked" @click="load">重试岗位计划</button></p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <button v-if="position.active" class="primary" :disabled="loading || busy || locked" @click="preview">预览岗位学习建议</button>
    <p v-else>岗位已撤销，已有计划仍可回看和管理；恢复岗位后可生成新建议。</p>
    <p v-if="!loading && !plans.length">尚未保存岗位学习计划。预览不会写入计划或调整成绩。</p>
    <ol class="saved-plans">
      <li v-for="plan in plans" :key="plan.plan_id">
        <div><strong>{{ plan.title }}</strong><p v-if="plan.data_error">计划数据异常，原记录保留；可撤销或预览删除岗位。</p><p v-else>{{ statusText(plan.status) }} · 已完成 {{ plan.completed_days.length }} / {{ plan.plan_data?.daily_plan.length }} 天</p><small>记录更新：{{ new Date(plan.updated_at).toLocaleString('zh-CN') }}</small></div>
        <div class="actions"><router-link v-if="!plan.data_error" :to="{ path: '/study-plan', query: { plan: plan.plan_id } }">回看学习计划</router-link><button :disabled="busy || loading || locked || (plan.data_error && plan.status === 'archived')" @click="transition(plan)">{{ plan.status === 'archived' ? '恢复学习计划' : '撤销学习计划' }}</button></div>
      </li>
    </ol>
    <ElDialog v-model="showPreview" title="核对岗位学习建议" width="min(720px, calc(100vw - 32px))" :close-on-click-modal="!busy" :close-on-press-escape="!busy" :show-close="!busy">
      <div v-if="suggestion" class="career-plan-preview">
        <p>{{ suggestion.method }}</p><p>本次安排 {{ suggestion.steps.length }} / {{ suggestion.requirements_total }} 项岗位要求；请核对词法关联和原记录。</p>
        <ol><li v-for="(step, index) in suggestion.steps" :key="step.label"><h3>第 {{ index + 1 }} 天 · {{ step.label }} <small>{{ step.status }}</small></h3><p>岗位原句：{{ step.requirement_quote }}</p><p>{{ step.reason }}</p><div class="actions"><router-link v-for="action in step.actions" :key="action.route" :to="action.route" @click="showPreview = false">{{ action.label }}</router-link></div></li></ol>
        <p v-if="saveError" role="alert">{{ saveError }}</p>
      </div>
      <template #footer><button :disabled="busy" @click="showPreview = false">继续核对建议</button><button class="primary" :disabled="busy || locked" @click="save">{{ busy ? '正在保存…' : '确认保存学习计划' }}</button></template>
    </ElDialog>
  </section>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { ElDialog, ElMessageBox } from 'element-plus'
import { changeCareerPlan, getCareerPlans, previewCareerPlan, saveCareerPlan } from '../services/api'
import type { CareerLearningPlan, CareerPlanPreview, CareerRecord } from '../types/career'
const props = defineProps<{ position: CareerRecord; locked?: boolean }>()
const plans = shallowRef<CareerLearningPlan[]>([]), suggestion = shallowRef<CareerPlanPreview | null>(null)
const loading = ref(false), busy = ref(false), showPreview = ref(false)
const error = ref(''), saveError = ref(''), notice = ref('')
let disposed = false, epoch = 0, currentPosition = ''
const current = (token: number, id: string) => !disposed && token === epoch && props.position.position_id === id
const message = (failure: unknown) => failure instanceof Error ? failure.message : '岗位学习计划暂时未能完成，请重试'
const statusText = (status: string) => ({ active: '可继续学习', archived: '已撤销', completed: '已完成' } as Record<string, string>)[status] || status
async function load() {
  const token = ++epoch, id = props.position.position_id
  loading.value = true; error.value = ''
  try { const result = await getCareerPlans(id); if (current(token, id)) plans.value = result }
  catch (failure) { if (current(token, id)) error.value = message(failure) }
  finally { if (current(token, id)) loading.value = false }
}
async function preview() {
  const token = ++epoch, id = props.position.position_id
  busy.value = true; error.value = ''; saveError.value = ''; notice.value = ''
  try { const result = await previewCareerPlan(id); if (current(token, id)) { suggestion.value = result; showPreview.value = true } }
  catch (failure) { if (current(token, id)) error.value = message(failure) }
  finally { if (current(token, id)) busy.value = false }
}
async function save() {
  if (!suggestion.value || busy.value) return
  const captured = suggestion.value, token = ++epoch, id = props.position.position_id
  busy.value = true; saveError.value = ''
  try {
    await saveCareerPlan(id, captured.evidence_revision)
    if (!current(token, id)) return
    showPreview.value = false; notice.value = '学习计划已保存，可回看原证据并完成每天任务。'; await load()
  } catch (failure) { if (current(token, id)) saveError.value = message(failure) }
  finally { if (!disposed && props.position.position_id === id) busy.value = false }
}
async function transition(plan: CareerLearningPlan) {
  const id = props.position.position_id, action = plan.status === 'archived' ? 'restore' : 'undo'
  try { await ElMessageBox.confirm(action === 'undo' ? '撤销这份学习计划后暂停每日任务，已完成进度保留。' : '恢复这份学习计划并保留原进度和证据。', '确认学习计划状态', { confirmButtonText: '确认计划变更', cancelButtonText: '保留现状' }) }
  catch { return }
  if (disposed || id !== props.position.position_id) return
  const token = ++epoch; busy.value = true; error.value = ''
  try { await changeCareerPlan(id, plan.plan_id, action); if (current(token, id)) await load() }
  catch (failure) { if (current(token, id)) error.value = message(failure) }
  finally { if (!disposed && id === props.position.position_id) busy.value = false }
}
watch(() => [props.position.position_id, props.position.revision], () => {
  epoch++; busy.value = false; loading.value = false; showPreview.value = false; suggestion.value = null; notice.value = ''
  if (currentPosition !== props.position.position_id) plans.value = []
  currentPosition = props.position.position_id; void load()
}, { immediate: true })
onBeforeUnmount(() => { disposed = true; epoch++ })
</script>

<style scoped>
.career-plans{background:var(--bg-surface);border:1px solid var(--border-subtle);border-radius:14px;padding:24px;overflow-wrap:anywhere}.career-plans header,.saved-plans li{display:flex;justify-content:space-between;align-items:start;gap:16px}.career-plans h2{margin:0 0 16px;font-size:22px}.eyebrow{font-size:12px;color:var(--accent)}.career-plans p,.career-plan-preview p{line-height:1.8;color:var(--text-secondary)}button{min-height:44px;border:1px solid var(--accent-border);background:var(--accent-soft);color:var(--accent);padding:10px 14px;border-radius:10px;cursor:pointer}button.primary{background:var(--accent);color:var(--bg-surface)}button:disabled{opacity:.5;cursor:default}.saved-plans{padding:0;list-style:none}.saved-plans li{margin-top:18px;padding-top:18px;border-top:1px solid var(--border-subtle)}.saved-plans small,.career-plan-preview small{color:var(--text-secondary);font-size:12px}.actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap}a{display:inline-flex;align-items:center;min-height:44px;color:var(--accent)}a:focus-visible,button:focus-visible{outline:2px solid var(--accent);outline-offset:3px}.career-plan-preview{overflow-wrap:anywhere}.career-plan-preview ol{padding-left:22px}.career-plan-preview li{margin:24px 0}.career-plan-preview h3{font-size:17px;line-height:1.8}.career-plan-preview h3 small{display:block}.career-plan-preview [role=alert],.career-plans [role=alert]{color:var(--danger)}@media(max-width:600px){.career-plans{padding:18px}.saved-plans li,.career-plans header{flex-direction:column}.career-plans header{gap:4px}}
</style>
