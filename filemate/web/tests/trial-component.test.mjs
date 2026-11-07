import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { parse, compileScript } from '@vue/compiler-sfc'
import ts from 'typescript'
import * as vue from 'vue'
import { createTrialRecordState } from '../src/today/trial-record-state.ts'

const tick = () => new Promise(resolve => setImmediate(resolve))
async function setup() {
  const source = await readFile(new URL('../src/components/TrialRecords.vue', import.meta.url), 'utf8')
  const script = compileScript(parse(source).descriptor, { id: 'trial-record-races' }).content
  const code = ts.transpileModule(script, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const module = { exports: {} }, scope = vue.effectScope(), callbacks = []
  const values = new Map(), storage = { getItem: k => values.get(k) ?? null, setItem: (k,v) => values.set(k,v), removeItem: k => values.delete(k) }
  const runtime = { ...vue, onBeforeUnmount: fn => callbacks.push(fn) }
  const deps = { '../today/trial-record-state': { createTrialRecordState, trialSessionStorage: () => storage, trialEpoch: () => 'epoch' } }
  new Function('require','module','exports',code)(name => name === 'vue' ? runtime : deps[name] ?? {}, module,module.exports)
  const requests = new Map(), client = { listRecords: async () => ({items:[],total:0}), detail: id => new Promise(resolve => requests.set(id,resolve)) }
  let state
  scope.run(() => { state = module.exports.default.setup(vue.reactive({ client, identity:'one' }), { expose(){}, emit(){} }) })
  await tick()
  return { state, client, requests, close(){ callbacks.forEach(fn=>fn());scope.stop() } }
}
const record = id => ({ record_id:id, kind:'feedback', title:`record ${id}`, content:{description:`text ${id}`} })

test('record detail ignores older reply after selecting another record', async () => {
  const x = await setup()
  const a = x.state.read('a'), b = x.state.read('b')
  x.requests.get('b')(record('b')); await b
  x.requests.get('a')(record('a')); await a
  assert.equal(x.state.detail.value.record_id,'b')
  x.close()
})

test('record selection cannot change beneath an in-flight deletion preview', async () => {
  const x = await setup()
  const a = x.state.read('a'); x.requests.get('a')(record('a')); await a
  let finish
  x.client.previewDelete = () => new Promise(resolve => { finish = resolve })
  const preview = x.state.controller.previewDelete('a')
  const b = x.state.read('b')
  if (x.requests.has('b')) x.requests.get('b')(record('b'))
  await b
  finish({confirmation_token:'token',affected:{}}); await preview
  assert.equal(x.state.detail.value.record_id,'a')
  x.close()
})
