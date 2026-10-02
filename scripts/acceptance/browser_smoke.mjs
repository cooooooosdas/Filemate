import { chromium, request } from 'playwright'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const base = process.env.FILEMATE_WEB_URL || 'http://127.0.0.1:5173'
const api = process.env.FILEMATE_API_URL || 'http://127.0.0.1:8001'
const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(scriptDir, '..', '..')
const outDir = process.env.FILEMATE_EVIDENCE_DIR || path.join(repoRoot, '_working', 'browser-acceptance')
fs.mkdirSync(outDir, { recursive: true })

const routes = [
  '/', '/today', '/import', '/classification', '/naming', '/schedule', '/history',
  '/ai-tools', '/study-plan', '/wrongbook', '/interview', '/interview-bank',
  '/growth', '/knowledge', '/digital-human', '/knowledge-graph', '/programming',
  '/career', '/goals', '/trust', '/login', '/register'
]

const username = process.env.FILEMATE_ACCEPTANCE_GATEWAY_USER
const password = process.env.FILEMATE_ACCEPTANCE_GATEWAY_PASSWORD
if (Boolean(username) !== Boolean(password)) throw new Error('Gateway credentials must be provided together')
const httpCredentials = username ? { username, password } : undefined
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || undefined })
const page = await browser.newPage({ httpCredentials })
const results = []

for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 844 }]) {
await page.setViewportSize(viewport)
for (const route of routes) {
  const errors = []
  const onConsole = (m) => { if (m.type() === 'error') errors.push(m.text()) }
  const onPageError = (e) => errors.push(String(e))
  page.on('console', onConsole)
  page.on('pageerror', onPageError)
  try {
    const resp = await page.goto(base + route, { waitUntil: 'domcontentloaded', timeout: 30000 })
    await page.waitForTimeout(800)
    const title = await page.title()
    const mainRegionCount = await page.locator('main').count()
    const mainText = await page.locator('main').innerText().catch(() => '')
    const hasHorizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
    const filename = viewport.width + '-' + (route === '/' ? 'home' : route.replace(/\//g, '_').slice(1)) + '.png'
    await page.screenshot({ path: path.join(outDir, filename), fullPage: true })
    results.push({
      route,
      viewport,
      status: resp ? resp.status() : null,
      title,
      hasMainContent: mainText.trim().length > 0,
      mainRegionCount,
      hasHorizontalOverflow,
      consoleErrors: errors,
    })
  } catch (err) {
    results.push({ route, viewport, status: null, title: '', consoleErrors: errors, error: String(err) })
  } finally {
    page.off('console', onConsole)
    page.off('pageerror', onPageError)
  }
}
}
await browser.close()

const ctx = await request.newContext({ baseURL: api, httpCredentials, timeout: 15000 })
const apiResults = []
for (const ep of ['/api/health', '/sessions', '/knowledge/sources', '/wrongbook', '/review/today', '/study-plans', '/interview/questions', '/analytics/overview', '/evaluation/feedback/summary', '/goals', '/trust/overview', '/api/digital-human/playbacks', '/api/knowledge-graph', '/api/programming/problems', '/api/programming/status', '/interview/review/status', '/api/career/catalog', '/api/career/status']) {
  try {
    const r = await ctx.get(ep)
    const body = await r.json().catch(() => null)
    apiResults.push({ endpoint: ep, status: r.status(), ok: r.ok() && body?.success === true })
  } catch (err) {
    apiResults.push({ endpoint: ep, status: null, ok: false, error: String(err) })
  }
}
await ctx.dispose()

const routeFailures = results.filter((item) =>
  item.status !== 200 || item.error || item.consoleErrors.length > 0 || !item.hasMainContent || item.mainRegionCount !== 1 || item.hasHorizontalOverflow
)
const apiFailures = apiResults.filter((item) => !item.ok)
const report = {
  baseline: process.env.FILEMATE_BASELINE || 'local',
  generated_at: new Date().toISOString(),
  sample_kind: 'empty_state_production_browser_regression',
  same_origin: new URL(base).origin === new URL(api).origin,
  route_count: routes.length,
  passed: routeFailures.length === 0 && apiFailures.length === 0,
  routes: results,
  api: apiResults,
  failures: { routes: routeFailures, api: apiFailures },
}
const out = path.join(outDir, 'browser-acceptance.json')
fs.writeFileSync(out, JSON.stringify(report, null, 2), 'utf-8')
console.log(JSON.stringify(report, null, 2))
if (!report.passed) process.exitCode = 1
