import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const base = process.env.FILEMATE_WEB_URL || 'http://127.0.0.1:5175'
const api = process.env.FILEMATE_API_URL || 'http://127.0.0.1:8003'
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR || '_working/v2-3-20261001/disabled')
assert.ok(out.startsWith(path.join(process.cwd(), '_working') + path.sep))
fs.mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
const results = []
const errors = []
page.on('pageerror', error => errors.push(String(error)))
async function check(name, action) { try { await action(); results.push({ name, passed: true }); console.log('PASS', name) } catch (e) { results.push({ name, passed: false, error: String(e) }); console.log('FAIL', name, String(e)) } }
try {
  await check('disabled module removes navigation and old URL returns workspace', async () => {
    await page.goto(base + '/programming')
    await page.locator('.learning-workspace').getByRole('heading', { level: 1 }).waitFor()
    assert.equal(await page.locator('a[href="/programming"]').count(), 0)
    assert.equal(new URL(page.url()).pathname, '/ai-tools')
  })
  const requests = [['GET', '/status'], ['GET', '/problems'], ['GET', '/overview'], ['POST', '/setup', {}],
    ['GET', '/submissions/id'], ['POST', '/submissions', { problem_id: 'array-sum', code: 'x', request_key: 'valid_request_key_123' }],
    ['POST', '/submissions/id/run', {}], ['POST', '/submissions/id/review', {}], ['POST', '/submissions/id/notes', { notes: 'x' }],
    ...['undo', 'cancel', 'restore'].map(action => ['POST', '/submissions/id/' + action, {}])]
  for (const [method, url, data] of requests) await check(method + ' ' + url + ' is disabled', async () => {
    const response = await page.request.fetch(api + '/api/programming' + url, { method, data })
    assert.equal(response.status(), 503)
  })
  for (const endpoint of ['/api/health', '/knowledge/sources', '/api/knowledge-graph']) await check('legacy ' + endpoint + ' still works', async () => {
    assert.equal((await page.request.get(api + endpoint)).status(), 200)
  })
  await page.screenshot({ path: path.join(out, 'disabled-module.png'), fullPage: true })
  assert.deepEqual(errors, [])
} finally { fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify({ passed: results.filter(r => r.passed).length, total: results.length, errors, results }, null, 2)); await browser.close() }
if (results.some(r => !r.passed)) process.exitCode = 1
