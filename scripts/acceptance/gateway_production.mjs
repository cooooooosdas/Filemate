import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR)
assert.ok(out.startsWith(path.resolve('_working') + path.sep))
fs.mkdirSync(out, { recursive: true })
const base = process.env.FILEMATE_WEB_URL
assert.equal(new URL(base).protocol, 'https:')
assert.ok(['127.0.0.1', 'localhost'].includes(new URL(base).hostname))
assert.equal(process.env.FILEMATE_ACCEPTANCE_INSECURE_TLS, '1')
const routes = [...new Set([...fs.readFileSync('filemate/web/src/router/index.ts', 'utf8')
  .matchAll(/path:\s*'([^']+)'/g)].map(match => match[1]))]
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || 'msedge', headless: true })
const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 1000 },
  httpCredentials: { username: process.env.FILEMATE_ACCEPTANCE_BASIC_USER, password: process.env.FILEMATE_ACCEPTANCE_BASIC_PASSWORD },
})
const page = await context.newPage()
const errors = [], violations = [], checks = []
page.on('pageerror', error => errors.push(String(error)))
await page.addInitScript(() => { window.__cspViolations = []; document.addEventListener('securitypolicyviolation', event => window.__cspViolations.push({ directive: event.violatedDirective, blocked: event.blockedURI })) })
async function check(name, run) {
  try { await run(); checks.push({ name, passed: true }) }
  catch (error) { checks.push({ name, passed: false, error: String(error) }); await page.screenshot({ path: path.join(out, `failure-${checks.length}.png`), fullPage: true }) }
}
try {
  await check('actual TLS gateway renders production Home and protects fresh learning data', async () => {
    await page.goto(base + '/')
    await page.locator('.overview').waitFor()
    assert.equal(await page.locator('.empty-files a').getAttribute('href'), '/knowledge')
    assert.equal(await page.locator('.hero-start').getAttribute('href'), '/ai-tools')
    assert.equal(await page.locator('.global-import').getAttribute('href'), '/import?intent=study')
    assert.equal(await page.evaluate(() => window.isSecureContext), true)
    const response = await context.request.get(base + '/api/health', { headers: { Accept: 'text/html' } })
    assert.equal(response.status(), 200)
    assert.equal((await response.json()).success, true)
    assert.equal(response.headers()['x-content-type-options'], 'nosniff')
  })
  await check('programming page actually loads Monaco under production CSP', async () => {
    await page.goto(base + '/programming')
    await page.locator('.monaco-editor').first().waitFor({ timeout: 40000 })
    await page.waitForTimeout(500)
    violations.push(...await page.evaluate(() => window.__cspViolations))
    assert.equal(violations.length, 0)
  })
  for (const route of routes) await check(`actual TLS production page ${route}`, async () => {
    const response = await page.goto(base + route)
    assert.equal(response.status(), 200)
    assert.match(response.headers()['content-type'], /text\/html/)
    await page.waitForFunction(() => (document.querySelector('main')?.innerText.trim().length || 0) > 0)
    await page.waitForTimeout(250)
    violations.push(...await page.evaluate(() => window.__cspViolations))
  })
  for (const width of [375, 768, 1440]) await check(`TLS production Home fits ${width}px`, async () => {
    await page.setViewportSize({ width, height: 1000 })
    await page.goto(base + '/')
    await page.locator('.overview').waitFor()
    await page.waitForTimeout(250)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
    await page.screenshot({ path: path.join(out, `home-${width}.png`), fullPage: true })
  })
  await check('all observed page errors and CSP violations are absent', async () => {
    assert.deepEqual(errors, [])
    assert.deepEqual(violations, [])
  })
} finally { await browser.close() }
const summary = { passed: checks.every(check => check.passed), total: checks.length, routes, checks, errors, violations,
  evidence_kind: 'actual HTTPS Caddy, production assets and same-origin API, no request relay; isolated synthetic tenant' }
fs.writeFileSync(path.join(out, 'summary.json'), JSON.stringify(summary, null, 2))
console.log(JSON.stringify({ passed: summary.passed, total: summary.total }))
if (!summary.passed) process.exitCode = 1
