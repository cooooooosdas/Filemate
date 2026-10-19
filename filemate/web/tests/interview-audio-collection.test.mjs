import test from 'node:test'
import assert from 'node:assert/strict'
import { AudioCollection } from '../src/interview/audio-collection.ts'
const binding={sessionId:'one',questionIndex:0,attemptId:null,token:'draft1'}
const take=(id='take1',b=binding)=>({id,binding:b,blob:new Blob(['audio']),captureSeconds:2,summary:null,partial:false,issue:null})

test('freeze retries keep original evidence; receipt alone binds immutable take',()=>{
 const c=new AudioCollection();c.context(binding);c.add(take())
 const frozen=c.freeze('answer',null);c.context({...binding,attemptId:'saved'})
 assert.equal(c.freeze('answer',null),frozen)
 assert.equal(c.receipt(frozen,'attempt1','wrong'),false)
 assert.equal(c.receipt(frozen,'attempt1','one'),true)
 assert.equal(c.items[0].attemptId,'attempt1');assert.equal(c.receipt(frozen,'attempt2','one'),false)
})
test('task changes detach unsaved audio, reanswer never reuses old evidence',()=>{
 const c=new AudioCollection();c.context(binding);c.add(take())
 c.context({...binding,questionIndex:1,token:'task2'})
 assert.equal(c.freeze('new answer',null).metrics,undefined)
 assert.equal(c.items.length,1);assert.equal(c.items[0].attemptId,null)
 c.context({...binding,attemptId:'attempt1'});c.add(take('take2',{...binding,attemptId:'attempt1'}))
 assert.equal(c.freeze('reanswer',null).takeId,'take2')
})
test('quotas never evict; explicit remove revokes URLs; session cleanup revokes all',()=>{
 const revoked=[];const c=new AudioCollection({create:()=>`blob:${Math.random()}`,revoke:u=>revoked.push(u)})
 c.context(binding);for(let i=0;i<30;i++)assert.equal(c.add(take(`t${i}`)),true)
 assert.equal(c.canRecord,false);assert.equal(c.add(take('extra')),false);assert.equal(c.items.length,30)
 c.remove('t0');assert.equal(revoked.length,1);assert.equal(c.canRecord,true)
 c.context({...binding,sessionId:'two'});assert.equal(c.items.length,0);assert.equal(revoked.length,30)
})
test('no empty or wrong-context evidence, transcript missing confidence stays null',()=>{
 const c=new AudioCollection();c.context(binding)
 const no=c.freeze('typed only',null);assert.equal(no.metrics,undefined)
 c.invalidate();c.add(take('old',{...binding,token:'old'}))
 assert.equal(c.freeze('typed only',null).metrics,undefined)
 c.invalidate();const asr={provider:'browser_web_speech',status:'completed',language:'zh-CN',segments:[{text:'原话',confidence:null,callback_seconds:1}],confidence:null}
 assert.equal(c.freeze('edited answer',asr).metrics.transcription.confidence,null)
})
