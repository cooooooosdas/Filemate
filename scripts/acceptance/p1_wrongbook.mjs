import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
const base = process.env.FILEMATE_WEB_URL, api = process.env.FILEMATE_API_URL
const out = process.env.FILEMATE_EVIDENCE_DIR
const checks = [], errors = []
page.on('pageerror', error => errors.push(String(error)))
await page.route('**/*', route => {
  const url = new URL(route.request().url())
  if (['xhr', 'fetch'].includes(route.request().resourceType()) && url.origin === base)
    return route.continue({ url: api + url.pathname + url.search })
  return route.continue()
})
try {
  await page.goto(base + '/wrongbook')
  await page.getByText('共 10000 道', { exact: false }).waitFor()
  assert.equal(await page.locator('.wrong-card').count(), 30)
  const first = await page.locator('.wrong-card h2').first().textContent()
  await page.getByRole('button', { name: '下一页', exact: true }).click()
  await page.getByText('第 2 /', { exact: false }).waitFor()
  await page.waitForFunction(value => document.querySelector('.wrong-card h2')?.textContent !== value, first)
  assert.equal(await page.locator('.wrong-card').count(), 30)
  checks.push('real 10000 records, page 2 changes questions')
  await page.getByRole('searchbox').fill('知识点09999')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await page.getByText('共 1 道', { exact: false }).waitFor()
  assert.equal(await page.locator('.wrong-card').count(), 1)
  checks.push('last question is reachable by full-dataset search')
  await page.setViewportSize({ width: 375, height: 900 })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
  await page.screenshot({ path: path.join(out, 'wrongbook-mobile.png'), fullPage: true })
  await page.getByRole('searchbox').fill('不存在的合成内容')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await page.getByText('当前筛选没有匹配错题', { exact: true }).waitFor()
  checks.push('375px layout and filtered empty state')
  assert.deepEqual(errors, [])
} finally {
  fs.writeFileSync(path.join(out, 'browser.json'), JSON.stringify({ checks, errors, sample_kind: 'synthetic_actual_api' }, null, 2))
  await browser.close()
}
console.log(JSON.stringify(checks))
