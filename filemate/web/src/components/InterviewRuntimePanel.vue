<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Clock, Conversation, VideoPlay } from '../icons'
import type { InterviewRuntime, RuntimeKind } from '../types/interviewRuntime'
import { formatRemaining, remainingSeconds } from '../interview/runtime'
const props=defineProps<{runtime:InterviewRuntime;busy:boolean}>()
const emit=defineEmits<{command:[kind:RuntimeKind]}>()
const tick=ref(performance.now()),received=ref(performance.now())
watch(()=>props.runtime,()=>{received.value=performance.now();tick.value=received.value},{immediate:true})
const timer=setInterval(()=>{tick.value=performance.now()},500)
onBeforeUnmount(()=>clearInterval(timer))
const seconds=computed(()=>remainingSeconds(props.runtime,received.value,tick.value))
const cooldown=computed(()=>Math.max(0,Math.ceil(props.runtime.event_cooldown_seconds-(tick.value-received.value)/1000)))
const running=computed(()=>props.runtime.status==='running'&&seconds.value>0)
const current=computed(()=>props.runtime.tasks[props.runtime.current_task])
const latest=computed(()=>props.runtime.events.filter(e=>e.kind==='audience').slice(-1)[0])
const labels={prepared:'准备开始',running:'连续计时中',interrupted:'已中断 · 等待继续',finished:'已主动结束',expired:'时间已到'}
</script>
<template>
  <section class="runtime-panel" aria-labelledby="runtime-title">
    <div class="runtime-top"><div><p class="eyebrow">实战训练 · {{ labels[runtime.status] }}</p><h2 id="runtime-title">{{ current?.title || '本场复盘' }}</h2></div><div class="runtime-clock"><Clock :size="26" aria-hidden="true" /><span aria-label="剩余时间" role="timer">{{ formatRemaining(seconds) }}</span></div></div>
    <ol class="runtime-steps" aria-label="实战步骤"><li v-for="task in runtime.tasks" :key="task.task_id" :aria-current="task.task_index===runtime.current_task?'step':undefined"><span>{{ task.task_index+1 }}</span><strong>{{ task.title }}</strong><small>{{ task.status==='answered'?'已保存':task.status==='skipped'?'已跳过':task.task_index===runtime.current_task?'当前步骤':'待完成' }}</small></li></ol>
    <p v-if="runtime.status==='prepared'">准备好后开始。全程连续计时，刷新或断网也不会暂停；已提交回答保存在学习空间。</p>
    <p v-else-if="runtime.status==='interrupted'">备份恢复后需主动继续。截止时间保持原值，不会重新计时。</p>
    <p v-else-if="runtime.status==='running'">{{ seconds>0?'按自己的节奏回答，可提前结束。':'正在同步结束状态，请保留未提交文字。' }} AI 预算已预留 {{ runtime.ai_reserved }} / 12 次请求，每次分析最多预留 2 次。</p>
    <p v-else>本场已经结束。已保存回答可在下方复盘与导出；未分析内容保持待评估。</p>
    <aside v-if="latest" class="audience"><Conversation :size="25" aria-hidden="true" /><div><strong>{{ latest.text }}</strong><p>{{ latest.attempt_id?'已关联一份回答依据':'可以在当前回答中回应这条评论' }}</p></div></aside>
    <div class="runtime-actions">
      <button v-if="runtime.status==='prepared'" type="button" class="primary" :disabled="busy" @click="emit('command','start')"><VideoPlay :size="22" aria-hidden="true" />开始 {{ Math.round(runtime.duration_seconds/60) }} 分钟实战</button>
      <button v-if="runtime.status==='interrupted'" type="button" class="primary" :disabled="busy||seconds===0" @click="emit('command','resume')">继续本场</button>
      <button v-if="running" type="button" :disabled="busy||cooldown>0||runtime.audience_count>=30" @click="emit('command','event')">{{ cooldown>0?`${cooldown} 秒后可互动`:'来一条模拟互动' }} · {{ runtime.audience_count }}/30</button>
      <button v-if="running&&current?.kind==='challenge'&&current.status!=='answered'" type="button" :disabled="busy" @click="emit('command','skip')">跳过这次挑战</button>
      <button v-if="['running','interrupted','prepared'].includes(runtime.status)" type="button" :disabled="busy" @click="emit('command','finish')">提前结束</button>
    </div><p class="fine">互动由规则生成，只是训练情境。内容分析仍须单独授权；不会自动打开设备。</p>
  </section>
</template>
<style scoped>
.runtime-panel{padding:26px;border:1px solid var(--border-default);border-radius:20px;background:var(--bg-elevated);font-size:17px;line-height:1.65;margin-bottom:22px;color:var(--text-primary)}.runtime-top{display:flex;justify-content:space-between;align-items:center;gap:20px}.eyebrow{font-size:15px;color:var(--accent);font-weight:700;margin:0}.runtime-top h2{font-size:30px;margin:2px 0 16px}.runtime-clock{display:flex;gap:12px;align-items:center;font-size:42px;font-variant-numeric:tabular-nums;font-weight:750;color:var(--accent)}.runtime-steps{list-style:none;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));padding:0;gap:12px}.runtime-steps li{display:grid;grid-template-columns:28px 1fr;gap:3px 8px;padding:12px;border-bottom:3px solid var(--border-default)}.runtime-steps li[aria-current]{border-color:var(--accent);background:var(--accent-soft);border-radius:8px 8px 0 0}.runtime-steps li>span{grid-row:span 2;font-size:21px;font-weight:700}.runtime-steps small,.fine,.audience p{font-size:15px;color:var(--text-secondary)}.runtime-actions{display:flex;gap:12px;flex-wrap:wrap}.runtime-actions button{min-height:48px;font:inherit;display:flex;align-items:center;justify-content:center;gap:10px;border:1px solid var(--border-default);border-radius:10px;padding:10px 18px;background:var(--bg-surface);color:var(--text-primary);cursor:pointer}.runtime-actions .primary{background:var(--accent);color:var(--text-on-accent,#fff);border-color:var(--accent)}.runtime-actions button:disabled{opacity:.55;cursor:default}.runtime-actions button:focus-visible{outline:3px solid var(--accent);outline-offset:3px}.audience{display:flex;gap:14px;border-left:3px solid var(--accent);background:var(--accent-soft);padding:16px;margin:16px 0}.audience svg{flex-shrink:0}.runtime-panel p{overflow-wrap:anywhere}@media(max-width:650px){.runtime-panel{padding:18px}.runtime-clock{font-size:34px}.runtime-steps{grid-template-columns:1fr 1fr}.runtime-steps li{padding:8px}.runtime-top h2{font-size:26px}.runtime-actions button{flex:1;min-width:140px}}
</style>
