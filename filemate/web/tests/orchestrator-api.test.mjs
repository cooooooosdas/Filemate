import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const names = ['getOrchestratorCapabilities', 'readOrchestratorSnapshot', 'previewOrchestratorSchedule', 'confirmOrchestratorSchedule', 'getOrchestratorToday', 'findOrchestratorOperation', 'previewOrchestratorUndo', 'confirmOrchestratorUndo']
function service(response = { success: true, data: { synthetic: true } }) {
  const source = readFileSync(new URL('../src/services/api.ts', import.meta.url), 'utf8')
  const tree = ts.createSourceFile('api.ts', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const selected = tree.statements.filter(n => ts.isFunctionDeclaration(n) && [...names, 'orchestratorResult'].includes(n.name?.text) || ts.isVariableStatement(n) && n.declarationList.declarations.some(d => d.name.getText(tree) === 'orchestratorRoot'))
  const compiled = ts.transpileModule(selected.map(n => n.getText(tree)).join('\n'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const calls = []
  const api = Object.fromEntries(['get', 'post'].map(method => [method, async (...args) => {
    calls.push({ method, args }); if (response instanceof Error) throw response; return response
  }]))
  const module = { exports: {} }
  new Function('api', 'module', 'exports', compiled)(api, module, module.exports)
  return { api: module.exports, calls }
}

test('all eight clients send the full body and encoded reference with bounded timeouts', async () => {
  const x = service()
  const body = { scope: { goal_id: 'g' }, options: { available_minutes: 0 } }
  for (const name of names) assert.equal(typeof x.api[name], 'function', name)
  await x.api.getOrchestratorCapabilities()
  await x.api.readOrchestratorSnapshot(body.scope)
  await x.api.previewOrchestratorSchedule(body)
  await x.api.confirmOrchestratorSchedule(body)
  await x.api.getOrchestratorToday()
  await x.api.findOrchestratorOperation('key/with space')
  await x.api.previewOrchestratorUndo('op/1')
  await x.api.confirmOrchestratorUndo('op/1', body)
  assert.deepEqual(x.calls, [
    { method: 'get', args: ['/api/learning/orchestrator/capabilities', { timeout: 15000 }] },
    { method: 'post', args: ['/api/learning/orchestrator/snapshot', body.scope, { timeout: 15000 }] },
    { method: 'post', args: ['/api/learning/orchestrator/preview', body, { timeout: 30000 }] },
    { method: 'post', args: ['/api/learning/orchestrator/confirm', body, { timeout: 30000 }] },
    { method: 'get', args: ['/api/learning/orchestrator/today', { timeout: 15000 }] },
    { method: 'get', args: ['/api/learning/orchestrator/operations/key%2Fwith%20space', { timeout: 15000 }] },
    { method: 'post', args: ['/api/learning/orchestrator/operations/op%2F1/undo-preview', {}, { timeout: 30000 }] },
    { method: 'post', args: ['/api/learning/orchestrator/operations/op%2F1/undo-confirm', body, { timeout: 30000 }] },
  ])
})

test('API and transport failures propagate once without manufacturing a receipt', async () => {
  for (const response of [{ success: false, data: null, error: 'synthetic-conflict' }, { success: true, data: null }, new Error('HTTP 503')]) {
    const x = service(response)
    await assert.rejects(x.api.confirmOrchestratorSchedule({}), /synthetic-conflict|未完成|503/)
    assert.equal(x.calls.length, 1)
  }
})
