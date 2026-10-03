<template>
  <section v-if="enabled" class="career-growth" aria-labelledby="career-growth-title">
    <header><div><p>岗位训练证据</p><h2 id="career-growth-title">我的求职训练</h2></div><button :disabled="loading" @click="load">刷新求职记录</button></header>
    <p v-if="loading" role="status">正在核对求职训练记录…</p>
    <p v-if="error" role="alert">{{ error }} <button :disabled="loading" @click="load">重试求职汇总</button></p>
    <template v-if="data">
      <dl>
        <div><dt>已保存岗位</dt><dd>{{ data.counts.positions }}</dd><small>其中 {{ data.counts.active_positions }} 个可继续训练</small></div>
        <div><dt>已完成基础笔试</dt><dd>{{ data.counts.completed_written }} 轮</dd><small v-if="data.counts.written_answers">实际答对 {{ data.counts.written_correct }} / {{ data.counts.written_answers }} 题</small><small v-else>作答表现待评测</small></div>
        <div><dt>关联岗位面试</dt><dd>{{ data.counts.interviews }} 场</dd><small>已答 {{ data.counts.interview_answers }} 题，内容评估 {{ data.counts.assessed_answers }} 题</small></div>
        <div><dt>已保存对比快照</dt><dd>{{ data.counts.review_snapshots }} 份</dd><small>按当时的岗位与证据保留</small></div>
      </dl>
      <p class="method">{{ data.method }}</p>
      <p class="updated">记录更新：{{ data.updated_at ? new Date(data.updated_at).toLocaleString('zh-CN') : '尚无记录' }}<span v-if="data.counts.excluded_records"> · {{ data.counts.excluded_records }} 条异常记录未计入，原记录保留。</span></p>
      <ul v-if="data.recent.length"><li v-for="item in data.recent" :key="item.training_id"><router-link :to="{ path: '/career', query: { position: item.position_id, training: item.training_id } }">{{ item.company }} · {{ item.title }} · {{ kindText(item.kind) }}</router-link><small>{{ new Date(item.created_at).toLocaleString('zh-CN') }}</small></li></ul>
      <router-link v-else to="/career">从一个岗位开始，保存第一份训练记录</router-link>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { getCareerOverview, getCareerStatus } from '../services/api'
import type { CareerOverview } from '../types/career'
const data = shallowRef<CareerOverview | null>(null)
const loading = ref(false), error = ref(''), enabled = ref(true)
let disposed = false, epoch = 0
const kindText = (kind: string) => ({ written: '基础笔试', interview: '岗位面试', review: '对比快照' } as Record<string, string>)[kind] || kind
async function load() {
  const current = ++epoch; loading.value = true; error.value = ''
  try {
    const status = await getCareerStatus()
    if (disposed || current !== epoch) return
    enabled.value = status.enabled
    if (!status.enabled) return
    const result = await getCareerOverview()
    if (!disposed && current === epoch) data.value = result
  } catch (failure) {
    if (!disposed && current === epoch) error.value = failure instanceof Error ? failure.message : '求职汇总读取失败'
  } finally { if (current === epoch) loading.value = false }
}
onMounted(load)
onBeforeUnmount(() => { disposed = true; epoch++ })
</script>

<style scoped>
.career-growth{padding:28px;border:1px solid var(--border-subtle);border-radius:16px;background:var(--bg-surface);margin-bottom:24px;overflow-wrap:anywhere}.career-growth header{display:flex;align-items:center;justify-content:space-between;gap:16px}.career-growth h2{font-size:22px;margin:0 0 12px}.career-growth header p{color:var(--accent);font-size:12px;margin:0 0 8px}.career-growth dl{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:20px 0}.career-growth dt,.career-growth small{font-size:12px;color:var(--text-secondary)}.career-growth dd{font-size:27px;margin:10px 0}.career-growth small{display:block;line-height:1.7}.method,.updated{font-size:12px;line-height:1.9;color:var(--text-secondary)}.career-growth a{color:var(--accent);line-height:1.8}.career-growth li{margin:14px 0}.career-growth ul{padding-left:20px}.career-growth button{min-height:44px;padding:10px 14px;border-radius:10px;border:1px solid var(--accent-border);background:var(--accent-soft);color:var(--accent);cursor:pointer}.career-growth button:disabled{opacity:.5;cursor:default}.career-growth a:focus-visible,.career-growth button:focus-visible{outline:2px solid var(--accent);outline-offset:3px}@media(max-width:1000px){.career-growth dl{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:560px){.career-growth{padding:18px}.career-growth header{align-items:start}.career-growth h2{font-size:20px}.career-growth header button{flex-shrink:0}}
</style>
