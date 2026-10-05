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
  const password = 'Synthetic9z123'
  const registered = await page.request.post(api + '/api/auth/register', { headers: { 'X-FileMate-Action': 'account' }, data: { email: 'privacy-ui@example.invalid', display_name: '合成注销回归', password } })
  assert.equal(registered.status(), 200)
  const upload = await page.request.post(api + '/knowledge/import', { multipart: { file: { name: 'synthetic.txt', mimeType: 'text/plain', buffer: Buffer.from('原创合成注销测试。') } } })
  assert.equal(upload.status(), 200)
  await page.goto(base + '/trust')
  await page.getByRole('heading', { name: '注销账号', exact: true }).waitFor()
  await page.getByRole('button', { name: '预览账号注销', exact: true }).click()
  await page.getByRole('heading', { name: '核对删除范围', exact: true }).waitFor()
  await page.getByRole('button', { name: '取消注销', exact: true }).click()
  assert.ok((await (await page.request.get(api + '/api/auth/me')).json()).data.user)
  await page.getByRole('button', { name: '预览账号注销', exact: true }).click()
  await page.getByLabel('输入当前密码确认', { exact: true }).fill(password)
  await page.getByRole('button', { name: '确认注销此账号', exact: true }).click()
  await page.getByRole('button', { name: '保留账号', exact: true }).click()
  assert.ok((await (await page.request.get(api + '/api/auth/me')).json()).data.user)
  await page.getByLabel('输入当前密码确认', { exact: true }).fill(password)
  await page.getByRole('button', { name: '确认注销此账号', exact: true }).click()
  await page.getByRole('button', { name: '永久注销', exact: true }).click()
  await page.getByText('账号与服务内学习资料已删除，所有登录已撤销。', { exact: true }).waitFor()
  assert.equal((await (await page.request.get(api + '/api/auth/me')).json()).data.user, null)
  assert.deepEqual((await (await page.request.get(api + '/knowledge/sources')).json()).data, [])
  const relogin = await page.request.post(api + '/api/auth/login', { headers: { 'X-FileMate-Action': 'account' }, data: { email: 'privacy-ui@example.invalid', password } })
  assert.equal(relogin.status(), 401)
  checks.push('actual registered account upload, preview cancellation, final cancellation and confirmed erasure; login denied and data absent')
  await page.setViewportSize({ width: 375, height: 900 })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
  await page.screenshot({ path: path.join(out, 'account-erasure-mobile.png'), fullPage: true })
  assert.deepEqual(errors, [])
  fs.writeFileSync(path.join(out, 'browser.json'), JSON.stringify({ passed: true, checks, errors }, null, 2))
} finally { await browser.close() }
