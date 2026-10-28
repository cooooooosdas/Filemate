<template>
  <section class="review-learning" aria-label="证据分析与学习行动">
    <header class="learning-heading"><div><p class="section-kicker">从原答出发</p><h2>找到下一步</h2></div><button :disabled="loading || a.dirty() || l.dirty()" @click="load">刷新证据</button></header>
    <p v-if="loading" role="status">正在读取真实作答与关联…</p><p v-if="error" role="alert" class="review-error">{{ error }} <button @click="load">重试读取</button></p>
    <label v-if="attempts.length">选择要复盘的真实作答<select :value="attemptId" :disabled="loading || a.dirty() || l.dirty()" @change="changeAttempt(($event.target as HTMLSelectElement).value)"><option v-for="item in attempts" :key="item.attempt_id" :value="item.attempt_id">{{ reviewTime(item.created_at) }} · {{ item.is_correct === null ? '待核对' : item.answer_revealed ? '辅助练习' : item.is_correct ? '本次答对' : '本次未答对' }}</option></select></label>
    <p v-else-if="!loading">先保存一次真实作答，再分析与安排短行动。</p>
    <ReviewConnections :items="connections" :course="course" :disabled="loading || a.dirty() || l.dirty()" @course="changeCourse" />
    <template v-if="a.state.context"><ReviewAnalysis :c="a" :enabled="analysisEnabled && !loading" :writable="canWrite && !manualDirty && !loading" @adopt="adopt" /><p v-if="manualDirty" class="review-notice">手动错因草稿尚未保存。请先保存或继续编辑，再采纳模型建议。</p><ReviewLearningPlan :c="l" :writable="canWrite && !loading" :goals="goals" :basis="a.state.context.next_actions[0]?.basis" @planning="mode='plan'" /></template>
    <p v-if="l.state.error" role="alert" class="review-error">{{ l.state.error }}</p>
    <section v-if="l.state.preview" class="learning-confirm" aria-label="确认变更" tabindex="-1" ref="confirmation"><h3>核对后再确认</h3><pre class="preserve">{{ JSON.stringify(l.state.preview.plan || l.state.preview.changes || {before:l.state.preview.before,after:l.state.preview.after},null,2) }}</pre><div class="review-actions"><button class="primary" :disabled="loading || l.state.busy || !canWrite || manualDirty && mode==='adopt'" @click="confirm">{{ l.state.uncertain ? '原样核验确认结果' : '确认本次变更' }}</button><button :disabled="l.state.busy || l.state.uncertain" @click="l.cancelPreview()">取消，保留原数据</button></div></section>
    <section v-if="receipt" class="review-receipt" aria-live="polite"><h3>变更已保存</h3><p>操作回执 {{ receipt.review_event_id }}</p><RouterLink v-if="receipt.route" :to="receipt.route">打开新增学习计划</RouterLink><RouterLink v-if="receipt.plan_id" to="/today">查看今日安排</RouterLink><button v-if="!undone" :disabled="loading || l.state.busy || !canWrite" @click="undo(receipt.review_event_id)">预览撤销此次变更</button></section>
    <details v-if="operations.length"><summary>可撤销的学习操作</summary><ul class="learning-links"><li v-for="item in operations" :key="item.event_id"><button :disabled="loading || !canWrite || l.state.busy" @click="undo(item.event_id)">{{ item.action==='analysis_adopt' ? '采纳错因' : '新增计划' }} · {{ reviewTime(item.created_at) }} · 预览撤销</button></li></ul></details>
  </section>
