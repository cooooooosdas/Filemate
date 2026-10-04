import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { performance } from 'node:perf_hooks'
import { chromium } from 'playwright'

const base = process.env.FILEMATE_WEB_URL || 'http://127.0.0.1:5198'
const api = process.env.FILEMATE_API_URL || 'http://127.0.0.1:8028'
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR || '_working/frontend-production')
assert.ok(out.startsWith(path.join(process.cwd(), '_working') + path.sep))
fs.mkdirSync(out, { recursive: true })
const baseline = process.env.FILEMATE_MEASURE_BASELINE === '1'
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || 'msedge', headless: true })
const results = [], errors = [], warnings = [], requests = [], timings = []
let injectingFailure = false
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
// 只桥接API传输，业务响应来自独立SQLite和现役FastAPI；静态资源来自编译包。
await context.route(/^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?\//, async route => {
  const request = route.request()
  if (!['fetch', 'xhr'].includes(request.resourceType())) return route.continue()
  const url = new URL(request.url())
  if (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/interview-vision/')) return route.continue()
  await route.fulfill({ response: await route.fetch({ url: api + url.pathname + url.search }) })
})
const page = await context.newPage()
page.setDefaultTimeout(20000)
page.on('pageerror', error => { if (!injectingFailure) errors.push(String(error)) })
page.on('console', message => {
  if (!injectingFailure && /Failed to resolve component|Failed to resolve directive|Unhandled error/.test(message.text())) warnings.push(message.text())
})
page.on('request', request => requests.push(request.url()))
async function check(name, run) {
  try { await run(); results.push({ name, kind: baseline ? 'controlled_baseline_bundle' : 'production_bundle_real_ui_api', passed: true }) }
  catch (error) { results.push({ name, passed: false, error: String(error) }); await page.screenshot({ path: path.join(out, `failure-${results.length}.png`), fullPage: true }) }
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 2))
  console.log(`${results.at(-1).passed ? 'PASS' : 'FAIL'} ${name}`)
}
async function goto(route) { await page.goto(base + route); await page.locator('main').waitFor() }
try {
  await check('cold compiled homepage renders exact empty state and readable icons', async () => {
    const start = performance.now()
    await goto('/')
    await page.locator('.overview').waitFor()
    timings.push({ route: '/', ready_ms: Math.round(performance.now() - start), context: 'cold isolated Edge context over loopback; includes real local API' })
    assert.match(await page.locator('.empty-files').innerText(), /个人知识库/)
    assert.equal(await page.locator('.empty-files a').getAttribute('href'), '/knowledge')
    assert.equal(await page.locator('.sidebar .el-icon svg').count() > 0, true)
    assert.equal(await page.locator('el-icon,el-button,el-dialog').count(), 0)
  })
  await check('homepage leaves editor, chart and vision resources lazy', async () => {
    const assets = requests.filter(url => /\/assets\/|\/interview-vision\//.test(url))
    assert.ok(assets.some(url => /\/Home-[^/]+\.js/.test(url)))
    assert.ok(assets.every(url => !/editor\.api|editor\.worker|vision\.worker|\.wasm|\/Classification-/.test(url)))
    assert.ok(requests.every(url => !url.includes('/@vite/')))
  })
  if (!baseline) {
    await check('settings dialog and explicit message services have actual CSS and keyboard controls', async () => {
      await page.getByRole('button', { name: '打开设置', exact: true }).click()
      const dialog = page.getByRole('dialog')
      await dialog.waitFor()
      const box = await page.locator('.el-dialog').boundingBox()
      assert.ok(box && box.width > 400 && box.width < 750)
      assert.ok(await dialog.locator('.el-dialog__header').count())
      await page.keyboard.press('Escape')
      await dialog.waitFor({ state: 'hidden' })
      await page.getByRole('button', { name: '刷新当前页面', exact: true }).click()
      await page.locator('.el-message').waitFor()
      assert.ok(await page.locator('.el-message').evaluate(element => getComputedStyle(element).position === 'fixed'))
    })
    await check('history loading directive and import controls remain functional after on-demand registration', async () => {
      await page.route('**/sessions**', async route => {
        const url = new URL(route.request().url())
        const response = await route.fetch({ url: api + url.pathname + url.search })
        await new Promise(resolve => setTimeout(resolve, 500))
        await route.fulfill({ response })
      })
      await goto('/history')
      await page.getByRole('heading', { name: '历史记录', exact: true }).waitFor()
      await page.locator('.el-loading-mask').first().waitFor()
      await page.locator('.el-loading-mask').first().waitFor({ state: 'hidden' })
      await page.unroute('**/sessions**')
      await goto('/import')
      await page.locator('.upload-zone').waitFor()
      assert.equal(await page.locator('#primary-file-upload').isEnabled(), true)
      assert.equal(await page.locator('el-upload,el-table,el-input,el-select').count(), 0)
      const upload = await page.locator('.upload-zone').boundingBox()
      assert.ok(upload && upload.width > 100)
    })
    await check('route chunk network failure presents recovery without blanking the application shell', async () => {
      await goto('/')
      await page.locator('.overview').waitFor()
      injectingFailure = true
      await page.route('**/assets/Today-*.js', route => route.abort('failed'))
      await page.locator('.sidebar a[href="/today"]').click()
      await page.getByRole('alert', { name: '页面加载失败', exact: true }).waitFor()
      assert.match(await page.locator('.page-load-error').innerText(), /未保存的输入/)
      assert.ok(await page.locator('.sidebar').isVisible())
      await page.unroute('**/assets/Today-*.js')
      injectingFailure = false
      await page.getByRole('button', { name: '重新打开页面', exact: true }).click()
      await page.getByRole('heading', { name: '今日学习', exact: true }).waitFor()
      assert.equal(new URL(page.url()).pathname, '/today')
      assert.equal(await page.locator('.page-load-error').count(), 0)
    })
  }
  for (const width of [375, 768, 1440]) await check(`compiled homepage and controls fit ${width}px`, async () => {
    await page.setViewportSize({ width, height: 1000 })
    await goto('/')
    await page.locator('.overview').waitFor()
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false)
    await page.screenshot({ path: path.join(out, `home-${width}.png`), fullPage: true })
  })
  assert.deepEqual(errors, [])
  assert.deepEqual(warnings, [])
  const report = { passed: results.filter(row => row.passed).length, total: results.length, errors, warnings, timings, requests, results,
    sample_kind: 'engineering', scope: 'isolated compiled UI and real local API; loopback timing is not production SLA' }
  fs.writeFileSync(path.join(out, 'summary.json'), JSON.stringify(report, null, 2))
  console.log(JSON.stringify({ passed: report.passed, total: report.total, errors, warnings, timings }))
  if (report.passed !== report.total) process.exitCode = 1
} finally { await browser.close() }
