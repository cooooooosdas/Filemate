import test from 'node:test'
import assert from 'node:assert/strict'
import { load, harness, clone, deferred } from './learning-coach-fixtures.mjs'

const day = '2026-11-03'
const token = 'c'.repeat(64)
const operationId = 'coach_operation_' + '1'.repeat(32)
async function setup() {
  const h = harness()
  await h.workspace.open((await import('./learning-coach-fixtures.mjs')).input())
  await h.workspace.submit('rule')
  const data = new Map(),
    calls = [],
    committed = new Map()
  const storage = {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
    removeItem: (key) => data.delete(key),
  }
  let now = Date.parse('2026-11-03T02:00:00Z'),
    refreshes = 0
  const client = {
    ...h.client,
    preview: async (draft) => {
      calls.push(['preview'])
      return {
        draft: clone(draft),
        issued_study_date: day,
        day_revisions: { [day]: 0 },
        changes: {},
        confirmation_token: token,
        expires_in_seconds: 900,
      }
    },
    confirm: async (body) => {
      assert.ok(
        [...data.values()].some((raw) => JSON.parse(raw).request_key === body.request_key),
        'locator precedes POST',
      )
      calls.push(['POST', body.request_key])
      const receipt = {
        operation_id: operationId,
        request_key: body.request_key,
        status: 'confirmed',
        study_dates: body.days.map((d) => d.study_date),
        day_revisions: Object.fromEntries(body.days.map((d) => [d.study_date, 1])),
        affected: { new_study_plans: 1, daily_schedules: 1 },
        plan_id: 'synthetic-plan',
      }
      committed.set(body.request_key, receipt)
      return receipt
    },
    operation: async (key) => {
      calls.push(['GET', key])
      if (!committed.has(key)) throw { status: 404 }
      return clone(committed.get(key))
    },
    undoPreview: async (id) => ({
      operation_id: id,
      issued_study_date: day,
      day_revisions: { [day]: 1 },
      plan_revision: 'a'.repeat(64),
      confirmation_token: token,
      expires_in_seconds: 900,
    }),
    undoConfirm: async (id, body) => {
      calls.push(['UNDO'])
      throw { status: 409 }
    },
  }
  const { createCoachCommands } = load('../src/today/coach-commands.ts')
  const commands = createCoachCommands(client, {
    state: h.workspace.state,
    storage,
    refresh: async () => {
      refreshes++
    },
    now: () => now,
  })
  return {
    ...h,
    state: h.workspace.state,
    client,
    commands,
    data,
    storage,
    calls,
    committed,
    refreshes: () => refreshes,
    advance: (value) => {
      now += value
    },
  }
}
async function lostResponseHarness() {
  const h = await setup(),
    confirm = h.client.confirm
  h.client.confirm = async (body) => {
    await confirm(body)
    throw new Error('synthetic response lost')
  }
  await h.commands.preview(h.state.draft)
  await h.commands.confirm()
  assert.equal(h.state.receipt, null)
  assert.equal(h.state.pending.kind, 'confirm')
  return h
}
test('lost_confirm_response_recovers_by_get_only', async () => {
  const h = await lostResponseHarness(),
    originalKey = h.state.pending.request_key
  h.calls.length = 0
  await h.commands.recover()
  assert.deepEqual(
    h.calls.map((c) => c[0]),
    ['GET'],
  )
  assert.equal(h.state.receipt.request_key, originalKey)
  assert.equal(h.state.pending, null)
})
test('persistence failure blocks writes and stores no private content', async () => {
  const h = await setup()
  await h.commands.preview(h.state.draft)
  h.storage.setItem = () => {
    throw new Error('quota')
  }
  await h.commands.confirm()
  assert.equal(h.calls.filter((c) => c[0] === 'POST').length, 0)
  assert.match(h.state.error, /存储|保存请求/)
})
test('editing_or_completing_invalidates_preview', async () => {
  const h = await setup()
  await h.commands.preview(h.state.draft)
  h.state.draft.days[0].options.available_minutes++
  await h.commands.confirm()
  assert.equal(h.calls.filter((c) => c[0] === 'POST').length, 0)
  await h.commands.preview(h.state.draft)
  h.commands.invalidate()
  await h.commands.confirm()
  assert.equal(h.calls.filter((c) => c[0] === 'POST').length, 0)
})
test('double_click_cannot_duplicate_plan', async () => {
  const h = await setup(),
    barrier = deferred(),
    confirm = h.client.confirm
  h.client.confirm = async (body) => {
    await barrier.promise
    return confirm(body)
  }
  await h.commands.preview(h.state.draft)
  const first = h.commands.confirm()
  await h.commands.confirm()
  barrier.resolve()
  await first
  assert.equal(h.calls.filter((c) => c[0] === 'POST').length, 1)
  assert.equal(h.state.receipt.status, 'confirmed')
})
test('tomorrow_receipt_does_not_replace_today', async () => {
  const h = await setup()
  h.state.draft.days[0].study_date = '2026-11-04'
  const input = clone(h.state.input)
  await h.commands.preview(h.state.draft)
  await h.commands.confirm()
  assert.deepEqual(h.state.receipt.study_dates, ['2026-11-04'])
  assert.deepEqual(h.state.input, input)
  assert.equal(h.refreshes(), 1)
})
test('expired_identity_clears_authority', async () => {
  const h = await setup(),
    barrier = deferred(),
    original = h.client.confirm
  h.client.confirm = async (body) => {
    await barrier.promise
    return original(body)
  }
  await h.commands.preview(h.state.draft)
  const write = h.commands.confirm()
  h.state.identity = 'new-account'
  h.state.generation++
  barrier.resolve()
  await write
  assert.equal(h.state.receipt, null)
})
test('undo_conflict_preserves_all_progress', async () => {
  const h = await setup()
  await h.commands.preview(h.state.draft)
  await h.commands.confirm()
  const receipt = clone(h.state.receipt)
  await h.commands.previewUndo(receipt.operation_id)
  await h.commands.confirmUndo()
  assert.deepEqual(h.state.receipt, receipt)
  assert.match(h.state.error, /整体|进度|变化/)
})
test('successful undo has its own operation id and lost response recovers that receipt', async () => {
  const h = await setup()
  await h.commands.preview(h.state.draft)
  await h.commands.confirm()
  const original = clone(h.state.receipt)
  h.client.undoConfirm = async (id, body) => {
    assert.equal(id, original.operation_id)
    const receipt = {
      ...original,
      operation_id: 'learning-coach-operation-' + '8'.repeat(32),
      request_key: body.request_key,
      status: 'undone',
      affected: { archived_study_plans: 1 },
      day_revisions: { [day]: 2 },
    }
    h.committed.set(body.request_key, receipt)
    throw new Error('synthetic lost undo response')
  }
  await h.commands.previewUndo(original.operation_id)
  await h.commands.confirmUndo()
  await h.commands.recover()
  assert.equal(h.state.receipt.status, 'undone')
  assert.notEqual(h.state.receipt.operation_id, original.operation_id)
  assert.equal(h.state.pending, null)
})
test('404 recovery and unknown requests never repost or overwrite locator', async () => {
  const h = await lostResponseHarness()
  h.committed.clear()
  h.calls.length = 0
  const pending = clone(h.state.pending)
  await h.commands.recover()
  await h.commands.preview(h.state.draft)
  await h.commands.confirm()
  assert.deepEqual(
    h.calls.map((c) => c[0]),
    ['GET'],
  )
  assert.deepEqual(h.state.pending, pending)
})
test('only minimal locator survives reload, request recovery is GET only', async () => {
  const h = await setup(),
    locator = {
      kind: 'request',
      request_key: 'coach_request_' + '2'.repeat(32),
      issued_study_date: day,
    }
  h.commands.trackRequest(locator)
  const raw = [...h.data.values()][0]
  assert.deepEqual(JSON.parse(raw), locator)
  assert.ok(!raw.includes('question') && !raw.includes('confirmation_token'))
  h.client.get = async (key) => {
    h.calls.push(['GET', key])
    return { ...h.state.run, request_key: key }
  }
  h.calls.length = 0
  await h.commands.recover()
  assert.deepEqual(
    h.calls.map((c) => c[0]),
    ['GET'],
  )
  assert.equal(h.state.pending, null)
})
test('controlled Shanghai midnight and expired preview require reread without POST', async () => {
  const h = await setup()
  await h.commands.preview(h.state.draft)
  h.advance(24 * 3600 * 1000)
  await h.commands.confirm()
  assert.equal(h.calls.filter((c) => c[0] === 'POST').length, 0)
  assert.match(h.state.error, /日期|过期/)
})
test('definite confirmation conflict releases locator but never reports saved', async () => {
  const h = await setup()
  h.client.confirm = async () => {
    throw { status: 409 }
  }
  await h.commands.preview(h.state.draft)
  await h.commands.confirm()
  assert.equal(h.state.pending, null)
  assert.equal(h.state.receipt, null)
  assert.match(h.state.error, /更新|预览/)
})
test('running request can be queried again without a second POST', async () => {
  const h = await setup(),
    locator = {
      kind: 'request',
      request_key: 'coach_request_' + '3'.repeat(32),
      issued_study_date: day,
    }
  h.commands.trackRequest(locator)
  h.client.get = async (key) => {
    h.calls.push(['GET'])
    return { ...h.state.run, status: 'running', proposal: null, request_key: key }
  }
  await h.commands.recover()
  await h.commands.recover()
  assert.equal(h.calls.filter((c) => c[0] === 'GET').length, 2)
})
test('coach actions use typed original targets rather than arbitrary stored URL', () => {
  const { resolveCoachAction } = load('../src/today/navigation.ts')
  assert.deepEqual(
    resolveCoachAction({
      action: 'practice_problem',
      target_ref: { kind: 'problem', id: 'cpp-first' },
    }),
    { path: '/programming', query: { problem: 'cpp-first' }, label: '打开原编程题' },
  )
  assert.equal(
    resolveCoachAction({
      action: 'practice_problem',
      target_ref: { kind: 'source', id: 'cpp-first' },
      route: 'https://example.invalid/',
    }),
    null,
  )
  assert.equal(
    resolveCoachAction({
      action: 'train_concept',
      target_ref: { kind: 'concept', id: 'node', course_id: null },
    }),
    null,
  )
})
test('saved native plan actions with title field reach their original function', () => {
  const { studyTrainingActions } = load('../src/today/navigation.ts')
  const links = studyTrainingActions({
    training_actions: [
      {
        action: 'read_source',
        title: '核对所选资料',
        route: 'https://example.invalid/',
        target_ref: { kind: 'source', id: 'saved-source' },
      },
    ],
  })
  assert.deepEqual(links, [
    {
      label: '核对所选资料',
      target: { path: '/ai-tools', query: { source: 'saved-source' }, label: '打开原资料' },
    },
  ])
  assert.deepEqual(studyTrainingActions({ tasks: ['旧版计划'] }), [])
  assert.deepEqual(
    studyTrainingActions({ training_actions: [{ label: 'unknown', route: '//example.invalid/' }] }),
    [],
  )
})
test('definite request rejection releases only its own locator', async () => {
  const h = await setup(),
    locator = {
      kind: 'request',
      request_key: 'coach_request_' + '4'.repeat(32),
      issued_study_date: day,
    }
  h.commands.trackRequest(locator)
  h.commands.rejectRequest({ status: 429 }, locator)
  assert.equal(h.state.pending, null)
  assert.equal(h.data.size, 0)
})
test('generation storage failure blocks POST and unknown response blocks new read', async () => {
  const h = await setup(),
    { createCoachWorkspace } = load('../src/today/coach-state.ts')
  const input = clone(h.state.input)
  const workspace = createCoachWorkspace(h.client, {
    identity: () => 'actor',
    beforeRequest: () => {
      throw new Error('storage unavailable')
    },
  })
  await workspace.open(input)
  h.calls.length = 0
  await workspace.submit('rule')
  assert.equal(workspace.state.pending, null)
  assert.match(workspace.state.error, /存储/)
  const other = createCoachWorkspace(
    {
      ...h.client,
      request: async () => {
        throw new Error('unknown response')
      },
    },
    { identity: () => 'actor' },
  )
  await other.open(input)
  await other.submit('rule')
  const key = other.state.pending.request_key
  h.calls.length = 0
  await other.readContext(input)
  await other.submit('rule')
  assert.equal(other.state.pending.request_key, key)
  assert.equal(h.calls.length, 0)
})
test('adding a day keeps canonical options, ordered future dates and seven-day bound', async () => {
  const h = await setup(),
    { appendCoachDay } = load('../src/today/coach-commands.ts')
  h.state.draft.days[0].study_date = '2026-11-04'
  const value = appendCoachDay(h.state.draft, day)
  assert.deepEqual(
    value.days.map((d) => d.study_date),
    ['2026-11-04', '2026-11-05'],
  )
  assert.deepEqual(value.days[1].options, {
    available_minutes: 40,
    item_order: [],
    pinned_ids: [],
    excluded_ids: [],
    minute_overrides: {},
  })
  let draft = value
  for (let i = 0; i < 10; i++) draft = appendCoachDay(draft, day)
  assert.equal(draft.days.at(-1).study_date, '2026-11-09')
  assert.equal(draft.days.length, 6)
  assert.equal(h.state.draft.days.length, 1)
})
test('read and preview network faults give an available recovery action', async () => {
  const h = await setup()
  h.client.preview = async () => {
    throw new Error('network')
  }
  await h.commands.preview(h.state.draft)
  assert.match(h.state.error, /预览/)
  assert.doesNotMatch(h.state.error, /存储|查询保存/)
  h.client.context = async () => {
    throw new Error('network')
  }
  const { createCoachWorkspace } = load('../src/today/coach-state.ts')
  const workspace = createCoachWorkspace(h.client, { identity: () => 'actor' })
  await workspace.open((await import('./learning-coach-fixtures.mjs')).input())
  assert.match(workspace.state.error, /重新读取/)
  assert.doesNotMatch(workspace.state.error, /查询原结果/)
})
test('removed records and denied permissions are distinguished from connection faults', () => {
  const { coachError } = load('../src/today/coach-state.ts')
  assert.match(coachError({ status: 404 }), /原记录|移除/)
  assert.doesNotMatch(coachError({ status: 404 }), /连接|查询原结果/)
  assert.match(coachError({ status: 403 }), /无权|账号/)
})
