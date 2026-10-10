import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import fs from 'node:fs'
import path from 'node:path'

const base = process.env.FILEMATE_WEB_URL || 'http://127.0.0.1:5173'
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR || '_working/natural-voice-acceptance')
fs.mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ channel: process.platform === 'win32' ? 'msedge' : undefined, headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
await context.request.get(base + '/api/auth/me')
const page = await context.newPage()
const results = [], pageErrors = []
page.on('pageerror', error => pageErrors.push(String(error)))
page.setDefaultTimeout(15000)
const button = name => page.getByRole('button', { name, exact: true })
const consent = () => page.getByRole('checkbox', { name: /允许将本次讲解正文/ })
async function waitState(value, timeout = 25000) {
  await page.waitForFunction(value => document.querySelector('.state-badge')?.dataset.state === value, value, { timeout })
}
async function check(name, kind, run) {
  console.log(`RUN ${name}`)
  try { results.push({ name, kind, passed: true, evidence: await run() }); console.log(`PASS ${name}`) }
  catch (error) { results.push({ name, kind, passed: false, error: String(error) }); await page.screenshot({ path: path.join(out, `failure-${results.length}.png`) }).catch(() => {}); console.log(`FAIL ${name}: ${error}`) }
}
async function open() { await page.goto(base + '/digital-human'); await page.locator('#lecture-text').waitFor() }
async function fill(text) { await page.locator('#lecture-text').fill(text); await consent().check() }
try {
  await check('responsive layout, curated defaults, and explicit consent', 'real_ui', async () => {
    for (const width of [375, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 }); await open()
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
      await page.screenshot({ path: path.join(out, `mentor-${width}.png`), fullPage: true })
    }
    assert.equal(await page.getByLabel('声音', { exact: true }).inputValue(), 'zh-CN-XiaoxiaoNeural')
    assert.equal(await page.getByLabel('声音', { exact: true }).locator('option').count(), 4)
    await page.locator('#lecture-text').fill('今天学习栈。')
    let calls = 0
    const listener = request => { if (request.url().endsWith('/speech')) calls++ }
    page.on('request', listener); await button('开始讲解').click()
    await page.getByRole('alert').filter({ hasText: '请先允许' }).waitFor(); page.off('request', listener)
    assert.equal(calls, 0)
    return { widths: [375, 768, 1440], default: 'Xiaoxiao', voices: 4, consent_required: true }
  })
  await check('Xiaoxiao actual synthesis and 50-character audio completes', 'real_tts', async () => {
    await open(); await fill('这道题考察二叉树遍历。请先理解前序与中序的访问顺序，再结合例子核对每一步，最后独立练习并复盘。'.padEnd(50, '学').slice(0, 50))
    const pending = page.waitForResponse(r => r.url().endsWith('/speech') && r.request().method() === 'POST', { timeout: 65000 })
    await button('开始讲解').click()
    const response = await pending
    assert.equal(response.status(), 200); assert.match(response.headers()['content-type'], /audio\/mpeg/)
    const bytes = (await response.body()).length; assert.ok(bytes > 1000)
    await waitState('playing'); await page.screenshot({ path: path.join(out, 'xiaoxiao-playing.png'), fullPage: true })
    await waitState('completed', 65000)
    return { voice: 'zh-CN-XiaoxiaoNeural', actual_audio_bytes: bytes, completed: true }
  })
  await check('Yunxia 500-character playback, animation, pause, resume, replay and stop', 'real_tts', async () => {
    await open(); await fill('理解栈的后进先出规律。把每次入栈和出栈画出来，再核对程序运行结果。'.repeat(20).slice(0, 500))
    await page.getByLabel('声音', { exact: true }).selectOption('zh-CN-YunxiaNeural')
    await button('开始讲解').click(); await waitState('playing', 65000)
    const frames = []
    for (let i = 0; i < 6; i++) { frames.push(await page.locator('.lip-motion').evaluate(el => getComputedStyle(el).transform)); await page.waitForTimeout(110) }
    assert.ok(new Set(frames).size > 2)
    await button('暂停').click(); await waitState('paused')
    assert.equal(await page.locator('.lip-motion').evaluate(el => getComputedStyle(el).animationName), 'none')
    await button('继续').click(); await waitState('playing')
    await page.emulateMedia({ reducedMotion: 'reduce' })
    assert.equal(await page.locator('.lip-motion').evaluate(el => getComputedStyle(el).animationName), 'none')
    await page.emulateMedia({ reducedMotion: 'no-preference' })
    await waitState('completed', 240000)
    await button('重播').click(); await waitState('playing', 65000)
    await button('停止').click(); await waitState('stopped')
    return { voice: 'zh-CN-YunxiaNeural', characters: 500, distinct_animation_frames: new Set(frames).size, completed: true, replay_stop: true }
  })
  await check('upstream failure preserves text and does not use robotic fallback', 'synthetic_fault_injection', async () => {
    await open(); await fill('这是故障模拟，正文应保留。')
    await page.route('**/api/digital-human/speech', route => route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ detail: 'Microsoft 自然语音暂不可用，请稍后重试' }) }))
    await button('开始讲解').click(); await waitState('failed')
    assert.match(await page.getByRole('alert').innerText(), /自然语音暂不可用/)
    assert.equal(await page.locator('#lecture-text').inputValue(), '这是故障模拟，正文应保留。')
    assert.equal(await page.evaluate(() => speechSynthesis.speaking), false)
    assert.equal(await page.locator('.lip-motion').evaluate(el => getComputedStyle(el).animationName), 'none')
    await page.unroute('**/api/digital-human/speech')
    return { no_device_fallback: true, text_preserved: true }
  })
  await check('playback metadata is private, deletable and restorable', 'real_api', async () => {
    const response = await context.request.get(base + '/api/digital-human/playbacks')
    const records = (await response.json()).data
    assert.ok(records.length >= 3)
    assert.equal(records.some(record => 'text' in record || 'audio' in record), false)
    assert.equal(records.some(record => record.provider === 'microsoft_edge' && record.status === 'completed'), true)
    const id = records[0].playback_id
    assert.equal((await context.request.delete(base + '/api/digital-human/playbacks/' + id)).status(), 200)
    assert.equal((await context.request.post(base + '/api/digital-human/playbacks/' + id + '/restore')).status(), 200)
    return { completed_records: records.filter(record => record.status === 'completed').length, minimal_metadata: true }
  })
} finally {
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify({ generated_at: new Date().toISOString(), sample_kind: 'synthetic_engineering_regression_with_real_microsoft_tts', passed: results.every(r => r.passed) && !pageErrors.length, results, pageErrors, limitation: 'Real MP3 decoding and browser playback events do not constitute human listening quality evaluation or phoneme-level lip alignment.' }, null, 2))
  await browser.close()
}
if (results.some(result => !result.passed) || pageErrors.length) process.exitCode = 1
