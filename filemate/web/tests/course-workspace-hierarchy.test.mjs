import assert from 'node:assert/strict'
import test from 'node:test'
import { groupWorkspaceOutline } from '../src/course-graph/workspace-hierarchy.ts'

test('outline_distinguishes_same_named_children_and_marks_multi_chapter_nodes', () => {
  const chapter = (id, title, parent_id = null) => ({ id, title, parent_id, sort_order: 0, concept_count: 1, child_count: 0 })
  const stack = { id: 'merged', label: '栈', chapter_ids: ['deep', 'b-child'], source_count: 2 }
  const page = { items: [stack], total: 1, chapter_groups: [chapter('a', '基础'), chapter('b', '拓展'),
    chapter('a-child', '同名', 'a'), chapter('deep', '第三层', 'a-child'), chapter('b-child', '同名', 'b')] }
  const groups = groupWorkspaceOutline(page)
  assert.deepEqual(groups.map(g => g.title), ['基础 / 同名 / 第三层', '拓展 / 同名'])
  assert.equal(groups[0].nodes[0].id, groups[1].nodes[0].id)
  assert.equal(groups[0].nodes[0].chapter_ids.length, 2)
  assert.equal(page.total, 1) // repetition in sections does not invent mastery or totals
})

test('missing_parents_are_explicit_and_virtual_groups_are_real_labels', () => {
  const page = { items: [{ id: 'a', chapter_ids: ['leaf'] }, { id: 'b', chapter_ids: ['@unassigned'] }],
    chapter_groups: [{ id: 'leaf', title: '末章', parent_id: 'unloaded' }, { id: '@unassigned', title: '未分组', parent_id: null }] }
  const groups = groupWorkspaceOutline(page)
  assert.equal(groups[0].title, '上级章节未加载 / 末章')
  assert.equal(groups[0].incomplete, true)
  assert.equal(groups[1].title, '未分组')
})
