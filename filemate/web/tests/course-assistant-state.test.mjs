import assert from 'node:assert/strict'
import test from 'node:test'
import { createGraphAssistantController } from '../src/course-graph/assistant-state.ts'

const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r }); return { resolve, promise } }
const saved = (id = 'w', status = 'ready') => ({ work_id: id, kind: 'answer', status, stale: false, payload: status === 'ready' ? { explanation: '原文说明', personal_facts: [{ status: 'no_evidence', counts: { attempts: 0 } }] } : {} })
function api(extra = {}) { return { answerGraphCourse: async () => saved(), getCourseLearningWork: async (_c, id) => saved(id), getCourseOperations: async () => ({ items: [], total: 0, offset: 0, limit: 50 }), previewGraphAssistantPlan: async () => ({ confirmation_token: 'p', tasks: [] }), confirmCoursePath: async () => ({ operation_id: 'o', plan_id: 'plan' }), cancelCourseLearningWork: async () => saved('w', 'cancelled'), ...extra } }
test('consent_is_per_request_not_restored', async () => {
  let calls = 0; const c = createGraphAssistantController(api({ answerGraphCourse: async () => { calls++; return saved() } }))
  c.open('s', 'c', 'n'); c.setQuestion('解释栈'); c.setMode('llm')
  assert.equal(await c.send(), false); c.setConsent(true); await c.send(); assert.equal(c.state.consent, false)
  assert.equal(await c.send(), false); assert.equal(calls, 1)
  c.open('s', 'other', 'n'); assert.equal(c.state.consent, false)
})
test('late_answer_never_crosses_scope', async () => {
  const pending = deferred(), c = createGraphAssistantController(api({ answerGraphCourse: () => pending.promise }))
  c.open('alice', 'c', 'n'); c.setQuestion('问题'); const request = c.send()
  c.open('bob', 'c', 'n'); pending.resolve(saved()); await request
  assert.equal(c.state.work, null); assert.equal(c.state.question, ''); assert.equal(c.state.busy, '')
})
test('network_unknown_does_not_duplicate_model_call', async () => {
  const calls = []; let first = true
  const c = createGraphAssistantController(api({ answerGraphCourse: async (_c, body) => { calls.push(body); if (first) { first = false; throw Error('network') }; return saved() } }))
  c.open('s', 'c', 'n'); c.setQuestion('问题'); c.setMode('llm'); c.setConsent(true)
  await c.send(); assert.equal(c.state.uncertain, true); assert.equal(c.state.consent, false)
  await c.send(); assert.equal(calls[0].request_key, calls[1].request_key); assert.equal(calls[1].allow_external_model, true)
})
test('facts_are_read_only_and_failed_model_has_no_fake_answer', async () => {
  const c = createGraphAssistantController(api({ answerGraphCourse: async () => saved('w', 'failed') }))
  c.open('s', 'c', 'n'); c.setQuestion('问题'); await c.send()
  assert.equal(c.state.work.status, 'failed'); assert.deepEqual(c.state.work.payload, {}); assert.equal(c.state.planPreview, null)
})
test('agent_preview_never_autoconfirms', async () => {
  let confirms = 0; const c = createGraphAssistantController(api({ confirmCoursePath: async () => { confirms++; return { plan_id: 'plan', operation_id: 'o' } } }))
  c.open('s', 'c', 'n'); c.setQuestion('学习栈'); await c.previewPlan()
  assert.equal(confirms, 0); await c.confirmPlan(); await c.confirmPlan(); assert.equal(confirms, 1)
  c.setPlanOptions({ days: 2 }); assert.equal(c.state.planPreview, null)
})
test('history_reopen_is_read_only', async () => {
  let sends = 0; const c = createGraphAssistantController(api({ answerGraphCourse: async () => { sends++ }, getCourseLearningWork: async () => ({ ...saved(), stale: true }) }))
  c.open('s', 'c', 'n'); await c.loadHistory(); await c.reopen('w'); assert.equal(sends, 0); assert.equal(c.state.work.stale, true)
})
test('cancellation_wins_over_late_answer', async () => {
  const pending = deferred(); let key
  const c = createGraphAssistantController(api({ answerGraphCourse: (_c, body) => { key = body.request_key; return pending.promise }, getCourseOperations: async () => ({ items: [{ work_id: 'w', request_key: key, work_kind: 'answer' }] }) }))
  c.open('s', 'c', 'n'); c.setQuestion('问题'); const request = c.send(); await c.cancel()
  pending.resolve(saved()); await request; assert.equal(c.state.work.status, 'cancelled'); assert.equal(c.state.busy, '')
})
test('editing_after_an_answer_is_unsent_and_keeps_the_previous_result', async () => {
  const c = createGraphAssistantController(api())
  c.open('s', 'c', 'n'); c.setQuestion('第一个问题'); await c.send()
  assert.equal(c.dirty(), false)
  c.setQuestion('新的问题'); assert.equal(c.dirty(), true)
  assert.equal(c.state.work.work_id, 'w')
  await c.send(); assert.equal(c.dirty(), false)
})
