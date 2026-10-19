<template>
  <article class="interview-coach-panel" aria-labelledby="coach-question">
    <ol class="coach-steps" aria-label="本场进度">
      <li>准备</li><li :aria-current="coach.phase !== 'summary' ? 'step' : undefined">作答与反馈</li><li :aria-current="coach.phase === 'summary' ? 'step' : undefined">汇总</li>
    </ol>
    <nav v-if="answeredQuestions?.length" class="coach-question-picker" aria-label="回看本场已答题"><button v-for="item in answeredQuestions" :key="item.index" type="button" :disabled="busy || historyLocked" :aria-pressed="coach.questionIndex===item.index && coach.phase!=='summary'" @click="$emit('select-question',item.index)">回看第 {{ item.index+1 }} 题</button><button v-if="completed && coach.phase!=='summary'" type="button" :disabled="busy" @click="$emit('select-question',null)">整场汇总</button></nav>
    <template v-if="coach.phase !== 'summary'">
      <p class="coach-kicker">第 {{ coach.questionIndex + 1 }} / {{ total }} 题 · {{ coach.phase === 'question' ? '想好再回答' : '回答已保存' }}</p>
      <h2 id="coach-question" tabindex="-1">{{ coach.question }}</h2>
      <form v-if="coach.phase === 'question' || editing" @submit.prevent="$emit('submit')">
        <label for="coach-answer">你的回答</label>
        <textarea id="coach-answer" :value="draft" name="coach_answer" maxlength="12000" rows="8" :disabled="busy || answerLocked" placeholder="说清你的判断、采取的行动，以及支持结论的证据。" @input="input" @compositionstart="$emit('composition', true)" @compositionend="$emit('composition', false)" />
        <div class="coach-answer-meta"><span>{{ draft.length }} / 12000 字</span><span>先保存，再分析</span></div>
        <slot name="answer-tools" />
        <button class="primary coach-save" :disabled="busy || answerLocked || !coach.canSubmit || !draft.trim() || composing" type="submit">{{ busy ? '正在处理…' : editing && coach.attemptId ? '保存这次重答' : '保存回答' }}</button>
      </form>
      <section v-else class="coach-feedback" aria-live="polite">
        <div class="coach-feedback-heading"><h3>一起回看这一题</h3><span>{{ coach.score == null ? '待分析' : `${coach.score.toFixed(0)} 分 · 模型参考` }}</span></div>
        <p v-if="coach.analysisStatus === 'running'">回答已保存，正在分析。可以撤销本场授权，阻止结果写入。<button type="button" :disabled="busy" @click="$emit('reload')">刷新分析状态</button></p>
        <p v-else-if="coach.analysisStatus !== 'succeeded'">{{ ['failed','interrupted','cancelled'].includes(coach.analysisStatus) ? '这次回答尚无有效分析；原文已保存，可以重试。' : '这次回答已保存，授权后可获取原句反馈。' }}</p>
        <p v-else>{{ coach.feedback }}</p>
        <div v-for="(area, name) in coach.analysis?.areas" :key="name" class="coach-evidence">
          <h4>{{ areaLabels[String(name)] || name }}</h4><blockquote v-if="area.evidence">{{ area.evidence }}</blockquote><p>{{ area.suggestion || '该项暂无具体建议。' }}</p>
        </div>
        <details v-if="coach.analysis?.dimension_evidence"><summary>查看四维评分依据</summary><p v-for="(quote, name) in coach.analysis.dimension_evidence" :key="name"><b>{{ name }}</b>：{{ quote || '没有可引用原句' }}</p></details>
        <details><summary>本次回答原文</summary><blockquote>{{ currentAnswer }}</blockquote></details>
        <div class="coach-actions"><button v-if="!answerLocked" type="button" :disabled="busy" @click="$emit('reanswer')">修改后再答</button><button v-if="coach.canRetry" type="button" :disabled="busy" @click="$emit('retry-analysis')">{{ coach.analysisStatus === 'succeeded' ? '重新分析本次回答' : '重试本次分析' }}</button><button class="primary" type="button" :disabled="busy || answerLocked || !coach.canAdvance" @click="$emit('advance')">{{ coach.questionIndex + 1 === total ? '完成并查看汇总' : '继续下一题' }}</button></div>
      </section>
      <label class="coach-consent"><input type="checkbox" :checked="externalConsent" :disabled="(busy || answerLocked) && !externalConsent" @change="$emit('consent-change', ($event.target as HTMLInputElement).checked)" /><span>本场提交后自动分析问题与文字回答；不发送音视频。可随时关闭。</span></label>
      <details v-if="coach.attemptId" class="coach-history" @toggle="historyToggle">
        <summary>查看重答历史与首末对照</summary>
        <p>每次回答独立保存。不同模型或规则的分数不计算进步幅度。</p>
        <p v-if="historyError" role="alert">{{ historyError }}</p>
        <button v-for="item in attempts" :key="item.attempt_id" type="button" :aria-pressed="selectedAttempt?.attempt_id === item.attempt_id" @click="$emit('select-attempt', item)">第 {{ item.version }} 版 · {{ item.analysis_status === 'succeeded' && !item.data_error && item.score != null ? `${item.score} 分（参考）` : '待分析' }} · {{ item.created_at }}</button>
        <button v-if="moreHistory" type="button" :disabled="busy" @click="$emit('load-history', true)">读取更早回答</button>
        <article v-if="selectedAttempt" class="coach-history-answer"><h3>第 {{ selectedAttempt.version }} 版 · 历史回答</h3><blockquote>{{ selectedAttempt.answer }}</blockquote><p v-if="selectedAttempt.analysis_status === 'succeeded'">{{ selectedAttempt.evaluation.feedback }}</p><slot name="history-media" /></article>
        <div v-if="comparison" class="coach-comparison"><section><h3>首次回答</h3><blockquote>{{ comparison.first.answer }}</blockquote></section><section><h3>末次回答</h3><blockquote>{{ comparison.last.answer }}</blockquote></section><p>{{ comparison.scores_comparable ? '两次分析来源一致，分数仍仅作模型训练参考。' : '来源不同或分析未完成，不比较分数。' }}</p></div>
      </details>
    </template>
    <section v-else class="coach-summary"><h2 id="coach-question" tabindex="-1">本场回答已保存</h2><p>到下方生成整场报告，回看当前回答的依据；未分析题目保留待分析。</p><slot name="summary" /></section>
    <p v-if="error" role="alert" class="coach-error">{{ error }} <button type="button" :disabled="busy" @click="$emit('reload')">重新读取，保留草稿</button></p>
  </article>
