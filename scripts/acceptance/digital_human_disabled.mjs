import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const web = process.env.FILEMATE_WEB_URL || 'http://127.0.0.1:5198'
const api = process.env.FILEMATE_API_URL || 'http://127.0.0.1:8028'
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR || '_working/digital-human-disabled')
assert.ok(out.startsWith(path.join(process.cwd(), '_working') + path.sep))
fs.mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || 'msedge', headless: true })
const context = await browser.newContext()
const page = await context.newPage(), errors = [], results = []
page.on('pageerror', error => errors.push(String(error)))
try {
  for (const route of ['/', '/ai-tools', '/knowledge', '/digital-human']) {
    await page.goto(web + route)
    await page.locator('#main-content').waitFor()
    assert.equal(await page.getByRole('link', { name: 'AI 导师讲解', exact: true }).count(), 0)
    assert.equal(await page.locator('.mentor-stage').count(), 0)
    results.push({ name: route + ' hides disabled mentor', passed: true })
  }
  assert.ok(new URL(page.url()).pathname === '/ai-tools')
  for (const [method, route, data] of [
    ['GET', '/api/digital-human/playbacks', undefined],
    ['POST', '/api/digital-human/playbacks', { text_length: 10, avatar_id: 'filemate-campus', voice_id: 'default', provider: 'web_speech' }],
    ['PATCH', '/api/digital-human/playbacks/isolated-record', { status: 'completed' }],
    ['DELETE', '/api/digital-human/playbacks/isolated-record', undefined],
    ['POST', '/api/digital-human/playbacks/isolated-record/restore', undefined],
  ]) {
    const response = await context.request.fetch(api + route, { method, data })
    assert.equal(response.status(), 503, await response.text())
    results.push({ name: method + ' ' + route, passed: true })
  }
  for (const route of ['/api/health', '/knowledge/sources', '/interview/questions']) {
    const response = await context.request.get(api + route)
    assert.equal(response.status(), 200)
    assert.equal((await response.json()).success, true)
    results.push({ name: 'legacy ' + route, passed: true })
  }
} finally {
  fs.writeFileSync(path.join(out, 'summary.json'), JSON.stringify({ passed: results.filter(row => row.passed).length, total: results.length, errors, results }, null, 2))
  await browser.close()
}
assert.equal(errors.length, 0)
console.log(`${results.length}/${results.length} disabled mentor checks passed`)
