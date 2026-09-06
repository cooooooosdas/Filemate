<template>
  <div class="growth-page">
    <header><div><h1>成长数据</h1><p>最近学了什么、哪些还要练，在这里回顾。</p></div><button type="button" @click="load">刷新数据</button></header>
    <div v-if="loading" class="state" aria-live="polite">正在汇总本地学习数据…</div>
    <DataState v-else-if="error" :error="error" @retry="load" />
    <template v-else-if="data">
      <CompanionCard
        class="companion-overview"
        :mood="companion.mood"
        :title="companion.title"
        :message="companion.message"
        :evidence="companion.evidence"
        :route="companion.route"
        :action-label="companion.actionLabel"
        :growth="companionGrowth"
      />
      <section class="kpis">
        <article><span>知识资料</span><strong>{{ data.source_count }}</strong><small>{{ data.artifact_count }} 个学习产物</small></article>
        <article><span>练习次数</span><strong>{{ data.quiz_attempt_count }}</strong><small>{{ data.mastered_wrong_count }} 道错题已掌握</small></article>
        <article><span>待复习错题</span><strong>{{ data.pending_wrong_count }}</strong><small>连续答对两次后移出</small></article>
        <article><span>计划完成度</span><strong>{{ format(data.study_completion_rate) }}%</strong><small>{{ data.completed_study_days }}/{{ data.total_study_days }} 个学习日已完成</small></article>
        <article class="accent"><span>面试参考均分</span><strong>{{ format(data.average_interview_score) }}</strong><small>{{ data.interview_count }} 场训练 · {{ data.assessed_interview_count }} 场有模型评估</small></article>
      </section>
      <section class="grid">
        <article class="panel ability"><div class="panel-head"><div><p class="eyebrow">能力画像</p><h2>面试能力表现</h2></div><span>仅统计有模型评估的回答</span></div>
          <div v-if="Object.keys(data.interview_dimensions).length" class="bars"><div v-for="(score,name) in data.interview_dimensions" :key="name"><label><span>{{ name }}</span><b>{{ format(score) }}</b></label><i><em :style="{width:`${score}%`}"></em></i></div></div>
          <p v-else class="empty">暂无内容评估记录；本地练习仍会保存，不据此推断能力。</p>
        </article>
        <article class="panel loop"><h2>学习进度</h2><div class="loop-flow"><span>已存资料<b>{{ data.source_count }}</b></span><i>→</i><span>完成计划<b>{{ data.completed_study_days }}</b></span><i>→</i><span>掌握错题<b>{{ data.mastered_wrong_count }}</b></span></div><p>统计来自这台设备上保存的学习记录。</p></article>
      </section>
      <section class="panel evidence"><div><p class="eyebrow">真实使用反馈</p><h2>匿名产品反馈</h2><p>只统计匿名哈希、相关/不相关选择和数值指标，不导出问题原文、资料名或身份信息。</p></div><div class="evidence-metrics"><span><b>{{ data.product_feedback.total }}</b>有效标注</span><span><b>{{ format(data.product_feedback.positive_rate) }}%</b>正向率</span><button type="button" :disabled="!data.product_feedback.total" @click="exportFeedback">导出匿名 CSV</button></div></section>
      <section class="panel recent"><div class="panel-head"><div><p class="eyebrow">训练记录</p><h2>最近模拟面试</h2></div></div>
        <div v-if="data.recent_interviews.length" class="table"><div v-for="item in data.recent_interviews" :key="item.interview_id" class="row"><div><RouterLink :to="{ path: '/interview', query: { interview: item.interview_id } }"><b>{{ item.target_role }} · {{ item.status === 'completed' ? '回看回答' : '继续练习' }}</b></RouterLink><small>{{ item.scenario }} · 已答 {{ item.current_index }} 题</small></div><span :class="item.status">{{ item.status === 'completed' ? '已完成' : '进行中' }}</span><strong>{{ format(item.overall_score) }}</strong></div></div>
        <p v-else class="empty">暂无模拟面试记录</p>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { downloadAnonymousFeedback, getLearningAnalytics, type LearningAnalytics } from '../services/api'
