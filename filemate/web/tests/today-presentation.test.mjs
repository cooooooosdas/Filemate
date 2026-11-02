import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'

const presentationURL = new URL('../src/today/presentation.ts', import.meta.url)
const navigationURL = new URL('../src/today/navigation.ts', import.meta.url)
const presentation = existsSync(presentationURL) ? await import(presentationURL.href) : null
const navigation = existsSync(navigationURL) ? await import(navigationURL.href) : null

function presentToday(...args) {
  assert.equal(typeof presentation?.presentToday, 'function', 'the real presentation adapter must exist')
  const shown = presentation.presentToday(...args)
  assert.ok(shown && typeof shown === 'object', 'return the presentation contract')
  return shown
}
function readStoredGoal(...args) {
  assert.equal(typeof navigation?.readStoredGoal, 'function', 'the saved goal reader must exist')
  return navigation.readStoredGoal(...args)
}
function task(id, status = 'pending') {
  return { task_id: id, kind: 'goal', title: id, goal_id: 'g1', course_id: null,
    source_id: 's1', status, eligibility: 'eligible', origin_refs: [], evidence_refs: [] }
}
function bundle() {
  return {
    snapshot: { scope: { goal_id: 'g1', source_ids: ['s1'] }, study_date: '2026-11-01',
      as_of: '2026-11-01T05:00:00Z', evidence_revision: 'revision-1',
      facts: { goal: { goal_id: 'g1', title: '数据结构期末', tasks: [] },
        sources: [{ source_id: 's1', original_name: '数据结构.md' }], attempts: [], graph: [], plan_links: [] },
      coverage: { attempts: { total: 0, returned: 0, truncated: false } } },
    projection: { tasks: [task('next')], completed: [], unavailable: [], overlaps: [],
      coverage: { returned: 1, truncated: false } },
  }
}
function attempt(id, created_at, extra = {}) {
  return { attempt_id: id, source_id: 's1', created_at, judgement_status: 'verified',
    judgement_method: 'objective_rule', is_correct: 1, purpose: 'independent_review', ...extra }
}
function addAttempts(value, records) {
  value.snapshot.facts.attempts = records
  value.snapshot.coverage.attempts = { total: records.length, returned: records.length, truncated: false }
}

test('history_and_truncation_are_not_today_statistics', () => {
  const value = bundle()
  value.projection.completed = [task('old-completion', 'completed')]
  addAttempts(value, [
    attempt('boundary', '2026-10-31T16:00:00Z'),
    attempt('naive-utc', '2026-10-31T17:00:00'),
    attempt('previous-day', '2026-10-31T15:59:59Z'),
    attempt('foreign', '2026-11-01T01:00:00Z', { source_id: 's-other' }),
    attempt('pending', '2026-11-01T01:00:00Z', { judgement_status: 'pending', is_correct: null }),
  ])
  const before = structuredClone(value)
  const shown = presentToday(value, null)
  assert.equal(shown.today_attempts, 2)
  assert.equal(shown.historical_completed, 1)
  assert.equal(shown.next_task, null, 'unconfirmed candidates are not an existing day arrangement')
  assert.match(shown.coverage_notices.join(' '), /掌握/)
  assert.deepEqual(value, before, 'presentation never writes domain completion')
  value.snapshot.coverage.attempts = { total: 101, returned: 5, truncated: true }
  const limited = presentToday(value, null)
  assert.equal(limited.today_attempts, null)
  assert.match(limited.coverage_notices.join(' '), /截断|部分|上限|完整/)
})

test('only the current saved scope and server day can supply the next task', () => {
  const value = bundle()
  const saved = { study_date: '2026-11-01', revision: 1, status: 'confirmed',
    scope: value.snapshot.scope, selected: [task('done', 'completed'), task('next')], completed: [] }
  assert.equal(presentToday(value, saved).next_task?.task_id, 'next')
  assert.equal(presentToday(value, { ...saved, study_date: '2026-10-31' }).next_task, null)
  assert.equal(presentToday(value, { ...saved, scope: { goal_id: 'other', source_ids: ['s1'] } }).next_task, null)
  assert.equal(presentToday(value, { ...saved, selected: [task('not-in-snapshot')] }).next_task, null)
  value.projection.tasks[0].eligibility = 'prerequisite_unavailable'
  assert.equal(presentToday(value, saved).next_task, null)
})

test('unverifiable dates or missing coverage do not manufacture a zero', () => {
  for (const stamp of ['invalid', '2026-02-31T01:00:00Z', '2026-11-01T23:00:00Z']) {
    const value = bundle()
    addAttempts(value, [attempt('bad-time', stamp)])
    const shown = presentToday(value, null)
    assert.equal(shown.today_attempts, null, stamp)
    assert.ok(shown.coverage_notices.length)
  }
  const value = bundle()
  delete value.snapshot.coverage.attempts
  assert.equal(presentToday(value, null).today_attempts, null)
})

