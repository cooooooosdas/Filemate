import assert from 'node:assert/strict'
import test from 'node:test'
import { ObservationAccumulator } from '../src/interview/observations.ts'
const sample = (second, changes = {}) => ({ second, face: true, luminance: 120, yaw: 0, pitch: 0, smile: .1, look: 0, ...changes })
test('continuous missing face and darkness form actual observed intervals', () => {
  const recorder = new ObservationAccumulator()
  for (let t = 0; t <= 4; t += .5) recorder.add(sample(t, { face: t >= 3, luminance: t >= 3 ? 120 : 10 }))
  const result = recorder.snapshot(4, 'recording')
  assert.equal(result.sample_count, 9)
  assert.equal(result.face_samples, 3)
  assert.equal(result.events.find(e => e.kind === 'no_face').end, 2.5)
  assert.equal(result.events.find(e => e.kind === 'low_light').end, 2.5)
})
test('observable motions have cooldown and never produce emotion labels', () => {
  const recorder = new ObservationAccumulator()
  recorder.add(sample(0))
  recorder.add(sample(.5, { yaw: 20, smile: .5, look: .4 }))
  recorder.add(sample(1))
  assert.deepEqual(recorder.snapshot(1, 'visual').events.map(e => e.kind), ['head_pose_change', 'smile_change', 'look_direction_change'])
})
test('poor light suppresses pose and smile interpretation', () => {
  const recorder = new ObservationAccumulator()
  recorder.add(sample(0))
  recorder.add(sample(.5, { luminance: 10, yaw: 60, smile: .9, look: .9 }))
  recorder.add(sample(1))
  assert.deepEqual(recorder.snapshot(1, 'recording').events, [])
})