import CompanionCard from '../components/CompanionCard.vue'
import DataState from '../components/DataState.vue'
import {
  calculateCompanionGrowth,
  getRecentCompanionEvent,
  type CompanionEvent,
  type CompanionMood
} from '../composables/useCompanion'
const data = ref<LearningAnalytics | null>(null); const loading = ref(true); const error = ref('')
const recentEvent = ref<CompanionEvent | null>(getRecentCompanionEvent())
const format = (value:number | null) => value == null ? '待评估' : Math.round(value)
const load = async () => { loading.value=true; error.value=''; try{data.value=await getLearningAnalytics()}catch(e:any){error.value=e?.message||'加载失败';ElMessage.error(error.value)}finally{loading.value=false} }
const exportFeedback = async () => { try{await downloadAnonymousFeedback();ElMessage.success('匿名评测数据已导出')}catch(error:any){ElMessage.error(error.message||'导出失败')} }
const companionGrowth = computed(() => data.value ? calculateCompanionGrowth({
  source_count: data.value.source_count,
  artifact_count: data.value.artifact_count,
  completed_study_days: data.value.completed_study_days,
  mastered_wrong_count: data.value.mastered_wrong_count,
  interview_count: data.value.interview_count
}) : null)
const companion = computed((): {
  mood: CompanionMood
  title: string
  message: string
  evidence: string
  route: string
  actionLabel: string
} => {
  if (recentEvent.value) {
    return {
      mood: recentEvent.value.mood,
      title: recentEvent.value.title,
      message: recentEvent.value.message,
      evidence: recentEvent.value.evidence,
      route: recentEvent.value.route || '/today',
      actionLabel: recentEvent.value.actionLabel || '继续学习'
    }
  }
  const analytics = data.value
  const latest = analytics?.recent_interviews?.[0]
  if (latest?.status === 'completed' && latest.overall_score != null && latest.overall_score < 60) {
    return {
      mood: 'encouraging',
      title: '这次不是失败，是一张更清楚的训练地图',
      message: '先从最近一轮回答里挑一个问题重练，我会保留原回答供你对照。',
      evidence: `依据：最近面试 ${format(latest.overall_score)} 分`,
      route: '/interview',
      actionLabel: '再练一轮'
    }
  }
  if (latest?.status === 'completed' && latest.overall_score != null && latest.overall_score >= 85) {
    return {
      mood: 'wink',
      title: '这轮表达已经很有说服力',
      message: '下一次可以提高难度，验证你在追问和压力场景下的稳定性。',
      evidence: `依据：最近面试 ${format(latest.overall_score)} 分`,
      route: '/interview',
      actionLabel: '挑战压力面'
    }
  }
  if ((analytics?.completed_study_days || 0) > 0) {
    return {
      mood: 'happy',
      title: '每完成一天，知识都会更有秩序一点',
      message: '今天的完成记录已经进入本地成长数据，可以继续处理下一项任务。',
      evidence: `依据：已完成 ${analytics?.completed_study_days || 0} 个学习日`,
      route: '/today',
      actionLabel: '查看今日任务'
    }
  }
  if ((analytics?.pending_wrong_count || 0) > 0) {
    return {
      mood: 'focused',
      title: '先把最容易遗忘的内容找回来',
      message: '待复习错题已经排入今日队列，完成后会同步更新掌握状态。',
      evidence: `依据：${analytics?.pending_wrong_count || 0} 道错题待复习`,
      route: '/today',
      actionLabel: '开始复习'
    }
  }
  return {
    mood: 'thinking',
    title: '我还需要一点真实学习记录来认识你',
    message: '完成一次资料练习或模拟面试后，这里会出现有证据的个性化建议。',
    evidence: '当前状态：样本不足，待评测',
    route: '/ai-tools',
    actionLabel: '生成第一组练习'
  }
})
onMounted(load)
</script>

