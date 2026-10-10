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
const directGateway = process.env.FILEMATE_PRODUCTION_GATEWAY === '1'
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 },
  ignoreHTTPSErrors: process.env.FILEMATE_ACCEPTANCE_INSECURE_TLS === '1',
  ...(directGateway ? { httpCredentials: { username: process.env.FILEMATE_ACCEPTANCE_BASIC_USER, password: process.env.FILEMATE_ACCEPTANCE_BASIC_PASSWORD } } : {}),
})
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
if (!directGateway) await context.route(base + '/**', async route => {
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
try {
  const created = await context.request.post(api + '/interviews', { data: { target_role: '生产包合成观察验收', allow_external_analysis: false } })
  const id = (await created.json()).data.interview_id
  await page.goto(base + '/interview?interview=' + id)
  await page.getByRole('heading', { name: '面试复盘报告', exact: true }).waitFor()
  await page.getByRole('button', { name: '开启摄像头', exact: true }).click()
  await page.getByRole('button', { name: '开启本地视觉观察', exact: true }).click()
  await page.getByRole('heading', { name: '实时面部动作', exact: true }).waitFor({ timeout: 40000 })
  await page.getByText('已检测到人脸', { exact: true }).waitFor({ timeout: 20000 })
  assert.equal(await page.locator('.live-face meter').count(), 3)
  const liveValues = await page.locator('.live-face meter').evaluateAll(meters => meters.map(meter => meter.value))
  assert.ok(liveValues.every(value => Number.isFinite(value) && value >= 0 && value <= 100))
  await page.screenshot({ path: path.join(dir, 'live-face-before-recording.png') })
  assert.equal(await page.locator('.camera-preview video').evaluate(video => video.paused), false)
  await page.getByRole('button', { name: '开始本地录像（含声音）', exact: true }).click()
  await page.getByText('正在记录可观察动作，不推断心理状态。', { exact: true }).waitFor({ timeout: 20000 })
  await page.waitForTimeout(1600)
  await page.getByRole('button', { name: /^停止本地录像/ }).click()
  await page.getByRole('textbox', { name: '当前训练回答', exact: true }).fill('首先复述问题，再给出背景、任务、行动和结果，结合索引案例解释边界。')
  const response = page.waitForResponse(r => r.url().endsWith('/interviews/' + id + '/answers') && r.request().method() === 'POST')
  await page.getByRole('button', { name: '提交并进入下一题', exact: true }).click()
  const result = (await (await response).json()).data
  assert.ok(result.turns[0].visual_metrics.face_samples > 0)
  assert.equal('jaw' in result.turns[0].visual_metrics, false)
  assert.equal('brow' in result.turns[0].visual_metrics, false)
  await page.getByRole('button', { name: '关闭摄像头', exact: true }).click()
  assert.equal(await page.locator('.live-face').count(), 0)
  assert.equal(errors.length, 0)
  assert.ok(requests.some(url => /assets\/vision.worker-/.test(url)))
  assert.ok(requests.filter(url => url.includes('/interview-vision/')).every(url => url.startsWith(base)))
  const captureErrors = await page.evaluate(() => window.__captureErrors)
  if (injectFailure) assert.ok(captureErrors.some(error => error.includes('Synthetic allocation failure')))
  fs.writeFileSync(path.join(dir, 'production-summary.json'), JSON.stringify({ passed: 4, total: 4, errors, inject_bitmap_failure: injectFailure, captureErrors, evidence_kind: directGateway ? 'production build through actual TLS Caddy and same-origin API, no request relay; synthetic canvas and denied microphone, real local inference and recorder' : 'production build, synthetic canvas input and denied microphone, real local CPU inference and recorder, isolated API relay', visual: result.turns[0].visual_metrics, assets: requests.filter(url => url.includes('interview-vision') || url.includes('vision.worker')) }, null, 2))
  console.log('PRODUCTION 4/4 JS_ERRORS 0')
} catch (error) {
  await page.screenshot({ path: path.join(dir, 'production-failure.png') })
  fs.writeFileSync(path.join(dir, 'production-failure.json'), JSON.stringify({ error: String(error), errors, requests, logs, captureErrors: await page.evaluate(() => window.__captureErrors), video: await page.locator('video').first().evaluate(v => ({ ready: v.readyState, width: v.videoWidth, height: v.videoHeight })), body: await page.locator('body').innerText() }, null, 2))
  throw error
} finally { await browser.close() }
