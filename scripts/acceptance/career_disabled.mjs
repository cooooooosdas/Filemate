import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const base = process.env.FILEMATE_WEB_URL || 'http://127.0.0.1:5188'
const api = process.env.FILEMATE_API_URL || 'http://127.0.0.1:8017'
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR || '_working/v2-5-20261001/disabled')
assert.ok(out.startsWith(path.join(process.cwd(), '_working') + path.sep))
fs.mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || 'msedge', headless: true })
const context = await browser.newContext()
const page = await context.newPage(), errors = [], results = []
page.on('pageerror', error => errors.push(String(error)))
try {
  await page.goto(base + '/ai-tools')
  await page.locator('.learning-workspace').getByRole('heading', { level: 1 }).waitFor()
  const position = { company: '合成企业', title: '训练岗位', region: '本地', industry: '软件',
    employment: '用户自定义', source: '合成回归', source_url: '', source_kind: 'user_import',
    collected_at: '2026-01-01T00:00:00Z', published_at: '', description: '岗位要求：理解数据结构与算法。',
    requirements: [{ label: '数据结构', category: 'knowledge', evidence: '数据结构' }] }
  const status = await context.request.get(api + '/api/career/status')
  results.push({ name: 'disabled status stays readable', passed: (await status.json()).data.enabled === false })
  for (const [method, route, body] of [
    ['GET', '/catalog'], ['GET', '/positions'], ['GET', '/events'], ['GET', '/overview'],
    ['POST', '/extract', { description: position.description }],
    ['POST', '/positions', { position, confirmed: true, request_key: 'off_position_12345678' }],
    ['GET', '/positions/missing'], ['PATCH', '/positions/missing', { position, confirmed: true, expected_revision: 1 }],
    ['GET', '/positions/missing/evidence'], ['GET', '/positions/missing/trainings'],
    ['POST', '/positions/missing/trainings', { kind: 'review', confirmed: true, expected_revision: 1, request_key: 'off_training_12345678' }],
    ['POST', '/positions/missing/state/undo', { confirmed: true }],
    ['GET', '/positions/missing/delete-preview'], ['DELETE', '/positions/missing', { confirmed: true, confirmation_token: 'a'.repeat(64) }],
    ['GET', '/trainings/missing'], ['GET', '/trainings/missing/export'],
    ['POST', '/trainings/missing/answers', { answers: { stack: 1 } }],
    ['GET', '/positions/missing/plan-preview'], ['GET', '/positions/missing/plans'],
    ['POST', '/positions/missing/plans', { confirmed: true, evidence_revision: 'a'.repeat(64) }],
    ['POST', '/positions/missing/plans/missing/undo', { confirmed: true }],
  ]) {
    const response = await context.request.fetch(api + '/api/career' + route, { method, data: body })
    results.push({ name: method + route, passed: response.status() === 503, status: response.status() })
  }
  await page.goto(base + '/career')
  await page.waitForURL('**/ai-tools')
  await page.locator('.learning-workspace').getByRole('heading', { level: 1 }).waitFor()
  results.push({ name: 'old URL redirects and career navigation hidden', passed: await page.getByRole('link', { name: '求职训练中心', exact: true }).count() === 0 })
  const created = await context.request.post(api + '/interviews', { data: { target_role: '合成关闭回归', allow_external_analysis: false } })
  const id = (await created.json()).data.interview_id
  await page.goto(base + '/interview?interview=' + id)
  await page.getByRole('textbox', { name: '当前训练回答', exact: true }).waitFor()
  await page.getByRole('textbox', { name: '当前训练回答', exact: true }).fill('合成回归：先明确目标，再描述实际行动与验证结果。')
  await page.getByRole('button', { name: '提交并进入下一题', exact: true }).click()
  await page.getByText('第 2 / 5 题', { exact: true }).waitFor()
  results.push({ name: 'original interview answer persists', passed: true })
  for (const route of ['/api/health', '/knowledge/sources', '/interview/questions', '/api/programming/problems']) {
    const response = await context.request.get(api + route)
    results.push({ name: 'legacy ' + route, passed: response.status() === 200, status: response.status() })
  }
  await page.goto(base + '/growth')
  await page.getByRole('heading', { name: '成长数据', exact: true }).waitFor()
  results.push({ name: 'career growth panel hidden while original growth works', passed: await page.locator('.career-growth').count() === 0 })
  await page.screenshot({ path: path.join(out, 'disabled-legacy.png') })
  const summary = { passed: results.filter(r => r.passed).length, total: results.length, errors, results }
  fs.writeFileSync(path.join(out, 'summary.json'), JSON.stringify(summary, null, 2))
  console.log(JSON.stringify({ passed: summary.passed, total: summary.total, errors }))
  if (summary.passed !== summary.total || errors.length) process.exitCode = 1
} finally { await browser.close() }
