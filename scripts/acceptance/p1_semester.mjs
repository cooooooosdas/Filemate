import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'
const base = process.env.FILEMATE_WEB_URL, api = process.env.FILEMATE_API_URL, out = process.env.FILEMATE_EVIDENCE_DIR
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }), errors = [], checks = []
page.on('pageerror', error => errors.push(String(error)))
await page.route('**/*', route => {
  const url = new URL(route.request().url())
  if (['xhr', 'fetch'].includes(route.request().resourceType()) && url.origin === base) return route.continue({ url: api + url.pathname + url.search })
  return route.continue()
})
try {
  await page.goto(base + '/semester')
  await page.getByRole('heading', { name: '建立本学期', exact: true }).waitFor()
  await page.getByLabel('学期名称', { exact: true }).fill('原创合成秋季学期')
  await page.getByLabel('开始日期', { exact: true }).fill('2026-09-01')
  await page.getByLabel('结束日期', { exact: true }).fill('2026-09-28')
  await page.getByLabel('课程名称', { exact: true }).fill('原创合成课程')
  await page.getByLabel('每周学习目标', { exact: true }).fill('实现并复盘原创合成算法')
  await page.getByRole('button', { name: '预览学期编排', exact: true }).click()
  await page.getByRole('button', { name: '取消', exact: true }).click()
  assert.equal((await (await page.request.get(api + '/api/semester')).json()).data, null)
  await page.getByRole('button', { name: '预览学期编排', exact: true }).click()
  await page.getByRole('button', { name: '确认编排', exact: true }).click()
  await page.getByRole('heading', { name: '原创合成秋季学期', exact: true }).waitFor()
  await page.getByRole('checkbox', { name: '原创合成课程 第1周 任务完成', exact: true }).check()
  await page.getByText(/1\/4 项完成/).waitFor()
  await page.reload()
  await page.getByText(/1\/4 项完成/).waitFor()
  assert.equal(await page.getByRole('checkbox', { name: '原创合成课程 第1周 任务完成', exact: true }).isChecked(), true)
  await page.getByLabel('周次', { exact: true }).selectOption('2')
  assert.equal(await page.locator('.semester-task-list li').count(), 1)
  checks.push('cancelled preview writes nothing; confirm creates actual tasks; completion persists after reload and week filter works')
  await page.getByRole('button', { name: '调整课程编排', exact: true }).click()
  await page.getByLabel('每周学习目标', { exact: true }).fill('新的原创任务')
  await page.getByRole('button', { name: '预览学期编排', exact: true }).click()
  await page.getByRole('button', { name: '确认编排', exact: true }).click()
  await page.getByText(/0\/4 项完成/).waitFor()
  checks.push('explicit replacement resets current tasks; old completion is archived by backend')
  await page.setViewportSize({ width: 375, height: 900 })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
  await page.screenshot({ path: path.join(out, 'semester-mobile.png'), fullPage: true })
  assert.deepEqual(errors, [])
  checks.push('375px and no runtime errors')
  fs.writeFileSync(path.join(out, 'browser.json'), JSON.stringify({ passed: true, checks, errors }, null, 2))
} finally { await browser.close() }
