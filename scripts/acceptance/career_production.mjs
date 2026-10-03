import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const base = process.env.FILEMATE_WEB_URL || 'http://127.0.0.1:5190'
const api = process.env.FILEMATE_API_URL || 'http://127.0.0.1:8019'
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR || '_working/v2-5-20261001/production')
assert.ok(out.startsWith(path.join(process.cwd(), '_working') + path.sep))
fs.mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
const page = await context.newPage(), errors = [], requests = [], results = []
page.setDefaultTimeout(20000)
page.on('pageerror', error => errors.push(String(error)))
page.on('request', request => requests.push(request.url()))

// 编译包保持原样，只将本机 API 传输接到隔离后端；响应来自真实实现。
await page.route(/^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?\//, async route => {
  const request = route.request()
  if (!['fetch', 'xhr'].includes(request.resourceType())) return route.continue()
  const url = new URL(request.url())
  await route.fulfill({ response: await route.fetch({ url: api + url.pathname + url.search }) })
})
const button = name => page.getByRole('button', { name, exact: true })
const read = async route => (await (await context.request.get(api + route)).json()).data
const dialog = () => page.getByRole('dialog')
let position, written, interview, review
async function check(name, run) {
  try { await run(); results.push({ name, kind: 'production_bundle_real_ui_api', passed: true }); console.log('PASS', name) }
  catch (error) { results.push({ name, passed: false, error: String(error) }); console.log('FAIL', name, String(error)); await page.screenshot({ path: path.join(out, `failure-${results.length}.png`) }) }
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 2))
}
async function create(kind, name) {
  await button(name).click()
  const response = page.waitForResponse(r => new URL(r.url()).pathname === `/api/career/positions/${position.position_id}/trainings` && r.request().method() === 'POST')
  await dialog().getByRole('button', { name: '确认创建训练', exact: true }).click()
  const accepted = await response
  assert.equal(accepted.status(), 200)
  const row = (await accepted.json()).data
  assert.equal(row.kind, kind)
  await page.waitForFunction(id => new URL(location.href).searchParams.get('training') === id, row.training_id)
  await page.getByRole('heading', { name: { written: '模拟笔试', interview: '岗位面试', review: '训练对比快照' }[kind], exact: true }).waitFor()
  return row
}
try {
  await check('compiled career route loads original catalog without auto-saving', async () => {
    await page.goto(base + '/career')
    await page.locator('.catalog-row').first().waitFor()
    assert.equal(await page.locator('.catalog-row').count(), 3)
    assert.equal((await read('/api/career/positions')).length, 0)
    assert.ok(requests.some(url => /\/assets\/Career-[^/]+\.js/.test(url)))
    assert.ok(requests.every(url => !url.includes('/@vite/')))
  })
  await check('compiled confirmation and actual quiz persist four correct answers', async () => {
    await page.locator('.catalog-row').first().getByRole('button').click()
    const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/career/positions' && r.request().method() === 'POST')
    await button('确认保存岗位').click()
    await dialog().getByRole('button', { name: '确认保存', exact: true }).click()
    position = (await (await response).json()).data
    await page.locator('.position-detail').waitFor()
    written = await create('written', '创建模拟笔试')
    for (const [id, index] of Object.entries({ cpp: 2, stack: 1, search: 2, network: 2 })) await page.locator(`input[name="${id}"][value="${index}"]`).check()
    await button('提交基础题').click()
    await page.getByText('本轮基础题：4 / 4 正确。此项只描述本轮作答。', { exact: true }).waitFor()
    assert.equal((await read(`/api/career/trainings/${written.training_id}`)).payload.result.correct, 4)
  })
  await check('compiled deep link saves one local interview answer and frozen comparison', async () => {
    interview = await create('interview', '创建岗位面试')
    await page.getByRole('link', { name: '进入本场岗位面试与复盘', exact: true }).click()
    await page.getByRole('textbox', { name: '当前训练回答', exact: true }).fill('合成生产包验收：我负责查询索引优化，用固定输入对比执行计划、返回结果和耗时，保留验证记录。')
    await button('提交并进入下一题').click()
    await page.getByText('第 2 / 5 题', { exact: true }).waitFor()
    const stored = await read(`/interviews/${interview.interview_id}`)
    assert.equal(stored.turns.length, 1)
    assert.equal(stored.assessed_turn_count, 0)
    await page.goto(`${base}/career?position=${position.position_id}`)
    await page.locator('.position-detail').waitFor()
    review = await create('review', '保存训练对比')
    assert.equal(review.payload.comparison.written.length, 1)
  })
  await check('compiled growth module reads exact counts and opens original snapshot', async () => {
    await page.goto(base + '/growth')
    const panel = page.locator('.career-growth')
    await panel.locator('dl').waitFor()
    assert.match(await panel.innerText(), /实际答对 4 \/ 4 题/)
    assert.match(await panel.innerText(), /已答 1 题，内容评估 0 题/)
    const counts = (await read('/api/career/overview')).counts
    assert.equal(counts.completed_written, 1)
    assert.equal(counts.review_snapshots, 1)
    await panel.scrollIntoViewIfNeeded()
    await page.screenshot({ path: path.join(out, 'growth-production.png') })
    await panel.getByRole('link', { name: /对比快照/ }).click()
    await page.getByRole('heading', { name: '训练对比快照', exact: true }).waitFor()
    assert.equal(new URL(page.url()).searchParams.get('training'), review.training_id)
    await page.screenshot({ path: path.join(out, 'career-production.png') })
  })
  const externalRequests = requests.filter(url => /^https?:/.test(url) && !['127.0.0.1', 'localhost'].includes(new URL(url).hostname))
  assert.deepEqual(errors, [])
  assert.deepEqual(externalRequests, [])
  const summary = { passed: results.filter(r => r.passed).length, total: results.length, errors, externalRequests, results }
  fs.writeFileSync(path.join(out, 'summary.json'), JSON.stringify(summary, null, 2))
  console.log(JSON.stringify({ passed: summary.passed, total: summary.total, errors, externalRequests }))
  if (summary.passed !== summary.total) process.exitCode = 1
} finally { await browser.close() }
