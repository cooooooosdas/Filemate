import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'
const base = process.env.FILEMATE_WEB_URL, api = process.env.FILEMATE_API_URL, out = process.env.FILEMATE_EVIDENCE_DIR
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }), errors = [], checks = []
page.on('pageerror', error => errors.push(String(error)))
let boundaryFailure = true
await page.route('**/*', route => {
  const url = new URL(route.request().url())
  if (url.pathname === '/api/privacy/boundary' && boundaryFailure) return route.abort('failed')
  if (['xhr', 'fetch'].includes(route.request().resourceType()) && url.origin === base) return route.continue({ url: api + url.pathname + url.search })
  return route.continue()
})
try {
  await page.goto(base + '/import')
  await page.getByText('未能确认数据保存位置，请先连接服务并重试。', { exact: true }).waitFor()
  assert.ok(await page.getByRole('button', { name: '选择资料', exact: true }).isDisabled())
  boundaryFailure = false
  await page.getByRole('button', { name: '重试读取说明', exact: true }).click()
  await page.getByText('网站资料保存在服务器', { exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: '选择资料', exact: true }).isDisabled(), false)
  await page.getByText(/匿名空间连续90天未使用后清理/).waitFor()
  checks.push('unknown storage location blocks upload; actual boundary retry shows server storage and real retention')
  for (const width of [375, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
    await page.screenshot({ path: path.join(out, `upload-boundary-${width}.png`), fullPage: true })
  }
  await page.goto(base + '/trust')
  await page.getByText('网站私有学习空间', { exact: true }).waitFor()
  assert.equal((await page.locator('main').innerText()).includes('资料本地保存'), false)
  await page.goto(base + '/knowledge')
  await page.getByText('私有空间检索 · 原文可回看', { exact: true }).waitFor()
  checks.push('website trust and search disclose correct location; desktop tablet mobile do not overflow')
  assert.deepEqual(errors, [])
  fs.writeFileSync(path.join(out, 'browser.json'), JSON.stringify({ passed: true, checks, errors }, null, 2))
} finally { await browser.close() }