<style scoped>
.growth-page{max-width:1180px;margin:0 auto;padding:28px;color:var(--text-primary)}header{display:flex;justify-content:space-between;align-items:end;gap:20px;margin-bottom:24px}header h1{font-size:32px;margin:0 0 7px}header p{margin:0;color:var(--text-secondary)}header button{padding:9px 14px;border:1px solid var(--accent-border);border-radius:9px;background:var(--accent-soft);color:var(--accent);cursor:pointer}.eyebrow{color:var(--accent)!important;font-size:11px;font-weight:800;letter-spacing:.08em}.kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px}.kpis article,.panel{background:var(--bg-surface);border:1px solid var(--border-subtle);border-radius:16px}.kpis article{min-width:0;padding:20px;display:flex;flex-direction:column}.kpis span,.kpis small{color:var(--text-secondary)}.kpis strong{font-size:34px;margin:10px 0}.kpis .accent{background:linear-gradient(145deg,var(--brand-blue),var(--brand-blue-strong));color:white;border-color:var(--brand-blue)}.kpis .accent span,.kpis .accent small{color:rgba(255,255,255,.84)}.grid{display:grid;grid-template-columns:1.35fr 1fr;gap:16px;margin-top:16px}.panel{padding:24px}.panel-head{display:flex;justify-content:space-between}.panel h2{margin:5px 0 20px;font-size:19px}.panel-head>span{font-size:12px;color:var(--text-muted)}.bars>div{margin:15px 0}.bars label{display:flex;justify-content:space-between;font-size:13px}.bars i{display:block;height:7px;background:var(--bg-elevated);border-radius:7px;margin-top:7px}.bars em{display:block;height:100%;background:var(--accent);border-radius:7px}.loop-flow{display:flex;align-items:center;gap:8px;margin:28px 0}.loop-flow span{flex:1;padding:13px 8px;text-align:center;background:var(--accent-soft);border-radius:10px;font-size:12px}.loop-flow b{display:block;font-size:22px;color:var(--accent);margin-top:5px}.loop>p:last-child,.empty{color:var(--text-muted);font-size:13px}.recent{margin-top:16px}.row{display:grid;grid-template-columns:1fr auto 60px;align-items:center;gap:18px;padding:14px 0;border-top:1px solid var(--border-subtle)}.row div{display:flex;flex-direction:column;gap:5px}.row small{color:var(--text-muted)}.row>span{font-size:12px;padding:4px 8px;border-radius:999px;background:var(--accent-soft);color:var(--accent)}.row>strong{text-align:right;font-size:22px}.state{padding:80px;text-align:center;color:var(--text-muted)}@media(max-width:980px){.kpis{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}}@media(max-width:520px){.growth-page{padding:16px}.kpis{grid-template-columns:1fr}.loop-flow{flex-direction:column}.loop-flow i{transform:rotate(90deg)}header{align-items:start;flex-direction:column}}
.evidence{display:flex;align-items:center;justify-content:space-between;gap:24px;margin-top:16px}.evidence h2{margin-bottom:8px}.evidence p{max-width:650px;margin:0;color:var(--text-secondary);font-size:13px;line-height:1.65}.evidence-metrics{display:flex;align-items:center;gap:22px}.evidence-metrics span{color:var(--text-muted);font-size:11px;text-align:right}.evidence-metrics b{display:block;color:var(--text-primary);font-size:24px}.evidence-metrics button{padding:9px 12px;border:1px solid var(--accent-border);border-radius:8px;background:var(--accent);color:white;cursor:pointer}.evidence-metrics button:disabled{opacity:.45;cursor:not-allowed}@media(max-width:760px){.evidence{align-items:flex-start;flex-direction:column}.evidence-metrics{width:100%;justify-content:space-between;flex-wrap:wrap}.evidence-metrics span{text-align:left}}
.companion-overview{margin-bottom:16px}
</style>
