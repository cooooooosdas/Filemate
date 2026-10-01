import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import fs from 'node:fs'
import path from 'node:path'

const base = process.env.FILEMATE_WEB_URL || 'http://127.0.0.1:5173'
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR || '_working/v2-1-acceptance')
fs.mkdirSync(out, { recursive: true })
const browser = await chromium.launch({
  channel: process.env.FILEMATE_BROWSER_CHANNEL || (process.platform === 'win32' ? 'msedge' : undefined), headless: true,
  args: ['--autoplay-policy=no-user-gesture-required'],
})
const results = []
const caseFilter = process.env.FILEMATE_CASE_FILTER ? new RegExp(process.env.FILEMATE_CASE_FILTER) : null
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
const page = await context.newPage()
page.setDefaultTimeout(10000)
const pageErrors = []
page.on('pageerror', error => pageErrors.push(String(error)))

async function check(name, kind, run) {
  if (caseFilter && !caseFilter.test(name)) return
  console.log(`RUN ${name} (${kind})`)
  try {
    const evidence = await run()
    results.push({ name, kind, passed: true, evidence })
    console.log(`PASS ${name} (${kind})`)
  } catch (error) {
    results.push({ name, kind, passed: false, error: String(error) })
    console.log(`FAIL ${name}: ${error}`)
  }
}
async function open(target = '/digital-human') {
  await page.goto(base + target)
  await page.locator('#lecture-text').waitFor()
}
const state = () => page.locator('.state-badge')
async function waitState(value, timeout = 20000) {
  await page.waitForFunction(value => document.querySelector('.state-badge')?.dataset.state === value, value, { timeout })
}
const button = name => page.getByRole('button', { name, exact: true })

