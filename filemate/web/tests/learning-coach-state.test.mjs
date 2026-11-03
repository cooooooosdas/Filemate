import test from 'node:test'
import assert from 'node:assert/strict'
import { harness, input, run, deferred } from './learning-coach-fixtures.mjs'

test('opening_never_requests_model', async () => {
  const h = harness(); await h.workspace.open(input())
  assert.equal(h.workspace.state.phase, 'ready')
  assert.deepEqual(h.calls.map(call => call[0]), ['context'])
  await h.workspace.submit('rule')
  const body = h.calls.find(call => call[0] === 'request')[1]
  assert.equal(body.mode, 'rule'); assert.equal(body.allow_external_model, false); assert.equal(body.consent_digest, null)
})
test('consent_is_bound_to_exact_context_and_input', async () => {
  const h = harness(); await h.workspace.open(input())
  h.workspace.state.input.question = '修改之后的私密问题'
  await h.workspace.submit('llm')
  assert.equal(h.calls.filter(call => call[0] === 'request').length, 0)
  await h.workspace.readContext(h.workspace.state.input)
  await h.workspace.submit('llm')
  assert.equal(h.calls.at(-1)[1].consent_digest, 'b'.repeat(64))
  assert.equal(h.calls.at(-1)[1].allow_external_model, true)
})
test('tampering with the displayed payload invalidates consent', async () => {
  const h = harness(); await h.workspace.open(input())
  h.workspace.state.context.external_payload.question = 'changed after preview'
  await h.workspace.submit('llm')
  assert.equal(h.calls.filter(call => call[0] === 'request').length, 0)
})
test('changed_identity_ignores_late_result and erases old authority', async () => {
  const h = harness(); const pending = deferred()
  h.client.context = () => pending.promise
  const work = h.workspace.open(input()); h.setIdentity('c'.repeat(64))
  pending.resolve({}); await work
  assert.equal(h.workspace.state.phase, 'expired')
  assert.equal(h.workspace.state.context, null); assert.equal(h.workspace.state.input, null)
})
test('model_error_keeps_rule_proposal with honest status', async () => {
  const h = harness(); await h.workspace.open(input()); await h.workspace.submit('rule')
  h.client.request = async () => run({ requested_mode: 'llm', effective_mode: 'rule_fallback', model_status: 'failed', safe_error_code: 'timeout' })
  await h.workspace.submit('llm')
  assert.equal(h.workspace.state.run.effective_mode, 'rule_fallback')
  assert.ok(h.workspace.state.run.proposal)
})
test('cancelled late response cannot replace the cancellation', async () => {
  const h = harness(); await h.workspace.open(input()); const pending = deferred()
  h.client.request = async () => pending.promise
  const work = h.workspace.submit('llm'); await h.workspace.cancel()
  pending.resolve(run({ model_status: 'succeeded' })); await work
  assert.equal(h.workspace.state.run.status, 'cancelled')
})
test('raw_text_is_never_persisted and close clears in-memory contents', async () => {
  const old = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { assert.fail('body reached persistent browser storage') } })
  try { const h = harness(); await h.workspace.open(input()); await h.workspace.submit('rule'); h.workspace.close(); assert.equal(h.workspace.state.input, null); assert.equal(h.workspace.state.run, null) }
  finally { if (old) Object.defineProperty(globalThis, 'localStorage', old); else delete globalThis.localStorage }
})


test('Vue reactive state can submit without cloning a Proxy into the browser API', async () => {
  const { reactive } = await import('vue')
  const h = harness(reactive); await h.workspace.open(input()); await h.workspace.submit('rule')
  assert.equal(h.workspace.state.phase, 'ready')
  assert.equal(h.calls.filter(call => call[0] === 'request').length, 1)
})
test('a different context clears advice and draft from the previous goal', async () => {
  const h = harness(); await h.workspace.open(input()); await h.workspace.submit('rule')
  const next = input(); next.scope.goal_id = 'another-synthetic-goal'
  await h.workspace.readContext(next)
  assert.equal(h.workspace.state.run, null); assert.equal(h.workspace.state.draft, null)
})


test('401 during evidence reading clears personal text and authority', async () => {
  const h = harness(); h.client.context = async () => { throw { status: 401 } }
  await h.workspace.open(input())
  assert.equal(h.workspace.state.phase, 'expired'); assert.equal(h.workspace.state.input, null); assert.equal(h.workspace.state.identity, null)
})
test('401 during cancellation clears the previous proposal', async () => {
  const h = harness(); await h.workspace.open(input()); await h.workspace.submit('rule')
  h.client.cancel = async () => { throw { status: 401 } }
  await h.workspace.cancel()
  assert.equal(h.workspace.state.phase, 'expired'); assert.equal(h.workspace.state.run, null); assert.equal(h.workspace.state.context, null)
})


test('fresh verification of unchanged evidence preserves the local rule if model transport fails', async () => {
  const h = harness(); await h.workspace.open(input()); await h.workspace.submit('rule')
  const original = structuredClone(h.workspace.state.run)
  await h.workspace.readContext(h.workspace.state.input)
  h.client.request = async () => { throw { status: 503 } }
  await h.workspace.submit('llm')
  assert.deepEqual(h.workspace.state.run, original)
  assert.equal(h.workspace.state.phase, 'error')
})


test('an identity change before cancellation prevents any write to the new account', async () => {
  const h = harness(); await h.workspace.open(input()); await h.workspace.submit('rule')
  h.setIdentity('d'.repeat(64)); await h.workspace.cancel()
  assert.equal(h.calls.filter(call => call[0] === 'cancel').length, 0)
  assert.equal(h.workspace.state.phase, 'expired')
})
test('an identity change before re-reading does not send the old private question', async () => {
  const h = harness(); await h.workspace.open(input())
  const old = h.workspace.state.input; h.setIdentity('d'.repeat(64)); await h.workspace.readContext(old)
  assert.equal(h.calls.filter(call => call[0] === 'context').length, 1)
  assert.equal(h.workspace.state.input, null)
})
