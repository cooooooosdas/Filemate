import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { createTodayWorkspace } from '../src/today/workspace-state.ts'

const moduleURL = new URL('../src/today/command-state.ts', import.meta.url)
const actual = existsSync(moduleURL) ? await import(moduleURL.href) : null
function createTodayCommands(...args) {
  assert.equal(typeof actual?.createTodayCommands, 'function', 'the real command controller must exist')
  return actual.createTodayCommands(...args)
}
const copy = value => JSON.parse(JSON.stringify(value))
const http = status => Object.assign(new Error(`HTTP ${status}`), { response: { status } })
const pendingKey = 'filemate-today-pending-v1:account%3Aone'
const scope = { goal_id: 'goal-one', course_id: 'course-one', source_ids: ['source-one'] }
const options = { available_minutes: 30, item_order: ['goal:one:task-one'], pinned_ids: [], excluded_ids: [], minute_overrides: {} }
function memory() {
  const values = new Map()
  return { values, getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) }
}
function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function fixture({ store = memory(), date = '2026-11-01' } = {}) {
  const task = { task_id: 'goal:one:task-one', kind: 'goal', title: 'private-task-title', source_id: 'source-one', goal_id: 'goal-one',
    course_id: 'course-one', status: 'pending', eligibility: 'eligible', origin_refs: [{ kind: 'goal', id: 'goal-one', task_id: 'task-one' }] }
  const state = { phase: 'ready', identity: 'account:one', generation: 1, dirty: true, error: '', write_status: 'idle',
    snapshot: { snapshot: { scope: copy(scope), study_date: date, as_of: `${date}T01:00:00Z`, evidence_revision: 'evidence-one',
      facts: { goal: { goal_id: 'goal-one', title: 'private-goal-title' }, sources: [] }, coverage: {} },
      projection: { tasks: [task], completed: [], unavailable: [], overlaps: [], coverage: {} } },
    day: { study_date: date, revision: 0, status: 'not_confirmed', scope: null, options: null, selected: [], completed: [], stale_refs: [], latest_operation: null },
    draft: { scope: copy(scope), expected_evidence_revision: 'evidence-one', options: copy(options) }, preview: null, receipt: null,
    undo_preview: null, pending: null }
  const server = { day: copy(state.day), receipts: new Map(), completed: ['existing-domain-completion'] }
  const calls = { preview: [], confirm: [], find: [], undoPreview: [], undo: [], refresh: 0 }
  let tokens = 0
  function receipt(requestKey, status = 'confirmed', receiptDate = state.snapshot.snapshot.study_date) {
    return { operation_id: `operation-${requestKey}`, request_key: requestKey, study_date: receiptDate,
      revision: status === 'confirmed' ? 1 : 2, status, affected: {} }
  }
  function accept(request, result = receipt(request.request_key)) {
    server.receipts.set(request.request_key, result)
    server.day = { ...copy(server.day), study_date: result.study_date, revision: result.revision, status: 'confirmed',
      scope: copy(request.scope), options: copy(request.options), selected: [copy(task)], latest_operation: copy(result) }
    return result
  }
  const handlers = {
    preview: async request => ({ rule_version: 'rules-one', selected: [copy(task)], deferred: [], deferred_count: 0,
      deferred_counts: {}, deferred_truncated: false, completed: [], coverage: {}, estimated_minutes: 30,
      scope: copy(request.scope), study_date: state.snapshot.snapshot.study_date, as_of: `${date}T01:00:00Z`,
      evidence_revision: request.expected_evidence_revision, day_revision: server.day.revision, changes: { added: 1 },
      confirmation_token: (++tokens % 2 ? 'a' : 'b').repeat(64), expires_in_seconds: 900 }),
    confirm: async request => accept(request),
    find: async key => { if (!server.receipts.has(key)) throw http(404); return copy(server.receipts.get(key)) },
    undoPreview: async operationId => ({ operation_id: operationId, study_date: server.day.study_date,
      day_revision: server.day.revision, confirmation_token: 'c'.repeat(64), expires_in_seconds: 900 }),
    undo: async (operationId, request) => {
      const result = receipt(request.request_key, 'undone', server.day.study_date)
      server.receipts.set(request.request_key, result)
      server.day = { ...copy(server.day), revision: result.revision, status: 'not_confirmed', scope: null,
        options: null, selected: [], latest_operation: copy(result) }
      return result
    },
    refresh: async () => { calls.refresh++; state.generation++; state.day = copy(server.day) },
  }
  const client = {
    previewOrchestratorSchedule: async body => { calls.preview.push(copy(body)); return handlers.preview(body) },
    confirmOrchestratorSchedule: async body => { calls.confirm.push(copy(body)); return handlers.confirm(body) },
    findOrchestratorOperation: async key => { calls.find.push(key); return handlers.find(key) },
    previewOrchestratorUndo: async id => { calls.undoPreview.push(id); return handlers.undoPreview(id) },
    confirmOrchestratorUndo: async (id, body) => { calls.undo.push({ id, body: copy(body) }); return handlers.undo(id, body) },
  }
  const commands = createTodayCommands(client, state, store, () => handlers.refresh())
  return { state, server, calls, handlers, store, commands, client, receipt, accept,
    fresh: () => createTodayCommands(client, state, store, () => handlers.refresh()) }
}

