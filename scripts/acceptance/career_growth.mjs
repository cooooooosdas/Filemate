import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const base = process.env.FILEMATE_WEB_URL || 'http://127.0.0.1:5191'
const api = process.env.FILEMATE_API_URL || 'http://127.0.0.1:8019'
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR || '_working/v2-5-20261001/growth')
assert.ok(out.startsWith(path.join(process.cwd(), '_working') + path.sep))
fs.mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
const page = await context.newPage(), errors = [], results = []
page.on('pageerror', error => errors.push(String(error)))
const read = async route => (await (await context.request.get(api + route)).json()).data
async function post(route, body) {
  const response = await context.request.post(api + route, { data: body })
  assert.equal(response.status(), 200, await response.text())
  return (await response.json()).data
}
const panel = () => page.locator('.career-growth')
async function open() { await page.goto(base + '/growth'); await panel().locator('dl').waitFor() }
async function check(name, kind, run) {
  try { await run(); results.push({ name, kind, passed: true }); console.log('PASS', name) }
  catch (error) { results.push({ name, kind, passed: false, error: String(error) }); console.log('FAIL', name, String(error)); await page.screenshot({ path: path.join(out, `failure-${results.length}.png`) }) }
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 2))
}
let position, written, interview, review
try {
  await check('empty career totals display zero actual counts and pending assessment', 'real_ui_api', async () => {
    await open()
    assert.equal((await read('/api/career/overview')).counts.positions, 0)
    assert.match(await panel().innerText(), /作答表现待评测/)
    assert.match(await panel().innerText(), /尚无记录/)
    assert.equal((await panel().locator('dd').first().innerText()).split('\n')[0], '0')
    assert.equal(await panel().locator('dd').first().locator('small').innerText(), '其中 0 个可继续训练')
  })
  await check('saved quiz and real local interview appear with exact counts', 'real_api_fixture_ui', async () => {
    const catalog = await read('/api/career/catalog')
    position = await post('/api/career/positions', { position: catalog[0], confirmed: true, request_key: 'growth_position_12345678' })
    const start = kind => post(`/api/career/positions/${position.position_id}/trainings`, { kind, expected_revision: 1, confirmed: true, request_key: `growth_training_${kind}_12345678` })
    written = await start('written')
    await post(`/api/career/trainings/${written.training_id}/answers`, { answers: { cpp: 2, stack: 1, search: 2, network: 2 } })
    interview = await start('interview')
    await post(`/interviews/${interview.interview_id}/answers`, { answer: '合成成长验收：我设计查询索引，并用固定输入对比执行计划和查询结果。' })
    review = await start('review')
    await open()
    assert.match(await panel().innerText(), /实际答对 4 \/ 4 题/)
    assert.match(await panel().innerText(), /已答 1 题，内容评估 0 题/)
    assert.equal((await read('/api/career/overview')).counts.trainings, 3)
  })
  await check('refresh is read-only and original snapshot link opens correct training', 'real_ui_api', async () => {
    const before = await read('/api/career/overview')
    await panel().getByRole('button', { name: '刷新求职记录', exact: true }).click()
    await page.waitForFunction(() => !document.querySelector('.career-growth [role="status"]'))
    assert.deepEqual(await read('/api/career/overview'), before)
    await panel().getByRole('link', { name: /对比快照/ }).click()
    await page.getByRole('heading', { name: '训练对比快照', exact: true }).waitFor()
    assert.equal(new URL(page.url()).searchParams.get('training'), review.training_id)
    await open()
  })
  await check('failed overview retains previous evidence and retry recovers', 'injected_network_ui', async () => {
    await page.route('**/api/career/overview', route => route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"合成汇总故障"}' }))
    await panel().getByRole('button', { name: '刷新求职记录', exact: true }).click()
    await panel().getByRole('alert').waitFor()
    assert.match(await panel().innerText(), /实际答对 4 \/ 4 题/)
    await page.unroute('**/api/career/overview')
    await panel().getByRole('button', { name: '重试求职汇总', exact: true }).click()
    await page.waitForFunction(() => !document.querySelector('.career-growth [role="alert"]'))
  })
  await check('growth module remains visible inside mobile tablet and desktop bounds', 'real_responsive_ui', async () => {
    for (const width of [375, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 })
      await page.evaluate(async () => { await Promise.all(document.getAnimations().filter(a => a.effect?.getTiming().iterations !== Infinity).map(a => a.finished.catch(() => {}))) })
      await panel().scrollIntoViewIfNeeded()
      const bounds = await panel().boundingBox()
      assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= width)
      assert.equal(await panel().evaluate(e => e.scrollWidth > e.clientWidth + 1), false)
      await page.screenshot({ path: path.join(out, `growth-${width}.png`) })
    }
  })
  await check('undo retains historical totals and deletion clears career totals while preserving interview', 'real_api_ui', async () => {
    await post(`/api/career/positions/${position.position_id}/state/undo`, { confirmed: true })
    await panel().getByRole('button', { name: '刷新求职记录', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('.career-growth')?.textContent.includes('其中 0 个'))
    assert.equal((await read('/api/career/overview')).counts.written_answers, 4)
    const preview = await read(`/api/career/positions/${position.position_id}/delete-preview`)
    const deleted = await context.request.delete(api + `/api/career/positions/${position.position_id}`, { data: { confirmed: true, confirmation_token: preview.confirmation_token } })
    assert.equal(deleted.status(), 200)
    await panel().getByRole('button', { name: '刷新求职记录', exact: true }).click()
    await panel().getByRole('link', { name: '从一个岗位开始，保存第一份训练记录', exact: true }).waitFor()
    assert.equal((await read(`/interviews/${interview.interview_id}`)).turns.length, 1)
    assert.equal((await read('/api/career/overview')).counts.trainings, 0)
  })
  assert.deepEqual(errors, [])
  const summary = { passed: results.filter(r => r.passed).length, total: results.length, errors, results }
  fs.writeFileSync(path.join(out, 'summary.json'), JSON.stringify(summary, null, 2))
  console.log(JSON.stringify({ passed: summary.passed, total: summary.total, errors }))
  if (summary.passed !== summary.total) process.exitCode = 1
} finally { await browser.close() }
