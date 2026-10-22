import assert from 'node:assert/strict'
import test from 'node:test'
import { createCourseReviewFlow, coursePanelEnabled } from '../src/course-graph/review-state.ts'

const node = (id, validation = 'valid') => ({ item_id: id, kind: 'node', validation, original: { label: id, excerpt: '原文' }, decision: 'pending' })
const snapshot = (nodes = [node('栈')]) => ({ course_id: 'c', draft_id: 'd', status: 'applied', revision_digest: 'r', sources: [{ source_id: 's', mode: 'local', status: 'ready', source_current: true, payload: { nodes, edges: [] } }] })
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r }); return { promise, resolve } }
const api = (overrides = {}) => ({ getCourse: async id => ({ course_id: id }), getDraft: async () => snapshot(),
  saveDecisions: async (_c, _d, _r, decisions) => {
    const s = snapshot(); s.sources[0].payload.nodes[0].decision = decisions[0]; return s
  }, preview: async () => ({ confirmation_token: 't', revision_digest: 'r' }), ...overrides })

test('late_course_result_does_not_replace_selection', async () => {
  const old = deferred()
  const flow = createCourseReviewFlow(api({ getCourse: id => id === 'old' ? old.promise : Promise.resolve({ course_id: id }) }))
  const request = flow.loadCourse('old')
  await flow.loadCourse('new')
  old.resolve({ course_id: 'old' }); await request
  assert.equal(flow.state.courseId, 'new')
  assert.equal(flow.state.course.course_id, 'new')
})

test('confirm_disabled_for_invalid_or_unsaved_decisions', async () => {
  const flow = createCourseReviewFlow(api({ getDraft: async () => snapshot([node('栈'), node('错项', 'invalid')]) }))
  await flow.loadCourse('c', 'd')
  assert.equal(flow.canPreview(), false)
  assert.equal(flow.setDecision({ item_id: '错项', verdict: 'accept' }), false)
  flow.setDecision({ item_id: '栈', verdict: 'accept' })
  assert.equal(flow.state.dirty, true)
  assert.equal(flow.canPreview(), false)
  await flow.saveDecisions(); assert.equal(flow.canPreview(), true)
  await flow.preview(); assert.equal(flow.canConfirm(), true)
  flow.setDecision({ item_id: '栈', verdict: 'revise', label: '栈结构' })
  assert.equal(flow.canConfirm(), false)
})

test('retry_reuses_key_and_stale_digest_requires_preview', async () => {
  const keys = []; let calls = 0
  const flow = createCourseReviewFlow(api({ confirm: async (_c, _d, body) => {
    keys.push(body.request_key); if (++calls === 1) throw new Error('network')
    throw Object.assign(new Error('revision_conflict'), { status: 409 })
  } }))
  await flow.loadCourse('c', 'd'); flow.setDecision({ item_id: '栈', verdict: 'accept' })
  await flow.saveDecisions(); await flow.preview(); await flow.confirm(); await flow.confirm()
  assert.equal(keys.length, 2); assert.equal(keys[0], keys[1])
  assert.equal(flow.state.preview, null); assert.equal(flow.canConfirm(), false)
})

test('cancel_stops_next_source_and_keeps_ready_results', async () => {
  const running = deferred(); const called = []
  const s = snapshot(); s.sources.push({ source_id: 's2', status: 'pending', mode: 'local', payload: {} })
  const flow = createCourseReviewFlow(api({ createDraft: async () => s,
    extract: async (_c, _d, sid) => { called.push(sid); return running.promise },
    cancel: async () => ({ ...s, status: 'cancelled' }) }))
  await flow.loadCourse('c'); flow.selectSources(['s', 's2'])
  // 首个来源已ready，不重复提取；取消执行中的第二个，不能再调后续来源。
  s.sources.push({ source_id: 's3', status: 'pending', mode: 'local', payload: {} })
  const request = flow.extract('local', false)
  await new Promise(r => setTimeout(r, 0)); await flow.cancel()
  running.resolve(s); await request
  assert.deepEqual(called, ['s2'])
  assert.equal(flow.state.snapshot.status, 'cancelled')
  assert.equal(flow.state.snapshot.sources[0].status, 'ready')
})

test('new_course_panel_off_keeps_legacy_route', () => {
  assert.equal(coursePanelEnabled(undefined), false)
  assert.equal(coursePanelEnabled('false'), false)
  assert.equal(coursePanelEnabled('true'), true)
})

test('revoked_candidates_are_restored_from_history_and_not_republished', async () => {
  const item = { ...node('栈'), review_status: 'revoked', decision: { item_id: '栈', verdict: 'accept' } }
  const flow = createCourseReviewFlow(api({ getDraft: async () => snapshot([item]) }))
  await flow.loadCourse('c', 'd')
  assert.equal(flow.canPreview(), false)
})

test('failed_first_source_does_not_starve_later_pending_sources', async () => {
  const s = snapshot(); s.sources[0].status = 'pending'
  s.sources.push({ ...s.sources[0], source_id: 'good' })
  const called = []
  const flow = createCourseReviewFlow(api({ createDraft: async () => structuredClone(s),
    getDraft: async () => ({ ...s, sources: s.sources.map(x => x.source_id === 's' ? { ...x, status: 'failed' } : x) }),
    extract: async (_c, _d, sid) => { called.push(sid); if (sid === 's') throw Object.assign(new Error('extraction_failed'), {status:502}); return { ...s, sources:s.sources.map(x => ({...x,status:x.source_id === 'good' ? 'ready' : 'failed'})) } }
  }))
  await flow.loadCourse('c'); flow.selectSources(['s', 'good']); await flow.extract('local', false)
  assert.deepEqual(called, ['s', 'good'])
  assert.equal(flow.state.snapshot.sources[1].status, 'ready')
})

test('unknown_network_extraction_keeps_key_until_its_result_is_known', async () => {
  const s = snapshot(); s.sources[0].status = 'pending'; const keys = []
  const flow = createCourseReviewFlow(api({ createDraft: async () => s, getDraft: async () => s,
    extract: async (_c, _d, _sid, _mode, _consent, key) => { keys.push(key); throw new Error('network') }
  }))
  await flow.loadCourse('c'); flow.selectSources(['s']); await flow.extract('local', false); await flow.extract('local', false, true)
  assert.equal(keys.length, 2); assert.equal(keys[0], keys[1])
})
