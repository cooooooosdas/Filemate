import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import ts from 'typescript'

export function load(relative, overrides = {}) {
  const url = new URL(relative, import.meta.url)
  assert.equal(existsSync(url), true, `missing implementation: ${relative}`)
  const source = ts.transpileModule(readFileSync(url, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', source)(id => {
    if (id in overrides) return overrides[id]
    const target = new URL(id.endsWith('.ts') ? id : `${id}.ts`, url)
    return load(target.href, overrides)
  }, module, module.exports)
  return module.exports
}
export const clone = value => structuredClone(value)
export function input() {
  return { scope: { goal_id: 'synthetic-goal', course_id: null, source_ids: [] }, selection: { interview_ids: [], submission_ids: [], concept_ids: [], wrong_ids: [], feedback_refs: [], position_id: null, requirement_indices: [] }, intent: 'budget', question: '合成私密问题', days: [{ study_date: '2026-11-03', options: { available_minutes: 40 } }] }
}
export function context(value = input()) {
  return { input: clone(value), as_of: '2026-11-03T02:00:00Z', context_revision: 'a'.repeat(64), restore_epoch: 'synthetic-epoch', facts: [], external_payload: { question: value.question, facts: [], coverage: { omitted_facts: 0, omitted_tasks: 0 } }, external_digest: 'b'.repeat(64), snapshot: { study_date: '2026-11-03', scope: clone(value.scope), facts: {}, coverage: {} }, projection: { tasks: [], completed: [], unavailable: [], overlaps: [], coverage: {} }, coverage: {} }
}
export function run(changes = {}) {
  return { work_id: 'synthetic-work', request_key: 'synthetic_request_key', status: 'ready', requested_mode: 'rule', effective_mode: 'rule', model_status: 'not_requested', safe_error_code: null, context_revision: 'a'.repeat(64), rule_version: 'learning-coach-rules-v1', prompt_version: 'learning-coach-v1', proposal: { facts: [], explanations: [], days: [{ ...input().days[0], schedule: { selected: [], completed: [], deferred: [], coverage: {} } }], new_actions: [], coverage: {}, overlaps: [], limitations: [] }, ...changes }
}
export function deferred() { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }
export function harness(wrap) {
  const calls = []
  let identity = 'a'.repeat(64)
  const client = {
    capabilities: async () => ({ enabled: true, contract_version: 'learning-coach-v1', limits: {}, quota_window: 'rolling_24h' }),
    context: async value => { calls.push(['context', clone(value)]); return context(value) },
    request: async body => { calls.push(['request', clone(body)]); return run({ request_key: body.request_key, requested_mode: body.mode }) },
    cancel: async key => { calls.push(['cancel', key]); return run({ status: 'cancelled', request_key: key, proposal: null }) },
  }
  const { createCoachWorkspace } = load('../src/today/coach-state.ts')
  const workspace = createCoachWorkspace(client, { identity: () => identity, wrap })
  return { client, calls, workspace, setIdentity: value => { identity = value } }
}
