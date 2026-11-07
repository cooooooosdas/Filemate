import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
const url = new URL('../src/today/goal-roadmap.ts', import.meta.url)
const module = existsSync(url) ? await import(url.href) : null
function roadmap(tasks) {
  assert.equal(typeof module?.groupGoalTasks, 'function', 'real goal grouping exists')
  return module.groupGoalTasks(tasks, '2026-11-06')
}
test('goal stages retain original objects, identifiers, order and unknown actions', () => {
  const tasks = [
    { task_id: 'import-source', route: '/ai-tools', status: 'pending', due_date: '2026-11-05' },
    { task_id: 'baseline-quiz', route: '/quiz', status: 'completed', due_date: '2026-11-01' },
    { task_id: 'review-evidence', route: '/growth', status: 'pending', due_date: '2026-11-07' },
    { task_id: 'custom-unknown', route: '/custom', status: 'invalidated', due_date: 'bad' },
  ]
  const groups = roadmap(tasks)
  assert.deepEqual(groups.map(group => group.key), ['prepare', 'practice', 'review', 'other'])
  assert.deepEqual(groups.flatMap(group => group.tasks), tasks)
  assert.equal(groups[0].tasks[0], tasks[0])
  assert.equal(groups[0].overdue, 1)
  assert.equal(groups[1].overdue, 0)
  assert.equal(groups[3].overdue, 0)
})
test('goal stage counts have real empty, completed and invalid-date semantics', () => {
  assert.deepEqual(roadmap([]), [])
  const groups = roadmap([{ task_id: 'review-source', status: 'pending', due_date: '2026-02-31' }])
  assert.equal(groups[0].overdue, 0)
})
