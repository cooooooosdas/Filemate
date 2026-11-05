import assert from 'node:assert/strict'
import test from 'node:test'
import { resolveHomeAction, createSampleImporter } from '../src/home/action.ts'

const ready = { status: 'ready', authenticated: false, sourceId: null, due: 0 }
test('home CTA uses confirmed library and account state', () => {
  assert.equal(resolveHomeAction({ ...ready, status: 'loading' }).kind, 'pending')
  assert.equal(resolveHomeAction({ ...ready, status: 'error' }).kind, 'retry')
  assert.equal(resolveHomeAction({ ...ready, authenticated: null }).kind, 'pending')
  assert.equal(resolveHomeAction(ready).kind, 'sample')
  assert.equal(resolveHomeAction({ ...ready, authenticated: true }).route, '/import?intent=study')
  assert.equal(resolveHomeAction({ ...ready, sourceId: 'a &中' }).route, '/ai-tools?source=a%20%26%E4%B8%AD')
  assert.equal(resolveHomeAction({ ...ready, sourceId: 'one', due: 3 }).route, '/wrongbook')
})
test('sample double click joins actual import; failure can retry', async () => {
  let calls = 0
  let release
  const run = createSampleImporter(() => { calls++; return new Promise(resolve => { release = resolve }) })
  const first = run(), second = run()
  assert.equal(calls, 1)
  release({ source_id: 'real' })
  assert.deepEqual(await first, await second)
  let attempts = 0
  const retry = createSampleImporter(async () => { if (++attempts === 1) throw new Error('offline'); return 'saved' })
  await assert.rejects(retry(), /offline/)
  assert.equal(await retry(), 'saved')
})
