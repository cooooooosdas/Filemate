<template>
  <details class="cl-section" @toggle="opened">
    <summary>问问图谱助手</summary><p>原文、训练事实、学习建议分开看。只在你点击后生成。</p>
    <p v-if="state.error" class="cw-status cw-error" role="alert">{{ state.error }}</p>
    <label>你想弄清什么<textarea :value="state.question" maxlength="2000" :disabled="!!state.busy" @input="controller.setQuestion(($event.target as HTMLTextAreaElement).value)" /></label>
    <fieldset :disabled="!!state.busy"><legend>回答方式</legend><label><input type="radio" :checked="state.mode === 'rule'" @change="controller.setMode('rule')" />原文与记录检索</label><label><input type="radio" :checked="state.mode === 'llm'" @change="controller.setMode('llm')" />模型解释</label></fieldset>
    <label v-if="state.mode === 'llm'"><input type="checkbox" :checked="state.consent" :disabled="!!state.busy" @change="controller.setConsent(($event.target as HTMLInputElement).checked)" />同意本次将所选课程原文与训练摘要发送给已配置模型；授权不保存为偏好</label>
    <button class="cw-primary" :disabled="!!state.busy || !state.question.trim() || (state.mode === 'llm' && !state.consent && !state.uncertain)" @click="controller.send()">{{ state.uncertain ? '读取原请求结果' : state.mode === 'rule' ? '查找原文与记录' : '授权并生成解释' }}</button><button v-if="state.busy === 'answer' || state.uncertain || state.work?.status === 'running'" @click="controller.cancel()">取消本次工作</button>
    <p v-if="state.busy" role="status">{{ state.busy === 'answer' ? '正在处理，最长约20秒…' : '正在读取或保存…' }}</p>
    <article v-if="state.work" class="cl-section" aria-label="助手已存结果">
      <p class="cw-kicker">{{ state.work.payload.mode === 'rule' ? '规则检索' : '模型工作' }} · {{ state.work.work_id }}</p>
      <p v-if="state.work.stale" role="status" class="cw-status">来源、目标或学习记录已变化；以下为历史结果，需重新生成后用于当前判断。</p>
      <template v-if="state.work.status === 'ready'"><h3>{{ state.work.payload.question }}</h3><p class="cl-answer">{{ state.work.payload.explanation }}</p><p v-if="state.work.payload.coverage">本次涵盖 {{ state.work.payload.coverage.concepts_in_context }} / {{ state.work.payload.coverage.total_course_concepts }} 个课程概念，{{ state.work.payload.coverage.quotes_in_context }} 条引文。上下文有限。</p>
        <h3>教材与资料依据</h3><blockquote v-for="quote in state.work.payload.textbook_evidence" :key="quote.evidence_id">{{ quote.quote }}<button @click="$emit('citation', quote.evidence_id)">定位这段原文</button></blockquote>
        <h3>你的真实训练记录</h3><article v-for="fact in state.work.payload.personal_facts" :key="fact.fact_id" class="cw-quote"><strong>{{ fact.label }}</strong><p>{{ statuses[fact.status] || fact.status }} · 实际作答 {{ fact.counts.attempts }} 次 · 到期复习 {{ fact.counts.due_reviews }} 项</p></article>
        <h3>学习建议</h3><ul><li v-for="(suggestion, index) in state.work.payload.suggestions" :key="index">{{ suggestion }}</li></ul><p v-for="limitation in state.work.payload.limitations" :key="limitation" class="cw-caption">{{ limitation }}</p>
      </template>
      <p v-else role="status">{{ statusText[state.work.status] || state.work.status }}<span v-if="state.work.error_code"> · {{ state.work.error_code }}</span>。原资料和回答保留，不补造分析。</p>
    </article>
    <section class="cl-section"><h3>让助手排出下一步</h3><p>固定四个只读／预览步骤，最多七项任务；确认后才新增计划。</p><label>目标<input :value="state.planOptions.goal" maxlength="500" :disabled="!!state.busy" @input="controller.setPlanOptions({ goal: ($event.target as HTMLInputElement).value })" /></label><div class="cl-fields"><label>天数<input :value="state.planOptions.days" type="number" min="1" max="7" :disabled="!!state.busy" @input="controller.setPlanOptions({ days: Number(($event.target as HTMLInputElement).value) })" /></label><label>每天分钟<input :value="state.planOptions.daily_minutes" type="number" min="5" max="180" :disabled="!!state.busy" @input="controller.setPlanOptions({ daily_minutes: Number(($event.target as HTMLInputElement).value) })" /></label></div><button :disabled="!!state.busy || !state.planOptions.goal.trim()" @click="controller.previewPlan()">预览任务建议</button><div v-if="state.planPreview" class="cl-confirm"><p>已执行 {{ state.planPreview.tool_steps?.length || 0 }} 个有界步骤，没有修改学习数据。</p><ol><li v-for="task in state.planPreview.tasks" :key="task.day_index"><strong>{{ task.label }}</strong> · {{ task.duration_minutes }} 分钟<p>{{ task.reason }}</p></li></ol><p v-if="state.planPreview.omitted_count">还有 {{ state.planPreview.omitted_count }} 项未排入本次日程。</p><button class="cw-primary" :disabled="!!state.busy" @click="controller.confirmPlan()">确认新增这些任务</button></div><p v-if="state.receipt" role="status">计划已保存。<RouterLink :to="`/study-plan?plan=${state.receipt.plan_id}`">打开计划</RouterLink></p></section>
    <section class="cl-section"><h3>已保存的问答</h3><button :disabled="!!state.busy" @click="controller.loadHistory(state.history.offset)">刷新历史</button><p v-if="!state.history.items.length">本页尚无问答记录。</p><button v-for="item in state.history.items" :key="item.operation_id" :disabled="!!state.busy" @click="controller.reopen(item.work_id!)">{{ new Date(item.created_at).toLocaleString() }} · 打开已存结果</button><nav class="cw-pagination" aria-label="助手历史分页"><button :disabled="!!state.busy || state.history.offset === 0" @click="controller.loadHistory(Math.max(0, state.history.offset-50))">前页</button><button :disabled="!!state.busy || state.history.offset+50 >= state.history.total" @click="controller.loadHistory(state.history.offset+50)">后页</button></nav></section>
  </details>
