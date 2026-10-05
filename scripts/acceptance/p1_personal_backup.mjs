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
  const upload = await page.request.post(api + '/knowledge/import', { multipart: { file: { name: 'synthetic-personal-backup.txt', mimeType: 'text/plain', buffer: Buffer.from('原创合成恢复资料，只用于工程回归。') } } })
  assert.equal(upload.status(), 200)
  const sid = (await upload.json()).data.source_id
  await page.goto(base + '/trust')
  await page.getByRole('heading', { name: '导出与恢复个人数据', exact: true }).waitFor()
  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载整包备份', exact: true }).click()
  const download = await downloadEvent, file = path.join(out, 'synthetic-personal-backup.zip')
  await download.saveAs(file)
  assert.ok(fs.statSync(file).size > 100)
  const deletion = (await (await page.request.get(api + `/knowledge/sources/${sid}/delete-preview`)).json()).data
  assert.equal((await page.request.delete(api + `/knowledge/sources/${sid}`, { data: { confirmed: true, confirmation_token: deletion.confirmation_token } })).status(), 200)
  assert.equal((await page.request.get(api + `/knowledge/sources/${sid}`)).status(), 404)
  await page.getByLabel('选择 FileMate 整包备份', { exact: true }).setInputFiles(file)
  await page.getByRole('button', { name: '校验并预览备份', exact: true }).click()
  await page.getByRole('heading', { name: '恢复预览', exact: true }).waitFor()
  await page.getByRole('button', { name: '确认恢复这份备份', exact: true }).click()
  await page.getByRole('button', { name: '取消', exact: true }).click()
  assert.equal((await page.request.get(api + `/knowledge/sources/${sid}`)).status(), 404)
  await page.getByRole('button', { name: '确认恢复这份备份', exact: true }).click()
  await page.getByRole('button', { name: '确认整体恢复', exact: true }).click()
  await page.getByText('个人数据与托管文件已恢复', { exact: true }).waitFor()
  const restored = await page.request.get(api + `/knowledge/sources/${sid}`)
  assert.equal(restored.status(), 200)
  assert.equal((await restored.json()).data.raw_text, '原创合成恢复资料，只用于工程回归。')
  checks.push('actual managed upload, UI signed backup download, confirmed source deletion, preview, cancellation and confirmed restore all work')
  await page.reload()
  await page.getByRole('heading', { name: '导出与恢复个人数据', exact: true }).waitFor()
  assert.equal((await page.request.get(api + `/knowledge/sources/${sid}`)).status(), 200)
  await page.setViewportSize({ width: 375, height: 900 })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
  await page.screenshot({ path: path.join(out, 'personal-backup-mobile.png'), fullPage: true })
  assert.deepEqual(errors, [])
  checks.push('reload persists restored data, 375px and no runtime errors')
  fs.writeFileSync(path.join(out, 'browser.json'), JSON.stringify({ passed: true, checks, errors }, null, 2))
} finally { await browser.close() }
