import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const dir = path.resolve(process.env.FILEMATE_EVIDENCE_DIR || '_working/v2-4-20261001')
assert.ok(dir.startsWith(path.join(process.cwd(), '_working') + path.sep))
fs.mkdirSync(dir, { recursive: true })
const fixture = path.resolve(process.env.FILEMATE_FACE_FIXTURE || '_working/v2-4-20261001/astronaut.png')
const base = process.env.FILEMATE_WEB_URL || 'http://127.0.0.1:5186', api = process.env.FILEMATE_API_URL || 'http://127.0.0.1:8014'
const injectFailure = process.env.FILEMATE_INJECT_BITMAP_FAILURE === '1'
const sameOrigin = process.env.FILEMATE_SAME_ORIGIN_ACCEPTANCE === '1'
const requireCsp = process.env.FILEMATE_REQUIRE_PRODUCTION_CSP === '1'
if (sameOrigin) assert.equal(api, base, 'same-origin acceptance must use the real gateway for all API calls')
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || 'msedge', headless: true })
const gatewayUser = process.env.FILEMATE_ACCEPTANCE_GATEWAY_USER
const gatewayPassword = process.env.FILEMATE_ACCEPTANCE_GATEWAY_PASSWORD
assert.equal(Boolean(gatewayUser), Boolean(gatewayPassword), 'both gateway test credentials are required')
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 },
  ...(gatewayUser ? { httpCredentials: { username: gatewayUser, password: gatewayPassword } } : {}) })
