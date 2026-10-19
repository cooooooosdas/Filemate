import assert from 'node:assert/strict'
import test from 'node:test'
import { remainingSeconds, formatRemaining, createRuntimeAdapter } from '../src/interview/runtime.ts'
import { configurationForScenario, legacyScenario, unavailableReason } from '../src/interview/configuration.ts'

test('continuous clock uses server remaining and monotonic elapsed; never negative',()=>{
  const r={status:'running',remaining_seconds:100}
  assert.equal(remainingSeconds(r,1000,31000),70)
  assert.equal(remainingSeconds(r,1000,301000),0)
  assert.equal(remainingSeconds({...r,status:'expired'},1000,1000),0)
  assert.equal(formatRemaining(600),'10:00')
})

test('timed selection is explicit and unsupported AI generation stays blocked',()=>{
  const c={...configurationForScenario('技术面','标准'),execution_mode:'timed',question_strategy:'random'}
  assert.equal(legacyScenario(c),null)
  assert.equal(unavailableReason(c),'')
  assert.match(unavailableReason({...c,question_strategy:'ai'}),/尚未/)
  assert.equal(unavailableReason({...c,category:'creator',track:'knowledge'}),'')
})

test('lost submit response replays original runtime revision and preserves attempt receipt',async()=>{
  let revision=1,fail=true
  const sent=[]
  const snapshot=()=>({revision,session:{interview_id:'timed',runtime:{revision,version_token:'token',current_task:0}}})
  const adapter=createRuntimeAdapter({get:async()=>snapshot(),submit:async()=>{throw Error('legacy used')}},async(id,input)=>{
    sent.push(structuredClone(input));revision=2
    if(fail){fail=false;throw Error('offline')}
    return {snapshot:snapshot(),receipt:{kind:'submit',request_key:input.request_key,attempt_id:'persisted'}}
  })
  await adapter.api.get('timed')
  const answer={request_key:'stable-key',expected_revision:9,question_index:0,answer:'原文',expected_attempt_id:null}
  await assert.rejects(adapter.api.submit('timed',answer),/offline/)
  await adapter.api.get('timed')
  const result=await adapter.api.submit('timed',answer)
  assert.deepEqual(sent[0],sent[1])
  assert.equal(sent[1].expected_revision,1)
  assert.equal(result.receipt.attempt_id,'persisted')
})

test('runtime start/event retry keeps command key; legacy dispatch remains unchanged',async()=>{
  let fail=true;const sent=[];let legacy=0
  const timed={session:{interview_id:'timed',runtime:{revision:0,version_token:'token',current_task:0}}}
  const adapter=createRuntimeAdapter({get:async id=>id==='fixed'?{session:{}}:timed,submit:async()=>{legacy++;return {}}},async(id,input)=>{
    sent.push(input);if(fail){fail=false;throw Error('offline')};return {snapshot:timed,receipt:{}}
  })
  await adapter.api.get('timed')
  await assert.rejects(adapter.command('timed','start'),/offline/)
  await adapter.command('timed','start')
  assert.equal(sent[0].request_key,sent[1].request_key)
  await adapter.api.get('fixed');await adapter.api.submit('fixed',{})
  assert.equal(legacy,1)
})
