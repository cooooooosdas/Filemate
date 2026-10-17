import assert from 'node:assert/strict'
import test from 'node:test'
import { initialCoachState, reduceCoach, projectCoach, createCoachController } from '../src/interview/coach-state.ts'
const snapshot = (id='one', patch={}) => ({session:{interview_id:id,questions:['问题'],turns:[],scenario:'技术面'},revision:0,displayed_index:0,phase:'question',external_consent:false,consent_revision:0,provider_identity:'provider',current_attempt:null,...patch})
test('late_response_cannot_replace_new_session', () => {
 let s=reduceCoach(initialCoachState(),{type:'open',id:'new-session',epoch:2})
 s=reduceCoach(s,{type:'snapshot',id:'old-session',epoch:1,value:snapshot('old-session')})
 assert.equal(s.sessionId,'new-session'); assert.equal(s.snapshot,null)
})
test('failed_latest_never_uses_historical_score', () => {
 assert.equal(projectCoach(snapshot('one',{phase:'feedback',current_attempt:{attempt_id:'latest',analysis_status:'failed',score:80,evaluation:{score:80}}})).score,null)
})
test('ime_composition_preserves_draft', () => {
 let s=reduceCoach(initialCoachState(),{type:'draft',text:'正在输入中文',composing:true})
 assert.equal(s.draft,'正在输入中文');assert.equal(s.composing,true)
 assert.equal(projectCoach(snapshot(),'save').canSubmit,false)
})
test('retry_uses_original_submit_key_but_new_explicit_analysis_key', async () => {
 let n=0;const saves=[],runs=[];let current=snapshot();let drop=true
 const api={get:async()=>current,submit:async(_,input)=>{saves.push(input); if(drop){drop=false;throw new Error('offline')} current=snapshot('one',{revision:1,phase:'feedback',current_attempt:{attempt_id:'v1',turn_id:'t',answer:input.answer,analysis_status:'failed',score:null}});return {snapshot:current,receipt:{}}},analyze:async(_,input)=>{runs.push(input);throw Object.assign(new Error('timeout'),{code:'analysis_failed'})}}
 const c=createCoachController(api,()=>`request_key_${++n}`)
 await c.open('one');c.setDraft('原回答')
 await c.submit(); await c.submit()
 assert.equal(saves[0].request_key,saves[1].request_key)
 await c.analyze();await c.analyze();assert.notEqual(runs[0].request_key,runs[1].request_key)
})
test('refresh_never_automatically_analyzes_and_conflict_keeps_draft',async()=>{
 let calls=0;const c=createCoachController({get:async()=>snapshot('one',{external_consent:true}),submit:async()=>{throw Object.assign(new Error('版本冲突'),{status:409,code:'revision_conflict'})},analyze:async()=>{calls++}})
 await c.open('one');c.setDraft('不能丢的草稿');await c.refresh();await c.submit()
 assert.equal(c.state.draft,'不能丢的草稿');assert.equal(calls,0);assert.equal(c.state.error.code,'revision_conflict')
})
