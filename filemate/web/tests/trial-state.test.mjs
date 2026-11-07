import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'

const url = new URL('../src/today/trial-record-state.ts', import.meta.url)
const implementation = existsSync(url) ? await import(url.href) : null
function fixture() {
  assert.equal(typeof implementation?.createTrialRecordState, 'function', 'trial record controller exists')
  const values = new Map(), calls = []
  const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) }
  const receipt = { record_id: 'record-one', kind: 'reflection', status: 'saved', created_at: '2026-11-06T00:00:00Z' }
  const client = {
    saveReflection: async body => { calls.push(['post', body]); throw new Error('lost response') },
    findRequest: async key => { calls.push(['get', key]); return receipt },
    readWeekly: async () => ({ revision: 'new-revision' }),
  }
  let epoch = 'one'
  const controller = implementation.createTrialRecordState(client, storage, { epoch: () => epoch })
  controller.bind('account-one')
  return { values, calls, client, receipt, controller, storage, epoch: value => { epoch = value } }
}

test('trial saves a body-free locator before POST and recovers exclusively with GET', async () => {
  const x = fixture()
  x.client.saveReflection = async body => {
    assert.deepEqual(JSON.parse([...x.values.values()][0]), { kind: 'reflection', request_key: body.request_key })
    x.calls.push(['post', body]); throw new Error('lost')
  }
  await x.controller.save('reflection', { notes: 'private reflection', expected_revision: 'old' })
  assert.equal(x.controller.state.pending.kind, 'reflection')
  assert.ok(![...x.values.values()].join('').includes('private'))
  await x.controller.recover()
  assert.deepEqual(x.calls.map(call => call[0]), ['post', 'get'])
  assert.equal(x.controller.state.receipt.status, 'saved')
  assert.equal(x.values.size, 0)
})

test('trial uncertain 404 preserves locator and blocks another POST', async () => {
  const x = fixture()
  await x.controller.save('reflection', { notes: 'draft' })
  x.client.findRequest = async () => { throw Object.assign(new Error('404'), { response: { status: 404 } }) }
  await x.controller.recover()
  await x.controller.save('reflection', { notes: 'draft' })
  assert.equal(x.calls.filter(call => call[0] === 'post').length, 1)
  assert.equal(x.values.size, 1)
  assert.ok(x.controller.state.pending)
})

test('trial storage failure prevents writes', async () => {
  const x = fixture()
  x.storage.setItem = () => { throw new Error('storage disabled') }
  await x.controller.save('reflection', { notes: 'draft' })
  assert.equal(x.calls.length, 0)
  assert.match(x.controller.state.error, /保存请求编号/)
})

test('trial account and restore epoch changes discard late replies', async () => {
  const x = fixture()
  let finish
  x.client.saveReflection = () => new Promise(resolve => { finish = resolve })
  const saving = x.controller.save('reflection', { notes: 'draft' })
  x.controller.bind('account-two')
  finish(x.receipt)
  await saving
  assert.equal(x.controller.state.receipt, null)
  x.client.saveReflection = async () => { x.epoch('two'); return x.receipt }
  await x.controller.save('reflection', { notes: 'draft' })
  assert.equal(x.controller.state.receipt, null)
})

test('trial 409 clears settled locator while allowing re-read without altering reflection input', async () => {
  const x = fixture(), input = { notes: 'keep my reflection', expected_revision: 'old' }
  x.client.saveReflection = async () => { throw Object.assign(new Error('changed'), { response: { status: 409 } }) }
  await x.controller.save('reflection', input)
  assert.equal(x.controller.state.conflict, true)
  assert.equal(x.controller.state.pending, null)
  await x.controller.readWeekly({ goal_id: 'goal-one' })
  assert.equal(x.controller.state.weekly.revision, 'new-revision')
  assert.equal(input.notes, 'keep my reflection')
})

test('trial deletion persists a fresh delete key and GET recovers deleted status', async () => {
  const x = fixture()
  x.client.previewDelete = async () => ({ confirmation_token: 'secret-token', affected: { records: 1 }, expires_in_seconds: 900 })
  x.client.confirmDelete = async (_id, body) => { x.calls.push(['delete', body]); throw new Error('lost') }
  await x.controller.previewDelete('record-one')
  await x.controller.confirmDelete()
  assert.deepEqual(Object.keys(JSON.parse([...x.values.values()][0])).sort(), ['kind', 'request_key'])
  assert.equal(x.controller.state.pending.kind, 'delete')
  x.client.findRequest = async () => ({ ...x.receipt, kind: 'delete', status: 'deleted', deleted: true })
  await x.controller.recover()
  assert.equal(x.controller.state.receipt.status, 'deleted')
  assert.equal(x.calls.length, 1)
})
