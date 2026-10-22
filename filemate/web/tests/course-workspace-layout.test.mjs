import assert from 'node:assert/strict'
import test from 'node:test'
import { layoutWorkspaceCanvas } from '../src/course-graph/workspace-layout.ts'

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
