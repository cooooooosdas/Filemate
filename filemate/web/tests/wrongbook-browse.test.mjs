import assert from 'node:assert/strict'
import test from 'node:test'
const mod = await import('../src/wrongbook/browse-state.ts').catch(() => ({}))
const scope = 'a'.repeat(64)
function memory() { const map = new Map(); return { map, getItem: k => map.get(k) ?? null, setItem: (k, v) => map.set(k, v), removeItem: k => map.delete(k) } }

test('only bounded navigation conditions enter the URL, never answers', () => {
  assert.equal(typeof mod.readReviewBrowse, 'function')
  const state = mod.readReviewBrowse({ focus: 'w', q: '栈', offset: '30', status: 'pending', answer: 'private', mode: 'focus' })
  assert.equal(state.focus, 'w'); assert.equal(state.offset, 30); assert.equal(state.filters.status, 'pending')
  assert.equal(mod.reviewBrowseQuery(state).answer, undefined)
  assert.ok(state.notice)
  const bad = mod.readReviewBrowse({ focus: ['a', 'b'], status: 'unknown', offset: '-20', q: 'x'.repeat(161) })
  assert.equal(bad.focus, ''); assert.equal(bad.offset, 0); assert.equal(bad.filters.status, 'all'); assert.ok(bad.notice)
})

test('batch metadata is identity scoped, bounded, and does not preserve extra text', () => {
  assert.equal(typeof mod.createReviewPreferences, 'function')
  const storage = memory(), a = mod.createReviewPreferences(storage, scope)
  const batch = { created_at: '2026-10-26T00:00:00Z', position: 0, items: [{ wrong_id: 'w', artifact_id: 'a', question_index: 0, question_digest: 'b'.repeat(64), attempt_id: 'saved', request_key: 'key-0000000000000', answer: 'private' }] }
  a.saveBatch(batch)
  assert.equal(a.getBatch().items[0].attempt_id, 'saved')
  assert.ok(!JSON.stringify([...storage.map]).includes('private'))
  assert.equal(mod.createReviewPreferences(storage, 'b'.repeat(64)).getBatch(), null)
  assert.equal(a.saveBatch({ ...batch, items: Array(21).fill(batch.items[0]) }), false)
})

test('blocked storage and corrupt preferences preserve usable in-page navigation', () => {
  assert.equal(typeof mod.createReviewPreferences, 'function')
  const storage = { getItem() { throw Error('blocked') }, setItem() { throw Error('blocked') }, removeItem() {} }
  const pref = mod.createReviewPreferences(storage, scope)
  pref.setBrowse(mod.readReviewBrowse({ focus: 'w' }), 235)
  assert.equal(pref.getBrowse().browse.focus, 'w'); assert.equal(pref.getBrowse().scroll, 235)
  const unknown = mod.createReviewPreferences(memory(), null)
  assert.equal(unknown.getBatch(), null)
})

test('stale navigation preferences cannot erase a newer focus batch',()=>{
 const data=new Map(),storage={getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)},scope='a'.repeat(64)
 const navigation=mod.createReviewPreferences(storage,scope),focus=mod.createReviewPreferences(storage,scope)
 const batch={created_at:new Date().toISOString(),position:0,items:[{wrong_id:'w',artifact_id:'a',question_index:0,question_digest:'a'.repeat(64),attempt_id:'saved'}]}
 focus.saveBatch(batch);navigation.setBrowse(mod.readReviewBrowse({mode:'focus'}));assert.deepEqual(mod.createReviewPreferences(storage,scope).getBatch(),batch)
})