test('duplicate identities are counted once and labels stay bounded literal text', () => {
  const value = bundle()
  const row = attempt('same-record', '2026-11-01T01:00:00Z')
  addAttempts(value, [row, { ...row }])
  value.snapshot.facts.sources.push({ ...value.snapshot.facts.sources[0] })
  value.snapshot.facts.goal.title = '<svg onload=alert(1)>练习</svg>'
  const shown = presentToday(value, null)
  assert.equal(shown.goal_title, value.snapshot.facts.goal.title)
  assert.equal(shown.today_attempts, 1)
  assert.match(shown.scope_label, /1\s*份/)
  value.snapshot.facts.goal.title = '知'.repeat(5000)
  assert.ok(Array.from(presentToday(value, null).goal_title).length <= 160)
})

test('unknown JSON and oversized collections are handled conservatively', () => {
  for (const value of [null, [], {}, { snapshot: null, projection: null },
    { snapshot: { facts: { goal: null, attempts: {}, sources: [null] }, coverage: null }, projection: { tasks: null, completed: [null] } }]) {
    const shown = presentToday(value, null)
    assert.equal(typeof shown.goal_title, 'string')
    assert.equal(shown.today_attempts, null)
    assert.equal(shown.historical_completed, 0)
  }
  const value = bundle()
  value.projection.completed = Array.from({ length: 10000 }, (_, i) => task(`history-${i}`, 'completed'))
  value.projection.coverage = { returned: 200, truncated: true }
  assert.ok(presentToday(value, null).historical_completed <= 200)
  assert.match(presentToday(value, null).coverage_notices.join(' '), /候选|历史|任务/)
})

function storedGoal() {
  return { artifact_id: 'older-than-recent-20', source_id: 's1', artifact_type: 'reverse_goal_plan',
    title: 'column-title', metadata: {}, created_at: '2026-10-01T00:00:00', updated_at: '2026-10-02T00:00:00',
    content: { title: '保存时目标', goal_type: 'exam', deadline: '2026-12-01', target_score: 90,
      source_id: 's1', source_name: '原资料', evidence_status: 'insufficient', evidence_snapshot: { quiz_attempts: 0 },
      last_agent_run_id: 'synthetic-run', gaps: [{ name: '练习证据', current: '待评测', target: '先练习', status: 'gap', evidence: '保存时说明' }],
      tasks: [{ task_id: 'review-source', title: '读资料', reason: '原理由', route: '/ai-tools', status: 'pending', due_date: '2026-11-02' }] } }
}

test('older stored goals restore their exact saved assessment without regenerating gaps', () => {
  const artifact = storedGoal()
  const before = structuredClone(artifact)
  const restored = readStoredGoal(artifact)
  assert.ok(restored, 'a valid saved goal must restore without regeneration')
  assert.equal(restored.goal_id, artifact.artifact_id)
  assert.equal(restored.title, '保存时目标')
  assert.equal(restored.created_at, artifact.created_at)
  assert.equal(restored.updated_at, artifact.updated_at)
  assert.deepEqual(restored.gaps, before.content.gaps)
  assert.deepEqual(restored.evidence_snapshot, before.content.evidence_snapshot)
  restored.tasks[0].status = 'completed'
  assert.deepEqual(artifact, before, 'restored mutable DTO must not mutate its artifact input')
})

test('malformed stored goal DTOs are rejected without fabricating defaults', () => {
  for (const value of [null, {}, { ...storedGoal(), artifact_type: 'summary' },
    { ...storedGoal(), content: 'not-json' }, { ...storedGoal(), content: [] },
    { ...storedGoal(), content: { ...storedGoal().content, goal_type: 'invented' } },
    { ...storedGoal(), content: { ...storedGoal().content, tasks: [null] } },
    { ...storedGoal(), content: { ...storedGoal().content, gaps: 'guessed' } }]) {
    assert.equal(readStoredGoal(value), null)
  }
})

test('partial_plan_days_are_disclosed_without_changing_practice_count', () => {
  const value = bundle()
  value.snapshot.coverage.plans = { total: 1, returned: 1, truncated: false, days_truncated: true }
  const shown = presentToday(value, null)
  assert.equal(shown.today_attempts, 0, 'complete practice evidence remains independently countable')
  assert.match(shown.coverage_notices.join(' '), /天数|计划.*(?:部分|截断|上限)/)
})
