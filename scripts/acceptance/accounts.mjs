import assert from 'node:assert/strict'
import crypto from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'
import { createRequire } from 'node:module'
const require = createRequire(path.resolve('_working/a11y-tools/package.json'))
const { chromium } = require('playwright')
const axe = await fs.readFile(require.resolve('axe-core/axe.min.js'), 'utf8')
const base = process.env.FILEMATE_WEB_URL || 'http://127.0.0.1:5206'
const out = process.env.FILEMATE_EVIDENCE_DIR || '_working/account-auth/browser'
await fs.mkdir(out, { recursive: true })
const browser = await chromium.launch({ channel: process.platform === 'win32' ? 'msedge' : undefined })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
const other = await browser.newContext()
const guest = await browser.newContext()
const page = await context.newPage(), device = await other.newPage()
const email = `synthetic-auth-${crypto.randomUUID()}@example.invalid`
const password = crypto.randomBytes(24).toString('base64url')
const newPassword = crypto.randomBytes(24).toString('base64url')
const checks = [], errors = []
const headers = { Origin: base, 'X-FileMate-Action': 'account' }
let sourceId, oldCode, newCode
for (const current of [page, device]) current.on('pageerror', error => errors.push(String(error)))
async function check(name, body) {
  const start = Date.now()
  await body()
  checks.push({ name, passed: true, elapsed_ms: Date.now() - start })
}
async function layoutAndAxe(label, mask = []) {
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    await page.addScriptTag({ content: axe })
    const violations = await page.evaluate(async () => (await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } })).violations.map(item => ({ id: item.id, targets: item.nodes.map(node => node.target) })))
    assert.deepEqual(violations, [], `${label} ${width} accessibility`)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `${label} ${width} overflow`)
    await page.screenshot({ path: `${out}/${label}-${width}.png`, fullPage: true, mask })
  }
  checks.push({ name: `${label}: four layouts and WCAG AA scans`, passed: true })
}
async function loginUI(current, pass) {
  await current.goto(base + '/login')
  await current.locator('#account').fill(email)
  await current.locator('#password').fill(pass)
  await current.getByRole('button', { name: '登录', exact: true }).click()
}
try {
  await check('account API reachable and own synthetic guest material imported', async () => {
    const state = await context.request.get(base + '/api/auth/me')
    assert.equal(state.status(), 200)
    assert.equal((await state.json()).data.enabled, true)
    const response = await context.request.post(base + '/knowledge/import', { headers, multipart: { file: { name: '合成账号验收.txt', mimeType: 'text/plain', buffer: Buffer.from('【原创合成资料】仅用于账号工程验收。栈采用后进先出 LIFO；队列采用先进先出 FIFO。') } } })
    assert.equal(response.status(), 200)
    sourceId = (await response.json()).data.source_id
    await guest.addCookies((await context.cookies()).filter(cookie => cookie.name === 'filemate_identity'))
  })
  await page.goto(base + '/register')
  await layoutAndAxe('register')
  await check('real registration form issues session and one-time recovery code', async () => {
    await page.locator('#display-name').fill('合成账号验收')
    await page.locator('#account').fill(email)
    await page.locator('#password').fill(password)
    await page.locator('#confirm-password').fill(password)
    await page.getByLabel('我会保存恢复码，并了解邮箱暂不验证归属').check()
    await page.getByRole('button', { name: '创建账号', exact: true }).click()
    await page.locator('#saved-recovery-code').waitFor()
    oldCode = await page.locator('#saved-recovery-code').inputValue()
    assert.equal(oldCode.length, 43)
    const cookies = await context.cookies()
    const session = cookies.find(cookie => cookie.name === 'filemate_session')
    assert.equal(session.httpOnly, true)
    assert.equal(session.sameSite, 'Lax')
    if (base.startsWith('https:')) assert.equal(session.secure, true)
    assert.equal(await page.evaluate(() => [...Object.keys(localStorage), ...Object.keys(sessionStorage)].some(key => /password|session|recovery|token/i.test(key))), false)
    assert.equal((await guest.request.get(base + `/knowledge/sources/${sourceId}`)).status(), 404)
  })
  await layoutAndAxe('recovery-code', [page.locator('#saved-recovery-code')])
  await check('recovery code saved before entering persistent account space', async () => {
    assert.equal(await page.getByRole('button', { name: '进入学习空间', exact: true }).isDisabled(), true)
    const downloadEvent = page.waitForEvent('download')
    await page.getByRole('button', { name: '下载保存', exact: true }).click()
    const download = await downloadEvent
    assert.equal(download.suggestedFilename(), 'FileMate-恢复码.txt')
    const stream = await download.createReadStream()
    let text = ''; for await (const chunk of stream) text += chunk.toString('utf8')
    assert.ok(text.includes(oldCode))
    await download.delete()
    await page.getByLabel('我已妥善保存恢复码').check()
    await page.getByRole('button', { name: '进入学习空间', exact: true }).click()
    await page.getByRole('button', { name: '查看我的账号', exact: true }).waitFor()
    assert.equal((await context.request.get(base + `/knowledge/sources/${sourceId}`)).status(), 200)
    await page.reload()
    await page.getByRole('button', { name: '查看我的账号', exact: true }).waitFor()
  })
  await check('second browser logs into same account and reads same material', async () => {
    await loginUI(device, password)
    await device.getByRole('button', { name: '查看我的账号', exact: true }).waitFor()
    assert.equal((await other.request.get(base + `/knowledge/sources/${sourceId}`)).status(), 200)
  })
  await check('logout returns private material inaccessible to guest and login restores it', async () => {
    await page.getByRole('button', { name: '查看我的账号', exact: true }).click()
    await page.getByRole('button', { name: '退出登录', exact: true }).click()
    await page.getByRole('link', { name: '登录 FileMate' }).waitFor()
    assert.equal((await context.request.get(base + `/knowledge/sources/${sourceId}`)).status(), 404)
    await loginUI(page, password)
    await page.getByRole('button', { name: '查看我的账号', exact: true }).waitFor()
  })
  await page.goto(base + '/recover')
  await layoutAndAxe('recover')
  await check('recovery form resets password, rotates code and invalidates both old devices', async () => {
    await page.locator('#account').fill(email)
    await page.locator('#recovery-code').fill(oldCode)
    await page.locator('#password').fill(newPassword)
    await page.locator('#confirm-password').fill(newPassword)
    await page.getByRole('button', { name: '重设密码', exact: true }).click()
    await page.locator('#saved-recovery-code').waitFor()
    newCode = await page.locator('#saved-recovery-code').inputValue()
    assert.notEqual(oldCode, newCode)
    assert.equal((await other.request.get(base + `/knowledge/sources/${sourceId}`)).status(), 401)
    const reuse = await guest.request.post(base + '/api/auth/recover', { headers, data: { email, recovery_code: oldCode, password } })
    assert.equal(reuse.status(), 401)
    await page.getByLabel('我已妥善保存恢复码').check()
    await page.getByRole('button', { name: '返回登录', exact: true }).click()
    await page.locator('#account').waitFor()
  })
  await layoutAndAxe('login')
  await check('old password rejected; new password restores original account material', async () => {
    await loginUI(page, password)
    await page.getByRole('alert').filter({ hasText: '邮箱或密码不正确' }).waitFor()
    await page.locator('#password').fill(newPassword)
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await page.getByRole('button', { name: '查看我的账号', exact: true }).waitFor()
    assert.equal((await context.request.get(base + `/knowledge/sources/${sourceId}`)).status(), 200)
  })
} catch (error) { checks.push({ name: 'browser account flow', passed: false, error: String(error) }) }
finally {
  if (sourceId) {
    try {
      await page.goto(base + '/knowledge')
      await page.getByRole('button', { name: '删除资料：合成账号验收.txt', exact: true }).click()
      const confirmation = page.locator('.el-message-box')
      await confirmation.waitFor()
      assert.ok((await confirmation.innerText()).includes('合成账号验收.txt'))
      await confirmation.getByRole('button', { name: '删除', exact: true }).click()
      await page.getByRole('button', { name: '删除资料：合成账号验收.txt', exact: true }).waitFor({ state: 'detached' })
      assert.equal((await context.request.get(base + `/knowledge/sources/${sourceId}`)).status(), 404)
      checks.push({ name: 'preview and delete only own synthetic material', passed: true })
    } catch (error) { checks.push({ name: 'synthetic cleanup', passed: false, error: String(error) }) }
  }
  await context.request.post(base + '/api/auth/logout', { headers, data: {} }).catch(() => {})
  await browser.close()
  const report = { passed: checks.every(item => item.passed) && errors.length === 0, sample_kind: 'synthetic_account_engineering_acceptance', base, checks, errors, limitations: ['Does not verify email ownership or measure real student learning outcomes.', 'Synthetic account registry remains; no real user data or credential values are included in this report.'] }
  await fs.writeFile(`${out}/summary.json`, JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report, null, 2))
  if (!report.passed) process.exitCode = 1
}