test('lost_confirm_uses_one_key_and_never_means_failure', async () => {
  const x = fixture(), lost = deferred()
  x.handlers.confirm = () => lost.promise
  await x.commands.preview()
  const first = x.commands.confirm()
  await x.commands.confirm()
  assert.equal(x.calls.confirm.length, 1)
  const original = x.calls.confirm[0]
  lost.reject(new Error('request timed out'))
  await first
  assert.equal(x.state.write_status, 'unknown')
  const locator = JSON.parse(x.store.getItem(pendingKey))
  assert.equal(locator.request_key, original.request_key)
  await x.commands.recover()
  assert.deepEqual(x.calls.find, [original.request_key])
  assert.equal(x.state.write_status, 'unknown', '404 does not prove no commit')
  x.accept(original)
  await x.commands.recover()
  assert.equal(x.state.write_status, 'saved')
  assert.equal(x.state.day.revision, 1)
  assert.equal(x.store.getItem(pendingKey), null)
  await x.commands.confirm()
  assert.equal(x.calls.confirm.length, 1)
})

test('missing_request_can_resume_with_fresh_preview_and_same_key', async () => {
  const x = fixture()
  x.handlers.confirm = async () => { throw new Error('never reached server') }
  await x.commands.preview(); await x.commands.confirm()
  const key = x.calls.confirm[0].request_key
  x.commands.dispose()
  const resumed = x.fresh()
  await resumed.recover()
  assert.equal(x.state.write_status, 'unknown')
  x.state.draft.options.available_minutes = 25; x.state.generation++
  await resumed.preview()
  x.handlers.confirm = async request => x.accept(request)
  await resumed.confirm()
  assert.equal(x.calls.confirm[1].request_key, key)
  assert.equal(x.calls.confirm[1].options.available_minutes, 25)
  assert.notEqual(x.calls.confirm[0].confirmation_token, x.calls.confirm[1].confirmation_token)
  assert.equal(x.server.receipts.size, 1)
  assert.equal(x.state.write_status, 'saved')
})

test('an older commit winning a resume conflict is recovered without claiming the new draft was saved', async () => {
  const x = fixture()
  x.handlers.confirm = async () => { throw new Error('lost') }
  await x.commands.preview(); await x.commands.confirm()
  const original = x.calls.confirm[0]
  x.state.draft.options.available_minutes = 25; x.state.generation++
  await x.commands.preview()
  x.accept(original)
  x.handlers.confirm = async () => { throw http(409) }
  await x.commands.confirm()
  assert.equal(x.calls.confirm[1].request_key, original.request_key)
  assert.equal(x.state.day.options.available_minutes, 30)
  assert.equal(x.state.draft.options.available_minutes, 25)
  assert.equal(x.state.dirty, true)
  assert.equal(x.state.write_status, 'saved')
  assert.equal(x.server.receipts.size, 1)
})

