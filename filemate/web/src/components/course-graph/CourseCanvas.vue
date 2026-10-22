<template>
  <section class="cw-canvas" aria-label="课程关系画布">
    <div class="cw-canvas-heading"><p>{{ data.mode === 'groups' ? '按章节展开知识' : '知识关系' }}<span> · {{ data.total_concepts }} 个概念</span></p><button @click="$emit('overview')"><IconFocusCentered :size="20" aria-hidden="true" />回概览</button></div>
    <p v-if="layoutError" class="cw-status" role="status">{{ layoutError }}</p>
    <p v-if="data.total_concepts === 0" class="cw-status" role="status">当前范围还没有已确认知识点。可在“整理课程”中选择资料并完成审核，或清除范围筛选。</p>
    <div ref="element" class="cw-chart" role="img" aria-label="可缩放的知识关系画布。也可使用下方键盘列表或切换大纲。" />
    <div class="cw-canvas-controls"><button aria-label="放大图谱" @click="zoom(1.25)"><IconPlus :size="22" aria-hidden="true" /></button><button aria-label="缩小图谱" @click="zoom(.8)"><IconMinus :size="22" aria-hidden="true" /></button><button @click="render(true)">重置视图</button><button @click="$emit('openList')">查看大纲</button></div>
    <p class="cw-caption">{{ data.mode === 'groups' ? '点击章节进入；章节连线汇总当前有效关系。' : '箭头保留关系原义；点击概念查看来源，双击展开一跳邻域。' }}</p>
    <p v-if="data.truncated" class="cw-status">当前为有界视图。其余知识点可通过搜索、大纲与章节分页查看。</p>
    <nav v-if="data.mode === 'groups' && data.group_total > data.group_limit" class="cw-pagination" aria-label="画布章节分页"><button :disabled="data.group_offset === 0" @click="$emit('groupPage', Math.max(0, data.group_offset-data.group_limit))">前页章节</button><span>{{ data.group_offset+1 }}–{{ Math.min(data.group_total, data.group_offset+data.group_limit) }} / {{ data.group_total }}</span><button :disabled="data.group_offset+data.group_limit >= data.group_total" @click="$emit('groupPage', data.group_offset+data.group_limit)">后页章节</button></nav>
    <details class="cw-keyboard-list"><summary>用键盘选择{{ data.mode === 'groups' ? '章节' : '知识点' }}</summary><div class="cw-list-buttons"><button v-for="group in data.groups" :key="group.id" @click="$emit('openGroup', group.id)">{{ group.title }} · {{ group.concept_count }}</button><button v-for="node in data.nodes" :key="node.id" :aria-pressed="selectedId === node.id" @click="$emit('select', node.id)">{{ node.label }}</button></div></details>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { init, use, type EChartsType } from 'echarts/core'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { IconFocusCentered, IconMinus, IconPlus } from '@tabler/icons-vue'
import { layoutWorkspaceCanvas, relationLabels, workspaceGraphViewport } from '../../course-graph/workspace-layout'
import type { WorkspaceCanvas } from '../../types/courseWorkspace'

