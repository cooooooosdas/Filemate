import assert from 'node:assert/strict'
import { test } from 'node:test'
import { decodeSpeechMotion, motionLevel } from '../src/digital-human/speech-motion.ts'

test('mouth motion follows actual sound energy, including silence and end of audio', () => {
  const track = { levels: new Float32Array([0, 0.1, 0, 0]), step: 0.025 }
  assert.equal(motionLevel(track, 0), 0)
  assert.ok(motionLevel(track, 0.025) > 0.5)
  assert.equal(motionLevel(track, 0.05), 0)
  assert.equal(motionLevel(track, 30), 0)
  assert.equal(motionLevel(track, NaN), 0)
  assert.equal(motionLevel(track, -1), 0)
})

test('audio analysis returns empty on unsupported, aborted, oversized and failed decoding', async t => {
  globalThis.window = { setTimeout }
  t.after(() => { delete globalThis.window })
  const blob = new Blob(['synthetic audio'])
  assert.equal(await decodeSpeechMotion(blob, 1, new AbortController().signal), null)
  window.OfflineAudioContext = class { async decodeAudioData() { throw new Error('cannot decode') } }
  assert.equal(await decodeSpeechMotion(blob, 1, new AbortController().signal), null)
  const abort = new AbortController(); abort.abort()
  assert.equal(await decodeSpeechMotion(blob, 1, abort.signal), null)
  assert.equal(await decodeSpeechMotion(blob, 901, new AbortController().signal), null)
  assert.equal(await decodeSpeechMotion(new Blob([new Uint8Array(8 * 1024 * 1024 + 1)]), 1, new AbortController().signal), null)
})

test('decoded silent sections stay closed rather than becoming a timed mouth loop', async t => {
  globalThis.window = { setTimeout, OfflineAudioContext: class {
    async decodeAudioData() { return { sampleRate: 8000, duration: 0.1, numberOfChannels: 1,
      length: 800, getChannelData: () => new Float32Array(800).map((_, i) => i < 200 ? 0.1 : 0) } }
  } }
  t.after(() => { delete globalThis.window })
  const track = await decodeSpeechMotion(new Blob(['synthetic PCM fixture']), 0.1, new AbortController().signal)
  assert.equal(track.levels.length, 4)
  assert.ok(motionLevel(track, 0) > 0)
  assert.equal(motionLevel(track, 0.05), 0)
})
