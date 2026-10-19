<script setup lang="ts">
import { computed } from 'vue'
import { Briefcase, Code, Collection, Conversation, Reading, ShieldCheck } from '../icons'
import { configurationForScenario, interviewDirections, unavailableReason } from '../interview/configuration'
import type { DraftClientState } from '../interview/configuration'
import type { InterviewCategory, InterviewConfiguration } from '../types/interviewConfiguration'

const props=defineProps<{ modelValue:InterviewConfiguration; draft:DraftClientState; busy:boolean }>()
const emit=defineEmits<{
  'update:modelValue':[value:InterviewConfiguration]
  save:[]; restore:[]; reload:[]
}>()
const icons={general:Briefcase,technical:Code,project:Collection,creator:Conversation,learning_expression:Reading}
const selected=computed(()=>interviewDirections.find(d=>d.id===props.modelValue.category)!)
const blocked=computed(()=>unavailableReason(props.modelValue))
function patch(value:Partial<InterviewConfiguration>){emit('update:modelValue',{...props.modelValue,...value})}
function selectCategory(category:InterviewCategory){
  const direction=interviewDirections.find(d=>d.id===category)!
  patch({category,track:direction.tracks[0]!.id,language:'zh-CN',difficulty_strategy:'standard'})
}
</script>

<template>
  <div class="creator">
    <div class="creator-heading"><div><p class="step-label">01 / 选择方向</p><h2>这次，你想练好什么？</h2></div><button type="button" :disabled="busy" @click="emit('update:modelValue',configurationForScenario('求职面试','标准')!)">使用快速配置</button></div>
    <fieldset class="direction-grid"><legend class="sr-only">训练方向</legend>
      <button v-for="direction in interviewDirections.slice(0,4)" :key="direction.id" type="button" :aria-pressed="modelValue.category===direction.id" :disabled="busy" @click="selectCategory(direction.id)">
        <component :is="icons[direction.id]" :size="28" aria-hidden="true" /><strong>{{ direction.label }}</strong><span>{{ direction.description }}</span>
      </button>
    </fieldset>
    <button class="expression-link" type="button" :aria-pressed="modelValue.category==='learning_expression'" :disabled="busy" @click="selectCategory('learning_expression')"><Reading :size="24" aria-hidden="true" /><span>想结合课程资料练习？进入学习表达训练</span></button>
    <fieldset class="track-picker"><legend>{{ selected.label }}专项</legend><button v-for="track in selected.tracks" :key="track.id" type="button" :disabled="busy" :aria-pressed="modelValue.track===track.id" @click="patch({track:track.id})">{{ track.label }}</button></fieldset>
    <p class="runtime-note"><ShieldCheck :size="22" aria-hidden="true" /><span>当前使用固定题逐题训练。{{ modelValue.duration_minutes }} 分钟是目标配置，计时任务引擎尚未启用。</span></p>
    <details class="advanced"><summary>语言、难度与任务配置 <span>{{ modelValue.language==='zh-CN'?'中文':'英文' }} · {{ modelValue.difficulty }}</span></summary>
      <fieldset class="track-picker"><legend>训练语言</legend><button v-for="language in ['zh-CN','en-US'] as const" :key="language" type="button" :disabled="busy" :aria-pressed="modelValue.language===language" @click="patch({language})">{{ language==='zh-CN'?'中文':'英文（通用求职）' }}</button></fieldset>
      <fieldset class="track-picker"><legend>题目难度</legend><button v-for="difficulty in ['入门','标准','压力面'] as const" :key="difficulty" type="button" :disabled="busy" :aria-pressed="modelValue.difficulty===difficulty" @click="patch({difficulty})">{{ difficulty==='压力面'?'进阶':difficulty }}</button></fieldset>
      <div class="advanced-grid"><label>目标时长 · 尚未计时<select :value="modelValue.duration_minutes" :disabled="busy" @change="patch({duration_minutes:Number(($event.target as HTMLSelectElement).value) as InterviewConfiguration['duration_minutes']})"><option v-for="minutes in [5,10,15,20,30]" :key="minutes" :value="minutes">{{ minutes }} 分钟</option></select></label>
        <label>选题方式<select :value="modelValue.question_strategy" :disabled="busy" @change="patch({question_strategy:($event.target as HTMLSelectElement).value as InterviewConfiguration['question_strategy']})"><option value="fixed">固定题 · 已可用</option><option value="random">随机题 · 仅保存配置</option><option value="ai">AI 选题 · 仅保存配置</option><option value="mixed">混合选题 · 仅保存配置</option></select></label></div>
      <fieldset class="track-picker"><legend>追问策略</legend><button type="button" :disabled="busy" :aria-pressed="modelValue.difficulty_strategy==='standard'" @click="patch({difficulty_strategy:'standard'})">标准追问</button><button type="button" :disabled="busy" :aria-pressed="modelValue.difficulty_strategy==='challenge'" @click="patch({difficulty_strategy:'challenge'})">挑战追问（通用求职）</button></fieldset>
    </details>
    <p v-if="blocked" class="blocked" role="status">{{ blocked }}</p>
    <section class="draft-bar" aria-label="配置草稿"><div><strong>{{ draft.remote.content?'有一份已保存配置':'保存配置，下次接着准备' }}</strong><p>保存在当前学习空间。仅恢复选项与输入，不恢复 AI 或设备授权。</p></div><div class="draft-actions"><button type="button" :disabled="busy||draft.busy||!draft.ready||!draft.enabled" @click="emit('save')">{{ draft.busy?'处理中…':'保存当前配置' }}</button><button v-if="draft.remote.content" type="button" :disabled="busy||draft.busy" @click="emit('restore')">恢复已保存配置</button><button type="button" :disabled="busy||draft.busy" @click="emit('reload')">读取最新草稿</button></div></section>
    <p v-if="draft.error" class="blocked" role="alert">{{ draft.error }} 当前页面输入不会被替换。</p>
    <p v-else class="save-status" role="status">{{ !draft.ready?'正在读取配置…':draft.remote.revision?`已有草稿版本 ${draft.remote.revision} · 更改后需点击保存`:'尚未保存配置' }}</p>
    <div class="permissions"><span>麦克风：未开启</span><span>摄像头：未开启</span><span>AI 分析：需要单独授权</span></div>
  </div>
