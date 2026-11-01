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

function actualHelper(name, ...args) {
  assert.equal(typeof navigation?.[name], 'function', `the real ${name} must exist`)
  return navigation[name](...args)
}
function oldGoalArtifact() {
  return { artifact_id: 'outside-recent-20', source_id: 's1', artifact_type: 'reverse_goal_plan', title: 'column title',
    metadata: {}, created_at: '2026-10-01T00:00:00', updated_at: '2026-10-02T00:00:00',
    content: { title: '原始考试目标', goal_type: 'exam', deadline: '2026-12-01', target_score: 90, source_id: 's1',
      source_name: '原资料', evidence_status: 'insufficient', evidence_snapshot: { quiz_attempts: 0 }, last_agent_run_id: 'saved-run',
      gaps: [{ name: '证据', current: '待评测', target: '练习', status: 'gap', evidence: '已存依据' }],
      tasks: [{ task_id: 'wanted-task', title: '阅读原资料', reason: '原理由', route: '/ai-tools', status: 'pending', due_date: '2026-11-02' }] } }
}

test('exact_goal_outside_recent_list_remains_selected', async () => {
  const requested = oldGoalArtifact(), recent = [{ goal_id: 'latest-but-unrelated' }], reads = []
  const result = await actualHelper('loadExactTodayGoal', requested.artifact_id, recent, async id => { reads.push(id); return requested })
  assert.deepEqual(reads, ['outside-recent-20'])
  assert.equal(result.goal.goal_id, requested.artifact_id)
  assert.deepEqual(result.goal.gaps, requested.content.gaps)
  assert.deepEqual(result.goal.evidence_snapshot, requested.content.evidence_snapshot)
  assert.equal(recent.length, 1, 'loading must not mutate or replan the recent list')
  const focus = actualHelper('locateGoalTask', result.goal, 'wanted-task')
  assert.equal(focus.index, 0)
  const missing = actualHelper('locateGoalTask', result.goal, 'nonexistent-task')
  assert.equal(missing.index, null)
  assert.ok(missing.notice)
})

test('a missing, malformed or foreign exact goal never falls back to the latest goal', async () => {
  for (const read of [async () => { throw Object.assign(new Error('missing'), { response: { status: 404 } }) },
    async () => ({ ...oldGoalArtifact(), artifact_type: 'summary' }), async () => ({ ...oldGoalArtifact(), artifact_id: 'foreign-goal' })]) {
    const result = await actualHelper('loadExactTodayGoal', 'outside-recent-20', [{ goal_id: 'unrelated' }], read)
    assert.equal(result.goal, null)
    assert.ok(result.notice)
  }
})

test('plan_day_and_semester_focus_do_not_choose_the_first_item', () => {
  const days = [{ day: 1 }, { day: 4 }, { day: 7 }]
  assert.equal(actualHelper('locatePlanDay', days, '7').index, 2, 'completion writes use this original zero-based index')
  for (const value of ['8', '7x', ['7', '4'], '0']) {
    const missing = actualHelper('locatePlanDay', days, value)
    assert.equal(missing.index, null)
    assert.ok(missing.notice)
  }
  const tasks = Array.from({ length: 83 }, (_, index) => ({ task_id: `task-${index + 1}` }))
  assert.deepEqual(actualHelper('locateSemesterTask', tasks, 'task-75'), { index: 74, page: 2, notice: '' })
  for (const list of [tasks.slice(0, 30), tasks.filter(row => row.task_id !== 'task-75')]) {
    const missing = actualHelper('locateSemesterTask', list, 'task-75')
    assert.equal(missing.index, null)
    assert.equal(missing.page, null)
    assert.ok(missing.notice)
  }
})

test('ambiguous domain task identities are unavailable rather than silently choosing one', () => {
  assert.equal(actualHelper('locatePlanDay', [{ day: 7 }, { day: 7 }], '7').index, null)
  assert.equal(actualHelper('locateSemesterTask', [{ task_id: 'same' }, { task_id: 'same' }], 'same').index, null)
  assert.equal(actualHelper('locateGoalTask', { tasks: [{ task_id: 'same' }, { task_id: 'same' }] }, 'same').index, null)
})

test('programming_missing_reference_is_explicit', () => {
  const problems = [{ id: 'first' }, { id: 'actual' }]
  assert.equal(actualHelper('locateProgrammingProblem', problems, 'actual').id, 'actual')
  for (const value of ['missing', ['first', 'actual'], undefined, null]) {
    const result = actualHelper('locateProgrammingProblem', problems, value)
    assert.equal(result.id, null)
    assert.match(result.notice, /选择|不存在|链接|题目/)
  }
})

test('goal interview targets preserve source focus goal scenario and target without claiming an existing session', () => {
  const goal = { goal_id: 'g1', source_id: 's1', goal_type: 'competition', title: '真实答辩目标' }
  const row = { task_id: 'task', route: '/interview', source_id: 's1', focus_wrong_id: 'wrong-one', status: 'pending' }
  const target = actualHelper('goalTaskTarget', goal, row)
  assert.deepEqual(target.query, { source: 's1', focus: 'wrong-one', goal: 'g1', scenario: '竞赛答辩', target: '真实答辩目标' })
  assert.equal(target.path, '/interview')
  assert.equal('interview' in target.query, false)
  assert.equal(/继续本场/.test(target.label), false)
  for (const route of ['javascript:alert(1)', 'https://external.invalid', '//external.invalid', '/interview?return=https://external.invalid']) {
    assert.equal(actualHelper('goalTaskTarget', goal, { ...row, route }), null)
  }
  const programming = actualHelper('goalTaskTarget', goal, { ...row, route: '/programming' })
  assert.equal(programming.path, '/programming')
  assert.deepEqual(programming.query, {})
  assert.match(programming.label, /选择/)
})

test('the existing review-evidence goal task keeps its original goal context', () => {
  const target = actualHelper('goalTaskTarget', { goal_id: 'old-goal' }, { task_id: 'review-evidence', route: '/goals', status: 'pending' })
  assert.equal(target?.path, '/goals')
  assert.deepEqual(target.query, { goal: 'old-goal', task_id: 'review-evidence' })
})
