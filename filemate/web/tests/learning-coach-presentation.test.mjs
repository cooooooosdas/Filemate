import test from 'node:test'
import assert from 'node:assert/strict'
import { load, run } from './learning-coach-fixtures.mjs'

test('presentation separates evidence, methods and model failure without inventing metrics', () => {
  const { presentCoach } = load('../src/today/coach-presentation.ts')
  const value = run({ requested_mode: 'llm', effective_mode: 'rule_fallback', model_status: 'failed', safe_error_code: 'timeout' })
  value.proposal.facts = [{ fact_id: 'synthetic-fact', kind: 'goal', display_text: '当前目标', data: { title: 'C++训练' } }]
  value.proposal.explanations = [{ text: '按已有目标继续训练', method_code: 'practice', fact_ids: ['synthetic-fact'] }]
  const shown = presentCoach(value)
  assert.equal(shown.facts.length, 1); assert.equal(shown.rule_days.length, 1)
  assert.ok(shown.methods.length); assert.match(shown.model_status, /规则|失败|不可用/)
  assert.doesNotMatch(JSON.stringify(shown), /分析完成|掌握率|学习提升/)
  assert.ok(Array.isArray(shown.coverage_notices))
})


test('exam evidence choices exclude interview judgments; job requirements are job-only', () => {
  const { coachEvidenceKinds } = load('../src/today/coach-presentation.ts')
  assert.equal(coachEvidenceKinds('exam').some(item => item.kind === 'interview'), false)
  assert.equal(coachEvidenceKinds('skill').some(item => item.kind === 'position'), false)
  assert.equal(coachEvidenceKinds('job').some(item => item.kind === 'position'), true)
})


test('coverage explains actual deferred counts without pretending all tasks fit', () => {
  const { presentCoach } = load('../src/today/coach-presentation.ts')
  const value = run(); value.proposal.days[0].schedule.deferred_counts = { estimate_required: 1 }; value.proposal.days[0].schedule.deferred_count = 1
  assert.ok(presentCoach(value).coverage_notices.some(text => text.includes('1') && text.includes('预计时长')))
})
