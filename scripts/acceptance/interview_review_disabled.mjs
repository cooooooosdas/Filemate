import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const base = process.env.FILEMATE_WEB_URL || 'http://127.0.0.1:5185'
const api = process.env.FILEMATE_API_URL || 'http://127.0.0.1:8015'
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR || '_working/v2-4-20261001/disabled')
assert.ok(out.startsWith(path.join(process.cwd(), '_working') + path.sep))
fs.mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || 'msedge', headless: true })
const context = await browser.newContext()
const page = await context.newPage(), errors = [], results = []
page.on('pageerror', error => errors.push(String(error)))
const created = await context.request.post(api + '/interviews', { data: { target_role: '关闭增强后的原面试训练', allow_external_analysis: false } })
assert.equal(created.status(), 200)
const id = (await created.json()).data.interview_id
for (const [method, route, body] of [
  ['GET', '/review'], ['POST', '/review', {}], ['POST', '/turns/missing/analyze', {}],
  ['POST', '/analysis/cancel', {}], ['POST', '/analysis/clear', {}],
  ['GET', '/delete-preview'], ['DELETE', '', { confirmed: true, confirmation_token: 'a'.repeat(64) }],
  ['GET', '/review/export?format=pdf']
]) {
  const response = await context.request.fetch(api + '/interviews/' + id + route, { method, data: body })
  results.push({ name: method + route, passed: response.status() === 503, status: response.status() })
}
await page.goto(base + '/interview?interview=' + id)
await page.getByRole('textbox', { name: '当前训练回答' }).waitFor()
results.push({ name: 'original interview route and text UI', passed: true })
results.push({ name: 'review and vision controls hidden', passed: await page.locator('.interview-review-panel,.vision-controls').count() === 0 })
await page.getByRole('textbox', { name: '当前训练回答' }).fill('首先明确任务，然后说明行动和结果，因为原训练流程仍然可以使用。')
await page.getByRole('button', { name: '提交并进入下一题', exact: true }).click()
await page.getByText('第 2 / 5 题', { exact: true }).waitFor()
results.push({ name: 'original answer persists and advances', passed: true })
for (const route of ['/api/health', '/knowledge/sources', '/interview/questions']) {
  const response = await context.request.get(api + route)
  results.push({ name: 'legacy ' + route, passed: response.status() === 200, status: response.status() })
}
fs.writeFileSync(path.join(out, 'summary.json'), JSON.stringify({ passed: results.filter(r => r.passed).length, total: results.length, errors, results }, null, 2))
console.log('SUMMARY', results.filter(r => r.passed).length, '/', results.length, 'JS_ERRORS', errors.length)
await browser.close()
if (results.some(r => !r.passed) || errors.length) process.exitCode = 1
