import assert from 'node:assert/strict'
import { test } from 'node:test'
import { MicrosoftSpeechProvider, NATURAL_VOICES } from '../src/digital-human/natural-speech.ts'

// MOCK: 音频事件只验证生命周期，真实声线由独立供应商和浏览器验收。
function setup(t, synthesize = async () => new Blob(['synthetic-audio'], { type: 'audio/mpeg' })) {
  const audios = []
  class Audio {
    duration = 5
    currentTime = 0
    constructor() { audios.push(this) }
    async play() { this.onplaying?.() }
    pause() {}
    load() {}
    removeAttribute() {}
  }
  globalThis.window = { Audio, setTimeout, clearTimeout }
  const provider = new MicrosoftSpeechProvider(synthesize)
  const log = []
  const events = { onStart: () => log.push('start'), onEnd: () => log.push('end'), onBoundary: n => log.push(n), onError: reason => log.push(reason) }
  const options = { voiceId: NATURAL_VOICES[0].voiceURI, rate: 1, volume: 0.8 }
  t.after(() => { provider.stop(); delete globalThis.window })
  return { provider, audios, log, events, options }
}
const flush = () => new Promise(resolve => setImmediate(resolve))

test('natural voices default to Xiaoxiao and exclude device robotic voices', () => {
  assert.equal(NATURAL_VOICES[0].voiceURI, 'zh-CN-XiaoxiaoNeural')
  assert.equal(NATURAL_VOICES[1].voiceURI, 'zh-CN-YunxiaNeural')
  assert.equal(NATURAL_VOICES.length, 4)
})
test('natural audio lifecycle releases audio and emits actual playback events', async t => {
  const { provider, audios, log, events, options } = setup(t)
  provider.speak('学'.repeat(500), options, events)
  await flush()
  assert.deepEqual(log, ['start'])
  const audio = audios[0]
  audio.currentTime = 2; audio.ontimeupdate()
  assert.equal(log.at(-1), 200)
  provider.pause(); audio.currentTime = 3; audio.ontimeupdate()
  assert.equal(log.at(-1), 200)
  provider.resume(); await flush(); assert.equal(log.at(-1), 'start')
  audio.onended(); assert.equal(log.at(-1), 'end')
  assert.equal(audio.onplaying, null)
})
test('stop aborts pending requests and prevents late playback', async t => {
  let resolve, signal
  const { provider, audios, log, events, options } = setup(t, async (_text, _voice, abort) => {
    signal = abort; return new Promise(done => { resolve = done })
  })
  provider.speak('学习', options, events); provider.stop()
  assert.equal(signal.aborted, true)
  resolve(new Blob(['audio'], { type: 'audio/mpeg' })); await flush()
  assert.equal(audios.length, 0); assert.deepEqual(log, [])
})
test('upstream failure is visible and never falls back to device speech', async t => {
  const { provider, audios, log, events, options } = setup(t, async () => { throw new Error('Microsoft 自然语音暂不可用') })
  provider.speak('学习', options, events); await flush()
  assert.match(log.at(-1), /暂不可用/); assert.equal(audios.length, 0)
})
