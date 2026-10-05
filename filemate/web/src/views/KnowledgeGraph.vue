<template>
  <div class="graph-page">
    <header class="graph-header">
      <div><p class="eyebrow">从资料出发 · 用练习验证</p><h1>我的知识图谱</h1><p>看见知识之间的联系，也看清下一步该复习什么。</p></div>
      <button aria-label="刷新证据" :disabled="loading || Boolean(busy)" @click="load"><el-icon><Refresh /></el-icon>刷新证据</button>
    </header>

    <section class="extract-panel" aria-labelledby="extract-title">
      <div><h2 id="extract-title">从一份资料开始</h2><p>提取结果先保留为草稿，核对原文后再加入图谱。</p></div>
      <div class="extract-fields">
        <label>选择资料<select v-model="sourceId" :disabled="loading || Boolean(busy)"><option value="">请选择已导入的资料</option><option v-for="source in sources" :key="source.source_id" :value="source.source_id">{{ source.original_name }}</option></select></label>
        <label>提取方式<select v-model="mode" :disabled="Boolean(busy)"><option value="local">本地规则提取</option><option value="llm">模型辅助提取</option></select></label>
        <button class="primary" :disabled="!sourceId || loading || Boolean(busy) || (mode === 'llm' && !externalConsent)" @click="extract">{{ busy === 'extract' ? '正在提取…' : '提取并预览' }}<el-icon><ArrowRight /></el-icon></button>
      </div>
      <label v-if="mode === 'llm'" class="consent"><input v-model="externalConsent" type="checkbox" :disabled="!!busy" />我同意将这份资料最多 20,000 字符发送给已配置的外部模型，用于提取知识点与关系。</label>
      <p v-else class="hint">本地规则不调用外部模型；只能识别资料中的显式结构，关系不足时不会补造。</p>
      <router-link v-if="!loading && !sources.length" to="/ai-tools">先去学习工作区导入资料</router-link>
    </section>

    <div v-if="error" class="message error" role="alert"><span>{{ error }}</span><button :disabled="loading || Boolean(busy)" @click="load">重新加载</button></div>
    <p v-if="notice" class="message" role="status">{{ notice }}</p>
    <p v-if="loading" role="status" class="loading">正在读取图谱与学习证据…</p>

    <section class="profile-panel" aria-labelledby="profile-title">
      <div class="panel-heading"><div><h2 id="profile-title">我的学习画像</h2><p>依据已确认图谱中的练习记录，随作答与错题复习更新。</p></div></div>
      <dl class="profile-metrics">
        <div><dt>有作答证据的知识点</dt><dd>{{ data.profile.observed_node_count }} / {{ data.profile.node_count }}</dd></div>
        <div><dt>累计有效作答</dt><dd>{{ data.profile.attempt_count }} 次</dd></div>
        <div><dt>待复习错题</dt><dd>{{ data.profile.pending_wrong_count }} 道</dd></div>
        <div><dt>尚待评测的知识点</dt><dd>{{ data.profile.unassessed_node_count }} 个</dd></div>
      </dl>
      <div class="profile-body">
        <h3>当前复习关注点 · 展示 {{ data.profile.weaknesses.length }} / {{ data.profile.weakness_total ?? data.profile.weaknesses.length }}</h3>
        <p v-if="!data.profile.attempt_count" class="hint">还没有有效作答记录。完成关联练习后，这里会展示有依据的复习关注点。</p>
        <p v-else-if="!data.profile.weaknesses.length" class="hint">当前记录未触发复习提醒。继续练习验证；这不代表所有知识点均已掌握。</p>
        <ul v-else class="weakness-list">
          <li v-for="weakness in data.profile.weaknesses" :key="weakness.node_id">
            <button :aria-pressed="selectedId === weakness.node_id" @click="selectNode(weakness.node_id)"><strong>{{ weakness.label }}</strong><span>查看证据<el-icon><ArrowRight /></el-icon></span></button>
            <small>{{ sourceName(weakness.source_id) }}</small><p>{{ weakness.reasons.join('；') }}。</p>
            <div v-if="weakness.prerequisites.length" class="prerequisite-links"><span>建议先核对前置概念：</span><button v-for="(pre, index) in weakness.prerequisites" :key="index" :title="pre.excerpt" @click="selectNode(pre.node_id)">{{ pre.label }}</button></div>
          </li>
        </ul>
        <p v-if="data.profile.excluded_sample_count" class="warning" role="status">{{ data.profile.excluded_sample_count }} 条记录因题目已修订、时间或判题字段异常，未计入当前统计；原始作答仍保留。</p>
        <details class="metric-rules"><summary>查看统计规则</summary><p>正确率取每个知识点最近 10 次有效作答；至少 3 次且低于 50% 标记高频错误，至少 5 次且不低于 80% 标记基本掌握，10 次且不低于 90% 标记熟练。30 天未作答提示回忆验证。待复习错题按未标记掌握的题目计数。学习时长尚无可靠记录，显示待评测。</p></details>
      </div>
    </section>

    <div class="graph-layout">
      <section class="map-panel" aria-labelledby="map-title" :aria-busy="loading">
        <div class="panel-heading"><div><h2 id="map-title">知识地图</h2><p>{{ data.profile.node_count }} 个知识点 · {{ data.edge_total ?? data.edges.length }} 条已确认关系</p></div><span class="privacy-label">当前学习空间</span></div>
        <div class="map-tools">
          <label class="search"><el-icon><Search /></el-icon><input v-model="search" maxlength="160" @keyup.enter="offset = 0; load()" type="search" placeholder="查找知识点或资料" aria-label="查找知识点或资料" /></label>
          <button :disabled="loading" @click="offset = 0; load()">搜索全部</button><div class="view-switch" aria-label="显示方式"><button :aria-pressed="view === 'graph'" @click="view = 'graph'">图谱</button><button :aria-pressed="view === 'list'" @click="view = 'list'">列表</button></div>
        </div>
        <div v-if="!data.profile.node_count && !loading" class="empty"><el-icon><Share /></el-icon><h3>知识地图，从你的资料长出来</h3><p>选择上方资料，提取并确认第一组知识点。尚无练习记录的知识点会显示“待评测”。</p></div>
        <div v-else-if="!filteredNodes.length && !loading" class="empty"><h3>没有找到匹配的知识点</h3><button @click="search = ''; offset = 0; load()">清除搜索</button></div>
        <div v-show="view === 'graph' && filteredNodes.length" class="chart-wrap">
          <div ref="chartElement" class="chart" role="img" aria-label="可缩放和拖动的知识关系图；请使用列表视图以键盘查看每个知识点" />
          <div class="chart-controls"><button aria-label="放大图谱" @click="zoom(1.25)"><el-icon><Plus /></el-icon></button><button aria-label="缩小图谱" @click="zoom(0.8)"><el-icon><Minus /></el-icon></button><button @click="resetChart">重置视图</button></div>
          <p class="map-caption">滚轮缩放 · 拖动节点 · 点击查看证据。箭头方向对应下方关系说明。</p>
        </div>
        <nav v-if="data.pagination?.total" class="map-tools" aria-label="知识点分页"><span>第 {{ Math.floor(offset / 200) + 1 }} / {{ Math.ceil(data.pagination.total / 200) }} 页 · 匹配 {{ data.pagination.total }} 个</span><button :disabled="loading || offset === 0" @click="offset -= 200; load()">上一页</button><button :disabled="loading || !data.pagination.has_more" @click="offset += 200; load()">下一页</button></nav>
        <p v-if="filteredNodes.length > 100" class="hint">当前地图展示本页前100个节点；列表显示本页全部，搜索与翻页可访问全部知识点。</p>
        <ul v-if="view === 'list' && filteredNodes.length" class="node-list" aria-label="知识点列表">
          <li v-for="node in filteredNodes" :key="node.id"><button :aria-pressed="selectedId === node.id" @click="selectNode(node.id)"><span><strong>{{ node.label }}</strong><small>{{ node.source_name || sourceName(node.source_id) }}</small></span><span class="status" :class="statusClass(node)">{{ node.metrics.status }}</span></button></li>
        </ul>
        <details v-if="filteredEdges.length" class="relations"><summary>查看关系与出处（{{ filteredEdges.length }}）</summary><ul><li v-for="(edge, index) in filteredEdges" :key="index"><strong>{{ nodeLabel(edge.from) }} → {{ nodeLabel(edge.to) }}</strong><span>{{ relationLabel(edge.relation) }}</span><q>{{ edge.excerpt }}</q></li></ul></details>
      </section>

      <aside class="evidence-panel" aria-labelledby="evidence-title">
        <template v-if="selectedNode">
          <p class="eyebrow">知识点证据</p><h2 id="evidence-title">{{ selectedNode.label }}</h2>
          <div class="status-row"><span class="status" :class="statusClass(selectedNode)">{{ selectedNode.metrics.status }}</span><span>{{ selectedNode.metrics.confidence }}</span></div>
          <dl class="metrics"><div><dt>作答样本</dt><dd>{{ selectedNode.metrics.sample_count }} 次</dd></div><div><dt>正确率</dt><dd>{{ percent(selectedNode.metrics.correct_rate) }}</dd></div><div><dt>待复习错题</dt><dd>{{ selectedNode.wrong_ids.length }} 道</dd></div><div><dt>学习时长</dt><dd>待评测</dd></div></dl>
          <p class="hint">正确率基于最近 {{ selectedNode.metrics.recent_sample_count }} 次有效作答；最近作答：{{ formatDate(selectedNode.metrics.last_reviewed_at) }}。掌握状态来自已保存的作答记录。</p>
          <div class="source-evidence"><h3>资料依据</h3><p>{{ selectedNode.source_name || sourceName(selectedNode.source_id) }}<span v-if="selectedNode.page_number"> · 第 {{ selectedNode.page_number }} 页</span></p><blockquote>{{ selectedNode.excerpt }}</blockquote><small v-if="selectedNode.chunk_id">片段 {{ selectedNode.chunk_id }}</small><router-link :to="{ path: '/ai-tools', query: { source: selectedNode.source_id } }">打开来源资料<el-icon><ArrowRight /></el-icon></router-link></div>
          <section class="question-evidence"><h3>关联练习 · {{ selectedNode.questions.length }}</h3><ul v-if="selectedNode.questions.length"><li v-for="question in selectedNode.questions" :key="`${question.artifact_id}-${question.question_index}`"><router-link :to="{ path: '/ai-tools', query: { source: selectedNode.source_id, artifact: question.artifact_id } }">{{ question.read_only_snapshot ? '历史题集 · ' : '' }}第 {{ question.question_index + 1 }} 题：{{ question.question }}</router-link></li></ul><p v-else class="hint">暂无关联题目，先从这份资料生成练习。</p><router-link v-if="selectedNode.wrong_ids.length" to="/wrongbook">去错题本复习（关联 {{ selectedNode.wrong_ids.length }} 道）</router-link></section>
          <section class="recommendation"><h3>下一步怎么学</h3><p>{{ recommendation(selectedNode) }}</p><button :disabled="!!busy" @click="previewPlan">{{ busy === 'preview-plan' ? '正在读取路径…' : '预览学习路径' }}</button></section>
          <section v-if="planPreview" class="plan-preview"><h3>{{ planPreview.title }}</h3><ol><li v-for="(step, index) in planPreview.steps" :key="`${step.node_id}-${index}`"><strong>{{ step.label }}</strong><p>{{ step.reason }}</p></li></ol><p class="hint">确认后新增学习计划，不覆盖已有计划。作答证据有变化时需重新预览。</p><button class="primary" :disabled="!!busy" @click="savePlan">{{ busy === 'save-plan' ? '正在保存…' : '确认加入学习计划' }}</button></section>
        </template>
        <div v-else class="empty evidence-empty"><el-icon><Aim /></el-icon><h2 id="evidence-title">选一个知识点，查看依据</h2><p>原文片段、练习表现和复习建议会显示在这里。没有数据时保留“待评测”。</p></div>
        <div v-if="createdPlan" class="saved-plan" role="status"><p>{{ planUndone ? '这份新计划已撤销，可恢复。' : '学习计划已保存。' }}</p><router-link v-if="!planUndone" :to="{ path: '/study-plan', query: { plan: createdPlan.plan_id } }">打开学习计划</router-link><button :disabled="!!busy" @click="togglePlan">{{ planUndone ? '恢复此计划' : '撤销此计划' }}</button></div>
      </aside>
    </div>

    <section class="history-panel" aria-labelledby="history-title">
      <div class="panel-heading"><div><h2 id="history-title">提取草稿与历史</h2><p>确认后才进入知识地图；撤销只移除这一批图谱内容，保留原资料与练习。</p></div></div>
      <p v-if="!data.batches.length" class="hint">还没有提取记录。</p>
      <details v-for="batch in data.batches" :key="batch.batch_id" :open="batch.batch_id === expandedBatch" class="batch">
        <summary @click.prevent="toggleBatch(batch)"><span><strong>{{ sourceName(batch.source_id) }}</strong><small>{{ batch.mode === 'llm' ? '模型辅助' : '本地规则' }} · {{ formatDate(batch.created_at) }}</small></span><span class="status">{{ batchStatus[batch.status] }}{{ batch.stale ? ' · 来源已变更' : '' }}</span></summary>
        <div v-if="batch.batch_id === expandedBatch && batch.payload_loaded !== false" class="batch-content"><p v-if="batch.stale" class="warning">资料内容已变化，请重新提取；旧草稿不能直接确认或恢复。</p><p v-if="batch.error_code" class="error" role="alert">{{ batch.data_error ? '此批数据异常，已暂停进入图谱，请重新提取。' : '提取未成功。请重新选择资料提取，原有图谱已保留。' }}</p>
          <h3>知识点预览 · {{ batch.payload.nodes.length }}</h3><ul class="draft-nodes"><li v-for="node in batch.payload.nodes" :key="node.id"><strong>{{ node.label }}</strong><blockquote>{{ node.excerpt }}</blockquote><small v-if="node.page_number">第 {{ node.page_number }} 页</small></li></ul>
          <h3>关系预览 · {{ batch.payload.edges.length }}</h3><ul class="draft-edges"><li v-for="(edge, index) in batch.payload.edges" :key="index"><p>{{ draftLabel(batch, edge.from) }} → {{ draftLabel(batch, edge.to) }} <strong>{{ relationLabel(edge.relation) }}</strong></p><q>{{ edge.excerpt }}</q></li></ul><p v-if="!batch.payload.edges.length" class="hint">没有提取到有原文依据的关系。</p>
          <div class="batch-actions"><button v-if="batch.status === 'draft'" class="primary" :disabled="!!busy || batch.stale || batch.data_error || !batch.payload.nodes.length" @click="updateBatch(batch, 'confirm')">确认加入图谱</button><button v-if="batch.status === 'confirmed' || batch.status === 'draft'" :disabled="!!busy" @click="updateBatch(batch, 'undo')">{{ batch.status === 'draft' ? '撤销草稿' : '撤销此批图谱' }}</button><button v-if="batch.status === 'undone'" :disabled="!!busy || batch.stale || batch.data_error" @click="updateBatch(batch, 'restore')">恢复此批图谱</button><span v-if="busy === batch.batch_id" role="status">正在保存…</span></div>
        </div>
      </details>
      <nav v-if="data.pagination && data.pagination.batch_total > 20" class="map-tools" aria-label="图谱历史分页"><span>{{ batchOffset + 1 }}—{{ Math.min(batchOffset + 20, data.pagination.batch_total) }} / {{ data.pagination.batch_total }} 批</span><button :disabled="loading || batchOffset === 0" @click="batchOffset -= 20; expandedBatch = ''; load()">上一批记录</button><button :disabled="loading || batchOffset + 20 >= data.pagination.batch_total" @click="batchOffset += 20; expandedBatch = ''; load()">下一批记录</button></nav>
      <div v-if="data.plans.length" class="plan-history">
        <h3>已确认的学习路径</h3>
        <div v-for="saved in data.plans" :key="saved.plan_id" class="plan-history-row">
          <div><strong>{{ saved.title }}</strong><small>{{ saved.status === 'archived' ? '已撤销' : saved.status === 'completed' ? '已完成' : '进行中' }} · {{ formatDate(saved.updated_at) }}</small></div>
          <router-link v-if="saved.status !== 'archived'" :to="{ path: '/study-plan', query: { plan: saved.plan_id } }">打开计划</router-link>
          <button :disabled="!!busy" @click="updateSavedPlan(saved.plan_id, saved.status === 'archived' ? 'restore' : 'undo')">{{ saved.status === 'archived' ? '恢复' : '撤销' }}</button>
        </div>
      </div>
    </section>
    <details class="operation-history"><summary>操作记录 · 最近 {{ data.events.length }} 条</summary><ol><li v-for="event in data.events" :key="event.event_id"><span>{{ eventLabel(event.action) }} · {{ sourceName(event.source_id) }}</span><time>{{ formatDate(event.created_at) }}</time></li></ol><p v-if="!data.events.length" class="hint">还没有操作记录。此阶段之前的历史不会补造。</p></details>
    <p class="footnote">数据更新于 {{ formatDate(data.updated_at) }} · 知识点按资料区分；同名不代表同一概念。学习画像仅反映已记录的学习活动。</p>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { Aim, ArrowRight, Minus, Plus, Refresh, Search, Share } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import { init, use, type EChartsType } from 'echarts/core'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { getGraphNodeDetail, getGraphBatchDetail, changeGraphBatch, changeGraphPlan, confirmGraphPlan, createGraphDraft, getKnowledgeGraph, getKnowledgeSources, previewGraphPlan, type KnowledgeSource } from '../services/api'
