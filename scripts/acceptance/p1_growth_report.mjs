import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'
const base = process.env.FILEMATE_WEB_URL, api = process.env.FILEMATE_API_URL, out = process.env.FILEMATE_EVIDENCE_DIR
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true }), errors = [], checks = []
page.on('pageerror', error => errors.push(String(error)))
await page.route('**/*', route => {
  const url = new URL(route.request().url())
  if (['xhr', 'fetch'].includes(route.request().resourceType()) && url.origin === base) return route.continue({ url: api + url.pathname + url.search })
  return route.continue()
})
try {
  const target = (await (await page.request.get(api + '/api/skills/targets?q=知识点00000')).json()).data[0]
  const ids = []
  for (let index = 0; index < 25; index++) {
    const response = await page.request.post(api + '/quiz/attempts', { data: { artifact_id: target.target_id, question_index: target.question_index, user_answer: '容量审计中的原创合成定义' } })
    assert.equal(response.status(), 200); ids.push((await response.json()).data.attempt_id)
  }
  await page.goto(base + '/growth')
  await page.getByRole('heading', { name: '成长报告', exact: true }).waitFor()
  await page.getByRole('button', { name: '生成成长报告', exact: true }).click()
  await page.getByRole('heading', { name: /记录依据 · 共/ }).waitFor()
  assert.equal(await page.locator('.report-records li').count(), 20)
  await page.getByRole('button', { name: '下一页依据', exact: true }).click()
  await page.getByText(/第2\//).waitFor()
  assert.ok(await page.locator('.report-records li').count() >= 5)
  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出报告 JSON', exact: true }).click()
  const download = await downloadEvent, file = path.join(out, 'synthetic-growth-report.json')
  await download.saveAs(file)
  const document = JSON.parse(fs.readFileSync(file, 'utf8'))
  assert.ok(ids.every(id => document.records.some(record => record.record_id === id)))
  assert.ok(document.metrics.quiz_attempts >= 25)
  checks.push('25 actual API answers included in persisted report; UI evidence paginates and export contains all record IDs')
  await page.reload()
  await page.getByRole('heading', { name: '成长报告', exact: true }).waitFor()
  await page.getByRole('button', { name: /^成长报告 \d/ }).first().click()
  await page.getByRole('heading', { name: /记录依据 · 共/ }).waitFor()
  checks.push('history reread after reload')
  await page.setViewportSize({ width: 375, height: 900 })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
  await page.screenshot({ path: path.join(out, 'growth-report-mobile.png'), fullPage: true })
  assert.deepEqual(errors, [])
  checks.push('375px and no runtime errors')
  fs.writeFileSync(path.join(out, 'browser.json'), JSON.stringify({ passed: true, checks, errors }, null, 2))
} finally { await browser.close() }
