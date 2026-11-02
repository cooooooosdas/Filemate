import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

function service(response = { success: true, data: { status: 'preview_only' }, error: null }) {
  const calls = []
  const api = Object.fromEntries(['get', 'post'].map(method => [method, async (...args) => {
    calls.push({ method, args })
    if (response instanceof Error) throw response
    return response
  }]))
  const source = readFileSync(new URL('../src/services/review-api.ts', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const module = { exports: {} }
  const dependencies = { './api': { reviewHTTP: api, getCourseBrowserScope: () => 'synthetic-scope' }, './llm-vault': { hasBrowserApiKey: async () => false } }
  const require = path => {
    assert.ok(path in dependencies, `unexpected runtime dependency: ${path}`)
    return dependencies[path]
  }
  new Function('require', 'module', 'exports', compiled)(require, module, module.exports)
  return { api: module.exports, calls }
}

test('session preview uses the shared read client, full filter and explicit timeout', async () => {
  const x = service()
  assert.equal(typeof x.api.getReviewSessionPreview, 'function')
  const params = { available_minutes: 12, sort: 'recommended', course_id: 'synthetic-course', q: '栈' }
  assert.equal((await x.api.getReviewSessionPreview(params)).status, 'preview_only')
  assert.deepEqual(x.calls, [{ method: 'get', args: ['/wrongbook/v2/session-preview', { params, timeout: 15000 }] }])
})

test('readiness posts only references and the preview filter, without model credentials', async () => {
  const x = service({ success: true, data: { status: 'ready' } })
  assert.equal(typeof x.api.checkReviewSession, 'function')
  const body = { refs: [{ wrong_id: 'w', revision: 1 }], filters: { source_id: 'source' } }
  assert.equal((await x.api.checkReviewSession(body)).status, 'ready')
  assert.deepEqual(x.calls, [{ method: 'post', args: ['/wrongbook/v2/session-check', body, { timeout: 10000 }] }])
})

test('transport and API failures surface once, preserving the callers preview', async () => {
  const transport = new Error('HTTP 409 synthetic')
  const x = service(transport)
  assert.equal(typeof x.api.checkReviewSession, 'function')
  await assert.rejects(x.api.checkReviewSession({ refs: [] }), error => error === transport)
  assert.equal(x.calls.length, 1)
  const unavailable = service({ success: false, data: null, error: '请重新预览' })
  await assert.rejects(unavailable.api.getReviewSessionPreview({ available_minutes: 4 }), /请重新预览/)
  assert.equal(unavailable.calls.length, 1)
})
