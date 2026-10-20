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
 const api={get:async()=>current,submit:async(_,input)=>{saves.push(input); if(drop){drop=false;throw new Error('offline')} current=snapshot('one',{revision:1,phase:'feedback',current_attempt:{attempt_id:'v1',turn_id:'t',answer:input.answer,analysis_status:'failed',score:null}});return {snapshot:current,receipt:{kind:'submit',request_key:input.request_key,attempt_id:'v1'}}},analyze:async(_,input)=>{runs.push(input);throw Object.assign(new Error('timeout'),{code:'analysis_failed'})}}
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

test('permission_can_be_revoked_during_analysis_and_old_snapshot_is_ignored',async()=>{
 let release;let current=snapshot('one',{revision:1,phase:'feedback',external_consent:true,current_attempt:{attempt_id:'a',analysis_status:'running'}})
 const c=createCoachController({get:async()=>current,analyze:()=>new Promise(resolve=>{release=resolve}),consent:async()=>{current={...current,revision:2,external_consent:false};return {snapshot:current}}})
 await c.open('one');const pending=c.analyze();await c.consent(false)
 assert.equal(c.state.snapshot.external_consent,false)
 release({snapshot:{...current,revision:1,external_consent:true}});await pending
 assert.equal(c.state.snapshot.external_consent,false)
})

test('analysis_pending_never_shows_old_success_as_current',()=>{
 const old=snapshot('one',{phase:'feedback',current_attempt:{attempt_id:'a',analysis_status:'succeeded',score:80,evaluation:{feedback:'旧反馈'}}})
 const view=projectCoach(old,'analysis')
 assert.equal(view.score,null);assert.equal(view.analysisStatus,'running')
})

test('lost_submit_receipt_cannot_analyze_or_own_later_tab_attempt',async()=>{
 let dropped=true,submittedKey,analyzed=[]
 const later=snapshot('one',{revision:3,phase:'feedback',external_consent:true,current_attempt:{attempt_id:'a3',answer:'另一标签回答',analysis_status:'unrequested'}})
 const c=createCoachController({get:async()=>later,submit:async(_,input)=>{submittedKey=input.request_key;if(dropped){dropped=false;throw new Error('lost response')}return {snapshot:later,receipt:{kind:'submit',request_key:submittedKey,attempt_id:'a2'}}},analyze:async(_,input)=>{analyzed.push(input.attempt_id);return {snapshot:later,receipt:{}}}})
 await c.open('one');c.setDraft('本次原回答');await c.submit();const result=await c.submit()
 assert.equal(result.receipt.attempt_id,'a2');assert.deepEqual(analyzed,[]);assert.equal(c.state.draft,'本次原回答');assert.equal(c.state.error.code,'saved_attempt_superseded')
})


test('fixed-question lost save exposes replay without a runtime draft context',async()=>{
 let current=snapshot(),calls=0;const api={get:async()=>current,submit:async(_id,input)=>{
  calls++;current={...current,revision:1,phase:'feedback',current_attempt:{attempt_id:'saved',answer:input.answer}};
  if(calls===1)throw Error('response lost');return {snapshot:current,receipt:{kind:'submit',request_key:input.request_key,attempt_id:'saved'}}
 }}
 const c=createCoachController(api,()=> 'fixed_question_replay');await c.open('one');c.setDraft('保留回答');await c.submit();assert.equal(c.canReplaySave,true);await c.submit();assert.equal(c.state.draft,'');assert.equal(c.canReplaySave,false)
})
