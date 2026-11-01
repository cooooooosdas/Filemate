import assert from 'node:assert/strict'
import test from 'node:test'
import { routeViewKey, hasInterviewDraft, todayItemTarget } from '../src/navigation/route-state.ts'
import * as todayNavigation from '../src/today/navigation.ts'

function routeHelper(name, ...args) {
  assert.equal(typeof todayNavigation[name], 'function', `the real ${name} must exist`)
  return todayNavigation[name](...args)
}

test('V2 review filter changes reuse the mounted workspace while legacy and explicit refresh still remount', () => {
  const before = '/wrongbook?focus=one'
  const after = '/wrongbook?q=stack&focus=two'
  assert.equal(routeViewKey('/wrongbook', before, 0, true), routeViewKey('/wrongbook', after, 0, true))
  assert.notEqual(routeViewKey('/wrongbook', before, 0, false), routeViewKey('/wrongbook', after, 0, false))
  assert.notEqual(routeViewKey('/wrongbook', before, 0, true), routeViewKey('/wrongbook', before, 1, true))
})

test('interview session query synchronization preserves the running page', () => {
  assert.equal(routeViewKey('/interview', '/interview', 0), routeViewKey('/interview', '/interview?interview=one', 0))
  assert.notEqual(routeViewKey('/interview', '/interview', 0), routeViewKey('/interview', '/interview', 1))
  assert.notEqual(routeViewKey('/programming', '/programming?submission=one', 0), routeViewKey('/programming', '/programming?submission=two', 0))
})

test('draft protection covers typed answers, recordings and preparation without treating saved answers as drafts', () => {
  const clean = { answer: '', recording: false, videoStarting: false, videoRecording: false, videoStopping: false, localRecordings: 0, preparation: false }
  assert.equal(hasInterviewDraft(clean), false)
  assert.equal(hasInterviewDraft({ ...clean, answer: '  ' }), false)
  assert.equal(hasInterviewDraft({ ...clean, answer: '我的回答' }), true)
  for (const name of ['recording', 'videoStarting', 'videoRecording', 'videoStopping', 'preparation']) assert.equal(hasInterviewDraft({ ...clean, [name]: true }), true)
  assert.equal(hasInterviewDraft({ ...clean, localRecordings: 1 }), true)
})

test('today links open the selected plan and preserve other task destinations', () => {
  assert.equal(todayItemTarget({ kind: 'plan_day', plan_id: 'plan-a', route: '/study-plan' }), '/study-plan?plan=plan-a')
  assert.equal(todayItemTarget({ kind: 'plan_day', plan_id: 'plan-b', route: '/study-plan' }), '/study-plan?plan=plan-b')
  assert.equal(todayItemTarget({ kind: 'plan_day', plan_id: 'a b&c', route: '/study-plan' }), '/study-plan?plan=a%20b%26c')
  assert.equal(todayItemTarget({ kind: 'wrong_question', route: '/wrongbook?focus=one' }), '/wrongbook?focus=one')
  assert.equal(todayItemTarget({ kind: 'plan_day', route: '/study-plan' }), '/study-plan')
})

test('course_graph_browsing_preserves_the_live_workspace_but_legacy_links_remount', () => {
  assert.equal(routeViewKey('/knowledge-graph', '/knowledge-graph?graph_scope=course&course=c', 0), routeViewKey('/knowledge-graph', '/knowledge-graph?graph_scope=course&course=c&node=n&view=outline', 0))
  assert.notEqual(routeViewKey('/knowledge-graph', '/knowledge-graph?source=a', 0), routeViewKey('/knowledge-graph', '/knowledge-graph?source=b', 0))
})

test('single route references reject duplicate or malformed identities without choosing the first value', () => {
  assert.deepEqual(routeHelper('readRouteReference', { goal: '目标 /甲' }, 'goal'), { value: '目标 /甲', present: true, notice: '' })
  assert.deepEqual(routeHelper('readRouteReference', {}, 'goal'), { value: null, present: false, notice: '' })
  for (const raw of [['one', 'two'], ['one'], null, '', 'a'.repeat(129), 'bad\nidentity', {}]) {
    const parsed = routeHelper('readRouteReference', { goal: raw }, 'goal')
    assert.equal(parsed.value, null)
    assert.equal(parsed.present, true)
    assert.ok(parsed.notice)
  }
})

test('wrongbook aliases are normalized only for V2 and ambiguous links block the record workspace', () => {
  const old = { wrong_id: 'actual-wrong', q: 'queue' }
  const legacy = routeHelper('normalizeWrongbookQuery', old, false)
  assert.deepEqual(legacy.query, old)
  assert.equal(legacy.changed, false)
  assert.equal(legacy.blocked, false)
  const v2 = routeHelper('normalizeWrongbookQuery', old, true)
  assert.deepEqual(v2.query, { focus: 'actual-wrong', q: 'queue' })
  assert.equal(v2.changed, true)
  assert.equal(v2.blocked, false)
  assert.deepEqual(old, { wrong_id: 'actual-wrong', q: 'queue' })
  for (const query of [{ wrong_id: ['one', 'two'] }, { focus: ['one', 'two'] }, { wrong_id: 'bad\nidentity' },
    { wrong_id: 'one', focus: 'two' }]) {
    for (const enabled of [true, false]) {
      const result = routeHelper('normalizeWrongbookQuery', query, enabled)
      assert.equal(result.blocked, true)
      assert.ok(result.notice)
    }
  }
})
