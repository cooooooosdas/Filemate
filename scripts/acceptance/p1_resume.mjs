import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'
const base = process.env.FILEMATE_WEB_URL, api = process.env.FILEMATE_API_URL, out = process.env.FILEMATE_EVIDENCE_DIR
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true })
const errors = [], checks = []
page.on('pageerror', error => errors.push(String(error)))
await page.route('**/*', route => {
  const url = new URL(route.request().url())
  if (['xhr', 'fetch'].includes(route.request().resourceType()) && url.origin === base) return route.continue({ url: api + url.pathname + url.search })
  return route.continue()
})
try {
  await page.goto(base + '/resume')
  await page.getByRole('heading', { name: '个人事实', exact: true }).waitFor()
  await page.getByLabel('姓名', { exact: true }).fill('原创合成学生')
  await page.getByLabel('学校', { exact: true }).fill('合成大学')
  await page.getByLabel('技能（每行一项，最多40项）', { exact: true }).fill('C++\n数据结构')
  await page.getByRole('button', { name: '添加项目', exact: true }).click()
  await page.getByLabel('项目名称', { exact: true }).fill('原创合成课程作品')
  await page.getByLabel('实际工作与成果', { exact: true }).fill('只用于浏览器功能验收，不代表真实学习效果。')
  await page.getByRole('button', { name: '保存个人事实', exact: true }).click()
  await page.getByText('个人事实已保存', { exact: true }).waitFor()
  await page.getByRole('button', { name: '生成简历', exact: true }).click()
  await page.getByText('简历已保存', { exact: true }).waitFor()
  assert.ok((await page.locator('.resume-preview pre').innerText()).includes('原创合成课程作品'))
  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出 JSON', exact: true }).click()
  const download = await downloadEvent
  const file = path.join(out, 'synthetic-resume.json'); await download.saveAs(file)
  const document = JSON.parse(fs.readFileSync(file, 'utf8'))
  assert.equal(document.profile.name, '原创合成学生')
  assert.equal(document.profile_revision, 1)
  checks.push('real profile save, persisted resume generation and JSON download')
  await page.reload()
  await page.getByRole('heading', { name: '个人事实', exact: true }).waitFor()
  assert.equal(await page.getByLabel('姓名', { exact: true }).inputValue(), '原创合成学生')
  await page.getByRole('button', { name: /原创合成学生 · 简历/ }).click()
  await page.locator('.resume-preview pre').waitFor()
  await page.getByLabel('学校', { exact: true }).fill('变更后的合成大学')
  assert.equal(await page.getByRole('button', { name: '生成简历', exact: true }).isDisabled(), true)
  await page.getByRole('button', { name: '保存个人事实', exact: true }).click()
  await page.getByText('个人事实已保存', { exact: true }).waitFor()
  assert.equal((await page.locator('.resume-preview pre').innerText()).includes('变更后的合成大学'), false)
  checks.push('reloading retains facts and old snapshot; dirty form prevents stale generation')
  await page.setViewportSize({ width: 375, height: 900 })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
  await page.screenshot({ path: path.join(out, 'resume-mobile.png'), fullPage: true })
  assert.deepEqual(errors, [])
  checks.push('375px usable without page overflow or runtime errors')
  fs.writeFileSync(path.join(out, 'browser.json'), JSON.stringify({ passed: true, checks, errors }, null, 2))
} finally { await browser.close() }