try {
  await check('responsive stage and visible controls', 'real_ui', async () => {
    const sizes = []
    for (const width of [375, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 1000 })
      await open()
      const geometry = await page.evaluate(() => {
        const stage = document.querySelector('.mentor-stage').getBoundingClientRect()
        const panel = document.querySelector('.mentor-panel').getBoundingClientRect()
        return {
          overflow: document.documentElement.scrollWidth > innerWidth,
          inside: panel.left >= stage.left && panel.right <= stage.right && panel.top >= stage.top && panel.bottom <= stage.bottom,
        }
      })
      assert.equal(geometry.overflow, false)
      assert.equal(geometry.inside, true)
      await page.screenshot({ path: path.join(out, `mentor-${width}.png`), fullPage: true })
      sizes.push({ width, ...geometry })
    }
    await page.getByLabel('形象', { exact: true }).selectOption('filemate-campus')
    await page.locator('.campus-image img').waitFor()
    await button('收起数字人').click()
    await button('展开导师').click()
    await page.getByLabel('显示字幕').uncheck()
    assert.match(await page.locator('.mentor-caption').innerText(), /字幕已关闭/)
    await page.getByLabel('显示字幕').check()
    await button('全屏').click()
    assert.equal(await page.evaluate(() => !!document.fullscreenElement), true)
    await button('退出全屏').click()
    return sizes
  })

  await check('50 characters synthesize with native browser speech events', 'real_tts', async () => {
    await open()
    const text = '这道题考察二叉树遍历。请先理解前序与中序的访问顺序，再结合例子核对每一步，最后独立练习并复盘。'.padEnd(50, '学').slice(0, 50)
    await page.locator('#lecture-text').fill(text)
    await button('开始讲解').click()
    await waitState('playing')
    const during = await page.evaluate(() => ({
      speaking: speechSynthesis.speaking,
      voices: speechSynthesis.getVoices().filter(voice => voice.lang.startsWith('zh')).map(voice => ({ name: voice.name, local: voice.localService })),
      mouth: document.querySelector('.mentor-art').classList.contains('talking'),
    }))
    assert.equal(during.speaking, true)
    assert.equal(during.mouth, true)
    await page.screenshot({ path: path.join(out, 'mentor-speaking.png'), fullPage: true })
    await waitState('completed', 60000)
    return { characters: text.length, ...during, completion: await state().innerText() }
  })

  await check('500 characters pause/resume/replay/stop on native speech', 'real_tts', async () => {
    await open()
    await page.locator('#lecture-text').fill('请先理解二叉树遍历，再结合示例核对访问顺序。'.repeat(30).slice(0, 500))
    await button('开始讲解').click()
    await waitState('playing')
    await button('暂停').click()
    await waitState('paused')
    assert.equal(await page.evaluate(() => speechSynthesis.paused), true)
    await button('继续').click()
    await waitState('playing')
    assert.equal(await page.evaluate(() => speechSynthesis.paused), false)
    await waitState('completed', 240000)
    await button('重播').click()
    await waitState('playing')
    await button('暂停').click()
    await button('重播').click()
    await waitState('playing')
    assert.equal(await page.evaluate(() => speechSynthesis.paused), false)
    await button('停止').click()
    await waitState('stopped')
    assert.equal(await page.evaluate(() => speechSynthesis.speaking), false)
    return { characters: 500, stopped: true }
  })

  await check('saved answer reloads when only query changes', 'real_api_ui', async () => {
    await open('/digital-human?ctx=v2-1-acceptance&message=0')
    await page.waitForFunction(() => document.querySelector('#lecture-text').value === '合成测试回答一：前序遍历先访问根节点，再遍历左右子树。')
    await page.evaluate(() => {
      history.pushState(null, '', '/digital-human?ctx=v2-1-acceptance&message=1')
      dispatchEvent(new PopStateEvent('popstate'))
    })
    await page.waitForFunction(() => document.querySelector('#lecture-text').value === '合成测试回答二：中序遍历先遍历左子树，再访问根节点。')
    assert.match(await page.locator('.source-tag').innerText(), /第 2 条/)
  })

  // MOCK: synthetic device events below test error/cancellation paths against real API/storage.
  await context.addInitScript(() => {
    const mock = { utterances: [], paused: false, failPause: false }
    class Utterance { constructor(text) { this.text = text } }
    const speech = {
      getVoices: () => [{ voiceURI: 'mock-voice', name: 'MOCK 中文声线', lang: 'zh-CN' }],
      speak: utterance => { mock.utterances.push(utterance); setTimeout(() => utterance.onstart?.(), 20) },
      cancel: () => {},
      get paused() { return mock.paused },
      pause: () => { if (mock.failPause) throw new Error('MOCK pause failure'); mock.paused = true },
      resume: () => { mock.paused = false },
      addEventListener: () => {}, removeEventListener: () => {},
    }
    Object.defineProperty(window, 'speechSynthesis', { value: speech, configurable: true })
    Object.defineProperty(window, 'SpeechSynthesisUtterance', { value: Utterance, configurable: true })
    window.__speechMock = mock
  })

  await check('empty input and server failure preserve the lecture and retry', 'mock_device_real_api', async () => {
    await open()
    assert.equal(await button('开始讲解').isDisabled(), true)
    const text = '用于网络异常回归的合成讲解。'
    await page.locator('#lecture-text').fill(text)
    await page.route('**/api/digital-human/playbacks', route => route.request().method() === 'POST' ? route.abort() : route.continue())
    await button('开始讲解').click()
    await waitState('failed')
    assert.equal(await page.locator('#lecture-text').inputValue(), text)
    await page.unroute('**/api/digital-human/playbacks')
    await button('重试').click()
    await waitState('playing')
    await button('停止').click()
  })

  await check('cancel before create response never starts audio and finishes the record', 'mock_device_real_api', async () => {
    await open()
    let identifier
    await page.route('**/api/digital-human/playbacks', async route => {
      if (route.request().method() !== 'POST') return route.continue()
      const response = await route.fetch()
      identifier = (await response.json()).data.playback_id
      await new Promise(resolve => setTimeout(resolve, 500))
      await route.fulfill({ response })
    })
    await page.locator('#lecture-text').fill('取消操作测试')
    await button('开始讲解').click()
    await waitState('starting')
    await button('停止').click()
    await waitState('stopped')
    await page.waitForTimeout(900)
    assert.equal(await page.evaluate(() => __speechMock.utterances.length), 0)
    assert.ok(identifier)
    const records = await (await context.request.get(base + '/api/digital-human/playbacks')).json()
    assert.equal(records.data.find(item => item.playback_id === identifier).status, 'stopped')
    await page.unroute('**/api/digital-human/playbacks')
  })

  await check('failed final-state sync can be retried without new playback', 'mock_device_real_api', async () => {
    await open()
    await page.route('**/api/digital-human/playbacks/*', route => route.request().method() === 'PATCH' ? route.abort() : route.continue())
    await page.locator('#lecture-text').fill('同步异常测试')
    await button('开始讲解').click()
    await waitState('playing')
    await page.evaluate(() => __speechMock.utterances.at(-1).onend())
    await waitState('completed')
    await button('重试同步').waitFor()
    await page.unroute('**/api/digital-human/playbacks/*')
    await button('重试同步').click()
    await button('重试同步').waitFor({ state: 'hidden' })
  })

  await check('pause failure remains failed and does not restart mouth animation', 'mock_device_real_api', async () => {
    await open()
    await page.locator('#lecture-text').fill('设备异常测试')
    await button('开始讲解').click()
    await waitState('playing')
    await page.evaluate(() => { __speechMock.failPause = true })
    await button('暂停').click()
    await waitState('failed')
    assert.match(await page.locator('.error-box').innerText(), /暂停失败/)
    assert.equal(await page.locator('.mentor-art.talking').count(), 0)
  })

  await check('context failure retry reloads the answer rather than playing empty text', 'mock_device_real_api', async () => {
    await page.route('**/ai/contexts/v2-1-acceptance', route => route.abort())
    await open('/digital-human?ctx=v2-1-acceptance&message=0')
    await button('重试').waitFor()
    await page.unroute('**/ai/contexts/v2-1-acceptance')
    await button('重试').click()
    await page.waitForFunction(() => document.querySelector('#lecture-text').value.startsWith('合成测试回答一'))
    assert.equal(await state().getAttribute('data-state'), 'idle')
  })

  await check('delete/undo retains the original saved answer', 'mock_device_real_api', async () => {
    await open('/digital-human?ctx=v2-1-acceptance&message=0')
    await page.waitForFunction(() => document.querySelector('#lecture-text').value.startsWith('合成测试回答一'))
    await button('开始讲解').click()
    await waitState('playing')
    const length = Array.from(await page.locator('#lecture-text').inputValue()).length
    await page.waitForFunction(length => document.querySelector('.history-panel li strong')?.textContent?.startsWith(`${length} 字`), length)
    await page.locator('.history-panel li').first().getByRole('button').click()
    await waitState('stopped')
    await button('撤销删除').click()
    assert.equal(await button('重试同步').count(), 0)
    assert.equal(await page.locator('#lecture-text').inputValue(), '合成测试回答一：前序遍历先访问根节点，再遍历左右子树。')
  })
} finally {
  await browser.close()
  const report = {
    version: 'V2.1.1', generated_at: new Date().toISOString(), sample_kind: 'synthetic_engineering_regression',
    passed: results.length > 0 && results.every(item => item.passed) && pageErrors.length === 0,
    results, pageErrors,
    limitation: 'Native speech events do not establish audible output quality or phoneme alignment. MOCK device tests do not establish real TTS.',
  }
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(report, null, 2), 'utf8')
  console.log(JSON.stringify({ passed: report.passed, cases: results.length, failures: results.filter(item => !item.passed), pageErrors }, null, 2))
  if (!report.passed) process.exitCode = 1
}
