<template>
  <section class="learning-evidence" aria-labelledby="learning-evidence-title">
    <header><div><h2 id="learning-evidence-title">学习记录与统计依据</h2><p>范围：这台设备保存的全部有效记录。最近记录链接最多展示五条。</p></div></header>
    <div class="evidence-grid">
      <article v-for="(metric, key) in profile.metrics" :key="key" :data-metric="key">
        <div class="metric-heading"><h3>{{ metric.label }}</h3><span>{{ statusLabel(metric.status) }}</span></div>
        <p class="sample">{{ metric.sample_count }} {{ metric.sample_unit }} · 更新：{{ updated(metric.updated_at) }}</p>
        <p class="observation">记录统计：{{ metric.value == null ? '待评测' : `${metric.value}${key === 'interview' ? ' 分' : '%'}` }}</p>
        <p v-if="metric.status === 'insufficient_samples'" class="sample">样本不足，待评测；摘要展示门槛为 {{ metric.minimum_samples }} {{ metric.sample_unit }}。</p>
        <p v-if="metric.status === 'historical_only'" class="sample">最近90天没有新的有效记录，这些统计仅供历史回看。</p>
        <details><summary>查看计算依据与原记录</summary><p>{{ metric.basis }}</p>
          <ul v-if="metric.records.length"><li v-for="record in metric.records" :key="record.record_id"><RouterLink :to="record.href">回看记录 {{ record.record_id }}</RouterLink></li></ul>
          <p v-else>尚无可追溯记录。</p>
          <p v-if="metric.excluded_count">已排除 {{ metric.excluded_count }} 条时间或内容异常记录，原数据保留。</p>
        </details>
      </article>
    </div>
    <p class="boundary">{{ profile.notice }}</p>
    <p class="boundary">{{ profile.unassessed_interview_turns }} 条回答没有有效模型评分；{{ profile.archived_plans_excluded }} 份已撤销计划不计入当前完成率。<template v-if="profile.unreadable_interview_sessions">另有 {{ profile.unreadable_interview_sessions }} 场面试记录暂不可解析。</template></p>
  </section>
</template>

<script setup lang="ts">
import type { LearningEvidenceMetric, LearningEvidenceProfile } from '../services/api'
defineProps<{ profile: LearningEvidenceProfile }>()
const statusLabel = (status: LearningEvidenceMetric['status']) => ({
  pending_assessment: '待评测', insufficient_samples: '样本不足，待评测',
  observed: '已有记录统计', historical_only: '仅有历史记录'
})[status]
const updated = (value: string | null) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '尚无记录'
</script>

<style scoped>
.learning-evidence{margin-top:20px;padding:24px;background:var(--bg-surface);border:1px solid var(--border-subtle);border-radius:14px}.learning-evidence h2{font-size:20px;margin:0 0 8px}.learning-evidence header p,.sample,.boundary{color:var(--text-secondary);font-size:13px;line-height:1.7}.evidence-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;margin-top:20px}.evidence-grid article{min-width:0;padding-top:16px;border-top:1px solid var(--border-subtle)}.metric-heading{display:flex;align-items:start;justify-content:space-between;gap:12px}.metric-heading h3{margin:0;font-size:16px}.metric-heading span{font-size:12px;color:var(--accent);white-space:nowrap}.observation{font-size:15px;font-weight:600}.evidence-grid details{font-size:13px;line-height:1.8}.evidence-grid summary{cursor:pointer;min-height:44px;display:flex;align-items:center;color:var(--accent)}.evidence-grid ul{padding-left:18px}.evidence-grid a{overflow-wrap:anywhere}.evidence-grid summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}.boundary{margin:16px 0 0}@media(max-width:620px){.learning-evidence{padding:16px}.evidence-grid{grid-template-columns:1fr}.metric-heading{flex-wrap:wrap}.metric-heading span{white-space:normal}}
</style>