import type { GraphBatch, GraphNode, GraphPlanPreview, GraphPlanResult, KnowledgeGraphData } from '../types/knowledgeGraph'

use([GraphChart, TooltipComponent, CanvasRenderer])
const route = useRoute()
const data = shallowRef<KnowledgeGraphData>({ nodes: [], edges: [], batches: [], plans: [], relations: {}, updated_at: '', events: [], profile: { node_count: 0, observed_node_count: 0, unassessed_node_count: 0, attempt_count: 0, pending_wrong_count: 0, excluded_sample_count: 0, study_time: null, status_counts: {}, weaknesses: [] } })
const sources = shallowRef<KnowledgeSource[]>([])
const sourceId = ref(''), mode = ref<'local' | 'llm'>('local'), externalConsent = ref(false)
const loading = ref(false), busy = ref(''), error = ref(''), notice = ref('')
const offset = ref(0), batchOffset = ref(0), selectedDetail = shallowRef<GraphNode | null>(null)
const search = ref(''), view = ref<'graph' | 'list'>('graph'), selectedId = ref(''), expandedBatch = ref('')
const planPreview = shallowRef<GraphPlanPreview | null>(null), createdPlan = shallowRef<GraphPlanResult | null>(null), planUndone = ref(false)
const chartElement = ref<HTMLDivElement | null>(null)
let chart: EChartsType | undefined, resizeObserver: ResizeObserver | undefined, disposed = false
let loadGeneration = 0
const batchStatus = { draft: '待确认', confirmed: '已确认', undone: '已撤销', failed: '提取失败' }
const nodesById = computed(() => new Map(data.value.nodes.map(node => [node.id, node])))
const sourceNames = computed(() => new Map(sources.value.map(source => [source.source_id, source.original_name])))
const selectedNode = computed(() => nodesById.value.get(selectedId.value) || (selectedDetail.value?.id === selectedId.value ? selectedDetail.value : undefined))
const filteredNodes = computed(() => data.value.nodes)
const chartNodes = computed(() => filteredNodes.value.slice(0, 100))
const filteredEdges = computed(() => {
  const ids = new Set(filteredNodes.value.map(node => node.id))
  return data.value.edges.filter(edge => ids.has(edge.from) && ids.has(edge.to))
})
function sourceName(id: string): string { return sourceNames.value.get(id) || '原资料不可用' }
function nodeLabel(id: string): string { return nodesById.value.get(id)?.label || id }
function draftLabel(batch: GraphBatch, id: string): string { return batch.payload.nodes.find(node => node.id === id)?.label || id }
function relationLabel(relation: string): string { return data.value.relations[relation] || relation }
function formatDate(value: string | null): string { return value ? new Date(value).toLocaleString('zh-CN') : '暂无记录' }
function percent(value: number | null): string { return value === null ? '待评测' : `${Math.round(value * 100)}%` }
function statusClass(node: GraphNode): string { return node.wrong_ids.length || ['高频错误', '长期遗忘风险'].includes(node.metrics.status) ? 'needs-review' : node.metrics.sample_count > 0 ? 'has-evidence' : '' }
function eventLabel(action: string): string { return ({ extract: '生成提取草稿', extract_failed: '提取失败', confirm: '确认加入图谱', undo: '撤销图谱批次', restore: '恢复图谱批次', plan_create: '创建学习计划', plan_undo: '撤销学习计划', plan_restore: '恢复学习计划' } as Record<string, string>)[action] || action }
function message(cause: unknown): string { return cause instanceof Error ? cause.message : '请求失败，请重试' }
let detailGeneration = 0
async function selectNode(id: string): Promise<void> {
  const current = ++detailGeneration
  selectedId.value = id; selectedDetail.value = null; planPreview.value = null
  if (nodesById.value.has(id)) return
  try { const node = await getGraphNodeDetail(id); if (!disposed && current === detailGeneration) selectedDetail.value = node }
  catch (cause) { if (!disposed && current === detailGeneration) error.value = message(cause) }
}
async function toggleBatch(batch: GraphBatch): Promise<void> {
  if (expandedBatch.value === batch.batch_id) { expandedBatch.value = ''; return }
  expandedBatch.value = batch.batch_id
  await loadBatchDetail(batch)
}
async function loadBatchDetail(batch: GraphBatch): Promise<void> {
  if (batch.payload_loaded !== false) return
  try {
    const detail = await getGraphBatchDetail(batch.batch_id)
    if (!disposed) data.value = { ...data.value, batches: data.value.batches.map(item => item.batch_id === detail.batch_id ? detail : item) }
  } catch (cause) { if (!disposed) error.value = message(cause) }
}
function recommendation(node: GraphNode): string {
  if (node.wrong_ids.length > 0) return `有 ${node.wrong_ids.length} 道待复习错题，建议先回到原文核对概念，再完成错题复练。`
  if (!node.metrics.sample_count) return '尚无作答证据。先阅读资料、完成关联练习，再判断需要补强的知识点。'
  if (node.metrics.status === '长期遗忘风险') return '距离上次复习已有一段时间，建议做一轮回忆练习，检查是否需要重新巩固。'
  return '已有练习证据，可以沿已确认的知识关系巩固前置概念，并继续练习验证。'
}
async function load(): Promise<void> {
  const generation = ++loadGeneration
  planPreview.value = null
  loading.value = true; error.value = ''
  try {
    const results = await Promise.allSettled([getKnowledgeGraph({ offset: offset.value, q: search.value, batch_offset: batchOffset.value }), getKnowledgeSources(200)])
    if (disposed || generation !== loadGeneration) return
    const [graph, sourceList] = results
    if (graph.status === 'fulfilled') {
      data.value = graph.value
      if (!selectedId.value && typeof route.query.node === 'string') void selectNode(route.query.node)
      const opened = data.value.batches.find(batch => batch.batch_id === expandedBatch.value)
      if (opened) await loadBatchDetail(opened)
    }
    if (sourceList.status === 'fulfilled') sources.value = sourceList.value
    const failures = results.filter((result): result is PromiseRejectedResult => result.status === 'rejected')
    if (failures.length) error.value = failures.map(result => message(result.reason)).join('；')
  } finally { if (!disposed && generation === loadGeneration) loading.value = false }
}
async function extract(): Promise<void> {
  if (!sourceId.value || busy.value) return
  busy.value = 'extract'; error.value = ''; notice.value = ''; planPreview.value = null
  try {
    const batch = await createGraphDraft(sourceId.value, mode.value, mode.value === 'llm' && externalConsent.value)
    if (disposed) return
    expandedBatch.value = batch.batch_id
    await load()
    notice.value = '提取草稿已保存。请在下方核对知识点、关系和原文，再确认加入图谱。'
  } catch (cause) { error.value = message(cause); await refreshAfterFailure() }
  finally { busy.value = '' }
}
async function refreshAfterFailure(): Promise<void> {
  try { const latest = await getKnowledgeGraph({ offset: offset.value, q: search.value, batch_offset: batchOffset.value }); if (!disposed) data.value = latest } catch { /* 保留原始错误与可重试草稿。 */ }
}
async function updateBatch(batch: GraphBatch, action: 'confirm' | 'undo' | 'restore'): Promise<void> {
  if (busy.value) return
  busy.value = batch.batch_id
  if (action === 'undo') {
    try { await ElMessageBox.confirm('撤销这批知识点与关系？原资料、作答和错题不会删除，之后可以恢复图谱。', '撤销此批图谱', { confirmButtonText: '撤销', cancelButtonText: '取消', type: 'warning' }) } catch { busy.value = ''; return }
  }
  if (disposed) return
  busy.value = batch.batch_id; error.value = ''; notice.value = ''; planPreview.value = null
  try {
    await changeGraphBatch(batch.batch_id, action)
    await load()
    notice.value = action === 'undo' ? '此批图谱已撤销，可在历史中恢复。' : '图谱已更新，学习状态仍由真实练习证据计算。'
  } catch (cause) { error.value = message(cause); await refreshAfterFailure() }
  finally { busy.value = '' }
}
async function previewPlan(): Promise<void> {
  const id = selectedId.value
  if (!id || busy.value) return
  busy.value = 'preview-plan'; error.value = ''; planPreview.value = null
  try { const preview = await previewGraphPlan(id); if (!disposed && id === selectedId.value) planPreview.value = preview }
  catch (cause) { error.value = message(cause) }
  finally { busy.value = '' }
}
async function savePlan(): Promise<void> {
  const preview = planPreview.value
  if (!preview || busy.value) return
  busy.value = 'save-plan'; error.value = ''
  try {
    const saved = await confirmGraphPlan(preview.node_id, preview.evidence_revision)
    if (disposed) return
    createdPlan.value = saved; planUndone.value = false; planPreview.value = null
    await load(); notice.value = '学习路径已加入计划，可继续记录每日完成情况。'
  }
  catch (cause) { error.value = message(cause); planPreview.value = null }
  finally { busy.value = '' }
}
async function togglePlan(): Promise<void> {
  if (!createdPlan.value || busy.value) return
  await updateSavedPlan(createdPlan.value.plan_id, planUndone.value ? 'restore' : 'undo')
}
async function updateSavedPlan(planId: string, action: 'undo' | 'restore'): Promise<void> {
  if (busy.value) return
  busy.value = 'saved-plan'; error.value = ''
  try {
    await changeGraphPlan(planId, action)
    if (disposed) return
    if (createdPlan.value?.plan_id === planId) planUndone.value = action === 'undo'
    await load()
    notice.value = action === 'undo' ? '这份学习计划已撤销，完成进度已保留。' : '这份学习计划已恢复。'
  } catch (cause) { error.value = message(cause) }
  finally { busy.value = '' }
}
function renderChart(): void {
  if (disposed || !chartElement.value || view.value !== 'graph' || !filteredNodes.value.length) return
  if (!chart) {
    chart = init(chartElement.value)
    chart.on('click', (event) => { if (event.dataType === 'node') selectNode(String((event.data as { id: string }).id)) })
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(chartElement.value)
  }
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  chart.setOption({
    animation: !reducedMotion,
    tooltip: { renderMode: 'richText', confine: true },
    series: [{
      type: 'graph', layout: chartNodes.value.length > 60 ? 'circular' : 'force', roam: true, draggable: true, scaleLimit: { min: 0.3, max: 3 },
      force: { repulsion: 240, edgeLength: [100, 150], gravity: 0.06, layoutAnimation: !reducedMotion },
      edgeSymbol: ['none', 'arrow'], edgeSymbolSize: 7,
      label: { show: true, position: 'bottom', fontSize: 14, color: '#193767', width: 100, overflow: 'truncate' },
      edgeLabel: { show: chartNodes.value.length <= 30, fontSize: 13, color: '#526581', formatter: '{c}' },
      lineStyle: { color: '#6D8077', curveness: 0.08, opacity: 0.7 },
      emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
      data: chartNodes.value.map(node => ({ id: node.id, name: node.label, value: `${node.metrics.status} · ${node.metrics.confidence}`, symbolSize: selectedId.value === node.id ? 34 : 26, itemStyle: { color: statusClass(node) === 'needs-review' ? '#9A651D' : node.metrics.sample_count ? '#245DDB' : '#6B8AC1', borderColor: '#FFFFFF', borderWidth: 3 } })),
      links: filteredEdges.value.filter(edge => chartNodes.value.some(node => node.id === edge.from) && chartNodes.value.some(node => node.id === edge.to)).map(edge => ({ source: edge.from, target: edge.to, value: relationLabel(edge.relation) }))
    }]
  }, { notMerge: true })
  chart.resize()
}
function zoom(factor: number): void {
  if (!chart) return
  const option = chart.getOption() as { series?: { zoom?: number }[] }
  const current = option.series?.[0]?.zoom || 1
  chart.setOption({ series: [{ zoom: Math.min(3, Math.max(0.3, current * factor)) }] })
}
function resetChart(): void { renderChart() }
let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(search, () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { offset.value = 0; void load() }, 300) })
watch([filteredNodes, view], async () => { await nextTick(); renderChart() })
watch(mode, () => { externalConsent.value = false })
watch(sourceId, () => { externalConsent.value = false })
onMounted(load)
onUnmounted(() => { disposed = true; loadGeneration++; detailGeneration++; clearTimeout(searchTimer); resizeObserver?.disconnect(); chart?.dispose() })
</script>