const errors = [], requests = [], logs = []
await context.addInitScript(({ dataUrl, injectFailure }) => {
  window.__captureErrors = []
  window.__failCaptureOnce = injectFailure
  const bitmap = window.createImageBitmap.bind(window)
  window.createImageBitmap = async (...args) => { try { if (window.__failCaptureOnce) { window.__failCaptureOnce = false; throw new DOMException('Synthetic allocation failure', 'InvalidStateError') }; return await bitmap(...args) } catch (error) { window.__captureErrors.push(String(error)); throw error } }
  const post = Worker.prototype.postMessage
  Worker.prototype.postMessage = function(...args) { try { return post.apply(this, args) } catch (error) { window.__captureErrors.push(String(error)); throw error } }
  const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 480
  const draw = canvas.getContext('2d'), image = new Image(); image.src = dataUrl
  setInterval(() => { draw.fillStyle = '#b0b0b0'; draw.fillRect(0, 0, 640, 480); if (image.complete) draw.drawImage(image, 80, 0, 480, 480) }, 50)
  navigator.mediaDevices.getUserMedia = async constraints => {
    if (constraints.video) return canvas.captureStream(20)
    throw new DOMException('Synthetic audio unavailable', 'NotFoundError')
  }
}, { dataUrl: 'data:image/png;base64,' + fs.readFileSync(fixture).toString('base64'), injectFailure })
// Relative API calls are relayed to the isolated test backend; built model assets stay untouched.
if (!sameOrigin) await context.route(base + '/**', async route => {
  const request = route.request(), url = new URL(request.url())
  if (['fetch', 'xhr'].includes(request.resourceType()) && !url.pathname.startsWith('/interview-vision/') && !url.pathname.startsWith('/assets/')) {
    return route.fulfill({ response: await context.request.fetch(api + url.pathname + url.search, { method: request.method(), data: request.postData(), headers: { 'Content-Type': 'application/json' } }) })
  }
  return route.continue()
})
const page = await context.newPage()
page.on('pageerror', error => errors.push(String(error)))
page.on('request', request => requests.push(request.url()))
page.on('console', message => logs.push(message.type() + ': ' + message.text()))
let createdInterviewId
try {
  const created = await context.request.post(api + '/interviews', { data: { target_role: '生产包合成观察验收', allow_external_analysis: false } })
  const createdBody = await created.json()
  assert.equal(created.status(), 200, JSON.stringify(createdBody))
  assert.equal(createdBody.success, true, JSON.stringify(createdBody))
  const id = createdInterviewId = createdBody.data.interview_id
  const navigation = await page.goto(base + '/interview?interview=' + id)
  const productionCsp = navigation.headers()['content-security-policy'] || ''
  if (requireCsp) assert.ok(productionCsp.includes("'wasm-unsafe-eval'"), 'actual gateway CSP must allow local WASM')
  await page.getByRole('heading', { name: '面试复盘报告', exact: true }).waitFor()
  await page.getByRole('button', { name: '开启摄像头', exact: true }).click()
  await page.getByRole('button', { name: '开启本地视觉观察', exact: true }).click()
  await page.getByText('本地视觉已就绪，开始录像后采集观察。', { exact: true }).waitFor({ timeout: 40000 })
  assert.equal(await page.locator('.camera-preview video').evaluate(video => video.paused), false)
  await page.getByRole('button', { name: '开始本地录像（含声音）', exact: true }).click()
  await page.getByText('正在记录可观察动作，不推断心理状态。', { exact: true }).waitFor({ timeout: 20000 })
  await page.waitForTimeout(1600)
  await page.getByRole('button', { name: /^停止本地录像/ }).click()
  await page.getByRole('textbox', { name: '当前训练回答', exact: true }).fill('首先复述问题，再给出背景、任务、行动和结果，结合索引案例解释边界。')
  const response = page.waitForResponse(r => r.url().endsWith('/interviews/' + id + '/answers') && r.request().method() === 'POST')
  await page.getByRole('button', { name: '提交并进入下一题', exact: true }).click()
  const answered = await response
  const payload = await answered.json()
  assert.equal(answered.status(), 200, JSON.stringify(payload))
  assert.equal(payload.success, true, JSON.stringify(payload))
  const result = payload.data
  assert.ok(result.turns[0].visual_metrics.face_samples > 0)
  assert.equal(errors.length, 0)
  assert.ok(requests.some(url => /assets\/vision.worker-/.test(url)))
  assert.ok(requests.filter(url => url.includes('/interview-vision/')).every(url => url.startsWith(base)))
  const captureErrors = await page.evaluate(() => window.__captureErrors)
  if (injectFailure) assert.ok(captureErrors.some(error => error.includes('Synthetic allocation failure')))
  fs.writeFileSync(path.join(dir, 'production-summary.json'), JSON.stringify({ passed: 4, total: 4, errors, inject_bitmap_failure: injectFailure, captureErrors, same_origin_gateway: sameOrigin, csp: productionCsp, sample_kind: 'synthetic_production_runtime_regression', evidence_kind: 'production build, synthetic canvas input and denied microphone, real local CPU inference and recorder, ' + (sameOrigin ? 'real same-origin authenticated gateway without API relay' : 'isolated API relay'), visual: result.turns[0].visual_metrics, assets: requests.filter(url => url.includes('interview-vision') || url.includes('vision.worker')) }, null, 2))
  console.log('PRODUCTION 4/4 JS_ERRORS 0')
} catch (error) {
  await page.screenshot({ path: path.join(dir, 'production-failure.png') })
  fs.writeFileSync(path.join(dir, 'production-failure.json'), JSON.stringify({ error: String(error), errors, requests, logs, captureErrors: await page.evaluate(() => window.__captureErrors), video: await page.locator('video').first().evaluate(v => ({ ready: v.readyState, width: v.videoWidth, height: v.videoHeight })), body: await page.locator('body').innerText() }, null, 2))
  throw error
} finally {
  try {
    if (createdInterviewId) {
      const preview = await context.request.get(api + '/interviews/' + createdInterviewId + '/delete-preview')
      const previewBody = await preview.json()
      assert.equal(preview.status(), 200, JSON.stringify(previewBody))
      const deleted = await context.request.delete(api + '/interviews/' + createdInterviewId, {
        data: { confirmed: true, confirmation_token: previewBody.data.confirmation_token },
      })
      const deletedBody = await deleted.json()
      assert.equal(deleted.status(), 200, JSON.stringify(deletedBody))
      assert.equal(deletedBody.data.deleted, true)
      fs.writeFileSync(path.join(dir, 'synthetic-cleanup.json'), JSON.stringify({
        sample_kind: 'owned_synthetic_acceptance_record', preview_confirmed: true, deleted: true,
      }, null, 2))
    }
  } catch (error) {
    console.error('Synthetic acceptance record cleanup failed:', String(error))
    process.exitCode = 1
  } finally { await browser.close() }
}
