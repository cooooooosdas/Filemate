import assert from 'node:assert/strict'
import test from 'node:test'
import { submissionEvidenceText, submissionVerdictText } from '../src/programming/submissionState.ts'

const record = (overrides = {}) => ({ status: 'completed', active: 1, data_error: false, result: { verdict: 'AC' }, ...overrides })

test('submission labels match the evidence eligibility contract', () => {
  for (const verdict of ['AC', 'WA', 'TLE', 'MLE', 'RE', 'CE']) {
    assert.equal(submissionEvidenceText(record({ result: { verdict } })), '计入练习统计')
  }
  for (const status of ['cancelled', 'failed']) {
    assert.equal(submissionEvidenceText(record({ status })), '不计入练习统计')
  }
  for (const status of ['queued', 'running']) {
    assert.equal(submissionEvidenceText(record({ status })), '尚未计入统计')
  }
  assert.equal(submissionEvidenceText(record({ result: {} })), '结果待核对，不计入统计')
})

test('unavailable and withdrawn records never claim statistical validity', () => {
  assert.equal(submissionEvidenceText(record({ data_error: true })), '记录不可用，不计入统计')
  assert.equal(submissionEvidenceText(record({ active: 0 })), '已撤销，不计入统计')
  assert.equal(submissionEvidenceText(record({ active: 0, data_error: true })), '已撤销，不计入统计')
})

test('unavailable records cannot display stale accepted or infrastructure verdicts', () => {
  assert.equal(submissionVerdictText(record({ data_error: true })), '记录不可用')
  assert.equal(submissionVerdictText(record({ status: 'failed', data_error: true })), '记录不可用')
  assert.equal(submissionVerdictText(record()), 'AC')
  assert.equal(submissionVerdictText(record({ status: 'cancelled' })), '已取消')
})
