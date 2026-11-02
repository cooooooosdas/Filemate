import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import ts from 'typescript'

const names = ['getOrchestratorCapabilities', 'getOrchestratorGoalOptions', 'readOrchestratorSnapshot',
  'previewOrchestratorSchedule', 'confirmOrchestratorSchedule', 'getOrchestratorToday',
  'findOrchestratorOperation', 'previewOrchestratorUndo', 'confirmOrchestratorUndo']

function evaluate(source, require) {
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', compiled)(require, module, module.exports)
  return module.exports
}
function service(response = { success: true, data: { synthetic: true } }) {
  const calls = []
  const http = Object.fromEntries(['get', 'post'].map(method => [method, async (...args) => {
    calls.push({ method, args })
    if (response instanceof Error) throw response
    return response
  }]))
  let apiImports = 0
  const implementation = new URL('../src/services/orchestrator-api.ts', import.meta.url)
  assert.equal(existsSync(implementation), true, 'the lazily loaded implementation must exist')
  const internal = evaluate(readFileSync(implementation, 'utf8'), id => {
    assert.equal(id, './api', 'reuse the authenticated HTTP module instead of constructing another client')
    apiImports++
    return { reviewHTTP: http }
  })
  assert.equal(apiImports, 1)
  const source = readFileSync(new URL('../src/services/api.ts', import.meta.url), 'utf8')
  const tree = ts.createSourceFile('api.ts', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const exportedNames = [...names, 'loadOrchestratorClient']
  const selected = tree.statements.filter(n =>
    ts.isFunctionDeclaration(n) && exportedNames.includes(n.name?.text) ||
    ts.isVariableStatement(n) && n.declarationList.declarations.some(d => exportedNames.includes(d.name.getText(tree))))
  let loads = 0
  const api = evaluate(selected.map(n => n.getText(tree)).join('\n'), id => {
    assert.equal(id, './orchestrator-api')
    loads++
    return internal
  })
  return { api, internal, calls, get loads() { return loads } }
}

test('the public loader actually defers the implementation import until explicitly called', async () => {
  const value = service()
  assert.equal(value.loads, 0)
  assert.equal(typeof value.api.loadOrchestratorClient, 'function')
  const loaded = await value.api.loadOrchestratorClient()
  assert.equal(loaded, value.internal)
  assert.equal(value.loads, 1)
  assert.equal(value.calls.length, 0)
})

test('all nine clients preserve exact bodies, encoded references and existing command timeouts', async () => {
  const receipt = { operation_id: 'actual-receipt', request_key: 'original-key', status: 'confirmed' }
  const value = service({ success: true, data: receipt })
  const body = { scope: { goal_id: 'g' }, options: { available_minutes: 0 } }
  const options = { q: '%_字面搜索', offset: 30 }
  for (const name of names) assert.equal(typeof value.api[name], 'function', name)
  await value.api.getOrchestratorCapabilities()
  await value.api.getOrchestratorGoalOptions(options)
  await value.api.readOrchestratorSnapshot(body.scope)
  await value.api.previewOrchestratorSchedule(body)
  assert.equal(await value.api.confirmOrchestratorSchedule(body), receipt)
  await value.api.getOrchestratorToday()
  await value.api.findOrchestratorOperation('key/with space')
  await value.api.previewOrchestratorUndo('op/1')
  assert.equal(await value.api.confirmOrchestratorUndo('op/1', body), receipt)
  assert.deepEqual(value.calls, [
    { method: 'get', args: ['/api/learning/orchestrator/capabilities', { timeout: 15000 }] },
    { method: 'post', args: ['/api/learning/orchestrator/goal-options', options, { timeout: 15000 }] },
    { method: 'post', args: ['/api/learning/orchestrator/snapshot', body.scope, { timeout: 15000 }] },
    { method: 'post', args: ['/api/learning/orchestrator/preview', body, { timeout: 30000 }] },
    { method: 'post', args: ['/api/learning/orchestrator/confirm', body, { timeout: 30000 }] },
    { method: 'get', args: ['/api/learning/orchestrator/today', { timeout: 15000 }] },
    { method: 'get', args: ['/api/learning/orchestrator/operations/key%2Fwith%20space', { timeout: 15000 }] },
    { method: 'post', args: ['/api/learning/orchestrator/operations/op%2F1/undo-preview', {}, { timeout: 30000 }] },
    { method: 'post', args: ['/api/learning/orchestrator/operations/op%2F1/undo-confirm', body, { timeout: 30000 }] },
  ])
})

test('API and transport failures propagate once without manufacturing a receipt or retrying', async () => {
  for (const response of [{ success: false, data: { untrusted: true }, error: 'synthetic-conflict' },
    { success: true, data: null }, { success: true }, new Error('HTTP 503')]) {
    const value = service(response)
    await assert.rejects(value.api.confirmOrchestratorSchedule({}), /synthetic-conflict|未完成|503/)
    assert.equal(value.calls.length, 1)
  }
})

test('today identity transport preserves network and auth failures instead of treating offline as account removal', async () => {
  const accepted = service({ success: true, data: { credential_scope: 'a'.repeat(64) } })
  assert.equal(typeof accepted.internal.getOrchestratorBrowserScope, 'function', 'the real strict today reader must exist')
  assert.equal(await accepted.internal.getOrchestratorBrowserScope(), 'a'.repeat(64))
  assert.deepEqual(accepted.calls, [{ method: 'get', args: ['/api/llm/status', { timeout: 15000 }] }])
  for (const credential_scope of [undefined, null, 'invalid', 'a'.repeat(65)]) {
    assert.equal(await service({ success: true, data: { credential_scope } }).internal.getOrchestratorBrowserScope(), null)
  }
  for (const failure of [new Error('network offline'), Object.assign(new Error('expired'), { response: { status: 401 } })]) {
    await assert.rejects(() => service(failure).internal.getOrchestratorBrowserScope(), error => error === failure)
  }
})
