import assert from 'node:assert/strict'
import test from 'node:test'
import { liveFaceIndicators } from '../src/interview/liveFace.ts'
const sample = { second: 1, face: true, luminance: 100, smile: .42, brow: .2, jaw: .1, yaw: 5.6, pitch: -3.2, look: 0 }
test('live readings use actual bounded coefficients, never emotion probabilities', () => {
  assert.deepEqual(liveFaceIndicators(sample), { status: '已检测到人脸', smile: 42, brow: 20, jaw: 10, yaw: 6, pitch: -3 })
  assert.equal(liveFaceIndicators({ ...sample, jaw: 3 }).jaw, 100)
  assert.equal('tension' in liveFaceIndicators(sample), false)
})
test('missing face or bad light clears previous readings rather than showing false zero', () => {
  for (const changes of [{ face: false }, { luminance: 10 }]) {
    const result = liveFaceIndicators({ ...sample, ...changes })
    assert.equal(result.smile, null); assert.equal(result.yaw, null); assert.equal(result.brow, null)
  }
  assert.equal(liveFaceIndicators({ ...sample, jaw: NaN }).jaw, null)
})
