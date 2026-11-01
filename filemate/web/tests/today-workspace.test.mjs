import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'

const workspaceURL = new URL('../src/today/workspace-state.ts', import.meta.url)
const preferencesURL = new URL('../src/today/preferences.ts', import.meta.url)
const workspaceModule = existsSync(workspaceURL) ? await import(workspaceURL.href) : null
const preferencesModule = existsSync(preferencesURL) ? await import(preferencesURL.href) : null
function createTodayWorkspace(...args) {
  assert.equal(typeof workspaceModule?.createTodayWorkspace, 'function', 'the real workspace controller must exist')
  return workspaceModule.createTodayWorkspace(...args)
}
function createTodayPreferences(...args) {
  assert.equal(typeof preferencesModule?.createTodayPreferences, 'function', 'the real preferences store must exist')
  return preferencesModule.createTodayPreferences(...args)
}
function createTodayStorage(...args) {
  assert.equal(typeof preferencesModule?.createTodayStorage, 'function', 'the per-tab storage adapter must exist')
  return preferencesModule.createTodayStorage(...args)
}

function memory() {
  const values = new Map()
  return { values, getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) }
}
function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const capabilities = { enabled: true, ui_contract: 'today-workspace-v1', rule_version: 'rules-v1',
  limits: { sources: 20, candidates: 200, selected: 20, daily_operations: 100 } }
function snapshot(scope, date = '2026-11-01', revision = 'evidence-1') {
  const resolved = { ...scope, source_ids: scope.source_ids ?? ['s1'] }
  return { snapshot: { scope: resolved, study_date: date, as_of: `${date}T01:00:00Z`, evidence_revision: revision,
    facts: { goal: { goal_id: scope.goal_id, title: scope.goal_id, tasks: [] }, sources: [{ source_id: 's1', original_name: '资料' }] },
    coverage: {} }, projection: { tasks: [], completed: [], unavailable: [], overlaps: [], coverage: {} } }
}
function fixture({ identity = 'account:one', caps = capabilities, read, wrap } = {}) {
  const store = memory(), calls = { caps: 0, identity: 0, today: 0, snapshots: [], confirms: 0 }
  let now = Date.parse('2026-11-01T01:00:00Z')
  let day = { study_date: '2026-11-01', revision: 0, status: 'not_confirmed', scope: null,
    options: null, selected: [], completed: [], stale_refs: [], latest_operation: null }
  const client = {
    getOrchestratorCapabilities: async () => { calls.caps++; if (caps instanceof Error) throw caps; return caps },
    getOrchestratorToday: async () => { calls.today++; return structuredClone(day) },
    readOrchestratorSnapshot: async scope => { calls.snapshots.push(structuredClone(scope)); return read ? read(scope) : snapshot(scope) },
    getOrchestratorGoalOptions: async () => ({ items: [], total: 0, offset: 0, limit: 30 }),
    confirmOrchestratorSchedule: async () => { calls.confirms++; throw new Error('not part of a draft read') },
  }
  const port = { client, getCourseBrowserScope: async () => { calls.identity++; return typeof identity === 'function' ? identity() : identity },
    listGraphCourses: async () => ({ items: [], total: 0, offset: 0, limit: 30 }),
    getGraphCourse: async id => ({ course_id: id, title: '明确课程',
      sources: Array.from({ length: 30 }, (_, i) => ({ source_id: `s${i + 1}`, original_name: `资料${i + 1}` })) }) }
  const workspace = createTodayWorkspace(port, store, () => now, wrap)
  return { workspace, store, calls, client, port, setNow: value => { now = value }, setDay: value => { day = value } }
}

test('initialization is shared and never silently chooses the most recent goal', async () => {
  const x = fixture()
  await Promise.all([x.workspace.initialize(), x.workspace.initialize()])
  assert.equal(x.calls.caps, 1)
  assert.equal(x.calls.identity, 1)
  assert.equal(x.calls.today, 1)
  assert.equal(x.calls.snapshots.length, 0)
  assert.equal(x.workspace.state.phase, 'ready')
  assert.equal(x.workspace.state.snapshot, null)
  assert.equal(x.workspace.state.draft, null)
  x.workspace.dispose()
})

