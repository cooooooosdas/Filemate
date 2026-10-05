import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const base = process.env.FILEMATE_WEB_URL, api = process.env.FILEMATE_API_URL
const size = Number(process.env.FILEMATE_CAPACITY_SIZE), out = process.env.FILEMATE_EVIDENCE_DIR
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
const result = { size, errors: [], sample_kind: 'synthetic_actual_api', passed: false }
await page.route('**/*', route => {
  const url = new URL(route.request().url())
  if (['xhr', 'fetch'].includes(route.request().resourceType()) && url.origin === base)
    return route.continue({ url: api + url.pathname + url.search })
  return route.continue()
})
page.on('pageerror', error => result.errors.push(String(error)))
await page.addInitScript(() => {
  window.auditTasks = []
  new PerformanceObserver(list => window.auditTasks.push(...list.getEntries().map(entry => entry.duration))).observe({ type: 'longtask', buffered: true })
})
try {
  const started = performance.now()
  await page.goto(base + '/knowledge-graph', { waitUntil: 'domcontentloaded' })
  await page.getByText(`${size} 个知识点`, { exact: false }).first().waitFor()
  await page.locator('.chart canvas').waitFor()
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
  result.graph_ready_ms = Math.round(performance.now() - started)
  await page.getByRole('button', { name: '列表', exact: true }).click()
  assert.equal(await page.locator('.node-list li').count(), Math.min(size, 200))
  const input = page.getByRole('searchbox', { name: '查找知识点或资料', exact: true })
  await input.fill(`知识点${String(size - 1).padStart(5, '0')}`)
  await page.waitForFunction(() => document.querySelectorAll('.node-list li').length === 1)
  await page.locator('.node-list li button').click()
  await page.locator('#evidence-title').waitFor()
  assert.ok((await page.locator('#evidence-title').textContent()).includes(String(size - 1).padStart(5, '0')))
  result.long_tasks = await page.evaluate(() => ({ maximum_ms: Math.round(Math.max(0, ...window.auditTasks)), count: window.auditTasks.length }))
  assert.ok(result.long_tasks.maximum_ms < 1500, 'main thread remains responsive')
  await page.setViewportSize({ width: 375, height: 900 })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
  await page.screenshot({ path: path.join(out, 'graph-mobile.png'), fullPage: true })
  assert.deepEqual(result.errors, [])
  result.passed = true
} finally {
  fs.writeFileSync(path.join(out, 'browser.json'), JSON.stringify(result, null, 2))
  await browser.close()
}
console.log(JSON.stringify(result))
