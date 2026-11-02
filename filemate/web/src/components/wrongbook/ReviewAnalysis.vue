<template>
  <section class="learning-section" aria-label="分析这次回答">
    <h3>用证据分析这次回答</h3>
    <p>分析只提出可能原因。你的原答、判题与复习进度不会被改写。</p>
    <p v-if="s.loading" role="status">正在读取将发送的数据…</p><p v-if="s.error" role="alert" class="review-error">{{ s.error }}</p>
    <template v-if="s.context">
      <div class="analysis-scope"><strong>本次外发范围</strong><p>当前题目、选中原答、{{ s.context.related_attempts.length }} 次相关作答、已确认错因及 {{ s.context.source_evidence.length }} 段资料原文。</p><p>Provider {{ s.context.provider_identity }} · {{ s.context.model }} · 提示词 {{ s.context.prompt_version }}</p><details><summary>核对全部输入数据</summary><pre class="preserve analysis-input">{{ JSON.stringify(s.context,null,2) }}</pre></details></div>
      <p v-if="!enabled">模型分析未开启；仍可查看证据、整理错因和新增学习任务。</p>
      <label v-else class="analysis-consent"><input v-model="s.authorized" type="checkbox" :disabled="s.busy || s.uncertain" />我同意仅本次发送上述学习数据给配置的模型服务</label>
      <div class="review-actions"><button class="primary" :disabled="!enabled || !s.authorized || s.busy || s.uncertain" @click="c.authorizeAndAnalyze(false)">分析这次回答</button><button v-if="s.analysis?.status==='ready'" :disabled="!enabled || !s.authorized || s.busy || s.uncertain" @click="c.authorizeAndAnalyze(true)">重新分析（一次新调用）</button><button :disabled="s.busy || s.uncertain" @click="c.loadContext()">重新读取证据</button><button v-if="s.uncertain" :disabled="s.busy" @click="c.recover()">查询原请求</button><button v-if="s.busy || s.uncertain" @click="c.cancel()">取消本次分析</button></div>
    </template>
    <article v-if="s.analysis" class="analysis-result" aria-live="polite">
      <h4>{{ statusLabel(s.analysis.status) }}</h4><p v-if="s.analysis.stale" class="review-notice">这份结果属于历史证据，不能直接采纳；请重新读取后授权分析。</p><p v-if="s.analysis.error_code">{{ errors[s.analysis.error_code] || '分析暂不可用，请核对服务配置后主动重试。' }}（{{ s.analysis.error_code }}）</p>
      <template v-if="s.analysis.result">
        <h4>{{ s.analysis.result.kind === 'insufficient_evidence' ? '证据不足，仍待核对' : '可能原因，等你确认' }}</h4>
        <article v-for="cause in s.analysis.result.possible_causes" :key="cause.cause_code" class="analysis-hypothesis"><label class="analysis-consent"><input v-model="selected" type="checkbox" :value="cause.cause_code" :disabled="s.analysis.stale || !writable" />{{ causeName(cause.cause_code) }}</label><p>{{ cause.hypothesis }}</p><h5>原答依据</h5><blockquote v-for="(quote,i) in cause.answer_evidence_refs" :key="i">{{ quote.quote }}</blockquote><h5>资料依据</h5><blockquote v-for="id in cause.source_evidence_refs" :key="id">{{ quoteFor(id) || '此引用属于历史上下文，请以原分析记录为准。' }}</blockquote></article>
        <button v-if="s.analysis.result.possible_causes.length" :disabled="!selected.length || s.analysis.stale || !writable" @click="$emit('adopt',s.analysis.analysis_id,[...selected])">预览采纳所选错因</button>
        <h4>仍然未知</h4><ul><li v-for="item in s.analysis.result.uncertainties" :key="item">{{ item }}</li></ul><p v-if="!s.analysis.result.uncertainties.length">本次输出没有列出其他未知项；仍需你核对建议。</p><p><strong>下一小步：</strong>{{ s.analysis.result.smallest_action }}</p><p>{{ s.analysis.result.targeted_practice_suggestion }}</p><p>{{ s.analysis.result.schedule_suggestion }}</p><details><summary>分析依据与运行记录</summary><ul><li v-for="reason in s.analysis.result.reasons" :key="reason">{{ reason }}</li></ul><pre class="preserve">{{ JSON.stringify(s.analysis.provenance,null,2) }}</pre></details>
      </template>
    </article>
    <details v-if="s.history.length"><summary>已保存的分析历史（最近20份）</summary><ul class="learning-links"><li v-for="item in s.history" :key="item.analysis_id"><button @click="c.selectHistory(item.analysis_id)">{{ statusLabel(item.status) }} · {{ reviewTime(item.created_at) }}{{ item.stale ? ' · 历史证据' : '' }}</button></li></ul></details>
  </section>
</template>
<script setup lang="ts">
import { ref,watch } from 'vue'
import type { ReviewCause } from '../../types/wrongbook'
import type { createReviewAnalysisController } from '../../wrongbook/analysis-state'
import { reviewCauses,reviewTime } from '../../wrongbook/presentation'
const props=defineProps<{c:ReturnType<typeof createReviewAnalysisController>;enabled:boolean;writable:boolean}>()
defineEmits<{adopt:[id:string,causes:ReviewCause[]]}>()
const s=props.c.state,selected=ref<ReviewCause[]>([])
watch(()=>s.analysis,()=>{selected.value=[]})
const causeName=(code:string)=>reviewCauses.find(item=>item.value===code)?.label || code
const quoteFor=(id:string)=>s.analysis?.source_evidence?.find(item=>item.evidence_id===id)?.quote
const statusLabel=(status:string)=>({running:'正在分析',ready:'分析已保存',failed:'分析未完成',cancelled:'已取消',interrupted:'分析已中断',cancelling:'正在取消'}[status]||status)
const errors:Record<string,string>={credentials_missing:'模型密钥未配置，请在设置中保存有效凭据。',timeout:'分析超时，原答与历史已保留。',invalid_output:'模型结果未通过结构或引用校验，没有保存为有效分析。',quota_exceeded:'已到调用额度，请稍后主动重试。',provider_unavailable:'模型服务暂不可用，请检查配置后主动重试。'}
</script>
