import assert from 'node:assert/strict'
import test from 'node:test'
import { createCourseLearningController } from '../src/course-graph/learning-state.ts'
import { isModelRequest, requiresModelCredential } from '../src/services/llm-vault.ts'

const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r }); return { resolve, promise } }
const page = items => ({ items, total: items.length, offset: 0, limit: 50 })
const question = { artifact_id: 'a', question_index: 0, question_digest: 'a'.repeat(64), question: { question_type: 'fill', stem: '____', answer: '栈' } }
function api(extra = {}) {
  return {
    getCourseLearning: async (_c, nid) => ({ concept_id: nid, status: 'no_evidence', counts: { attempts: 0 }, plans: page([]), wrongs: page([]), question_refs: page([]) }),
    getCourseQuestions: async () => page([question]), getCourseRelated: async () => page([]),
    submitQuizAttempt: async () => ({ is_correct: false, correct_answer: '栈', wrong_id: 'wrong' }),
    previewCoursePath: async () => ({ confirmation_token: 'token', tasks: [] }),
    confirmCoursePath: async () => ({ operation_id: 'o', plan_id: 'p' }),
    generateCoursePractice: async () => { throw Error('must not generate implicitly') },
    ...extra,
  }
}
test('late_read_cannot_cross_node_or_identity', async () => {
  const old = deferred(), c = createCourseLearningController(api({ getCourseLearning: (_c, n) => n === 'old' ? old.promise : Promise.resolve({ concept_id: n }) }))
  const pending = c.open('alice', 'c', 'old'); await c.open('alice', 'c', 'new', true)
  old.resolve({ concept_id: 'old' }); await pending
  assert.equal(c.state.evidence.concept_id, 'new')
  c.resetIdentity(); assert.equal(c.state.evidence, null); assert.equal(c.state.answer, '')
})
test('answer_failure_retains_draft_and_retry_uses_same_version', async () => {
  const calls = []; let first = true
  const c = createCourseLearningController(api({ submitQuizAttempt: async (...args) => { calls.push(args); if (first) { first = false; throw Error('network') }; return { is_correct: false } } }))
  await c.open('s', 'c', 'n'); c.chooseQuestion(question); c.setAnswer('我的回答')
  await c.submitAnswer(); assert.equal(c.state.answer, '我的回答'); assert.equal(c.state.answerReceipt, null)
  await c.submitAnswer(); assert.deepEqual(calls[0], calls[1]); assert.deepEqual(calls[1][3], question.question)
  assert.equal(c.state.answerReceipt.is_correct, false)
})
test('confirm_receipt_dedupes_refresh_not_write', async () => {
  const calls = []; let first = true
  const c = createCourseLearningController(api({ confirmCoursePath: async (_cid, body) => { calls.push(body); if (first) { first = false; throw Error('network') }; return { operation_id: 'o', plan_id: 'p' } } }))
  await c.open('s', 'c', 'n'); c.setPathOptions({ goal: '目标', days: 2, daily_minutes: 20 })
  await c.previewPath(); await c.confirmPath(); await c.confirmPath(); await c.confirmPath()
  assert.equal(calls.length, 2); assert.equal(calls[0].request_key, calls[1].request_key); assert.equal(c.state.planReceipt.plan_id, 'p')
})
test('changed_options_invalidate_preview', async () => {
  const c = createCourseLearningController(api()); await c.open('s', 'c', 'n')
  await c.previewPath(); c.setPathOptions({ days: 3 }); assert.equal(c.state.pathPreview, null)
  assert.equal(await c.confirmPath(), false)
})
test('no_auto_model_after_read_or_reopen', async () => {
  let calls = 0; const c = createCourseLearningController(api({ generateCoursePractice: async () => { calls++ } }))
  await c.open('s', 'c', 'n'); await c.loadEvidence(); await c.open('s', 'c', 'n')
  assert.equal(calls, 0)
  const path = '/api/knowledge-graph/courses/c/concepts/n/practice-drafts'
  assert.equal(isModelRequest('POST', path), true)
  assert.equal(requiresModelCredential('POST', path, { mode: 'local' }), false)
  assert.equal(requiresModelCredential('POST', path, { mode: 'llm' }), true)
  assert.equal(isModelRequest('POST', path + '/confirm'), false)
  assert.equal(isModelRequest('POST', '/api/knowledge-graph/courses/c/assistant/answer'), true)
  assert.equal(isModelRequest('POST', '/api/knowledge-graph/courses/c/assistant/plan/preview'), false)
})
test('cancel_and_navigation_preserve_or_explicitly_discard', async () => {
  const c = createCourseLearningController(api()); await c.open('s', 'c', 'n'); c.chooseQuestion(question); c.setAnswer('未提交')
  assert.equal(await c.open('s', 'c', 'other'), false); assert.equal(c.state.answer, '未提交')
  assert.equal(await c.open('s', 'c', 'other', true), true); assert.equal(c.state.answer, '')
  c.dispose(); assert.equal(c.state.evidence, null)
})
test('plan_completion_does_not_upgrade_training', async () => {
  const c = createCourseLearningController(api({ getCourseLearning: async () => ({ status: 'no_evidence', counts: { attempts: 0 }, plans: page([{ completed: true }]) }) }))
  await c.open('s', 'c', 'n'); assert.equal(c.state.evidence.status, 'no_evidence'); assert.equal(c.state.evidence.counts.attempts, 0)
})
