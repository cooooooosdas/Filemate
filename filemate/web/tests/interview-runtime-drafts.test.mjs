import assert from 'node:assert/strict'
import test from 'node:test'
import { createCoachController, projectCoach } from '../src/interview/coach-state.ts'
import { createRuntimeAdapter } from '../src/interview/runtime.ts'
const snap=(revision=1,index=0,token='token',attempt=null)=>({session:{interview_id:'timed',questions:['开场','主题'],runtime:{status:'running',revision,version_token:token,current_task:index}},revision,displayed_index:index,phase:'question',current_attempt:attempt,external_consent:false})
const result=(s,input)=>({snapshot:s,receipt:{kind:'submit',request_key:input.request_key,attempt_id:'saved'}})

test('background task or restored token changes never rebind an old draft',async()=>{
 for(const change of [snap(2,1),snap(2,0,'restored'),snap(2,0,'token',{attempt_id:'other'})]){
  let current=snap();const sent=[]
  const c=createCoachController({get:async()=>current,submit:async(_,input)=>{sent.push(input);return result(current,input)}})
  await c.open('timed');c.setDraft('opening draft');current=change;await c.refresh();await c.submit()
  assert.equal(sent.length,0);assert.equal(c.state.draft,'opening draft');assert.equal(c.state.error.code,'draft_context_changed')
  assert.equal(projectCoach(c.state.snapshot,'idle',c.state.draftContext).canSubmit,false)
  c.setDraft('');c.setDraft('new task draft');assert.equal(projectCoach(c.state.snapshot,'idle',c.state.draftContext).canSubmit,true)
 }
})

test('same-tab reload restores original draft context only after authorized snapshot',async()=>{
 const data=new Map();let reads=0
 const store={load:id=>{reads++;return data.get(id)},save:(id,value)=>data.set(id,structuredClone(value)),remove:id=>data.delete(id)}
 const api={get:async()=>snap()}
 const first=createCoachController(api,undefined,undefined,store);await first.open('timed');first.setDraft('reload draft');first.dispose()
 const second=createCoachController(api,undefined,undefined,store);await second.open('timed')
 assert.equal(second.state.draft,'reload draft');assert.deepEqual(second.state.draftContext,first.state.draftContext ?? {questionIndex:0,attemptId:null,versionToken:'token'})
 const denied=createCoachController({get:async()=>{throw Object.assign(Error('not found'),{status:404})}},undefined,undefined,store)
 const before=reads;await denied.open('timed');assert.equal(reads,before);assert.equal(denied.state.draft,'')
 second.setDraft('');assert.equal(data.has('timed'),false)
})

test('definite 409 permits fresh explicit same-task retry, network ambiguity retains key',async()=>{
 let current=snap(),n=0;const sent=[]
 const base={get:async()=>current}
 const adapter=createRuntimeAdapter(base,async(_,input)=>{sent.push(structuredClone(input));if(sent.length===1){current=snap(2);throw Object.assign(Error('conflict'),{status:409})};return result({...current,current_attempt:{attempt_id:'saved'}},input)})
 const c=createCoachController(adapter.api,()=>`request-key-${++n}`)
 await c.open('timed');c.setDraft('same task draft');await c.submit();await c.submit()
 assert.equal(sent.length,2);assert.equal(sent[1].expected_revision,2);assert.notEqual(sent[0].request_key,sent[1].request_key);assert.equal(c.state.draft,'')
})

test('bounded temporary storage ignores corrupt payloads and unavailable browser storage',async()=>{
 const {createRuntimeDraftStore}=await import('../src/interview/runtime-drafts.ts')
 const values=new Map();const storage={getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)}
 const store=createRuntimeDraftStore(storage),context={questionIndex:0,attemptId:null,versionToken:'token'}
 store.save('one',{text:'stored',context});assert.deepEqual(store.load('one'),{text:'stored',context});assert.equal(store.load('two'),null)
 store.remove('one');assert.equal(store.load('one'),null)
 for(const value of ['null','{}',JSON.stringify({text:'x',context:{...context,questionIndex:-1}}),JSON.stringify({text:'x'.repeat(12001),context})]){values.set('filemate.interview-runtime.draft.v1:one',value);assert.equal(store.load('one'),null)}
 const blocked=createRuntimeDraftStore({getItem(){throw Error('blocked')},setItem(){throw Error('quota')},removeItem(){throw Error('blocked')}})
 assert.equal(blocked.load('one'),null);blocked.save('one',{text:'draft',context});blocked.remove('one');assert.equal(blocked.available,false)
})

test('ambiguous committed timed save remains replayable after snapshot changes attempt',async()=>{
 let current=snap(),fail=true;const sent=[]
 const adapter=createRuntimeAdapter({get:async()=>current},async(_,input)=>{sent.push(structuredClone(input));current=snap(2,0,'token',{attempt_id:'saved'});if(fail){fail=false;throw Error('lost response')};return result(current,input)})
 const c=createCoachController(adapter.api,()=> 'same-request-key');await c.open('timed');c.setDraft('original');await c.submit()
 assert.equal(c.canReplaySave,true);assert.equal(projectCoach(c.state.snapshot,'idle',c.state.draftContext,c.canReplaySave).canSubmit,true)
 await c.submit();assert.deepEqual(sent[0],sent[1]);assert.equal(c.state.draft,'')
})