test('a previously confirmed today scope is restored without treating a recent goal as consent', async () => {
  const x = fixture()
  x.setDay({ study_date: '2026-11-01', revision: 1, status: 'confirmed',
    scope: { goal_id: 'explicitly-saved', source_ids: ['s1'] },
    options: { available_minutes: 30, item_order: [], pinned_ids: [], excluded_ids: [], minute_overrides: {} },
    selected: [], completed: [], stale_refs: [], latest_operation: null })
  await x.workspace.initialize()
  assert.equal(x.workspace.state.snapshot?.snapshot.scope.goal_id, 'explicitly-saved')
  assert.equal(x.workspace.state.draft?.options.available_minutes, 30)
  assert.equal(x.workspace.state.dirty, false)
  assert.equal(x.calls.confirms, 0)
  x.workspace.dispose()
})

test('explicit false alone permits legacy mode; unavailable or incompatible contracts do not', async () => {
  for (const caps of [{ ...capabilities, enabled: false }, { ...capabilities, ui_contract: undefined },
    Object.assign(new Error('HTTP 404'), { response: { status: 404 } }),
    Object.assign(new Error('HTTP 401'), { response: { status: 401 } })]) {
    const x = fixture({ caps })
    await x.workspace.initialize()
    assert.equal(x.workspace.state.phase, caps.enabled === false ? 'legacy' : caps.response?.status === 401 ? 'expired' : 'error')
    assert.equal(x.calls.snapshots.length, 0)
    x.workspace.dispose()
  }
})

test('late_goal_identity_and_restore_results_are_discarded', async () => {
  const slow = deferred()
  const x = fixture({ read: scope => scope.goal_id === 'A' ? slow.promise : snapshot(scope) })
  await x.workspace.initialize()
  const pending = x.workspace.selectScope({ goal_id: 'A', source_ids: ['s1'] })
  await x.workspace.selectScope({ goal_id: 'B', source_ids: ['s1'] })
  slow.resolve(snapshot({ goal_id: 'A', source_ids: ['s1'] }))
  await pending
  assert.equal(x.workspace.state.snapshot?.snapshot.scope.goal_id, 'B')
  x.workspace.state.preview = { confirmation_token: 'old-authority' }
  x.workspace.resetIdentity()
  assert.equal(x.workspace.state.identity, null)
  assert.equal(x.workspace.state.snapshot, null)
  assert.equal(x.workspace.state.draft, null)
  assert.equal(x.workspace.state.preview, null)
  const before = x.calls.snapshots.length
  await x.workspace.selectScope({ goal_id: 'C', source_ids: ['s1'] }).catch(() => {})
  assert.equal(x.calls.snapshots.length, before, 'identity must be re-established first')
  x.workspace.dispose()

  const late = deferred()
  const y = fixture({ read: () => late.promise })
  await y.workspace.initialize()
  const request = y.workspace.selectScope({ goal_id: 'A' })
  y.workspace.dispose()
  const disposed = structuredClone(y.workspace.state)
  late.resolve(snapshot({ goal_id: 'A' }))
  await request
  assert.deepEqual(y.workspace.state, disposed)
})

test('late identity lookup cannot restore the old account after an explicit reset', async () => {
  const slowIdentity = deferred()
  let reads = 0
  const x = fixture({ identity: () => ++reads === 1 ? slowIdentity.promise : 'account:new' })
  const oldInitialization = x.workspace.initialize()
  await new Promise(resolve => setImmediate(resolve))
  x.workspace.resetIdentity()
  await x.workspace.initialize()
  assert.equal(x.workspace.state.identity, 'account:new')
  slowIdentity.resolve('account:old')
  await oldInitialization
  assert.equal(x.workspace.state.identity, 'account:new')
  assert.equal(x.workspace.state.snapshot, null)
  x.workspace.dispose()
})

test('identity lookup failure cannot retain a previously loaded account snapshot', async () => {
  let unavailable = false
  const x = fixture({ identity: () => unavailable ? null : 'account:one' })
  await x.workspace.initialize()
  await x.workspace.selectScope({ goal_id: 'A' })
  unavailable = true
  await x.workspace.refresh()
  assert.equal(x.workspace.state.identity, null)
  assert.equal(x.workspace.state.snapshot, null)
  assert.equal(x.workspace.state.draft, null)
  assert.equal(x.workspace.state.preview, null)
  assert.notEqual(x.workspace.state.phase, 'legacy')
  x.workspace.dispose()
})

