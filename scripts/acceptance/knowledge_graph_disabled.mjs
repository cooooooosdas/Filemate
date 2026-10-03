import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const web = process.env.FILEMATE_DISABLED_WEB_URL || 'http://127.0.0.1:5174'
const api = process.env.FILEMATE_DISABLED_API_URL || 'http://127.0.0.1:8002'
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR || '_working/v2-2-20261001/disabled')
fs.mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ channel: process.platform === 'win32' ? 'msedge' : undefined, headless: true })
const page = await browser.newPage()
const errors = []
const results = []
page.on('pageerror', error => errors.push(String(error)))
try {
  for (const [route, title] of [['/', /^今天，/], ['/knowledge-graph', '学习工作区'], ['/wrongbook', '错题复盘'], ['/digital-human', /^让学习，有声可循/]]) {
    await page.goto(web + route)
    await page.getByRole('heading', { name: title, exact: true }).waitFor()
    assert.equal(await page.getByRole('link', { name: '我的知识图谱', exact: true }).count(), 0)
    if (route === '/knowledge-graph') assert.ok(page.url().endsWith('/ai-tools'))
    results.push({ route, passed: true })
  }
  for (const [method, route, data] of [
    ['get', '/api/knowledge-graph'],
    ['post', '/api/knowledge-graph/drafts', { source_id: 'none' }],
    ['post', '/api/knowledge-graph/batches/none/confirm', {}],
    ['post', '/api/knowledge-graph/batches/none/undo', {}],
    ['post', '/api/knowledge-graph/batches/none/restore', {}],
    ['get', '/api/knowledge-graph/nodes/none/plan'],
    ['post', '/api/knowledge-graph/nodes/none/plan', { evidence_revision: '0'.repeat(64) }],
    ['post', '/api/knowledge-graph/plans/none/undo', {}],
    ['post', '/api/knowledge-graph/plans/none/restore', {}],
  ]) {
    const response = await page.request[method](api + route, data ? { data } : {})
    assert.equal(response.status(), 503)
    results.push({ route, method, status: 503, passed: true })
  }
  for (const route of ['/api/health', '/knowledge/sources', '/wrongbook']) {
    assert.equal((await page.request.get(api + route)).status(), 200)
    results.push({ route, status: 200, passed: true })
  }
  assert.deepEqual(errors, [])
  console.log(`${results.length}/${results.length} feature boundary checks passed`)
} finally {
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify({ results, errors }, null, 2))
  await browser.close()
}