use([GraphChart, TooltipComponent, CanvasRenderer])
const props = defineProps<{ data: WorkspaceCanvas; selectedId: string; reducedMotion: boolean }>()
const emit = defineEmits<{ select: [id: string]; openGroup: [id: string]; expand: [id: string]; overview: []; openList: []; groupPage: [offset: number] }>()
const element = ref<HTMLDivElement | null>(null)
const layout = computed(() => layoutWorkspaceCanvas(props.data)), layoutError = computed(() => layout.value.error)
let metrics: PerformanceObserver | undefined, frame = 0
let chart: EChartsType | undefined, resize: ResizeObserver | undefined, theme: MutationObserver | undefined
const short = (s: string) => [...s].length > 12 ? [...s].slice(0, 12).join('') + '…' : s
function render(reset = false) {
  if (!chart || !element.value) return
  const style = getComputedStyle(element.value), color = (name: string) => style.getPropertyValue(name).trim()
  const ink = color('--text-primary'), secondary = color('--text-muted'), accent = color('--accent'), surface = color('--bg-surface')
  const previous = chart.getOption() as { series?: { zoom?: number }[] }
  const groups = props.data.mode === 'groups'
  const nodes = groups ? props.data.groups.map((g, index) => ({ id: g.id, name: g.title, kind: 'group',
    x: 120 + index % 4 * 250, y: 80 + Math.floor(index / 4) * 130, symbol: 'roundRect', symbolSize: [132, 66],
    label: { show: true, formatter: `${short(g.title)}\n${g.concept_count} 个概念`, color: ink, fontSize: 16, lineHeight: 24 },
    itemStyle: { color: color('--accent-soft'), borderColor: accent, borderWidth: 1.5 } })) : layout.value.nodes.map(n => ({
      ...n, name: n.label, kind: 'concept', symbolSize: n.id === props.selectedId ? 64 : props.data.nodes.length > 30 ? 23 : 48,
      label: { show: props.data.nodes.length <= 30 || n.id === props.selectedId, formatter: short(n.label), color: ink, fontSize: 16, position: 'bottom' },
      itemStyle: { color: n.id === props.selectedId ? color('--accent-soft') : surface, borderColor: n.id === props.selectedId ? accent : secondary, borderWidth: n.id === props.selectedId ? 3 : 1.5 },
    }))
  const links = groups ? props.data.group_edges.map(e => ({ source: e.from_group, target: e.to_group,
    label: { show: true, formatter: `${e.relation_count} 条关系`, fontSize: 15, color: secondary } })) : layout.value.edges.map(e => ({
      source: e.from, target: e.to, name: relationLabels[e.relation], label: { show: props.data.nodes.length < 25, formatter: relationLabels[e.relation], color: secondary, fontSize: 15 },
    }))
  chart.setOption({ animation: !props.reducedMotion, animationDurationUpdate: 160, tooltip: { renderMode: 'richText', formatter: (p: unknown) => (p as { name?: string }).name || '' },
    series: [{ type: 'graph', ...workspaceGraphViewport, layout: 'none', roam: true, draggable: true, zoom: reset ? 1 : previous.series?.[0]?.zoom || 1,
      scaleLimit: { min: .3, max: 3 }, data: nodes, links, edgeSymbol: ['none', 'arrow'], edgeSymbolSize: [0, 8],
      lineStyle: { color: secondary, width: 1.5, opacity: .8, curveness: .06 }, emphasis: { focus: 'adjacency', lineStyle: { width: 3 } } }],
  }, { notMerge: true })
  if (import.meta.env.DEV) element.value.dataset.animationEnabled = String(chart.getOption().animation)
}
function zoom(factor: number) { const current = chart?.getOption() as { series?: { zoom?: number }[] } | undefined; chart?.setOption({ series: [{ zoom: Math.min(3, Math.max(.3, (current?.series?.[0]?.zoom || 1) * factor)) }] }) }
onMounted(() => {
  if (!element.value) return
  chart = init(element.value)
  if (import.meta.env.DEV && PerformanceObserver.supportedEntryTypes.includes('longtask')) {
    const tasks: { start: number; duration: number }[] = []
    metrics = new PerformanceObserver(list => { tasks.push(...list.getEntries().map(e => ({ start: e.startTime, duration: e.duration }))); if (element.value) element.value.dataset.longTasks = JSON.stringify(tasks.slice(-200)) })
    metrics.observe({ type: 'longtask', buffered: false }); element.value.dataset.longTasks = '[]'
  }
  const choose = (event: unknown, expand = false) => {
    const e = event as { dataType: string; data: { id: string; kind: string } }
    if (e.dataType !== 'node') return
    if (e.data.kind === 'group') emit('openGroup', e.data.id)
    else if (expand) emit('expand', e.data.id)
    else emit('select', e.data.id)
  }
  chart.on('click', e => choose(e)); chart.on('dblclick', e => choose(e, true))
  resize = new ResizeObserver(() => chart?.resize()); resize.observe(element.value)
  theme = new MutationObserver(() => render()); theme.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme', 'style'] })
  render(true)
  if (import.meta.env.DEV) frame = requestAnimationFrame(() => { chart?.getZr().flush(); if (element.value) element.value.dataset.firstInteractiveMs = String(performance.now()) })
})
watch(() => props.data, () => render(true))
watch(() => [props.selectedId, props.reducedMotion], () => render())
onUnmounted(() => { resize?.disconnect(); theme?.disconnect(); metrics?.disconnect(); cancelAnimationFrame(frame); chart?.dispose(); chart = undefined })
</script>
