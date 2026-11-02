import assert from 'node:assert/strict'
import test from 'node:test'
import { readReviewBrowse, reviewBrowseQuery } from '../src/wrongbook/browse-state.ts'
const mod = await import('../src/wrongbook/session-state.ts').catch(() => ({}))
const ref = { wrong_id: 'w', artifact_id: 'a', question_index: 0, question_digest: 'a'.repeat(64), source_id: 's', revision: 1, next_review_at: '2026-10-25T00:00:00Z' }
const preview = () => ({ status: 'preview_only', filters: { sort: 'recommended' }, items: [{ ref: { ...ref }, stem: '栈的顺序', priority: { reason: '已到期', rule_version: 'review2-priority-v1' } }], selected_count: 1, eligible_count: 50, available_minutes: 12 })
const ready = () => ({ status: 'ready', refs: [{ ...ref }], as_of: '2026-10-30T00:00:00Z' })
function setup(overrides = {}) {
  assert.equal(typeof mod.createReviewSessionController, 'function')
  const calls = []
  const api = { getReviewSessionPreview: async p => { calls.push(p); return preview() }, checkReviewSession: async body => { calls.push(body); return ready() }, ...overrides }
  return { c: mod.createReviewSessionController(api), calls }
}
test('recommended survives URL and preference round trips while due stays default', () => {
  assert.equal(readReviewBrowse({}).filters.sort, 'due')
  const browse = readReviewBrowse({ sort: 'recommended' })
  assert.equal(browse.filters.sort, 'recommended')
  assert.equal(reviewBrowseQuery(browse).sort, 'recommended')
})
test('preview sends applied filters and integer budget; no page traversal or writing', async () => {
  const { c, calls } = setup()
  assert.equal(await c.load({ q: '栈', sort: 'due' }, 12), true)
  assert.deepEqual(calls, [{ q: '栈', sort: 'due', available_minutes: 12, minutes_per_question: 4 }])
  assert.equal(c.state.preview.eligible_count, 50)
  assert.deepEqual((await c.check()).refs, [ref])
  assert.deepEqual(calls[1], { refs: [ref], filters: preview().filters })
})
test('invalid budget never reaches API', async () => {
  const { c, calls } = setup()
  for (const n of [true, -1, 1441, 9.5, NaN, '12']) assert.equal(await c.load({}, n), false)
  for (const n of [false, 0, 61, 1.5]) assert.equal(await c.load({}, 12, n), false)
  assert.equal(calls.length, 0)
})
test('zero budget is valid but empty server selection cannot start', async () => {
  const { c, calls } = setup({ getReviewSessionPreview: async () => ({ ...preview(), items: [], selected_count: 0 }) })
  assert.equal(await c.load({}, 0), true)
  assert.equal(await c.check(), null)
  assert.equal(calls.length, 0)
})
test('newer preview wins and stale preview cannot restore old filters', async () => {
  let release
  const { c } = setup({ getReviewSessionPreview: p => p.available_minutes === 12 ? new Promise(r => { release = r }) : Promise.resolve({ ...preview(), available_minutes: 20 }) })
  const old = c.load({}, 12); await c.load({}, 20); release(preview()); await old
  assert.equal(c.state.preview.available_minutes, 20)
})
test('budget or identity invalidation rejects a late successful check', async () => {
  let release
  const { c } = setup({ checkReviewSession: () => new Promise(r => { release = r }) })
  await c.load({}, 12); const checking = c.check(); c.invalidate(); release(ready())
  assert.equal(await checking, null); assert.equal(c.state.preview, null); assert.equal(c.state.checking, false)
})
test('409 requires a fresh preview and never falls back to different questions', async () => {
  const { c } = setup({ checkReviewSession: async () => { throw { response: { status: 409 } } } })
  await c.load({}, 12); assert.equal(await c.check(), null)
  assert.equal(c.state.preview, null); assert.match(c.state.error, /重新.*预览/)
})

test('shared HTTP client normalized 409 also invalidates preview', async () => {
  const { c } = setup({ checkReviewSession: async () => { throw Object.assign(Error('changed'), { status: 409, code: 'conflict' }) } })
  await c.load({}, 12); assert.equal(await c.check(), null)
  assert.equal(c.state.preview, null); assert.match(c.state.error, /重新.*预览/)
})
test('network check failure preserves preview and allows explicit retry', async () => {
  let fail = true
  const { c } = setup({ checkReviewSession: async () => { if (fail) throw Error('offline'); return ready() } })
  await c.load({}, 12); assert.equal(await c.check(), null); assert.ok(c.state.preview)
  fail = false; assert.deepEqual((await c.check()).refs, [ref])
})
test('partial or changed check results cannot replace the preview', async () => {
  for (const refs of [[], [{ ...ref, revision: 2 }], [{ ...ref, wrong_id: 'other' }]]) {
    const { c } = setup({ checkReviewSession: async () => ({ ...ready(), refs }) })
    await c.load({}, 12); assert.equal(await c.check(), null)
  }
})
test('double check does not dispatch another request', async () => {
  let release, count = 0
  const { c } = setup({ checkReviewSession: () => { count++; return new Promise(r => { release = r }) } })
  await c.load({}, 12); const first = c.check(); assert.equal(await c.check(), null)
  assert.equal(count, 1); release(ready()); await first
})
test('disposing rejects late preview and all later operations', async () => {
  let release
  const { c } = setup({ getReviewSessionPreview: () => new Promise(r => { release = r }) })
  const pending = c.load({}, 12); c.dispose(); release(preview())
  assert.equal(await pending, false); assert.equal(c.state.preview, null)
  assert.equal(await c.load({}, 12), false); assert.equal(await c.check(), null)
})
