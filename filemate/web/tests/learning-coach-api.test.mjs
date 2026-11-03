import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import { load } from './learning-coach-fixtures.mjs'

test('all twelve coach methods reuse authenticated HTTP and only model requests wait 65 seconds', async () => {
  const calls = []
  const http = Object.fromEntries(['get', 'post'].map(method => [method, async (...args) => { calls.push({ method, args }); return { success: true, data: { synthetic: true } } }]))
  const client = load('../src/services/learning-coach-api.ts', { './api': { reviewHTTP: http } })
  await client.capabilities(); await client.catalog({}); await client.context({}); await client.request({ mode: 'llm' }); await client.get('synthetic/key')
  await client.cancel('synthetic/key'); await client.preview({}); await client.confirm({}); await client.operation('synthetic/key'); await client.undoPreview('synthetic/op'); await client.undoConfirm('synthetic/op', {}); await client.day('2026-11-03')
  assert.equal(calls.length, 12)
  assert.deepEqual(calls.map(call => call.method), ['get', 'post', 'post', 'post', 'get', 'post', 'post', 'post', 'get', 'post', 'post', 'post'])
  assert.equal(calls[3].args[2].timeout, 65000)
  assert.match(calls[4].args[0], /synthetic%2Fkey$/)
  assert.deepEqual(calls.at(-1).args[1], { study_date: '2026-11-03' })
  assert.ok(calls.every(call => !JSON.stringify(call.args).includes('X-FileMate-LLM-Key')))
})
test('rule request never requires browser credentials', () => {
  const { requiresModelCredential } = load('../src/services/llm-vault.ts')
  const path = '/api/learning/orchestrator/coach/requests'
  assert.equal(requiresModelCredential('POST', path, { mode: 'rule' }), false)
  assert.equal(requiresModelCredential('POST', path, { mode: 'llm' }), true)
  assert.equal(requiresModelCredential('POST', '/api/learning/orchestrator/coach/context', { mode: 'llm' }), false)
})
test('public coach loader defers its implementation until invoked', async () => {
  const raw = readFileSync(new URL('../src/services/api.ts', import.meta.url), 'utf8')
  const tree = ts.createSourceFile('api.ts', raw, ts.ScriptTarget.Latest, true)
  const node = tree.statements.find(item => ts.isVariableStatement(item) && item.declarationList.declarations.some(declaration => declaration.name.getText(tree) === 'loadLearningCoachClient'))
  assert.ok(node, 'a real lazy loader is required')
  let imports = 0
  const module = { exports: {} }
  new Function('require', 'module', 'exports', ts.transpileModule(node.getText(tree), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText)(id => { assert.equal(id, './learning-coach-api'); imports++; return { synthetic: true } }, module, module.exports)
  assert.equal(imports, 0); assert.equal((await module.exports.loadLearningCoachClient()).synthetic, true); assert.equal(imports, 1)
})
