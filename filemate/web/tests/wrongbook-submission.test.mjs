import assert from 'node:assert/strict'
import test from 'node:test'
const mod = await import('../src/wrongbook/submission.ts').catch(() => ({}))
const present = await import('../src/wrongbook/presentation.ts').catch(() => ({}))
const raw = { question_type: 'choice', stem: '栈的次序？', answer: 'A', options: ['后进先出', '先进先出'], analysis: '后进先出' }
const ref = { artifact_id: 'a', question_index: 0, question_digest: 'd'.repeat(64), wrong_id: 'w' }
const scope = 'a'.repeat(64)
const receipt = { attempt_id: 'saved', wrong_id: 'w', is_correct: false, score: 0, feedback: '未通过', judgement_method: 'objective_rule', judgement_status: 'verified', rule_version: 'review-interval-v2', reference_answer: 'A', eligible: false, reason: 'wrong', before: {}, after: {}, review_event_id: 'e' }
async function until(check) { for (let n = 0; n < 100 && !check(); n++) await new Promise(resolve => setTimeout(resolve, 5)); assert.ok(check(), 'request should start') }
function memory() { const map = new Map(); return { map, getItem: k => map.get(k) ?? null, setItem: (k, v) => map.set(k, v), removeItem: k => map.delete(k) } }
function setup(api = {}, storage = memory()) {
  assert.equal(typeof mod.createReviewSubmission, 'function')
  const requests = []; let serial = 0
  const control = mod.createReviewSubmission({ submitReviewAnswer: async body => { requests.push(structuredClone(body)); return receipt }, getReviewReceipt: async () => { throw { status: 404 } }, ...api }, { scope, storage, makeKey: () => `request-key-${++serial}-000000` })
  return { control, requests, storage }
}

test('double click and Enter are one saved operation and keep the raw question', async () => {
  let release
  const pending = new Promise(resolve => { release = resolve })
  const { control, requests } = setup({ submitReviewAnswer: async body => { requests.push(body); await pending; return receipt } })
  await control.open(ref, raw); control.setAnswer('B')
  const a = control.submit(), b = control.submit(); await until(() => requests.length === 1)
  assert.equal(requests.length, 1)
  release(); await Promise.all([a, b])
  assert.equal(control.state.receipt.attempt_id, 'saved'); assert.deepEqual(requests[0].expected_question, raw)
  await control.submit(); assert.equal(requests.length, 1)
})

test('a lost response blocks changed input and retries the exact saved key', async () => {
  const requests = []; let calls = 0
  const { control, storage } = setup({ submitReviewAnswer: async body => { requests.push(structuredClone(body)); if (++calls === 1) throw { status: 503 }; return receipt } })
  await control.open(ref, raw); control.setAnswer('private-answer'); await control.submit()
  assert.equal(control.state.uncertain, true)
  assert.equal(control.setAnswer('changed'), false)
  await control.submit()
  assert.equal(requests.length, 2); assert.deepEqual(requests[0], requests[1]); assert.equal(control.state.uncertain, false)
  assert.ok(!JSON.stringify([...storage.map]).includes('private-answer'))
})

test('refresh first recovers a persisted receipt without another POST', async () => {
  const storage = memory()
  const first = setup({ submitReviewAnswer: async () => { throw Error('offline') } }, storage).control
  await first.open(ref, raw); first.setAnswer('B'); await first.submit(); first.dispose()
  let posted = 0
  const second = setup({ submitReviewAnswer: async () => { posted++; return receipt }, getReviewReceipt: async () => receipt }, storage).control
  await second.open(ref, raw); await second.recover()
  assert.equal(second.state.receipt.attempt_id, 'saved'); assert.equal(posted, 0)
})

test('missing receipt after refresh stays uncertain and requires the original body', async () => {
  const storage = memory()
  const first = setup({ submitReviewAnswer: async () => { throw Error('offline') } }, storage).control
  await first.open(ref, raw); first.setAnswer('B'); await first.submit(); first.dispose()
  const { control, requests } = setup({}, storage)
  await control.open(ref, raw); await control.recover()
  assert.equal(control.state.uncertain, true)
  control.setAnswer('A'); assert.equal(await control.submit(), false); assert.equal(requests.length, 0)
  control.setAnswer('B'); await control.submit(); assert.equal(requests.length, 1)
})

test('viewing an answer is sticky through answer edits and a failed send', async () => {
  const { control, requests } = setup()
  await control.open(ref, raw); control.revealAnswer(); control.setAnswer(''); control.setAnswer('A'); await control.submit()
  assert.equal(requests[0].answer_revealed, true)
  assert.equal(control.state.answerRevealed, true)
  assert.equal(typeof present.reviewResultLabel, 'function')
  assert.match(present.reviewResultLabel({ ...receipt, is_correct: null }), /待核对/)
})

test('a revision conflict keeps the draft but blocks resubmitting a stale snapshot', async () => {
  const { control } = setup({ submitReviewAnswer: async () => { throw { status: 409 } } })
  await control.open(ref, raw); control.setAnswer('保留原稿'); await control.submit()
  assert.equal(control.state.answer, '保留原稿'); assert.equal(control.state.stale, true)
  assert.equal(await control.submit(), false)
})

test('late response cannot enter another question or identity', async () => {
  let release
  const { control } = setup({ submitReviewAnswer: () => new Promise(resolve => { release = resolve }) })
  await control.open(ref, raw); control.setAnswer('B'); const posting = control.submit()
  await until(() => typeof release === 'function')
  control.resetIdentity('b'.repeat(64)); await control.open({ ...ref, artifact_id: 'other' }, raw)
  release(receipt); await posting
  assert.equal(control.state.receipt, null); assert.equal(control.state.answer, '')
})

test('display normalization never edits the expected question or runs HTML', () => {
  assert.equal(typeof present.presentReviewQuestion, 'function')
  const input = { type: '选择题', question: '<script>hello</script>', options: { X: '左边', Y: '右边' }, answer: 'Y', explanation: '引用全文' }
  const before = structuredClone(input), shown = present.presentReviewQuestion(input)
  assert.deepEqual(shown.options, [{ key: 'X', text: '左边' }, { key: 'Y', text: '右边' }])
  assert.equal(shown.stem, '<script>hello</script>'); assert.equal(shown.type, 'choice'); assert.deepEqual(input, before)
})

test('schedule events expose their actual undo action',()=>{
 assert.equal(typeof present.reviewEventAction,'function')
 assert.equal(present.reviewEventAction('schedule_pause'),'pause')
 assert.equal(present.reviewEventAction('schedule_undo'),'undo')
})
