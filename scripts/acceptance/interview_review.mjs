import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const root = process.cwd()
const base = process.env.FILEMATE_WEB_URL || 'http://127.0.0.1:5184'
const api = process.env.FILEMATE_API_URL || 'http://127.0.0.1:8014'
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR || '_working/v2-4-20261001/ui')
assert.ok(out.startsWith(path.join(root, '_working') + path.sep))
fs.mkdirSync(out, { recursive: true })
const fixture = path.resolve(process.env.FILEMATE_FACE_FIXTURE || '_working/v2-4-20261001/astronaut.png')
const dataUrl = 'data:image/png;base64,' + fs.readFileSync(fixture).toString('base64')
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true })
await context.addInitScript(({ dataUrl }) => {
  window.__cameraDenied = true
  window.__cameraMode = 'face'
  window.__tracks = []
  const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 480
  const drawing = canvas.getContext('2d')
  const image = new Image(); image.src = dataUrl
  setInterval(() => {
    drawing.fillStyle = window.__cameraMode === 'dark' ? '#080808' : '#b0b0b0'
    drawing.fillRect(0, 0, 640, 480)
    if (window.__cameraMode === 'face' && image.complete) drawing.drawImage(image, 80, 0, 480, 480)
  }, 50)
  navigator.mediaDevices.getUserMedia = async constraints => {
    if (constraints.video) {
      if (window.__cameraDenied) throw new DOMException('Synthetic device unavailable', 'NotFoundError')
      const stream = canvas.captureStream(20)
      window.__tracks.push(...stream.getTracks())
      return stream
    }
    const audio = new AudioContext(); const oscillator = audio.createOscillator(); const gain = audio.createGain(); gain.gain.value = 0
    const destination = audio.createMediaStreamDestination(); oscillator.connect(gain); gain.connect(destination); oscillator.start()
    window.__tracks.push(...destination.stream.getTracks())
    return destination.stream
  }
  window.SpeechRecognition = class {
    start() { window.__recognition = this; setTimeout(() => this.onstart?.(), 0) }
    stop() { this.onend?.() }
  }
  window.__speechResult = text => window.__recognition?.onresult?.({ results: [[{ transcript: text }]] })
}, { dataUrl })
const page = await context.newPage()
page.setDefaultTimeout(15000)
const errors = [], requests = [], results = []
page.on('pageerror', e => errors.push(String(e)))
page.on('request', request => requests.push({ url: request.url(), method: request.method(), body: request.postData() }))
const button = name => page.getByRole('button', { name, exact: true })
let id, firstTurn, firstReport
async function check(name, kind, run) {
  console.log('RUN', name)
  try { const evidence = await run(); results.push({ name, kind, passed: true, evidence }); console.log('PASS', name) }
  catch (error) { results.push({ name, kind, passed: false, error: String(error) }); console.log('FAIL', name, String(error)); await page.screenshot({ path: path.join(out, 'failure-' + results.length + '.png'), fullPage: true }) }
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 2))
}
const stored = async () => (await (await context.request.get(api + '/interviews/' + id)).json()).data
async function submit(text) {
  await page.getByRole('textbox', { name: '当前训练回答', exact: true }).fill(text)
  const responsePromise = page.waitForResponse(response => response.url() === api + '/interviews/' + id + '/answers' && response.request().method() === 'POST')
  await button('提交并进入下一题').click()
  const response = await responsePromise
  assert.equal(response.status(), 200)
  const data = (await response.json()).data
  await page.getByText(`第 ${Math.min(data.current_index + 1, 5)} / 5 题`, { exact: true }).waitFor()
  return data
}
try {
  await check('open original interview and create local session without external calls', 'real_ui_api', async () => {
    await page.goto(base + '/interview')
    await page.getByLabel('训练主题或目标方向').fill('后端项目表达训练')
    await page.getByLabel('训练场景').selectOption('求职面试')
    const response = page.waitForResponse(r => r.url() === api + '/interviews' && r.request().method() === 'POST')
    await button('开始模拟面试').click()
    const created = await response
    assert.equal(created.request().postDataJSON().allow_external_analysis, false)
    id = (await created.json()).data.interview_id
    await page.getByRole('heading', { name: '面试复盘报告', exact: true }).waitFor()
    assert.equal(await button('生成规则复盘报告').isDisabled(), true)
    assert.equal(await button('提交并进入下一题').isDisabled(), true)
    return { interview_id: id }
  })
  await check('no camera permission retains text training', 'device_failure_injection_real_ui', async () => {
    await button('开启摄像头').click()
    await page.getByText('当前无法访问摄像头，将跳过视频分析；可继续文字或语音回答。', { exact: true }).waitFor()
    assert.equal(await page.getByRole('textbox', { name: '当前训练回答' }).isEditable(), true)
    assert.equal(await button('开始本地录像（含声音）').isDisabled(), true)
  })
  await check('local camera and model retry loads only same-origin assets', 'canvas_device_real_local_model', async () => {
    await page.evaluate(() => { window.__cameraDenied = false })
    await button('开启摄像头').click()
    await button('关闭摄像头').waitFor()
    await button('开启本地视觉观察').click()
    await page.getByRole('heading', { name: '实时面部动作', exact: true }).waitFor({ timeout: 40000 })
    assert.ok(requests.some(r => r.url.includes('face_landmarker.task')))
    assert.ok(requests.filter(r => r.url.includes('interview-vision')).every(r => r.url.startsWith(base)))
  })
  await check('real face inference and observable low-light and absence timeline during actual recording', 'real_mediapipe_canvas_pixels_mediarecorder', async () => {
    await button('开始本地录像（含声音）').click()
    await page.getByText('正在记录可观察动作，不推断心理状态。', { exact: true }).waitFor({ timeout: 20000 })
    await page.waitForTimeout(1600)
    await button('语音回答').click()
    await button('停止录音').waitFor()
    await page.evaluate(() => window.__speechResult('嗯，首先分析项目背景，因为需要支持范围查询，例如使用有序索引。'))
    await page.waitForTimeout(2800)
    await page.evaluate(() => window.__speechResult('嗯，首先分析项目背景，因为需要支持范围查询，例如使用有序索引。然后呢，验证条件并记录结果。'))
    await button('停止录音').click()
    await button('语音回答').waitFor()
    await page.evaluate(() => { window.__cameraMode = 'dark' })
    await page.getByText('当前视频质量较低，视觉观察可信度可能下降。', { exact: true }).waitFor()
    await page.waitForTimeout(2400)
    await page.evaluate(() => { window.__cameraMode = 'blank' })
    await page.getByText('当前未检测到稳定人脸，可检查镜头位置。', { exact: true }).waitFor()
    await page.waitForTimeout(2400)
    await page.getByRole('button', { name: /^停止本地录像/ }).click()
    await button('开始本地录像（含声音）').waitFor()
    const data = await submit('嗯，首先分析项目背景，因为需要支持范围查询，例如使用有序索引。然后呢，验证条件并记录结果。')
    firstTurn = data.turns[0]
    assert.ok(firstTurn.visual_metrics.face_samples > 0)
    assert.ok(firstTurn.visual_metrics.low_light_samples > 0)
    assert.ok(firstTurn.visual_metrics.events.some(e => e.kind === 'no_face'))
    assert.ok(firstTurn.visual_metrics.events.some(e => e.kind === 'low_light'))
    assert.equal(firstTurn.visual_metrics.timeline_origin, 'recording')
    assert.ok(firstTurn.fluency_metrics.recording_offset_seconds >= 0)
    assert.ok(firstTurn.fluency_metrics.long_pause_count > 0)
    assert.ok(await page.locator('#interview-replay-0').evaluate(video => video.readyState >= 1))
    assert.equal(firstTurn.score, null)
    return { visual: firstTurn.visual_metrics, speech: firstTurn.fluency_metrics, note: 'speech recognition callbacks injected; actual local video recording and visual model' }
  })
  await check('generate persistent report and seek synchronized local video', 'real_ui_api_video', async () => {
    await button('生成规则复盘报告').click()
    await button('更新规则复盘报告').waitFor()
    firstReport = (await (await context.request.get(api + '/interviews/' + id + '/review')).json()).data.report
    assert.equal(firstReport.visual.sample_count, firstTurn.visual_metrics.sample_count)
    assert.equal(firstReport.assessed, 0)
    const event = firstReport.timeline.find(e => e.kind === 'low_light')
    const replayButton = page.locator('.report-timeline button').filter({ hasText: '画面亮度偏低' }).first()
    assert.equal(await replayButton.isEnabled(), true)
    await replayButton.click()
    await page.waitForFunction(second => document.querySelector('#interview-replay-0')?.currentTime >= second - .1, event.start)
    assert.equal(await page.getByText('薄弱知识点待评估，不由回答长度或面部动作推断。', { exact: true }).count(), 1)
  })
  await check('download real local video and all three report formats', 'real_downloads', async () => {
    const names = []
    for (const name of ['下载本地录像', '导出 PDF', '导出 JSON', '导出 Markdown']) {
      const pending = page.waitForEvent('download')
      await button(name).click()
      const download = await pending
      const filename = download.suggestedFilename(); await download.saveAs(path.join(out, filename)); names.push(filename)
      assert.ok(fs.statSync(path.join(out, filename)).size > 200)
    }
    assert.ok(fs.readFileSync(path.join(out, names.find(name => name.endsWith('.pdf')))).subarray(0, 4).equals(Buffer.from('%PDF')))
    assert.equal(JSON.parse(fs.readFileSync(path.join(out, names.find(name => name.endsWith('.json'))), 'utf8')).interview_id, id)
    return { files: names }
  })
  await check('network retry preserves one submission after server accepted but response lost', 'network_failure_injection_real_api_idempotency', async () => {
    let once = true
    await page.route(api + '/interviews/' + id + '/answers', async route => {
      if (!once) return route.continue()
      once = false
      const response = await route.fetch(); assert.equal(response.status(), 200)
      await route.abort('failed')
    })
    await page.getByRole('textbox', { name: '当前训练回答' }).fill('先明确需求，再验证方案与边界，最后对照测试结果复盘。')
    await button('提交并进入下一题').click()
    await page.waitForFunction(() => !document.querySelector('.answer-actions .primary')?.disabled)
    assert.equal((await stored()).current_index, 2)
    await button('提交并进入下一题').click()
    await page.getByText('第 3 / 5 题', { exact: true }).waitFor()
    assert.equal((await stored()).turns.length, 2)
    await page.unroute(api + '/interviews/' + id + '/answers')
  })
  await check('finish all original interview questions and refresh report from actual records', 'real_ui_api', async () => {
    for (let i = 2; i < 5; i++) await submit('首先说明情境和任务，然后描述行动，因为需要核对依据，例如验证样例，最后总结结果和边界。')
    await page.getByText('本轮训练完成', { exact: true }).waitFor()
    await button('生成规则复盘报告').click()
    await button('更新规则复盘报告').waitFor()
    const report = (await (await context.request.get(api + '/interviews/' + id + '/review')).json()).data.report
    assert.equal(report.answered, 5); assert.equal(report.status, 'completed'); assert.equal(report.overall_score, null)
    return { answered: 5, assessed: 0 }
  })
  await check('model API failure keeps answers rhythm and generated report', 'model_failure_injection_ui', async () => {
    await page.route(api + '/interviews/' + id + '/turns/**/analyze', route => route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ success: false, error: '模型分析暂不可用；原回答、节奏与报告保留' }) }))
    await page.locator('.consent input').check()
    await button('分析这一题的内容').click()
    await page.getByRole('alert').filter({ hasText: '模型分析暂不可用' }).waitFor()
    assert.equal((await stored()).turns.length, 5)
    assert.equal(await button('导出 PDF').isEnabled(), true)
    await page.unroute(api + '/interviews/' + id + '/turns/**/analyze')
  })
  await check('report read failure shows retry while earlier evidence stays visible', 'read_failure_injection_ui', async () => {
    await page.route(api + '/interviews/' + id + '/review', route => route.request().method() === 'GET' ? route.abort('failed') : route.continue())
    await button('刷新报告').click()
    await page.locator('.report-error').filter({ hasText: /Network|网络/ }).waitFor()
    assert.equal(await button('导出 JSON').isEnabled(), true)
    await page.unroute(api + '/interviews/' + id + '/review')
    await button('刷新报告').click()
    await page.waitForFunction(() => !document.querySelector('.report-error'))
  })
  await check('responsive report and original camera release on navigation', 'real_ui_layout_lifecycle', async () => {
    await page.waitForFunction(() => !document.querySelector('.el-message'))
    for (const width of [375, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 1000 })
      await page.waitForTimeout(500)
      await page.locator('#interview-report-title').evaluate(element => element.scrollIntoView({ block: 'start' }))
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), true)
      await page.screenshot({ path: path.join(out, 'report-' + width + '.png') })
      await page.locator('.content-scroll').evaluate(element => { element.scrollTop = 0 })
      await page.screenshot({ path: path.join(out, 'interview-' + width + '.png') })
    }
    await page.locator('a[href="/growth"]').first().click()
    await page.waitForFunction(() => window.__tracks.every(track => track.readyState === 'ended'))
  })
  await check('page refresh restores records report and timeline without video or automatic camera', 'real_persistence_privacy', async () => {
    await page.goto(base + '/interview?interview=' + id)
    await button('更新规则复盘报告').waitFor()
    assert.equal(await page.locator('.local-replay video').count(), 0)
    assert.equal(await button('开启摄像头').isVisible(), true)
    assert.ok((await stored()).turns[0].visual_metrics.sample_count > 0)
    assert.ok(await page.locator('.report-timeline button:disabled').count() > 0)
  })
  await check('clear analysis preview cancellation then confirmed clearing retains raw answers and rhythm', 'real_ui_api_privacy', async () => {
    await button('清空本场分析').click(); await button('保留分析').click()
    assert.ok((await stored()).turns[0].visual_metrics.sample_count > 0)
    await button('清空本场分析').click(); await button('确认清空').click()
    await button('生成规则复盘报告').waitFor()
    const record = await stored()
    assert.equal(record.turns.length, 5)
    assert.ok(record.turns[0].fluency_metrics.long_pause_count > 0)
    assert.deepEqual(record.turns[0].visual_metrics, {})
  })
  await check('delete preview cancel then delete removes only selected practice', 'real_ui_api_privacy', async () => {
    await button('删除本场练习').click(); await button('保留练习').click()
    assert.equal((await context.request.get(api + '/interviews/' + id)).status(), 200)
    await button('删除本场练习').click(); await button('确认删除本场练习').click()
    await button('开始模拟面试').waitFor()
    assert.equal((await context.request.get(api + '/interviews/' + id)).status(), 404)
  })
} finally {
  const summary = { passed: results.filter(r => r.passed).length, total: results.length, errors, results,
    evidence_kind: 'synthetic engineering regression, public-domain NASA/scikit-image image, real local model and video recorder, injected device/speech/network/model failures',
    external_media_requests: requests.filter(r => /^https?:/.test(r.url) && !r.url.startsWith(base) && !r.url.startsWith(api)),
    media_uploads: requests.filter(r => r.method === 'POST' && (r.body || '').includes('base64')) }
  fs.writeFileSync(path.join(out, 'summary.json'), JSON.stringify(summary, null, 2))
  console.log('SUMMARY', summary.passed, '/', summary.total, 'JS_ERRORS', errors.length)
  await browser.close()
  if (summary.passed !== summary.total || errors.length || summary.external_media_requests.length || summary.media_uploads.length) process.exitCode = 1
}