test('confirm_and_undo_bind_the_reviewed_revision', async t => {
  let now = Date.parse('2026-11-01T01:00:00Z')
  t.mock.method(Date, 'now', () => now)
  const x = fixture()
  await x.commands.preview()
  const reviewed = copy(x.calls.preview[0])
  await x.commands.confirm()
  assert.deepEqual(x.calls.confirm[0], { ...reviewed, confirmation_token: 'a'.repeat(64), request_key: x.calls.confirm[0].request_key, confirmed: true })
  const confirmKey = x.calls.confirm[0].request_key
  await x.commands.previewUndo(x.state.day.latest_operation.operation_id)
  assert.equal(x.state.write_status, 'undo_preview')
  assert.equal(x.state.undo_preview.day_revision, 1)
  assert.equal(x.calls.undo.length, 0, 'undo preview does not mutate a domain or schedule')
  await x.commands.confirmUndo()
  assert.equal(x.calls.undo[0].id, x.calls.undoPreview[0])
  assert.notEqual(x.calls.undo[0].body.request_key, confirmKey)
  assert.equal(x.calls.undo[0].body.confirmation_token, 'c'.repeat(64))
  assert.deepEqual(x.server.completed, ['existing-domain-completion'])
  assert.equal(x.state.write_status, 'saved')
  assert.equal(x.state.day.revision, 2)
  now += 900_000
})

test('changed options, changed generation and expired preview never reach confirm', async t => {
  let now = Date.parse('2026-11-01T01:00:00Z')
  t.mock.method(Date, 'now', () => now)
  for (const change of [x => { x.state.draft.options.available_minutes++ }, x => { x.state.generation++ }, () => { now += 900_000 }]) {
    const x = fixture()
    await x.commands.preview()
    change(x)
    await x.commands.confirm()
    assert.equal(x.calls.confirm.length, 0)
    assert.equal(x.state.preview, null)
    assert.match(x.state.error, /预览|变化|过期/)
  }
})

test('pending_locator_survives_refresh_without_secrets', async () => {
  const x = fixture(), inFlight = deferred()
  x.handlers.confirm = () => inFlight.promise
  await x.commands.preview()
  const pending = x.commands.confirm()
  const raw = x.store.getItem(pendingKey), locator = JSON.parse(raw)
  assert.deepEqual(Object.keys(locator).sort(), ['kind', 'request_key', 'study_date'])
  assert.equal(locator.kind, 'confirm')
  assert.match(locator.request_key, /^[a-zA-Z0-9_-]{16,80}$/)
  for (const secret of ['confirmation_token', 'scope', 'options', 'snapshot', 'private-', 'source-one']) assert.equal(raw.includes(secret), false)
  x.commands.dispose()
  const disposed = copy(x.state)
  inFlight.reject(new Error('disconnected'))
  await pending
  assert.deepEqual(x.state, disposed, 'disposed controllers do not write UI after a late response')
  assert.ok(x.store.getItem(pendingKey))
})

test('pending undo can only resume the original undo, never a new schedule confirmation', async () => {
  const x = fixture()
  await x.commands.preview(); await x.commands.confirm()
  const operationId = x.state.day.latest_operation.operation_id
  x.handlers.undo = async () => { throw new Error('lost undo response') }
  await x.commands.previewUndo(operationId); await x.commands.confirmUndo()
  const key = x.calls.undo[0].body.request_key
  x.commands.dispose()
  const resumed = x.fresh()
  await resumed.recover()
  await resumed.preview()
  assert.equal(x.calls.preview.length, 1, 'pending undo blocks schedule preview')
  await resumed.previewUndo('another-operation')
  assert.equal(x.calls.undoPreview.length, 1)
  await resumed.previewUndo(operationId)
  x.handlers.undo = async (id, request) => {
    const result = x.receipt(request.request_key, 'undone')
    x.server.receipts.set(request.request_key, result)
    x.server.day.latest_operation = result; x.server.day.revision = result.revision
    return result
  }
  await resumed.confirmUndo()
  assert.equal(x.calls.undo[1].body.request_key, key)
  assert.equal(x.calls.undo[1].id, operationId)
  assert.equal(x.calls.confirm.length, 1)
})