</template>
<script setup lang="ts">
import type { CoachView, AttemptView } from '../types/interviewCoach'
defineProps<{answeredQuestions?:{index:number;question:string}[];completed?:boolean;answerLocked?:boolean;historyLocked?:boolean;coach:CoachView;draft:string;busy:boolean;total:number;editing:boolean;composing:boolean;externalConsent:boolean;currentAnswer:string;error?:string;attempts:AttemptView[];selectedAttempt:AttemptView|null;moreHistory:boolean;historyError?:string;comparison?:{first:AttemptView;last:AttemptView;scores_comparable:boolean}|null}>()
const emit=defineEmits<{'select-question':[index:number|null];'update:draft':[text:string];composition:[active:boolean];submit:[];'retry-analysis':[];advance:[];'select-attempt':[attempt:AttemptView];reanswer:[];'consent-change':[allowed:boolean];'load-history':[more:boolean];reload:[]}>()
const areaLabels:Record<string,string>={completeness:'是否说完整',logic:'推理是否清楚',technical_coverage:'专业内容',technical_expression:'技术表达',relevance:'是否回应问题',star:'经历与行动'}
function input(event:Event){emit('update:draft',(event.target as HTMLTextAreaElement).value)}
function historyToggle(event:Event){if((event.target as HTMLDetailsElement).open)emit('load-history',false)}
</script>
