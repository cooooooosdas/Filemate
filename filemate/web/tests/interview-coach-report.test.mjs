import assert from 'node:assert/strict'
import test from 'node:test'
import { reportInputKey } from '../src/interview/report-state.ts'
test('same_score_new_run_and_pending_analysis_invalidate_report',()=>{
 const first={interview_id:'one',turns:[{turn_id:'t',answer:'回答',score:80,scoring_mode:'llm',attempt_id:'a',analysis_run_id:'r1',source_revision:'v1'}]}
 const next={...first,turns:[{...first.turns[0],analysis_run_id:'r2',source_revision:'v2'}]}
 assert.notEqual(reportInputKey(first,false),reportInputKey(next,false))
 assert.notEqual(reportInputKey(first,false),reportInputKey(first,true))
})