test('shared sources require explicit course choice rather than a guessed first course', async () => {
  const x = fixture({ read: scope => {
    if (!scope.course_id) throw Object.assign(new Error('explicit_course_required'), { response: { status: 422 } })
    return snapshot(scope)
  } })
  await x.workspace.initialize()
  await x.workspace.selectScope({ goal_id: 'A', source_ids: ['s1'] })
  assert.equal(x.calls.snapshots.length, 1)
  assert.ok(x.workspace.state.error)
  await x.workspace.selectScope({ goal_id: 'A', course_id: 'course-explicit', source_ids: ['s1'] })
  assert.equal(x.workspace.state.snapshot.snapshot.scope.course_id, 'course-explicit')
  x.workspace.dispose()
})

test('malformed task responses never become the current rendered snapshot', async () => {
  const x = fixture({ read: scope => {
    const value = snapshot(scope)
    value.projection.tasks = [null]
    return value
  } })
  await x.workspace.initialize()
  await x.workspace.selectScope({ goal_id: 'A' })
  assert.equal(x.workspace.state.snapshot, null)
  assert.equal(x.workspace.state.draft, null)
  assert.ok(x.workspace.state.error)
  x.workspace.dispose()
})

test('the injected reactive wrapper is the only state that receives updates', async () => {
  const writes = []
  let proxy
  const x = fixture({ wrap: state => { proxy = new Proxy(state, { set(target, key, value) {
    writes.push(key); target[key] = value; return true
  } }); return proxy } })
  assert.equal(x.workspace.state, proxy)
  await x.workspace.initialize(capabilities)
  assert.equal(x.calls.caps, 0)
  assert.ok(writes.includes('phase'))
  await x.workspace.selectScope({ goal_id: 'A' })
  assert.ok(writes.includes('snapshot'))
  x.workspace.dispose()
})

test('scope_and_draft_never_save_silently', async () => {
  const x = fixture()
  await x.workspace.initialize()
  await x.workspace.selectScope({ goal_id: 'A', course_id: 'course-1', source_ids: ['s1'] })
  assert.deepEqual(x.calls.snapshots[0].source_ids, ['s1'], 'course metadata is not permission to select all sources')
  const options = { available_minutes: 0, item_order: [], pinned_ids: [], excluded_ids: [], minute_overrides: {} }
  x.workspace.state.preview = { confirmation_token: 'stale-token' }
  x.workspace.setOptions(options)
  assert.equal(x.workspace.state.draft?.options.available_minutes, 0)
  assert.equal(x.workspace.state.preview, null)
  assert.equal(x.workspace.state.dirty, true)
  assert.equal(x.calls.confirms, 0)
  options.available_minutes = 999
  assert.equal(x.workspace.state.draft.options.available_minutes, 0)
  for (const value of [NaN, Infinity, -1, 1.5, 1441]) {
    assert.throws(() => x.workspace.setOptions({ ...options, available_minutes: value }))
  }
  const before = x.calls.snapshots.length
  await x.workspace.selectScope({ goal_id: 'A', source_ids: Array.from({ length: 21 }, (_, i) => `s${i}`) }).catch(() => {})
  assert.equal(x.calls.snapshots.length, before)
  x.workspace.dispose()
})

test('dirty refresh retains the draft and a failed read retains the saved day', async () => {
  let revision = 'evidence-1', failure = false
  const x = fixture({ read: scope => { if (failure) throw new Error('HTTP 503'); return snapshot(scope, '2026-11-01', revision) } })
  await x.workspace.initialize()
  await x.workspace.selectScope({ goal_id: 'A' })
  x.workspace.setOptions({ available_minutes: 17, pinned_ids: [], item_order: [], excluded_ids: [], minute_overrides: {} })
  const draft = structuredClone(x.workspace.state.draft)
  revision = 'evidence-2'
  await x.workspace.refresh()
  assert.deepEqual(x.workspace.state.draft, draft)
  assert.match(x.workspace.state.error, /证据|变化|重新/)
  const day = structuredClone(x.workspace.state.day)
  failure = true
  await x.workspace.refresh()
  assert.deepEqual(x.workspace.state.draft, draft)
  assert.deepEqual(x.workspace.state.day, day)
  assert.ok(x.workspace.state.error)
  assert.equal(x.calls.confirms, 0)
  x.workspace.dispose()
})

test('a new server study date invalidates previous-day authority', async () => {
  let date = '2026-11-01'
  const x = fixture({ read: scope => snapshot(scope, date, `evidence-${date}`) })
  await x.workspace.initialize()
  await x.workspace.selectScope({ goal_id: 'A' })
  x.workspace.state.preview = { confirmation_token: 'yesterday' }
  date = '2026-11-02'
  x.setNow(Date.parse('2026-11-02T01:00:00Z'))
  x.setDay({ study_date: date, revision: 0, status: 'not_confirmed', scope: null,
    options: null, selected: [], completed: [], stale_refs: [], latest_operation: null })
  await x.workspace.refresh()
  assert.equal(x.workspace.state.preview, null)
  assert.equal(x.workspace.state.day.study_date, date)
  assert.equal(x.calls.confirms, 0)
  x.workspace.dispose()
})