</template>

<style scoped>
.creator{font-size:17px;line-height:1.6}.creator-heading{display:flex;justify-content:space-between;gap:20px;align-items:center}.creator-heading h2{font-size:28px;line-height:1.4;margin:4px 0 20px}.step-label{font-size:15px;color:var(--accent);font-weight:700;margin:0}.creator button,.creator select{font:inherit;min-height:44px;border-radius:10px;border:1px solid var(--border-default);background:var(--bg-elevated);color:var(--text-primary);cursor:pointer;padding:10px 16px}.creator button:disabled{opacity:.55;cursor:default}.creator button:focus-visible,.creator summary:focus-visible,.creator select:focus-visible{outline:3px solid var(--accent);outline-offset:3px}.creator button[aria-pressed=true]{background:var(--accent-soft);border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent)}fieldset{border:0;padding:0;margin:0}.direction-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.direction-grid button{display:flex;flex-direction:column;align-items:start;text-align:left;gap:9px;padding:20px 16px;min-height:156px}.direction-grid strong{font-size:20px}.direction-grid span{font-size:15px;color:var(--text-secondary)}.direction-grid svg{color:var(--accent)}.expression-link{display:flex;align-items:center;gap:10px;margin:14px 0 20px;width:100%;text-align:left}.track-picker{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}.track-picker legend{float:left;width:100%;margin-bottom:10px;font-weight:700}.runtime-note{display:flex;gap:10px;align-items:start;background:var(--accent-soft);padding:16px;border-radius:12px;color:var(--text-primary)}.runtime-note svg{flex-shrink:0;margin-top:3px;color:var(--accent)}.advanced{border-block:1px solid var(--border-subtle);padding:16px 0}.advanced summary{cursor:pointer;font-weight:700;min-height:44px;align-content:center}.advanced summary span{display:inline-block;margin-left:10px;font-size:15px;color:var(--text-secondary);font-weight:400}.advanced-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.advanced-grid label{display:flex;flex-direction:column;gap:8px}.creator select{width:100%}.draft-bar{display:flex;justify-content:space-between;gap:20px;align-items:center;background:var(--bg-elevated);padding:18px;border-radius:12px;margin-top:22px}.draft-bar p{margin:4px 0 0;font-size:15px;color:var(--text-secondary)}.draft-actions{display:flex;gap:10px;flex-wrap:wrap}.blocked{border-left:3px solid var(--accent);padding:12px 16px;background:var(--accent-soft);overflow-wrap:anywhere}.permissions{display:flex;flex-wrap:wrap;gap:10px 24px;color:var(--text-secondary);font-size:15px;margin-top:12px}.save-status{font-size:15px;color:var(--text-secondary)}.sr-only{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}.runtime-note,.draft-bar{overflow-wrap:anywhere}@media(max-width:1100px){.direction-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.draft-bar{flex-direction:column;align-items:start}}@media(max-width:540px){.creator-heading{flex-direction:column;align-items:start;margin-bottom:16px}.creator-heading h2{font-size:26px;margin-bottom:0}.direction-grid{grid-template-columns:1fr 1fr}.direction-grid button{padding:14px;min-height:140px}.direction-grid strong{font-size:19px}.advanced-grid{grid-template-columns:1fr}.draft-actions{width:100%}.draft-actions button{flex:1;min-width:125px}}
</style>
