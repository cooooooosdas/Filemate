import assert from 'node:assert/strict'
import test from 'node:test'
import { layoutWorkspaceCanvas, workspaceGraphViewport } from '../src/course-graph/workspace-layout.ts'
import { init, use } from 'echarts/core'
import { GraphChart } from 'echarts/charts'
import { SVGRenderer } from 'echarts/renderers'

const node = (id, chapters = ['chapter']) => ({ id, label: id, aliases: [], chapter_ids: chapters, source_count: 1, member_count: 1, source_status: 'available' })
const edge = (from, to, relation) => ({ id: `${from}-${to}`, from, to, relation, relation_ids: [], evidence_count: 1 })
const data = (nodes, edges = []) => ({ mode: 'concepts', nodes, edges, groups: [] })

test('deterministic_layout_preserves_direction', () => {
  const input = data([node('b'), node('a'), node('c')], [edge('a', 'b', 'prerequisite'), edge('c', 'b', 'depends_on')])
  const a = layoutWorkspaceCanvas(input), b = layoutWorkspaceCanvas(input)
  assert.deepEqual(a, b)
  const byId = new Map(a.nodes.map(n => [n.id, n]))
  assert.ok(byId.get('a').x < byId.get('b').x)
  assert.ok(byId.get('b').x < byId.get('c').x)
  assert.deepEqual(a.edges, input.edges)
})

test('related_to_cycles_are_not_dependencies', () => {
  const input = data([node('a'), node('b')], [edge('a', 'b', 'related_to'), edge('b', 'a', 'related_to')])
  assert.equal(layoutWorkspaceCanvas(input).error, '')
})

test('invalid_dependency_cycle_uses_safe_grid_and_reports_it', () => {
  const result = layoutWorkspaceCanvas(data([node('a'), node('b')], [edge('a', 'b', 'prerequisite'), edge('b', 'a', 'prerequisite')]))
  assert.ok(result.error)
  assert.equal(result.nodes.length, 2)
  assert.ok(result.nodes.every(n => Number.isFinite(n.x) && Number.isFinite(n.y)))
})

test('isolated_and_long_label_nodes_stay_selectable', () => {
  const label = '<long-name>' + '知识'.repeat(60)
  const result = layoutWorkspaceCanvas(data([node('isolated'), { ...node('long'), label }]))
  assert.deepEqual(result.nodes.map(n => n.id), ['isolated', 'long'])
  assert.equal(result.nodes[1].label, label)
})

test('duplicate_group_members_keep_same_concept_id', () => {
  const result = layoutWorkspaceCanvas(data([node('same', ['a', 'b']), node('other', ['b'])]))
  assert.equal(new Set(result.nodes.map(n => n.id)).size, 2)
  assert.equal(result.nodes.find(n => n.id === 'same').chapter_ids.length, 2)
})

test('node_budget_remains_100', () => {
  const result = layoutWorkspaceCanvas(data(Array.from({ length: 150 }, (_, i) => node(`n${i}`))))
  assert.equal(result.nodes.length, 100)
  assert.ok(result.error)
})

test('one_hundred_isolated_nodes_use_a_bounded_grid', () => {
  const result=layoutWorkspaceCanvas({nodes:Array.from({length:100},(_,i)=>({id:String(i),label:String(i)})),edges:[]})
  assert.ok(Math.max(...result.nodes.map(n=>n.y))-Math.min(...result.nodes.map(n=>n.y))<=1200)
  assert.ok(new Set(result.nodes.map(n=>n.x)).size>1)
})

test('real_graph_projection_preserves_node_aspect_for_single_rows_and_columns', () => {
  use([GraphChart, SVGRenderer])
  for (const points of [[[0, 0]], [[0, 0], [180, 0]], [[0, 0], [0, 110]]]) {
    const chart = init(null, null, { renderer: 'svg', ssr: true, width: 700, height: 480 })
    try {
      chart.setOption({ animation: false, series: [{ type: 'graph', ...workspaceGraphViewport, layout: 'none', data: points.map(([x, y], index) => ({ id: String(index), x, y })) }] })
      const origin = chart.convertToPixel({ seriesIndex: 0 }, [0, 0])
      const dx = chart.convertToPixel({ seriesIndex: 0 }, [1, 0])[0] - origin[0]
      const dy = chart.convertToPixel({ seriesIndex: 0 }, [0, 1])[1] - origin[1]
      assert.ok(Number.isFinite(dx) && Math.abs(dx / dy - 1) < .001, `${points.length} nodes: x/y scale ${dx / dy}`)
    } finally { chart.dispose() }
  }
})
