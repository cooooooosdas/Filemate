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
  const response = await page.request.post(api + '/api/programming/submissions', { data: { problem_id: 'array-sum', code: '// synthetic delete test only\nint main(){return 0;}', request_key: 'synthetic-delete-' + Date.now(), language: 'cpp17' } })
  assert.equal(response.status(), 200)
  const id = (await response.json()).data.submission_id
  assert.equal((await page.request.post(api + `/api/programming/submissions/${id}/cancel`, { data: {} })).status(), 200)
  await page.goto(base + '/programming?submission=' + id)
  await page.getByRole('button', { name: '彻底删除此提交', exact: true }).waitFor()
  await page.getByRole('button', { name: '彻底删除此提交', exact: true }).click()
  await page.getByRole('button', { name: '取消', exact: true }).click()
  assert.equal((await page.request.get(api + `/api/programming/submissions/${id}`)).status(), 200)
  await page.getByRole('button', { name: '彻底删除此提交', exact: true }).click()
  await page.getByRole('button', { name: '确认彻底删除', exact: true }).click()
  await page.getByText('此提交的源码、反馈与关联报告已删除', { exact: true }).waitFor()
  assert.equal((await page.request.get(api + `/api/programming/submissions/${id}`)).status(), 404)
  await page.waitForURL('**/programming?problem=array-sum')
  await page.reload()
  await page.getByRole('heading', { name: '编程练习', exact: true }).waitFor()
  assert.equal((await page.request.get(api + `/api/programming/submissions/${id}`)).status(), 404)
  checks.push('actual cancelled synthetic submission; cancel dialog preserves data, confirmation deletes and reload does not resurrect it')
  await page.setViewportSize({ width: 375, height: 900 })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
  await page.screenshot({ path: path.join(out, 'coding-delete-mobile.png'), fullPage: true })
  assert.deepEqual(errors, [])
  fs.writeFileSync(path.join(out, 'browser.json'), JSON.stringify({ passed: true, checks, errors }, null, 2))
} finally { await browser.close() }