</template>
<script setup lang="ts">
import { reactive,ref,watch,onBeforeUnmount,nextTick } from 'vue'
import * as api from '../../services/review-api'
import { getReverseGoals } from '../../services/api'
import type { ReviewDetail,ReviewAttempt,ReviewCause,ReviewEvent } from '../../types/wrongbook'
import type { ReviewConnection,LearningReceipt } from '../../types/reviewLearning'
import { createReviewAnalysisController } from '../../wrongbook/analysis-state'
import { createReviewLearningController } from '../../wrongbook/learning-state'
import { browserReviewStorage } from '../../wrongbook/submission'
import { reviewTime } from '../../wrongbook/presentation'
import ReviewAnalysis from './ReviewAnalysis.vue'
import ReviewLearningPlan from './ReviewLearningPlan.vue'
import ReviewConnections from './ReviewConnections.vue'
const props=defineProps<{detail:ReviewDetail;selectedAttempt?:string;canWrite:boolean;analysisEnabled:boolean;manualDirty:boolean}>()
const emit=defineEmits<{changed:[]}>()
const observe=<T extends object>(s:T)=>reactive(s) as T
const a=createReviewAnalysisController(api,observe,browserReviewStorage()),l=createReviewLearningController(api,observe)
const attempts=ref<ReviewAttempt[]>([]),connections=ref<ReviewConnection[]>([]),operations=ref<ReviewEvent[]>([]),goals=ref<{artifact_id:string;title:string}[]>([]),loading=ref(false),error=ref(''),attemptId=ref(''),course=ref(''),receipt=ref<LearningReceipt|null>(null),undone=ref(false),mode=ref(''),confirmation=ref<HTMLElement|null>(null)
let epoch=0
async function context(){const e=epoch;await a.open(props.detail,attemptId.value,course.value||undefined);if(e!==epoch)return;const c=a.state.context;if(c){const start=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());l.refresh(props.detail,{expected_revision:c.review_state.revision,attempt_id:attemptId.value,course_id:course.value||undefined,start_date:start,tasks:c.next_actions.map(({action_id,title,instructions,duration_minutes,day_offset})=>({action_id,title,instructions,duration_minutes,day_offset}))})}}
async function load(){const e=++epoch;loading.value=true;error.value='';a.invalidate();try{const [p,c,events]=await Promise.all([api.getReviewAttempts(props.detail.wrong_id),api.getReviewConnections(props.detail.wrong_id),api.getReviewEvents(props.detail.wrong_id)]);if(e!==epoch)return;attempts.value=p.items;connections.value=c.items;operations.value=events.items.filter(item=>['analysis_adopt','learning_plan_confirm'].includes(item.action)&&!events.items.some(row=>row.undo_of===item.event_id));attemptId.value=p.items.some(item=>item.attempt_id===props.selectedAttempt)?props.selectedAttempt!:p.items[0]?.attempt_id||'';if(attemptId.value)await context();try{const rows=await getReverseGoals();if(e===epoch)goals.value=rows.filter(item=>item.source_id===props.detail.source_id).map(item=>({artifact_id:item.goal_id,title:item.title}))}catch{/* 目标关联可省略。 */}}catch{if(e===epoch)error.value='证据面板暂不可读，基础作答和历史仍可使用。'}finally{if(e===epoch)loading.value=false}}
async function changeAttempt(id:string){if(loading.value||a.dirty()||l.dirty())return;attemptId.value=id;await context()}
async function changeCourse(id:string){if(loading.value||a.dirty()||l.dirty())return;course.value=id;await context()}
async function adopt(id:string,causes:ReviewCause[]){if(loading.value||props.manualDirty||!props.canWrite)return;mode.value='adopt';await l.previewAdoption(id,{selected_causes:causes,expected_revision:props.detail.revision})}
async function undo(id:string){if(loading.value||!props.canWrite)return;mode.value='undo';await l.previewUndo(id)}
async function confirm(){if(loading.value||!props.canWrite)return;if(props.manualDirty&&mode.value==='adopt')return;const kind=mode.value;if(await l.confirm()){receipt.value=l.state.receipt;undone.value=kind==='undo';window.dispatchEvent(new CustomEvent('filemate:review-changed',{detail:{source:'review-learning'}}));emit('changed');void load()}}
watch(()=>l.state.preview,async value=>{if(value){await nextTick();confirmation.value?.focus()}})
watch([()=>props.detail.wrong_id,()=>props.detail.revision,()=>props.selectedAttempt],(value,old)=>{if(old?.[0]&&value[0]!==old[0])invalidate();void load()},{immediate:true})
function invalidate(){++epoch;a.invalidate();l.invalidate();attempts.value=[];connections.value=[];receipt.value=null}
onBeforeUnmount(invalidate)
defineExpose({dirty:()=>a.dirty()||l.dirty(),invalidate})
</script>