test('an acknowledged save remains saved when refreshing the day fails', async () => {
  const x = fixture()
  x.handlers.refresh = async () => { throw http(503) }
  await x.commands.preview(); await x.commands.confirm()
  assert.equal(x.state.write_status, 'saved')
  assert.match(x.state.error, /已保存.*刷新/)
  assert.equal(x.state.preview, null)
  assert.equal(x.store.getItem(pendingKey), null)
  await x.commands.confirm()
  assert.equal(x.calls.confirm.length, 1)
})

test('a nonthrowing refresh error after receipt also preserves saved status', async () => {
  const x = fixture()
  x.handlers.refresh = async () => { x.state.error = '读取暂不可用，请重试' }
  await x.commands.preview(); await x.commands.confirm()
  assert.equal(x.state.write_status, 'saved')
  assert.match(x.state.error, /已保存.*刷新/)
})

test('blocked or silently dropped pending storage prevents a network write', async () => {
  for (const blocked of [
    { getItem() { return null }, setItem() { throw new Error('blocked') }, removeItem() {} },
    { getItem() { return null }, setItem() {}, removeItem() {} },
  ]) {
    const x = fixture({ store: blocked })
    await x.commands.preview(); await x.commands.confirm()
    assert.equal(x.calls.confirm.length, 0)
    assert.notEqual(x.state.write_status, 'saved')
    assert.match(x.state.error, /存储|保存请求/)
  }
})

test('in-flight writes block other preview, undo and confirmation operations', async () => {
  const x = fixture(), flight = deferred()
  await x.commands.preview()
  x.handlers.confirm = () => flight.promise
  const first = x.commands.confirm()
  await x.commands.preview(); await x.commands.previewUndo('anything'); await x.commands.confirmUndo(); await x.commands.recover()
  assert.equal(x.calls.preview.length, 1)
  assert.equal(x.calls.undoPreview.length, 0)
  assert.equal(x.calls.undo.length, 0)
  assert.equal(x.calls.find.length, 0)
  flight.resolve(x.accept(x.calls.confirm[0])); await first
})

test('401 clears identity and authority; 429 never creates an automatic retry loop', async () => {
  const expired = fixture()
  expired.handlers.confirm = async () => { throw http(401) }
  await expired.commands.preview(); await expired.commands.confirm()
  assert.equal(expired.state.phase, 'expired')
  assert.equal(expired.state.identity, null)
  assert.equal(expired.state.snapshot, null)
  assert.equal(expired.state.draft, null)
  assert.equal(expired.state.preview, null)
  assert.equal(expired.store.getItem(pendingKey), null)
  const limited = fixture()
  limited.handlers.confirm = async () => { throw http(429) }
  await limited.commands.preview(); await limited.commands.confirm()
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(limited.calls.confirm.length, 1)
  assert.equal(limited.state.draft.options.available_minutes, 30)
  assert.match(limited.state.error, /频繁|次数|稍后/)
})

