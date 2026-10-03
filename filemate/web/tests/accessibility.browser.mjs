import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../../../', import.meta.url))
const runtime = path.resolve(process.env.FILEMATE_A11Y_RUNTIME || path.join(root, '_working/a11y-tools'))
const require = createRequire(path.join(runtime, 'package.json'))
const { chromium } = require('playwright')
const axeSource = await fs.readFile(require.resolve('axe-core/axe.min.js'), 'utf8')
const base = process.env.FILEMATE_WEB_URL || 'http://127.0.0.1:5189'
const api = process.env.FILEMATE_API_URL
const gatewayUser = process.env.FILEMATE_ACCEPTANCE_GATEWAY_USER
const gatewayPassword = process.env.FILEMATE_ACCEPTANCE_GATEWAY_PASSWORD
assert.equal(Boolean(gatewayUser), Boolean(gatewayPassword), 'Gateway credentials must be supplied together')
if (['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname)) assert.ok(api, 'Local preview requires an explicitly selected isolated FILEMATE_API_URL')
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR || path.join(root, '_working/a4-accessibility'))
assert.ok(out.startsWith(path.join(root, '_working') + path.sep), 'Evidence must stay in this project _working')
const settleMs = Number(process.env.FILEMATE_ROUTE_SETTLE_MS || 800)
assert.ok(Number.isInteger(settleMs) && settleMs >= 800 && settleMs <= 30000)
const routes = ['/', '/today', '/import', '/classification', '/naming', '/schedule', '/history', '/ai-tools', '/study-plan', '/wrongbook', '/interview', '/interview-bank', '/growth', '/knowledge', '/digital-human', '/knowledge-graph', '/programming', '/career', '/goals', '/trust', '/login', '/register']
await fs.mkdir(out, { recursive: true })
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || (process.platform === 'win32' ? 'msedge' : undefined) })
const context = await browser.newContext({
  ignoreHTTPSErrors: process.env.FILEMATE_ACCEPTANCE_INSECURE_TLS === '1',
  ...(gatewayUser ? { httpCredentials: { username: gatewayUser, password: gatewayPassword } } : {}),
})
const relayErrors = []
// Optional relay targets a real isolated API, never the existing user's local service.
if (api && new URL(api).origin !== new URL(base).origin) {
  await context.route(base + '/**', async route => {
    const request = route.request(), url = new URL(request.url())
    if (['fetch', 'xhr'].includes(request.resourceType()) && !/^\/(assets|interview-vision)\//.test(url.pathname)) {
      try {
        const method = request.method(), body = request.postData()
        const options = { method }
        if (!['GET', 'HEAD'].includes(method) && body !== null) {
          options.data = body
          options.headers = { 'Content-Type': 'application/json' }
        }
        return await route.fulfill({ response: await context.request.fetch(api + url.pathname + url.search, options) })
      } catch (error) {
        relayErrors.push({ path: url.pathname, error: String(error) })
        await route.abort('failed').catch(() => {})
        return
      }
    }
    return route.continue()
  })
}
const page = await context.newPage()
const results = []
let complete = false
async function persist() {
  await fs.writeFile(path.join(out, 'accessibility.json'), JSON.stringify({
    generated_at: new Date().toISOString(), base, api_relay: api || null,
    sample_kind: 'automated_ui_accessibility_regression', axe_version: require('axe-core/package.json').version,
    scope: 'Empty/default pages and named transient surfaces; no real user or full WCAG certification',
    complete, passed: complete && relayErrors.length === 0 && results.every(r => r.passed), relayErrors, results
  }, null, 2))
}
await persist()
async function audit() {
  await page.evaluate(axeSource)
  return page.evaluate(async () => {
    const report = await window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } })
    return {
      violations: report.violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.map(n => ({ target: n.target, html: n.html, summary: n.failureSummary })) })),
      manual_review: report.incomplete.map(v => ({ id: v.id, count: v.nodes.length }))
    }
  })
}
async function check(name, task) {
  try { const evidence = await task(); results.push({ name, passed: true, evidence }); console.log('PASS ' + name) }
  catch (error) { results.push({ name, passed: false, error: String(error) }); console.log('FAIL ' + name + ': ' + String(error).slice(0, 180)) }
  await persist()
}
try {
  for (const width of [375, 768, 1280]) {
    await page.setViewportSize({ width, height: 844 })
    for (const route of routes) await check(`${width} ${route}`, async () => {
      const errors = []
      const onError = error => errors.push(String(error))
      const onConsole = message => { if (message.type() === 'error') errors.push(message.text()) }
      page.on('pageerror', onError); page.on('console', onConsole)
      try {
        const response = await page.goto(base + route, { waitUntil: 'domcontentloaded' })
        await page.waitForTimeout(settleMs)
        const evidence = await audit()
        const layout = await page.evaluate(() => {
          const content = document.querySelector('.content-scroll')
          return { overflow: document.documentElement.scrollWidth > innerWidth, contentOverflow: content ? content.scrollWidth > content.clientWidth + 1 : false, mainCount: document.querySelectorAll('main').length }
        })
        await page.screenshot({ path: path.join(out, `${width}-${route === '/' ? 'home' : route.slice(1)}.png`), fullPage: true })
        assert.equal(response.status(), 200)
        assert.equal(layout.mainCount, 1)
        assert.equal(layout.overflow, false)
        assert.equal(layout.contentOverflow, false)
        assert.deepEqual(errors, [])
        assert.deepEqual(evidence.violations, [], JSON.stringify(evidence.violations))
        return { ...layout, ...evidence }
      } finally { page.off('pageerror', onError); page.off('console', onConsole) }
    })
  }
  await check('mobile drawer: modal background, keyboard wrap, Escape, same-route and resize focus', async () => {
    await page.setViewportSize({ width: 375, height: 844 })
    await page.goto(base); await page.waitForTimeout(settleMs)
    const menu = page.getByRole('button', { name: '打开导航', exact: true })
    await menu.click()
    const drawer = page.getByRole('dialog', { name: '主导航', exact: true })
    await drawer.waitFor()
    assert.equal(await page.locator('#main-content').evaluate(e => e.inert), true)
    assert.equal(await drawer.locator('.brand-link').evaluate(e => e === document.activeElement), true)
    await page.keyboard.press('Shift+Tab')
    assert.equal(await drawer.getByRole('button', { name: '打开应用设置' }).evaluate(e => e === document.activeElement), true)
    await page.keyboard.press('Tab')
    assert.equal(await drawer.locator('.brand-link').evaluate(e => e === document.activeElement), true)
    await page.keyboard.press('Escape')
    assert.equal(await menu.evaluate(e => e === document.activeElement), true)
    assert.equal(await page.locator('#main-content').evaluate(e => e.inert), false)
    await menu.click(); await page.keyboard.press('Control+k')
    await page.getByRole('dialog', { name: '查找功能', exact: true }).waitFor()
    await page.waitForTimeout(350)
    await page.keyboard.press('Escape'); await page.waitForTimeout(350)
    assert.equal(await menu.evaluate(e => e === document.activeElement), true)
    await menu.click(); await drawer.locator('.brand-link').click()
    assert.equal(await page.locator('#main-content').evaluate(e => e === document.activeElement), true)
    await menu.click(); await page.setViewportSize({ width: 1280, height: 844 })
    await page.waitForTimeout(300)
    assert.equal(await page.locator('#main-content').evaluate(e => e.inert), false)
    assert.equal(await page.locator('#main-content').evaluate(e => e === document.activeElement), true)
  })
  for (const route of ['/login', '/register']) await check(`invalid form focus ${route}`, async () => {
    await page.goto(base + route); await page.waitForTimeout(settleMs)
    await page.locator('form button[type=submit]').click()
    assert.equal(await page.locator('form input[aria-invalid=true]').first().evaluate(e => e === document.activeElement), true)
    const evidence = await audit()
    assert.deepEqual(evidence.violations, [], JSON.stringify(evidence.violations))
    return evidence
  })
  await check('question editor dialog labels', async () => {
    await page.goto(base + '/interview-bank'); await page.waitForTimeout(settleMs)
    await page.getByRole('button', { name: '新增题目', exact: true }).click()
    await page.getByRole('dialog', { name: '新增题目', exact: true }).waitFor()
    await page.waitForTimeout(350)
    const evidence = await audit()
    assert.deepEqual(evidence.violations, [], JSON.stringify(evidence.violations))
    await page.getByRole('button', { name: '取消', exact: true }).click()
    return evidence
  })
  await check('settings and finder dialog labels', async () => {
    await page.goto(base); await page.waitForTimeout(settleMs)
    await page.getByRole('button', { name: '打开设置', exact: true }).click()
    await page.getByRole('dialog', { name: '应用设置', exact: true }).waitFor()
    await page.waitForTimeout(settleMs)
    const settings = await audit()
    assert.deepEqual(settings.violations, [], JSON.stringify(settings.violations))
    await page.getByRole('button', { name: '关闭', exact: true }).click()
    await page.waitForTimeout(350)
    await page.keyboard.press('Control+k')
    await page.getByRole('dialog', { name: '查找功能', exact: true }).waitFor()
    await page.waitForTimeout(350)
    const finder = await audit()
    assert.deepEqual(finder.violations, [], JSON.stringify(finder.violations))
    await page.keyboard.press('Escape')
    return { settings, finder }
  })
  await check('reduced motion and keyboard skip link', async () => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto(base); await page.waitForTimeout(settleMs)
    await page.keyboard.press('Tab')
    assert.equal(await page.getByRole('link', { name: '跳到主要内容', exact: true }).evaluate(e => e === document.activeElement && getComputedStyle(e).outlineStyle !== 'none'), true)
    await page.keyboard.press('Enter')
    assert.equal(await page.locator('#main-content').evaluate(e => e === document.activeElement), true)
    const longAnimations = await page.evaluate(() => document.getAnimations().filter(a => a.playState === 'running' && Number(a.effect?.getComputedTiming().duration) > 1).length)
    assert.equal(longAnimations, 0)
  })
  complete = true
} catch (error) {
  results.push({ name: 'fatal harness failure', passed: false, error: String(error) })
} finally { await browser.close(); await persist() }
if (!complete || relayErrors.length || results.some(r => !r.passed)) process.exitCode = 1
