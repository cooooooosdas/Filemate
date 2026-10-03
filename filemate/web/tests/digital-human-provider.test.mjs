import assert from 'node:assert/strict'
import { test } from 'node:test'
import { BrowserSpeechProvider, splitSpeechText } from '../src/digital-human/provider.ts'

// MOCK: deterministic Web Speech events exercise lifecycle failures, not audio quality.
function setup(t) {
  t.mock.timers.enable({ apis: ['Date', 'setTimeout'], now: 0 })
  const calls = []
  const speech = {
    paused: false,
    getVoices: () => [{ voiceURI: 'local-zh', lang: 'zh-CN' }],
    speak: utterance => calls.push(utterance),
    cancel() {},
    pause() { this.paused = true },
    resume() { this.paused = false },
  }
  class Utterance {
    constructor(text) { this.text = text }
  }
  globalThis.window = {
    speechSynthesis: speech, SpeechSynthesisUtterance: Utterance,
    setTimeout: (...args) => globalThis.setTimeout(...args),
    clearTimeout: (...args) => globalThis.clearTimeout(...args),
  }
  const provider = new BrowserSpeechProvider()
  const log = []
  const events = {
    onStart: () => log.push('start'),
    onBoundary: index => log.push(index),
    onEnd: () => log.push('end'),
    onError: reason => log.push(reason),
  }
  const options = { voiceId: 'local-zh', rate: 1, volume: 0.5 }
  t.after(() => { provider.stop(); delete globalThis.window })
  return { provider, speech, calls, events, options, log }
}

test('chunks preserve 50/500/5000-character scripts and Unicode boundaries', () => {
  for (const size of [50, 500, 5000]) {
    const text = '知识点，'.repeat(Math.ceil(size / 4)).slice(0, size)
    const chunks = splitSpeechText(text)
    assert.equal(chunks.join(''), text)
    assert.ok(chunks.every(chunk => chunk.length > 0 && chunk.length <= 140))
  }
  const text = '学'.repeat(139) + '𠮷' + '习'.repeat(140)
  assert.equal(splitSpeechText(text).join(''), text)
  assert.ok(splitSpeechText(text).every(chunk => !/[\uD800-\uDBFF]$/.test(chunk) && !/^[\uDC00-\uDFFF]/.test(chunk)))
  assert.deepEqual(splitSpeechText(' \n '), [])
  for (const invalid of [0, 1, -1, 1.5, NaN, Infinity]) assert.throws(() => splitSpeechText('abc', invalid), RangeError)
})

test('500 characters play sequentially with global subtitle offsets and one completion', t => {
  const { provider, calls, events, options, log } = setup(t)
  const text = '学'.repeat(500)
  provider.speak(text, options, events)
  let offset = 0
  for (let index = 0; index < calls.length; index++) {
    const utterance = calls[index]
    assert.equal(utterance.voice.voiceURI, 'local-zh')
    assert.equal(utterance.rate, 1)
    assert.equal(utterance.volume, 0.5)
    utterance.onstart()
    utterance.onboundary({ charIndex: 10 })
    assert.equal(log.at(-1), offset + 10)
    offset += utterance.text.length
    utterance.onend()
    utterance.onend() // A duplicated browser event cannot advance twice.
  }
  assert.equal(offset, 500)
  assert.equal(calls.length, 4)
  assert.equal(log.filter(item => item === 'start').length, 1)
  assert.equal(log.filter(item => item === 'end').length, 1)
  t.mock.timers.tick(300000)
  assert.equal(log.at(-1), 'end')
})

test('a silent speech service times out once and supports retry', t => {
  const { provider, calls, events, options, log } = setup(t)
  provider.speak('测试讲解', options, events)
  t.mock.timers.tick(15000)
  assert.match(log[0], /未响应/)
  calls[0].onstart()
  calls[0].onend()
  assert.equal(log.length, 1)
  provider.speak('重试', options, events)
  calls[1].onstart()
  calls[1].onend()
  assert.equal(log.at(-1), 'end')
})

