import assert from 'node:assert/strict'
import test from 'node:test'
const mod = await import('../src/wrongbook/workspace-state.ts').catch(() => ({}))
const question = { type: 'fill', question: '栈的顺序', answer: '后进先出' }
const detail = id => ({ wrong_id: id, artifact_id: 'a', question_index: 0, question_digest: 'd'.repeat(64), question, revision: 1, error_causes: [], custom_tags: [], error_cause_note: '', error_cause: '', read_only_snapshot: false, data_error: false, source_id: 's' })
function setup(overrides = {}) {
  assert.equal(typeof mod.createReviewWorkspaceController, 'function')
  const calls = []
  const api = { getReviewBrowserScope: async () => 'a'.repeat(64), getReviewCapabilities: async () => ({ write_enabled: true }), getReviewSummary: async () => ({ total: 1 }), getReviewPage: async p => ({ items: [detail('first')], total: 1, has_more: false, offset: p.offset }), getReviewDetail: async id => detail(id), getReviewAttempts: async () => ({ items: [], total: 0 }), getReviewEvents: async () => ({ items: [], total: 0 }), getLearningSource: async () => ({ raw_text: '原文' }), setReviewDiagnosis: async (id, body) => { calls.push(body); return { ...detail(id), error_causes: body.error_causes } }, previewReviewSchedule: async (id, body) => ({ wrong_id: id, before: {}, after: { schedule_status: 'paused' }, confirmation_token: 'token' }), confirmReviewSchedule: async (id, body) => { calls.push(body); return { wrong_id: id, after: { schedule_status: 'paused' }, review_event_id: 'event' } }, submitReviewAnswer: async () => ({}), getReviewReceipt: async () => ({}), ...overrides }
  return { control: mod.createReviewWorkspaceController(api), calls }
}

test('clearing a confirmed empty selection removes the old writable question and ignores a late detail', async () => {
  let release
  const {control: c} = setup({getReviewDetail: id => id === 'late' ? new Promise(resolve => { release = resolve }) : Promise.resolve(detail(id))})
  await c.initialize(); await c.select('first')
  c.submission.setAnswer('unsubmitted draft'); c.state.diagnosis.note = 'unsaved note'
  c.clearSelection()
  assert.equal(c.state.detail, null); assert.equal(c.state.selected, '')
  assert.equal(c.writable(), false); assert.equal(c.dirty(), false)
  assert.equal(c.submission.state.answer, '')
  const pending = c.select('late'); c.clearSelection(); release(detail('late')); await pending
  assert.equal(c.state.detail, null); assert.equal(c.state.selected, '')
  assert.equal(c.state.detailLoading, false)
})

test('after an answer refresh detail revision without losing receipt or unsaved diagnosis',async()=>{
 let revision=1;const expected=[]
 const {control:c}=setup({getReviewDetail:async id=>({...detail(id),revision}),submitReviewAnswer:async()=>{revision++;return {attempt_id:'saved'}},setReviewDiagnosis:async(id,b)=>{expected.push(b.expected_revision);return {}}})
 await c.initialize();await c.select('first');c.state.diagnosis.note='my unsaved diagnosis';c.submission.setAnswer('A');await c.submission.submit()
 assert.equal(await c.refreshAfterAnswer(),true);assert.equal(c.state.detail.revision,2);assert.equal(c.submission.state.receipt.attempt_id,'saved');assert.equal(c.state.diagnosis.note,'my unsaved diagnosis')
 await c.saveDiagnosis();assert.deepEqual(expected,[2])
})

test('late answer detail refresh cannot replace another selection',async()=>{
 let release,hold=false;const {control:c}=setup({getReviewDetail:async id=>hold&&id==='first'?new Promise(r=>{release=r}):detail(id)})
 await c.initialize();await c.select('first');hold=true;const refresh=c.refreshAfterAnswer();await c.select('second');release({...detail('first'),revision:9});await refresh
 assert.equal(c.state.detail.wrong_id,'second')
})