<style scoped>
.profile-panel{border:1px solid var(--border-subtle);border-radius:14px;background:#FFFFFF;margin-bottom:20px}.profile-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin:0 24px;border-top:1px solid var(--border-subtle);border-bottom:1px solid var(--border-subtle);padding:20px 0;gap:18px}.profile-metrics dt{font-size:14px;color:var(--text-secondary);line-height:1.6}.profile-metrics dd{font-size:23px;margin:8px 0 0;font-family:ui-monospace,Consolas,monospace}.profile-body{padding:22px 24px}.weakness-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;list-style:none;padding:0}.weakness-list li{border:1px solid var(--border-subtle);border-radius:10px;padding:14px;min-width:0}.weakness-list li>button{justify-content:space-between;width:100%;padding:0;border:0;min-height:44px;text-align:left}.weakness-list strong{overflow-wrap:anywhere}.weakness-list button span{display:flex;align-items:center;gap:6px;font-size:14px;white-space:nowrap}.weakness-list small{display:block;color:var(--text-muted);font-size:14px;overflow-wrap:anywhere}.weakness-list p{font-size:13px;margin-top:8px}.prerequisite-links{display:flex;gap:8px;flex-wrap:wrap;align-items:center;font-size:14px;margin-top:12px}.prerequisite-links button{padding:6px 10px;font-size:14px}.metric-rules{font-size:14px;margin-top:16px}.metric-rules summary,.operation-history summary{min-height:44px;align-content:center;cursor:pointer}.metric-rules p{padding-top:8px}.operation-history{margin-top:20px;padding:16px 24px;border:1px solid var(--border-subtle);border-radius:14px;background:#FFFFFF;font-size:13px}.operation-history li{display:flex;justify-content:space-between;gap:16px;padding:10px 0;line-height:1.6;border-bottom:1px solid var(--border-subtle)}.operation-history span{overflow-wrap:anywhere}.operation-history time{color:var(--text-muted);flex-shrink:0;font-size:14px}.operation-history ol{padding:0;list-style:none}
@media(max-width:768px){.profile-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.weakness-list{grid-template-columns:1fr}.operation-history li{flex-direction:column;gap:4px}}
.graph-page{max-width:1480px;margin:0 auto;padding:28px;color:var(--text-primary);font-family:"MiSans","HarmonyOS Sans SC","Microsoft YaHei",sans-serif}
.plan-history{margin:24px 24px 0;padding-top:20px;border-top:1px solid var(--border-subtle)}.plan-history-row{display:flex;align-items:center;gap:12px;padding:12px 0;border-top:1px solid var(--border-subtle)}.plan-history-row>div{flex:1;min-width:0}.plan-history-row strong{font-size:13px;overflow-wrap:anywhere}.plan-history-row small{display:block;font-size:14px;color:var(--text-muted);margin-top:5px}.plan-history-row a{font-size:14px}
.graph-page *{box-sizing:border-box}.graph-page h1{font-size:30px;letter-spacing:-1px;margin:4px 0 10px}.graph-page h2{font-size:19px;margin:0 0 8px}.graph-page h3{font-size:15px;margin:0 0 10px}.graph-page p{line-height:1.7;margin:0;color:var(--text-secondary)}.graph-page a{color:var(--accent);text-underline-offset:4px;overflow-wrap:anywhere}.graph-page button,.graph-page input,.graph-page select{font:inherit}.graph-page button{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:44px;padding:10px 14px;border:1px solid var(--border-subtle);border-radius:10px;background:#FFFFFF;color:var(--text-primary);cursor:pointer}.graph-page button:hover:not(:disabled){background:var(--accent-soft);border-color:var(--accent)}.graph-page button:disabled{opacity:.55;cursor:not-allowed}.graph-page .primary{color:#FFFFFF;background:var(--accent);border-color:var(--accent)}.graph-page .primary:hover:not(:disabled){background:var(--accent-hover)}.graph-page :is(button,input,select,a,summary):focus-visible{outline:2px solid var(--accent);outline-offset:3px}.graph-page .el-icon{font-size:19px;flex-shrink:0}.graph-header{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:24px}.eyebrow{font-size:14px;letter-spacing:1px;color:var(--accent)!important}.extract-panel,.map-panel,.evidence-panel,.history-panel{border:1px solid var(--border-subtle);background:#FFFFFF;border-radius:14px}.extract-panel{padding:24px;margin-bottom:20px}.extract-fields{display:grid;grid-template-columns:minmax(0,1fr) minmax(150px,.5fr) auto;gap:16px;align-items:end;margin-top:18px}.extract-fields label{display:grid;gap:8px;font-size:13px;min-width:0}.extract-fields select{width:100%;min-height:44px;border:1px solid var(--border-subtle);background:var(--bg-elevated);padding:10px;border-radius:10px;color:var(--text-primary)}.consent{display:flex;align-items:flex-start;gap:10px;font-size:13px;line-height:1.7;margin-top:14px}.consent input{width:20px;height:20px;accent-color:var(--accent);flex-shrink:0}.hint{font-size:14px;margin-top:12px!important}.message{padding:14px 18px;background:var(--accent-soft);border:1px solid var(--border-subtle);border-radius:10px;margin:14px 0;display:flex;align-items:center;justify-content:space-between;gap:16px}.error{color:var(--danger)!important}.warning{color:var(--warning)!important;margin-bottom:14px!important}.loading{padding:14px 0}.graph-layout{display:grid;grid-template-columns:minmax(0,7fr) minmax(0,5fr);gap:20px;align-items:start}.map-panel{overflow:hidden;min-width:0}.panel-heading{display:flex;justify-content:space-between;gap:16px;padding:22px 24px 18px}.panel-heading p{font-size:14px}.privacy-label{font-size:14px;color:var(--text-secondary);white-space:nowrap;padding-top:3px}.map-tools{display:flex;padding:0 24px;gap:12px;align-items:center}.search{display:flex;align-items:center;gap:8px;padding:0 12px;min-width:0;flex:1;border:1px solid var(--border-subtle);border-radius:10px}.search input{border:0;background:transparent;min-width:0;width:100%;min-height:44px;color:var(--text-primary)}.view-switch{display:flex;flex-shrink:0}.view-switch button{border-radius:0;padding:8px 12px}.view-switch button:first-child{border-radius:10px 0 0 10px}.view-switch button:last-child{border-radius:0 10px 10px 0}.view-switch button[aria-pressed=true]{background:var(--accent-soft);color:var(--accent);border-color:var(--accent)}.chart-wrap{position:relative;margin-top:16px;background:radial-gradient(var(--border-subtle) .7px,transparent .7px);background-size:18px 18px}.chart{height:470px;width:100%}.chart-controls{position:absolute;top:8px;left:20px;display:flex;gap:6px}.chart-controls button{padding:8px 11px;font-size:14px}.map-caption{font-size:14px;padding:12px 24px;background:var(--bg-elevated)}.empty{padding:70px 30px;text-align:center}.empty>.el-icon{font-size:32px;color:var(--accent);margin-bottom:18px}.empty p{font-size:13px;max-width:350px;margin:12px auto}.evidence-panel{padding:24px;min-width:0}.evidence-panel h2{font-size:24px;line-height:1.4;overflow-wrap:anywhere;margin:8px 0 12px}.status-row{display:flex;align-items:center;gap:10px;font-size:14px;color:var(--text-secondary)}.status{display:inline-block;font-size:14px;padding:5px 8px;border-radius:6px;background:var(--accent-soft);color:var(--text-secondary);white-space:nowrap}.status.needs-review{color:var(--warning);background:#FAF4E8}.status.has-evidence{color:var(--accent)}.metrics{display:grid;grid-template-columns:1fr 1fr;border-top:1px solid var(--border-subtle);border-bottom:1px solid var(--border-subtle);margin:20px 0 12px;padding:16px 0;gap:18px}.metrics dt{font-size:14px;color:var(--text-secondary)}.metrics dd{margin:5px 0 0;font-size:23px;font-family:ui-monospace,Consolas,monospace}.source-evidence,.question-evidence,.recommendation,.plan-preview{margin-top:24px;padding-top:20px;border-top:1px solid var(--border-subtle)}.source-evidence p{font-size:14px}.source-evidence blockquote,.draft-nodes blockquote{font-size:13px;line-height:1.8;margin:12px 0;padding-left:12px;border-left:3px solid var(--border-subtle);color:var(--text-secondary);overflow-wrap:anywhere;white-space:pre-wrap}.source-evidence small{display:block;font-size:10px;overflow-wrap:anywhere;color:var(--text-muted);margin-bottom:10px}.source-evidence a{display:inline-flex;align-items:center;gap:8px;font-size:13px;min-height:44px}.question-evidence ul{padding-left:18px;font-size:13px;line-height:1.8}.question-evidence li{margin:10px 0}.question-evidence>a{font-size:13px;display:inline-block;padding:12px 0}.recommendation p{font-size:13px}.recommendation button{margin-top:14px;width:100%}.plan-preview ol{padding-left:22px;font-size:13px;line-height:1.7}.plan-preview li{margin-bottom:12px}.plan-preview button{width:100%;margin-top:12px}.saved-plan{padding:14px;background:var(--accent-soft);margin-top:18px;border-radius:10px;font-size:13px}.saved-plan button{margin-top:10px;margin-left:8px}.node-list{list-style:none;padding:16px 24px;margin:0;max-height:540px;overflow:auto}.node-list li+li{margin-top:8px}.node-list button{width:100%;text-align:left;justify-content:space-between}.node-list button>span:first-child{min-width:0}.node-list strong{display:block;overflow-wrap:anywhere;font-weight:500}.node-list small{display:block;font-size:14px;color:var(--text-muted);margin-top:5px;overflow-wrap:anywhere}.node-list button[aria-pressed=true]{border-color:var(--accent);background:var(--accent-soft)}.relations{padding:16px 24px;border-top:1px solid var(--border-subtle);font-size:14px}.relations summary,.batch summary{cursor:pointer;min-height:44px;align-content:center}.relations ul{padding-left:18px;line-height:1.8}.relations li{margin:12px 0}.relations li span{margin-left:8px;color:var(--accent)}.relations q{display:block;color:var(--text-secondary);overflow-wrap:anywhere}.history-panel{margin-top:20px;padding-bottom:20px}.history-panel>.hint{padding:0 24px}.batch{margin:0 24px;border-top:1px solid var(--border-subtle)}.batch summary{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:16px 0;list-style:none}.batch summary strong{font-size:14px;overflow-wrap:anywhere}.batch summary small{display:block;font-size:14px;color:var(--text-muted);margin-top:6px}.batch summary:before{content:'+';font:20px ui-monospace;flex-shrink:0}.batch[open] summary:before{content:'−'}.batch summary>span:first-of-type{flex:1;min-width:0}.batch-content{padding:4px 0 20px}.draft-nodes{display:grid;grid-template-columns:1fr 1fr;gap:12px;list-style:none;padding:0}.draft-nodes li{border:1px solid var(--border-subtle);border-radius:10px;padding:14px;min-width:0}.draft-nodes strong{font-size:14px;overflow-wrap:anywhere}.draft-nodes small{font-size:14px;color:var(--text-muted)}.draft-edges{padding-left:20px;font-size:14px;line-height:1.8}.draft-edges li{margin-bottom:12px}.draft-edges q{color:var(--text-secondary);overflow-wrap:anywhere}.draft-edges strong{color:var(--accent)}.batch-actions{display:flex;align-items:center;gap:12px;margin-top:16px;font-size:14px}.footnote{font-size:14px;padding-top:20px}.evidence-empty{padding:60px 8px}
@media(max-width:1100px){.graph-layout{grid-template-columns:1fr}.evidence-empty{padding:24px}.extract-fields{grid-template-columns:minmax(0,1fr) minmax(140px,.6fr)}.extract-fields>.primary{grid-column:1/-1}.chart{height:420px}}
@media(max-width:600px){.graph-page{padding:18px 12px}.graph-header{align-items:flex-start;gap:10px}.graph-header h1{font-size:26px}.graph-header>button{font-size:0;padding:10px}.graph-header>button .el-icon{font-size:20px}.graph-header p:not(.eyebrow){font-size:13px}.extract-panel,.evidence-panel{padding:18px}.extract-fields{grid-template-columns:1fr}.panel-heading{padding:18px}.privacy-label{display:none}.map-tools{padding:0 18px;flex-wrap:wrap}.search{flex-basis:100%}.chart{height:360px}.map-caption{padding:12px 18px}.draft-nodes{grid-template-columns:1fr}.batch{margin:0 18px}.batch summary{flex-wrap:wrap}.batch summary>.status{margin-left:24px}.message{align-items:flex-start;flex-direction:column}.relations,.node-list{padding:16px 18px}.node-list button{align-items:flex-start}.footnote{line-height:1.8}}
</style>
