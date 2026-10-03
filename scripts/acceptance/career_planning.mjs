import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const base = process.env.FILEMATE_WEB_URL || 'http://127.0.0.1:5192'
const api = process.env.FILEMATE_API_URL || 'http://127.0.0.1:8020'
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR || '_working/b2-career-plan-20261002/ui')
assert.ok(out.startsWith(path.join(process.cwd(), '_working') + path.sep))
fs.mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true })
const page = await context.newPage(), errors = [], requests = [], results = []
page.setDefaultTimeout(20000)
page.on('pageerror', error => errors.push(String(error)))
page.on('request', request => requests.push(request.url()))
if (process.env.FILEMATE_PRODUCTION_PROXY === '1') {
  await page.route(/^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?\//, async route => {
    if (!['fetch', 'xhr'].includes(route.request().resourceType())) return route.continue()
    const url = new URL(route.request().url())
    await route.fulfill({ response: await route.fetch({ url: api + url.pathname + url.search }) })
  })
}
const read = async route => (await (await context.request.get(api + route)).json()).data
async function post(route, data) {
  const response = await context.request.post(api + route, { data })
  assert.equal(response.status(), 200, await response.text())
  return (await response.json()).data
}
const panel = () => page.locator('.career-plans'), modal = () => page.getByRole('dialog', { name: '核对岗位学习建议', exact: true })
const button = name => page.getByRole('button', { name, exact: true })
let position, prefix, firstPlan, written, secondPlan
async function open() {
  await page.goto(`${base}/career?position=${position.position_id}`)
  await panel().getByRole('button', { name: '预览岗位学习建议', exact: true }).waitFor()
  await page.waitForFunction(() => !document.querySelector('.career-plans [role="status"]')?.textContent.includes('正在读取'))
}
async function preview() { await button('预览岗位学习建议').click(); await modal().waitFor() }
async function check(name, kind, run) {
  try { await run(); results.push({ name, kind, passed: true }); console.log('PASS', name) }
  catch (error) { results.push({ name, kind, passed: false, error: String(error) }); console.log('FAIL', name, String(error)); await page.screenshot({ path: path.join(out, `failure-${results.length}.png`) }) }
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 2))
}
try {
  await page.goto(base + '/career')
  await page.locator('.catalog-row').first().waitFor()
  assert.equal((await read('/api/career/positions')).length, 0)
  const catalog = await read('/api/career/catalog')
  position = await post('/api/career/positions', { position: catalog[0], confirmed: true, request_key: 'planning_ui_role_12345678' })
  prefix = `/api/career/positions/${position.position_id}`
  await open()
  await check('empty suggestion is pending and cancellation writes no plan', 'real_ui_api', async () => {
    assert.equal((await read(prefix + '/plans')).length, 0)
    await preview()
    assert.match(await modal().innerText(), /待评测/)
    await modal().getByRole('button', { name: '继续核对建议', exact: true }).click()
    assert.equal((await read(prefix + '/plans')).length, 0)
  })
  await check('new wrong answer invalidates open preview and refresh shows original evidence', 'real_ui_api', async () => {
    await preview()
    written = await post(prefix + '/trainings', { confirmed: true, expected_revision: 1, kind: 'written', request_key: 'planning_ui_written_12345678' })
    await post(`/api/career/trainings/${written.training_id}/answers`, { answers: { cpp: 2, stack: 1, search: 2, network: 0 } })
    await modal().getByRole('button', { name: '确认保存学习计划', exact: true }).click()
    await modal().getByRole('alert').waitFor()
    assert.equal((await read(prefix + '/plans')).length, 0)
    await modal().getByRole('button', { name: '继续核对建议', exact: true }).click()
    await preview()
    assert.match(await modal().locator('h3').first().innerText(), /计算机网络.*建议复练/s)
    assert.match(await modal().innerText(), new RegExp(written.training_id))
  })
  await check('lost accepted save retries the same evidence and persists one real plan', 'real_ui_injected_transport', async () => {
    let lost = false
    await page.route('**/api/career/positions/*/plans', async route => {
      if (route.request().method() === 'POST' && !lost) {
        lost = true
        const url = new URL(route.request().url())
        await route.fetch({ url: process.env.FILEMATE_PRODUCTION_PROXY === '1' ? api + url.pathname + url.search : route.request().url() })
        await route.abort('failed')
      }
      else await route.fallback()
    })
    await modal().getByRole('button', { name: '确认保存学习计划', exact: true }).click()
    await modal().getByRole('alert').waitFor()
    assert.equal((await read(prefix + '/plans')).length, 1)
    await modal().getByRole('button', { name: '确认保存学习计划', exact: true }).click()
    await modal().waitFor({ state: 'hidden' })
    await panel().getByRole('link', { name: '回看学习计划', exact: true }).waitFor()
    const saved = await read(prefix + '/plans')
    assert.equal(saved.length, 1); firstPlan = saved[0]
    await page.unroute('**/api/career/positions/*/plans')
    assert.equal((await read(`/study-plans/${firstPlan.plan_id}`)).plan_data.daily_plan[0].focus, '计算机网络')
  })
  await check('original study page saves day progress and exports actual CSV and ICS', 'real_ui_api', async () => {
    await panel().getByRole('link', { name: '回看学习计划', exact: true }).click()
    await page.locator('.plan-results').waitFor()
    assert.equal(new URL(page.url()).searchParams.get('plan'), firstPlan.plan_id)
    await page.getByRole('button', { name: '标记为已完成', exact: true }).first().click()
    await page.getByRole('button', { name: '标记为未完成', exact: true }).waitFor()
    assert.deepEqual((await read(`/study-plans/${firstPlan.plan_id}`)).completed_days, [0])
    assert.ok(await page.getByRole('link', { name: '回看基础作答', exact: true }).count())
    for (const [name, extension] of [['导出 CSV', 'csv'], ['加入日历 (.ics)', 'ics']]) {
      const download = page.waitForEvent('download'); await button(name).click(); const file = await download
      await file.saveAs(path.join(out, `learning-plan.${extension}`))
      assert.match(fs.readFileSync(path.join(out, `learning-plan.${extension}`), 'utf8'), /计算机网络/)
    }
    await open()
  })
  await check('cancel undo keeps plan and confirmed undo restore preserves progress', 'real_ui_api', async () => {
    await button('撤销学习计划').click()
    await page.getByRole('button', { name: '保留现状', exact: true }).click()
    assert.equal((await read(prefix + '/plans'))[0].status, 'active')
    await button('撤销学习计划').click(); await button('确认计划变更').click()
    await button('恢复学习计划').waitFor()
    assert.deepEqual((await read(prefix + '/plans'))[0].completed_days, [0])
    await button('恢复学习计划').click(); await button('确认计划变更').click()
    await button('撤销学习计划').waitFor()
    assert.deepEqual((await read(prefix + '/plans'))[0].completed_days, [0])
  })
  await check('new correct practice changes suggestion and saves separate plan', 'real_ui_api', async () => {
    const newer = await post(prefix + '/trainings', { confirmed: true, expected_revision: 1, kind: 'written', request_key: 'planning_ui_new_answer_12345678' })
    await post(`/api/career/trainings/${newer.training_id}/answers`, { answers: { cpp: 2, stack: 1, search: 2, network: 2 } })
    await preview()
    assert.doesNotMatch(await modal().innerText(), /建议复练/)
    await modal().getByRole('button', { name: '确认保存学习计划', exact: true }).click()
    await modal().waitFor({ state: 'hidden' })
    await page.waitForFunction(() => document.querySelectorAll('.saved-plans li').length === 2)
    const saved = await read(prefix + '/plans')
    assert.equal(saved.length, 2); secondPlan = saved.find(row => row.plan_id !== firstPlan.plan_id)
    assert.deepEqual(saved.find(row => row.plan_id === firstPlan.plan_id).completed_days, [0])
  })
  await check('failed plan read preserves saved list and retry recovers', 'injected_network_ui', async () => {
    await page.route('**/api/career/positions/*/plans', route => route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"合成读取故障"}' }))
    await button('刷新岗位计划').click(); await panel().getByRole('alert').waitFor()
    assert.equal(await panel().locator('.saved-plans li').count(), 2)
    await page.unroute('**/api/career/positions/*/plans')
    await button('重试岗位计划').click()
    await page.waitForFunction(() => !document.querySelector('.career-plans [role="alert"]'))
  })
  await check('undo role keeps plan history and restoring role resumes suggestions', 'real_ui_api', async () => {
    await button('撤销岗位').click(); await button('确认变更').click()
    await button('恢复岗位').waitFor()
    assert.equal(await button('预览岗位学习建议').count(), 0)
    assert.equal(await panel().locator('.saved-plans li').count(), 2)
    await button('恢复岗位').click(); await button('确认变更').click()
    await button('预览岗位学习建议').waitFor()
  })
  await check('saved list and confirmation dialog fit mobile tablet and desktop', 'real_responsive_ui', async () => {
    for (const width of [375, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 })
      await page.evaluate(async () => { await Promise.all(document.getAnimations().filter(a => a.effect?.getTiming().iterations !== Infinity).map(a => a.finished.catch(() => {}))) })
      await panel().scrollIntoViewIfNeeded()
      const box = await panel().boundingBox()
      assert.ok(box.x >= 0 && box.x + box.width <= width)
      await page.screenshot({ path: path.join(out, `plans-${width}.png`) })
      await preview()
      const dialogBox = await modal().boundingBox()
      assert.ok(dialogBox.x >= 0 && dialogBox.x + dialogBox.width <= width)
      assert.equal(await modal().evaluate(e => e.scrollWidth > e.clientWidth + 1), false)
      await page.screenshot({ path: path.join(out, `preview-${width}.png`) })
      await modal().getByRole('button', { name: '继续核对建议', exact: true }).click()
    }
  })
  await check('deletion includes plan progress rejects stale token then removes owned plans', 'real_ui_api', async () => {
    await button('预览删除岗位').click()
    assert.match(await page.getByRole('dialog').innerText(), /2份岗位学习计划及进度/)
    const changed = await context.request.patch(api + `/study-plans/${secondPlan.plan_id}/days/0`, { data: { completed: true } })
    assert.equal(changed.status(), 200)
    await button('确认删除岗位').click()
    await page.locator('.career-page > .error').waitFor()
    assert.equal((await read(prefix + '/plans')).length, 2)
    await button('预览删除岗位').click(); await button('确认删除岗位').click()
    await page.getByRole('heading', { name: '先选一个你要训练的岗位', exact: true }).waitFor()
    assert.equal((await context.request.get(api + `/study-plans/${firstPlan.plan_id}`)).status(), 404)
    assert.equal((await context.request.get(api + `/study-plans/${secondPlan.plan_id}`)).status(), 404)
    assert.equal((await read('/api/career/positions')).length, 0)
  })
  const externalRequests = requests.filter(url => /^https?:/.test(url) && !['127.0.0.1', 'localhost'].includes(new URL(url).hostname))
  const summary = { passed: results.filter(r => r.passed).length, total: results.length, errors, externalRequests, results }
  fs.writeFileSync(path.join(out, 'summary.json'), JSON.stringify(summary, null, 2))
  console.log(JSON.stringify({ passed: summary.passed, total: summary.total, errors, externalRequests }))
  if (summary.passed !== summary.total || errors.length || externalRequests.length) process.exitCode = 1
} finally { await browser.close() }