test('failed post-answer refresh preserves success and blocks stale revision writes until retry',async()=>{
 let fail=false;const {control:c}=setup({getReviewDetail:async id=>{if(fail)throw Error('offline');return detail(id)}})
 await c.initialize();await c.select('first');c.submission.state.receipt={attempt_id:'saved'};fail=true
 assert.equal(await c.refreshAfterAnswer(),false);assert.equal(c.submission.state.receipt.attempt_id,'saved');assert.equal(c.writable(),false)
 fail=false;await c.refreshAfterAnswer();assert.equal(c.writable(),true)
})
test('deep links select their actual id, and missing ids never fall back to first', async () => {
  const { control: c } = setup({ getReviewDetail: async id => { if (id === 'gone') throw { status: 404 }; return detail(id) } })
  await c.initialize(); await c.loadPage({}); await c.select('page100'); assert.equal(c.state.detail.wrong_id, 'page100')
  await c.select('gone'); assert.equal(c.state.detail, null); assert.match(c.state.detailError, /不存在|不可用/)
})
test('deleting the final page returns to the final valid offset, including empty library', async () => {
  const offsets = []; const { control: c } = setup({ getReviewPage: async p => { offsets.push(p.offset); return { items: p.offset ? [] : [detail('w')], total: 1, has_more: false, offset: p.offset } } })
  await c.loadPage({}, 60); assert.deepEqual(offsets, [60, 0]); assert.equal(c.state.offset, 0)
})
test('late detail and source responses cannot replace the selected question', async () => {
  let finish; const { control: c } = setup({ getReviewDetail: id => id === 'old' ? new Promise(r => { finish = r }) : Promise.resolve(detail(id)) })
  const old = c.select('old'); await c.select('new'); finish(detail('old')); await old; assert.equal(c.state.detail.wrong_id, 'new')
})
test('detail and history failures can be retried independently', async () => {
  let fails = true; const { control: c } = setup({ getReviewAttempts: async () => { if (fails) throw Error('offline'); return { items: [{ attempt_id: 'x' }], total: 1 } } })
  await c.select('w'); await c.history('attempts'); assert.ok(c.state.historyError); assert.equal(c.state.detail.wrong_id, 'w'); fails = false; await c.history('attempts'); assert.equal(c.state.historyItems.length, 1)
})
test('cleared diagnosis sends an empty list, conflict preserves the draft', async () => {
  const { control: c, calls } = setup(); await c.initialize(); await c.select('w'); c.state.diagnosis.error_causes = ['careless']; await c.saveDiagnosis(); assert.deepEqual(calls[0].error_causes, ['careless'])
  c.state.diagnosis.error_causes = []; await c.saveDiagnosis(); assert.deepEqual(calls[1].error_causes, [])
  const { control: x } = setup({ setReviewDiagnosis: async () => { throw { status: 409 } } }); await x.initialize(); await x.select('w'); x.state.diagnosis.note = '原稿'; await x.saveDiagnosis(); assert.equal(x.state.diagnosis.note, '原稿'); assert.match(x.state.writeError, /变化|刷新/)
})
test('schedule confirms exactly the previewed command; retry preserves key and token', async () => {
  let attempts = 0; const sent = []; const { control: c } = setup({ confirmReviewSchedule: async (id, body) => { sent.push(structuredClone(body)); if (++attempts === 1) throw Error('lost'); return { after: {}, review_event_id: 'e' } } })
  await c.initialize(); await c.select('w'); await c.previewSchedule({ action: 'pause' }); assert.equal(sent.length, 0); await c.confirmSchedule(); await c.confirmSchedule(); assert.deepEqual(sent[0], sent[1]); assert.equal(c.state.preview, null)
})
test('saved writes followed by failed refresh are described as saved', async () => {
  let reads = 0; const { control: c } = setup({ getReviewDetail: async id => { if (++reads > 1) throw Error('offline'); return detail(id) } }); await c.initialize(); await c.select('w'); await c.previewSchedule({ action: 'resume' }); assert.equal(await c.confirmSchedule(), true); assert.match(c.state.message, /已保存.*刷新/); assert.equal(c.state.writeError, '')
})
test('capability failure blocks writing and switching identity discards old UI application', async () => {
  const { control: c, calls } = setup({ getReviewCapabilities: async () => { throw Error('offline') } }); await c.initialize(); await c.select('w'); assert.equal(await c.previewSchedule({ action: 'pause' }), false); assert.equal(calls.length, 0); c.resetIdentity(null); assert.equal(c.state.detail, null); assert.equal(c.state.capability, null)
})