test('pause suspends the watchdog and ignores late subtitle boundaries', t => {
  const { provider, calls, events, options, log } = setup(t)
  provider.speak('测试', options, events)
  calls[0].onstart()
  t.mock.timers.tick(10000)
  provider.pause()
  calls[0].onboundary({ charIndex: 1 })
  const before = [...log]
  t.mock.timers.tick(300000)
  assert.deepEqual(log, before)
  provider.resume()
  assert.equal(window.speechSynthesis.paused, false)
  t.mock.timers.tick(19999)
  assert.deepEqual(log, before)
  t.mock.timers.tick(1)
  assert.match(log.at(-1), /播放超时/)
})

test('replay after pause restores the queue and ignores old callbacks', t => {
  const { provider, calls, events, options, log } = setup(t)
  provider.speak('旧讲解', options, events)
  calls[0].onstart()
  provider.pause()
  provider.speak('新讲解', options, events)
  assert.equal(window.speechSynthesis.paused, false)
  const before = [...log]
  calls[0].onerror({ error: 'canceled' })
  calls[0].onend()
  assert.deepEqual(log, before)
  calls[1].onstart()
  calls[1].onend()
  assert.equal(log.at(-1), 'end')
})

test('stop during startup cancels timers and prevents all late events', t => {
  const { provider, calls, events, options, log } = setup(t)
  provider.speak('取消操作', options, events)
  provider.stop()
  provider.stop()
  calls[0].onstart()
  calls[0].onboundary({ charIndex: 1 })
  calls[0].onend()
  calls[0].onerror({ error: 'network' })
  t.mock.timers.tick(300000)
  assert.deepEqual(log, [])
})

test('network error is terminal even if end/start arrive later', t => {
  const { provider, calls, events, options, log } = setup(t)
  provider.speak('学'.repeat(500), options, events)
  calls[0].onerror({ error: 'network' })
  calls[0].onstart()
  calls[0].onend()
  calls[0].onerror({ error: 'network' })
  t.mock.timers.tick(300000)
  assert.equal(calls.length, 1)
  assert.equal(log.length, 1)
  assert.match(log[0], /network/)
})

test('native speak/pause/resume failures are translated into recoverable errors', t => {
  const { provider, speech, calls, events, options, log } = setup(t)
  speech.speak = () => { throw new Error('device failure') }
  assert.doesNotThrow(() => provider.speak('测试', options, events))
  assert.match(log.at(-1), /启动失败/)
  speech.speak = utterance => calls.push(utterance)
  provider.speak('测试', options, events)
  calls[0].onstart()
  speech.pause = () => { throw new Error('device failure') }
  assert.doesNotThrow(() => provider.pause())
  assert.match(log.at(-1), /暂停失败/)
  provider.speak('测试', options, events)
  calls[1].onstart()
  speech.pause = function () { this.paused = true }
  provider.pause()
  speech.resume = () => { throw new Error('device failure') }
  assert.doesNotThrow(() => provider.resume())
  assert.match(log.at(-1), /继续失败/)
})

test('empty text, invalid settings, unavailable voices and unsupported browser', t => {
  const { provider, speech, events, options, log, calls } = setup(t)
  provider.speak('  ', options, events)
  assert.match(log.at(-1), /输入/)
  provider.speak('测试', { ...options, rate: NaN }, events)
  provider.speak('测试', { ...options, volume: 2 }, events)
  assert.equal(calls.length, 0)
  speech.getVoices = () => { throw new Error('unavailable') }
  assert.deepEqual(provider.voices(), [])
  provider.speak('测试', options, events)
  assert.equal(calls[0].voice, null)
  delete window.SpeechSynthesisUtterance
  provider.speak('测试', options, events)
  assert.match(log.at(-1), /不支持/)
})