test('the real workspace can reinitialize after command authentication expires', async () => {
  const x = fixture()
  let identityReads = 0
  Object.assign(x.client, {
    getOrchestratorCapabilities: async () => ({ enabled: true, ui_contract: 'today-workspace-v1' }),
    getOrchestratorToday: async () => copy(x.server.day),
    readOrchestratorSnapshot: async () => copy(x.state.snapshot),
  })
  const workspace = createTodayWorkspace({ client: x.client, getCourseBrowserScope: async () => { identityReads++; return 'account:one' } }, x.store, () => Date.parse('2026-11-01T01:00:00Z'))
  await workspace.initialize(); await workspace.selectScope(scope); workspace.setOptions(copy(options))
  const commands = createTodayCommands(x.client, workspace.state, x.store, () => workspace.refresh())
  x.handlers.confirm = async () => { throw http(401) }
  await commands.preview(); await commands.confirm()
  assert.equal(workspace.state.phase, 'expired')
  await workspace.initialize()
  assert.equal(identityReads, 2)
  assert.equal(workspace.state.phase, 'ready')
  assert.equal(workspace.state.identity, 'account:one')
  commands.dispose(); workspace.dispose()
})

test('old-day receipts are read-only history and do not replace the current day', async () => {
  const x = fixture({ date: '2026-11-02' }), key = 'old-day-request-key'
  x.store.setItem(pendingKey, JSON.stringify({ kind: 'confirm', request_key: key, study_date: '2026-11-01' }))
  x.server.receipts.set(key, x.receipt(key, 'confirmed', '2026-11-01'))
  const current = copy(x.state.day)
  await x.commands.recover()
  assert.deepEqual(x.state.day, current)
  assert.equal(x.state.day.study_date, '2026-11-02')
  assert.equal(x.state.draft.scope.goal_id, 'goal-one')
  assert.match(x.state.error, /历史|旧日|11-01/)
  assert.equal(x.store.getItem(pendingKey), null)
})

test('a fresh explicit current-day preview can resume a missing old-day key', async () => {
  const x = fixture({ date: '2026-11-02' }), key = 'missing-old-day-key'
  x.store.setItem(pendingKey, JSON.stringify({ kind: 'confirm', request_key: key, study_date: '2026-11-01' }))
  await x.commands.recover()
  await x.commands.preview(); await x.commands.confirm()
  assert.equal(x.calls.confirm[0].request_key, key)
  assert.equal(x.state.day.study_date, '2026-11-02')
  assert.equal(x.state.write_status, 'saved')
})

test('missing latest receipt pointers disable undo without guessing an operation', async () => {
  const x = fixture()
  await x.commands.preview(); await x.commands.confirm()
  const id = x.state.receipt.operation_id
  x.state.day.latest_operation = null
  await x.commands.previewUndo(id)
  assert.equal(x.calls.undoPreview.length, 0)
  assert.match(x.state.error, /回执|定位|撤销/)
})

test('a changed undo revision and disposed preview cannot retain authority', async () => {
  const x = fixture()
  await x.commands.preview(); await x.commands.confirm()
  await x.commands.previewUndo(x.state.day.latest_operation.operation_id)
  x.state.day.revision++
  await x.commands.confirmUndo()
  assert.equal(x.calls.undo.length, 0)
  assert.equal(x.state.undo_preview, null)
  assert.notEqual(x.state.write_status, 'undo_preview', 'expired authority cannot leave the undo dialog armed')
  const y = fixture(), later = deferred()
  y.handlers.preview = () => later.promise
  const preview = y.commands.preview()
  y.commands.dispose()
  const disposed = copy(y.state)
  later.resolve({ confirmation_token: 'late-token' })
  await preview
  assert.deepEqual(y.state, disposed)
})

test('a failed new undo selection clears the previously reviewed undo permission', async () => {
  const x = fixture()
  await x.commands.preview(); await x.commands.confirm()
  await x.commands.previewUndo(x.state.day.latest_operation.operation_id)
  assert.ok(x.state.undo_preview)
  await x.commands.previewUndo('wrong-operation')
  assert.equal(x.state.undo_preview, null)
  assert.notEqual(x.state.write_status, 'undo_preview')
  assert.equal(x.calls.undoPreview.length, 1)
})

