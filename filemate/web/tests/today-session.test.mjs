import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import ts from 'typescript'
const path = new URL('../src/services/today-session.ts', import.meta.url)
const actual = existsSync(path) ? await import(path.href) : null
const prefix = 'filemate-today-pending-v1:'
function store() {
  const map = new Map()
  return { get length() { return map.size }, key: n => [...map.keys()][n] ?? null,
    getItem: key => map.get(key) ?? null, setItem: (key, value) => map.set(key, value), removeItem: key => map.delete(key) }
}
function tab(localStorage = store()) {
  const win = new EventTarget()
  Object.assign(win, { localStorage, sessionStorage: store() })
  let resets = 0
  win.addEventListener('filemate:today-invalidated', () => resets++)
  assert.equal(typeof actual?.installTodaySessionBoundary, 'function', 'real application-lifetime invalidation boundary')
  const dispose = actual.installTodaySessionBoundary(win)
  return { win, dispose, get resets() { return resets } }
}
function publicFunction(name, api, window) {
  const source = readFileSync(new URL('../src/services/api.ts', import.meta.url), 'utf8')
  const tree = ts.createSourceFile('api.ts', source, ts.ScriptTarget.Latest, true)
  const fn = tree.statements.find(node => ts.isFunctionDeclaration(node) && node.name?.text === name || ts.isVariableStatement(node) && node.declarationList.declarations.some(value => value.name.getText(tree) === name))
  assert.ok(fn, `actual public ${name} export`)
  const compiled = ts.transpileModule(fn.getText(tree), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const exports = {}
  new Function('api','window','Event','exports','accountOptions', compiled)(api, window, Event, exports, {})
  return exports[name]
}
test('restore_on_other_route_and_logout_clear_real_session_pointers', async () => {
  const x = tab()
  x.win.sessionStorage.setItem(prefix+'account-one', 'old undo locator')
  x.win.sessionStorage.setItem('filemate-coach-pending-v1:account-one', 'minimal coach locator')
  x.win.sessionStorage.setItem('filemate-trial-pending-v1:account-one:epoch', 'minimal trial locator')
  x.win.sessionStorage.setItem('unrelated', 'keep')
  await publicFunction('restorePersonalData', { post: async () => ({ data: { restored: true } }) }, x.win)({})
  assert.equal(x.win.sessionStorage.getItem(prefix+'account-one'), null)
  assert.equal(x.win.sessionStorage.getItem('filemate-coach-pending-v1:account-one'), null)
  assert.equal(x.win.sessionStorage.getItem('filemate-trial-pending-v1:account-one:epoch'), null)
  assert.equal(x.win.sessionStorage.getItem('unrelated'), 'keep')
  x.win.sessionStorage.setItem(prefix+'account-one', 'new pending locator')
  await publicFunction('logoutAccount', { post: async () => ({}) }, x.win)()
  assert.equal(x.win.sessionStorage.getItem(prefix+'account-one'), null)
  assert.equal(x.resets, 2)
  x.dispose()
})
test('other_tab_restore_invalidates_local_pending_and_notifies_live_controller', () => {
  const first = tab(), second = tab(first.win.localStorage)
  second.win.sessionStorage.setItem(prefix+'account-one', 'old locator')
  first.win.dispatchEvent(new Event('filemate:data-restored'))
  const key = actual.TODAY_EPOCH_KEY
  assert.ok(first.win.localStorage.getItem(key))
  second.win.dispatchEvent(Object.assign(new Event('storage'), { key, storageArea: second.win.localStorage }))
  assert.equal(second.win.sessionStorage.getItem(prefix+'account-one'), null)
  assert.equal(second.resets, 1)
  first.dispose(); second.dispose()
})