test('preferences_and_day_rollover_are_scoped', () => {
  const store = memory()
  const one = createTodayPreferences(store, 'account:one')
  one.write({ mode: 'exam', last_goal_id: 'goal-one', confirmation_token: 'must-not-persist' })
  assert.deepEqual(createTodayPreferences(store, 'account:one').read(), { mode: 'exam', last_goal_id: 'goal-one' })
  assert.deepEqual(createTodayPreferences(store, 'account:two').read(), { mode: 'daily', last_goal_id: null })
  assert.equal([...store.values.values()].join('').includes('must-not-persist'), false)
  one.write({ mode: 'project', last_goal_id: 'goal-two' })
  assert.equal(store.values.size, 1)
  const key = [...store.values.keys()][0]
  store.values.set(key, '{broken')
  assert.deepEqual(createTodayPreferences(store, 'account:one').read(), { mode: 'daily', last_goal_id: null })
  const blocked = { getItem() { throw new Error('blocked') }, setItem() { throw new Error('blocked') }, removeItem() { throw new Error('blocked') } }
  const transient = createTodayPreferences(blocked, 'account:one')
  transient.write({ mode: 'exam', last_goal_id: 'local-only' })
  assert.deepEqual(transient.read(), { mode: 'exam', last_goal_id: 'local-only' })
})

test('completed items and invalid option references cannot be changed in a draft', async () => {
  const x = fixture({ read: scope => {
    const value = snapshot(scope)
    value.projection.completed = [{ task_id: 'done', status: 'completed' }]
    return value
  } })
  await x.workspace.initialize()
  await x.workspace.selectScope({ goal_id: 'A' })
  for (const options of [
    { available_minutes: 30, item_order: ['done'] },
    { available_minutes: 30, excluded_ids: ['done'] },
    { available_minutes: 30, minute_overrides: { done: 5 } },
    { available_minutes: 30, pinned_ids: ['missing'] },
    { available_minutes: 30, item_order: ['duplicate', 'duplicate'] },
    { available_minutes: 30, minute_overrides: { invalid: 0 } },
  ]) assert.throws(() => x.workspace.setOptions(options))
  assert.equal(x.calls.confirms, 0)
  x.workspace.dispose()
})

test('leaving preserves a pending lookup, but identity reset removes only that identity locator', async () => {
  const local = memory(), session = memory()
  const storage = createTodayStorage(local, session)
  const own = 'filemate-today-pending-v1:account%3Aone'
  const other = 'filemate-today-pending-v1:account%3Atwo'
  storage.setItem(own, '{"request_key":"keep-on-leave"}')
  storage.setItem(other, '{"request_key":"other"}')
  const x = fixture()
  const workspace = createTodayWorkspace(x.port, storage, () => Date.parse('2026-11-01T01:00:00Z'))
  await workspace.initialize()
  workspace.dispose()
  assert.ok(storage.getItem(own))
  const y = createTodayWorkspace(x.port, storage, () => Date.parse('2026-11-01T01:00:00Z'))
  await y.initialize()
  y.resetIdentity()
  assert.equal(storage.getItem(own), null)
  assert.ok(storage.getItem(other))
  y.dispose()
})

test('per-tab pending locators survive that tab refresh without crossing into another tab', () => {
  const local = memory(), firstSession = memory(), secondSession = memory()
  const first = createTodayStorage(local, firstSession), second = createTodayStorage(local, secondSession)
  const preference = 'filemate-today-preferences-v1:account-one'
  const pending = 'filemate-today-pending-v1:account-one'
  first.setItem(preference, '{"mode":"daily"}')
  first.setItem(pending, '{"request_key":"first-tab-key"}')
  second.setItem(pending, '{"request_key":"second-tab-key"}')
  assert.equal(createTodayStorage(local, firstSession).getItem(pending), '{"request_key":"first-tab-key"}')
  assert.equal(second.getItem(pending), '{"request_key":"second-tab-key"}')
  assert.equal(second.getItem(preference), '{"mode":"daily"}')
  assert.equal(local.values.has(pending), false)
  first.removeItem(pending)
  assert.equal(second.getItem(pending), '{"request_key":"second-tab-key"}')
})
