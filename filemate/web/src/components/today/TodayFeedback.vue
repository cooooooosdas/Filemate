<template>
  <section class="action-paper action-feedback" aria-labelledby="action-feedback-heading">
    <h2 id="action-feedback-heading">只看真实记录</h2>
    <dl><div><dt>今日可核验的练习作答</dt><dd>{{ presentation.today_attempts === null ? '待核验' : presentation.today_attempts + ' 次' }}</dd></div><div><dt>当前目标已完成任务（含历史）</dt><dd>{{ presentation.historical_completed }} 项</dd></div></dl><p class="action-help">学习记录与学习能力不同，完成任务不等于掌握知识。</p>
    <p v-for="notice in presentation.coverage_notices" :key="notice" class="action-help">{{ notice }}</p>
    <details><summary>需要巩固的依据与查询范围</summary><p>本次仅依据已选 {{ bundle.snapshot.scope.source_ids?.length ?? 0 }} 份资料与当前目标。快照截至 {{ bundle.snapshot.as_of }}。</p><p v-if="!targets.length">当前任务没有明确关联的概念，尚未能核对概念练习，不代表全课程缺少学习证据。</p><template v-else><p>仅查询 {{ targets.length }} 个明确关联概念，每次最多5个，不扩展到全课程。</p><button type="button" :disabled="loading" @click="readEvidence">{{ loading ? '正在核对…' : '核对关联概念的训练记录' }}</button></template><p v-if="error" role="alert">{{ error }}</p><article v-for="item in evidence" :key="item.concept_id"><h3>{{ item.label }}</h3><p>{{ statusLabel(item.status) }} · 规则 {{ item.rule_version }}</p><p>截至 {{ item.as_of }} · 近7天错答 {{ item.counts.wrong_attempts_7d }} 次 · 到期复习 {{ item.counts.due_reviews }} 项</p><p v-if="!item.active_support">来源当前不可用，不能据此推断学习能力。</p></article></details>
    <details v-if="bundle.projection.completed.length"><summary>查看已读历史完成记录</summary><ul><li v-for="task in bundle.projection.completed" :key="task.task_id">{{ task.title }} · 原领域状态 {{ task.status }}</li></ul></details>
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { OrchestratorSnapshot } from '../../types/orchestrator'
import type { TodayPresentation } from '../../types/today'
import type { LearningEvidence } from '../../types/courseLearning'
import { getCourseLearning } from '../../services/api'
import { resolveTodayTask } from '../../today/navigation'
const props = defineProps<{ bundle: OrchestratorSnapshot; presentation: TodayPresentation }>()
const targets = computed(() => { const found = new Map<string, { course: string; concept: string }>(); for (const task of props.bundle.projection.tasks) for (const link of resolveTodayTask(task, props.bundle).related) if (link.path === '/knowledge-graph' && link.query.course && link.query.node) found.set(`${link.query.course}:${link.query.node}`, { course: link.query.course, concept: link.query.node }); return [...found.values()].slice(0, 5) })
const evidence = ref<LearningEvidence[]>([]), error = ref(''), loading = ref(false)
let generation = 0, abort: AbortController | null = null
function reset() { generation++; abort?.abort(); evidence.value = []; loading.value = false; error.value = '' }
watch(() => props.bundle.snapshot.evidence_revision, reset)
async function readEvidence() {
  reset(); const ticket = generation; abort = new AbortController(); loading.value = true
  const results = await Promise.allSettled(targets.value.map(item => getCourseLearning(item.course, item.concept, 0, abort!.signal)))
  if (ticket !== generation) return
  evidence.value = results.flatMap(result => result.status === 'fulfilled' ? [result.value] : [])
  if (results.some(result => result.status === 'rejected')) error.value = '部分关联记录暂未能读取，已读结果保留，可手动重试。'
  loading.value = false
}
const statuses: Record<string, string> = { no_evidence: '尚无已关联训练证据', practiced: '已有练习记录', needs_reinforcement: '近期需要巩固', recently_stable: '近期训练表现稳定' }
const statusLabel = (status: string) => statuses[status] ?? '状态待核对'
onBeforeUnmount(reset)
</script>
