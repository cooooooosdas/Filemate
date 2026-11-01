import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'

const navigationURL = new URL('../src/today/navigation.ts', import.meta.url)
const navigation = existsSync(navigationURL) ? await import(navigationURL.href) : null

function resolveTodayTask(...args) {
  assert.equal(typeof navigation?.resolveTodayTask, 'function', 'the real navigation adapter must exist')
  const result = navigation.resolveTodayTask(...args)
  assert.ok(result && typeof result === 'object', 'return an explicit navigation result')
  return result
}

function bundle() {
  return { snapshot: { scope: { goal_id: 'g1', source_ids: ['s1'] },
    facts: { goal: { goal_id: 'g1', tasks: [{ task_id: 'review-source' }] }, sources: [{ source_id: 's1' }],
      plans: [{ plan_id: 'plan /甲', source_id: 's1', days: [{ day_index: 2, day: 7, completed: false }] }],
      semester: [{ artifact_id: 'semester-original', task_id: 'later-page', completed: false }],
      plan_links: [], graph: [] } }, projection: { tasks: [], completed: [] } }
}
function task(kind, origin_refs, extra = {}) {
  return { task_id: 'projected-id', kind, goal_id: 'g1', course_id: null, source_id: 's1',
    title: '真实任务', route: '/ignored', origin_refs, evidence_refs: [], ...extra }
}

test('targets_use_real_origin_identity', () => {
  const value = bundle()
  const cases = [
    [task('review', [{ kind: 'review', id: 'wrong /甲', cycle: 'actual-cycle' }]), '/wrongbook', { wrong_id: 'wrong /甲' }],
    [task('goal', [{ kind: 'goal', id: 'g1', template_id: 'review-source' }]), '/goals', { goal: 'g1', task_id: 'review-source' }],
    [task('plan', [{ kind: 'plan', id: 'plan /甲', day_index: 2 }]), '/study-plan', { plan: 'plan /甲', day: '7' }],
    [task('semester', [{ kind: 'semester', id: 'semester-original', task_id: 'later-page' }]), '/semester', { task_id: 'later-page' }],
  ]
  for (const [entry, path, query] of cases) {
    const result = resolveTodayTask(entry, value)
    assert.equal(result.primary?.path, path)
    assert.deepEqual(result.primary?.query, query)
    assert.equal(typeof result.primary?.label, 'string')
  }
})

test('a source action uses the real source while graph links require explicit concept and course evidence', () => {
  const value = bundle()
  const entry = task('plan', [{ kind: 'plan', id: 'plan /甲', day_index: 2 }])
  let result = resolveTodayTask(entry, value)
  assert.ok(result.related.some(link => link.path === '/ai-tools' && link.query.source === 's1'))
  assert.equal(result.related.some(link => link.path === '/knowledge-graph'), false)
  value.snapshot.scope.course_id = 'course-1'
  entry.course_id = 'course-1'
  value.snapshot.facts.plan_links = [{ plan_id: 'plan /甲', day_index: 2, concept_id: 'node-actual' }]
  value.snapshot.facts.graph = [{ concept_id: 'node-actual', source_id: 's1', status: 'confirmed' }]
  result = resolveTodayTask(entry, value)
  assert.deepEqual(result.related.find(link => link.path === '/knowledge-graph')?.query,
    { graph_scope: 'course', course: 'course-1', node: 'node-actual' })
  value.snapshot.facts.graph = []
  assert.equal(resolveTodayTask(entry, value).related.some(link => link.path === '/knowledge-graph'), false)
})

test('missing precise domain references never select a first record', () => {
  const value = bundle()
  for (const entry of [task('review', []), task('plan', [{ kind: 'plan', id: 'missing', day_index: 0 }]),
    task('plan', [{ kind: 'plan', id: 'plan /甲', day_index: 1 }]),
    task('goal', [{ kind: 'goal', id: 'other-goal', template_id: 'review-source' }]),
    task('semester', [{ kind: 'semester', id: 'semester-original', task_id: 'missing' }]),
    task('programming', [], { route: '/programming' }), task('interview', [], { route: '/interview' })]) {
    const result = resolveTodayTask(entry, value)
    assert.equal(result.primary, null)
    assert.ok(result.notice.length)
    assert.equal(result.related.some(link => 'problem' in link.query || 'session' in link.query), false)
  }
})

test('untrusted route strings cannot become primary navigation', () => {
  const value = bundle()
  for (const route of ['javascript:alert(1)', 'https://external.invalid/', '//external.invalid', '/admin', '/programming?problem=first']) {
    const result = resolveTodayTask(task('unrecognized', [], { route }), value)
    assert.equal(result.primary, null)
    assert.equal(result.related.some(link => /^(?:https?:|javascript:|\/\/)/i.test(link.path)), false)
  }
  const trusted = task('review', [{ kind: 'review', id: 'real-wrong' }], { route: 'javascript:alert(1)' })
  assert.equal(resolveTodayTask(trusted, value).primary?.path, '/wrongbook', 'reconstruct from trusted identity, never execute route text')
})

test('unknown input and out-of-scope origins stay unavailable', () => {
  const value = bundle()
  for (const entry of [null, {}, [], task('review', [null]),
    task('review', [{ kind: 'review', id: 'wrong' }], { source_id: 'foreign' }),
    task('review', [{ kind: 'review', id: 'wrong' }], { goal_id: 'foreign' })]) {
    assert.equal(resolveTodayTask(entry, value).primary, null)
  }
  assert.equal(resolveTodayTask(task('review', [{ kind: 'review', id: 'wrong' }]), null).primary, null)
})