</template>
<script setup lang="ts">
import { onUnmounted, shallowReactive, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import * as api from '../../services/api'
import { createGraphAssistantController } from '../../course-graph/assistant-state'
const props = defineProps<{ scope: string; courseId: string; nodeId: string }>()
defineEmits<{ citation: [evidenceId: string] }>()
const controller = createGraphAssistantController(api, shallowReactive), state = controller.state
const statuses: Record<string, string> = { no_evidence: '暂无训练证据', practiced: '已有练习', needs_reinforcement: '需要巩固', recently_stable: '近期表现稳定' }
const statusText: Record<string, string> = { failed: '分析失败，可重新授权后重试', cancelled: '已取消', interrupted: '工作中断，需要重试', running: '工作处理中' }
let leaveApproved = false
watch(() => [state.question, state.work, state.planPreview], () => { leaveApproved = false })
watch(() => [props.scope, props.courseId, props.nodeId], () => { leaveApproved = false; controller.open(props.scope, props.courseId, props.nodeId) }, { immediate: true })
function opened(event: Event) { if ((event.target as HTMLDetailsElement).open && !state.history.items.length) void controller.loadHistory() }
async function canLeave() { if (!controller.dirty() || leaveApproved) return true; try { await ElMessageBox.confirm('有未完成的问答或计划预览。已保存结果可从历史读取，切换知识点会清除本页未保存输入。', '离开图谱助手？', { confirmButtonText: '继续离开', cancelButtonText: '留在这里' }); leaveApproved = true; return true } catch { return false } }
onUnmounted(controller.dispose)
defineExpose({ canLeave, dirty: controller.dirty })
</script>