test('a malformed or foreign preview cannot authorize a confirmation', async () => {
  for (const alteration of [value => { value.scope.goal_id = 'another-goal' }, value => { value.evidence_revision = 'other-evidence' },
    value => { value.selected = Array.from({ length: 21 }, () => ({})) }]) {
    const x = fixture(), original = x.handlers.preview
    x.handlers.preview = async body => { const value = await original(body); alteration(value); return value }
    await x.commands.preview(); await x.commands.confirm()
    assert.equal(x.calls.confirm.length, 0)
    assert.equal(x.state.preview, null)
    assert.ok(x.state.error)
  }
})


async function publicError(status, code = 'synthetic_rejection') {
  const ts = (await import('typescript')).default
  const { readFileSync } = await import('node:fs')
  const source = readFileSync(new URL('../src/services/api.ts', import.meta.url), 'utf8')
  const tree = ts.createSourceFile('api.ts', source, ts.ScriptTarget.Latest, true)
  const statement = tree.statements.find(node => node.getText(tree).startsWith('api.interceptors.response.use('))
  assert.ok(statement, 'exercise the actual public response normalizer')
  let rejected
  const api = { interceptors: { response: { use: (_success, error) => { rejected = error } } } }
  const compiled = ts.transpileModule(statement.getText(tree).replaceAll('import.meta.env.DEV', 'false'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText
  new Function('api', 'window', 'Event', compiled)(api, { dispatchEvent() {} }, Event)
  try { await rejected({ response: { status, data: { error: 'synthetic rejection', data: { error_code: code } } } }) }
  catch (error) { assert.equal(error.status, status); return error }
  throw new Error('normalizer manufactured success')
}

test('public_normalized_rejections_are_classified_by_the_actual_controller', async () => {
  for (const status of [422, 429]) {
    const x = fixture(), error = await publicError(status)
    x.handlers.confirm = async () => { throw error }
    await x.commands.preview(); await x.commands.confirm()
    assert.equal(x.state.write_status, 'idle', `public HTTP ${status} is a definite first rejection`)
    assert.equal(x.store.getItem(pendingKey), null)
    if (status === 429) assert.match(x.state.error, /次数/)
    assert.equal(x.calls.confirm.length, 1)
  }
  const x = fixture()
  x.handlers.confirm = async request => { x.accept(request); throw await publicError(409) }
  await x.commands.preview(); await x.commands.confirm()
  assert.equal(x.calls.find.length, 1)
  assert.equal(x.state.write_status, 'saved')
})

test('confirmed_then_undone_receipt_is_a_verified_terminal_outcome', async () => {
  const x = fixture()
  x.handlers.confirm = async request => { x.accept(request); throw new Error('lost ack') }
  await x.commands.preview(); await x.commands.confirm()
  const key = x.calls.confirm[0].request_key
  x.server.receipts.set(key, { ...x.server.receipts.get(key), status: 'undone' })
  x.server.day = { ...x.server.day, revision: 2, status: 'not_confirmed', scope: null, options: null, selected: [], latest_operation: null }
  await x.commands.recover()
  assert.equal(x.state.pending, null)
  assert.equal(x.store.getItem(pendingKey), null)
  assert.equal(x.state.receipt.status, 'undone')
  await x.commands.preview()
  assert.equal(x.calls.preview.length, 2)
  assert.equal(x.calls.confirm.length, 1)
})

test('first_undo_definitely_rejected_by_concurrent_revision_does_not_deadlock', async () => {
  const x = fixture()
  await x.commands.preview(); await x.commands.confirm()
  await x.commands.previewUndo(x.state.day.latest_operation.operation_id)
  x.server.day.revision = 2
  x.handlers.undo = async () => { throw await publicError(409, 'schedule_changed_since_operation') }
  await x.commands.confirmUndo()
  assert.equal(x.state.pending, null)
  assert.equal(x.store.getItem(pendingKey), null)
  await x.commands.preview()
  assert.equal(x.calls.preview.length, 2)
  assert.equal(x.calls.undo.length, 1)
})

test('unknown_previous_undo_plus_404_still_keeps_the_original_key', async () => {
  const x = fixture()
  await x.commands.preview(); await x.commands.confirm()
  const operation = x.state.day.latest_operation.operation_id
  await x.commands.previewUndo(operation)
  x.handlers.undo = async () => { throw new Error('lost before outcome known') }
  await x.commands.confirmUndo()
  const key = x.calls.undo[0].body.request_key
  await x.commands.previewUndo(operation)
  x.handlers.undo = async () => { throw await publicError(409, 'schedule_changed_since_operation') }
  await x.commands.confirmUndo()
  assert.equal(x.state.pending.request_key, key)
  assert.equal(x.state.write_status, 'unknown')
  assert.equal(x.calls.find.length, 1)
})

test('cross_midnight_old_undo_authority_never_sends_a_write', async () => {
  const original = Date.now
  let clock = Date.parse('2026-11-01T15:59:30Z')
  Date.now = () => clock
  try {
    const x = fixture()
    await x.commands.preview(); await x.commands.confirm()
    await x.commands.previewUndo(x.state.day.latest_operation.operation_id)
    clock += 60000
    await x.commands.confirmUndo()
    assert.equal(x.calls.undo.length, 0)
    assert.equal(x.state.undo_preview, null)
    assert.ok(x.calls.refresh >= 2, 'date boundary re-reads authoritative server state')
  } finally { Date.now = original }
})

test('kept_open_midnight_check_revokes_preview_without_user_submission', async () => {
  const original = Date.now
  let clock = Date.parse('2026-11-01T15:59:30Z')
  Date.now = () => clock
  try {
    const x = fixture()
    await x.commands.preview()
    assert.equal(typeof x.commands.checkDayBoundary, 'function')
    clock += 60000
    await x.commands.checkDayBoundary()
    assert.equal(x.state.preview, null)
    assert.equal(x.calls.confirm.length, 0)
    assert.equal(x.calls.refresh, 1)
  } finally { Date.now = original }
})


test('normalized_auth_entry_and_exact_goal_errors_retain_public_meaning', async () => {
  const { resolveTodayEntry } = await import('../src/today/entry-state.ts')
  const { loadExactTodayGoal } = await import('../src/today/navigation.ts')
  assert.match(resolveTodayEntry(null, await publicError(429)).message, /请求较多/)
  assert.match(resolveTodayEntry(null, await publicError(401)).message, /登录已过期/)
  const missing = await loadExactTodayGoal('missing-goal', [], async () => { throw await publicError(404) })
  assert.equal(missing.goal, null)
  assert.match(missing.notice, /不存在或当前账号/)
  const x = fixture()
  x.handlers.confirm = async () => { throw await publicError(401) }
  await x.commands.preview(); await x.commands.confirm()
  assert.equal(x.state.phase, 'expired')
  assert.equal(x.state.identity, null)
})

test('shared_restore_epoch_rejects_an_old_tab_locator_even_before_storage_event_delivery', async () => {
  const { TODAY_EPOCH_KEY } = await import('../src/services/today-session.ts')
  const x = fixture()
  x.handlers.confirm = async () => { throw new Error('lost acknowledgement') }
  await x.commands.preview(); await x.commands.confirm()
  const oldKey = x.calls.confirm[0].request_key
  x.commands.dispose()
  x.store.setItem(TODAY_EPOCH_KEY, 'synthetic-restore-generation')
  const next = x.fresh()
  await next.recover()
  assert.equal(x.calls.find.length, 0)
  assert.equal(x.store.getItem(pendingKey), null)
  x.handlers.confirm = async request => x.accept(request)
  await next.preview(); await next.confirm()
  assert.equal(x.state.write_status, 'saved')
  assert.notEqual(x.calls.confirm[1].request_key, oldKey)
  assert.equal(x.store.getItem(TODAY_EPOCH_KEY), 'synthetic-restore-generation')
})
