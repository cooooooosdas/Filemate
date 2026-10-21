import test from 'node:test'
import assert from 'node:assert/strict'
import { VideoCollection } from '../src/interview/video-collection.ts'
import { VIDEO_LIMITS } from '../src/interview/video-capture.ts'
const binding={sessionId:'one',questionIndex:0,attemptId:null,token:'draft'}
const take=(id='clip',b=binding)=>({id,binding:b,blob:new Blob(['video']),duration:2,hasAudio:false,partial:false,issue:null})

test('frozen video and visual evidence survive lost response and local deletion',()=>{
 const c=new VideoCollection();c.context(binding);c.add(take());const metrics={sample_count:2,events:[]}
 const frozen=c.freeze('answer',metrics);metrics.sample_count=99;c.remove('clip')
 assert.equal(c.freeze('answer',undefined),frozen);assert.equal(frozen.metrics.sample_count,2)
 assert.equal(c.receipt(frozen,'attempt','wrong'),false);assert.equal(c.receipt(frozen,'attempt','one'),true)
 assert.equal(c.receipt(frozen,'attempt','one'),false);c.clear()
})
test('only matching receipt binds retained video to its immutable attempt',()=>{
 const c=new VideoCollection();c.context(binding);c.add(take());const frozen=c.freeze('first',undefined)
 c.context({...binding,attemptId:'saved',token:'next'});assert.equal(c.receipt(frozen,'saved','one'),true);assert.equal(c.items[0].attemptId,'saved')
 c.invalidate();c.context({...binding,attemptId:'saved',token:'reanswer'});c.add(take('new',{...binding,attemptId:'saved',token:'reanswer'}))
 const second=c.freeze('reanswer',undefined);c.receipt(second,'saved2','one');assert.deepEqual(c.items.map(t=>t.attemptId),['saved','saved2']);c.clear()
})
test('question changes retain detached clips but block wrong-attempt attachment',()=>{
 const c=new VideoCollection();c.context(binding);c.add(take());const frozen=c.freeze('answer',undefined)
 c.context({...binding,questionIndex:1});assert.equal(c.items.length,1);assert.equal(c.freeze('answer',undefined).takeId,null);assert.equal(c.receipt(frozen,'wrong','one'),false);c.clear()
})
test('quota refusal never evicts existing clips; URLs revoke once on explicit deletion or session change',()=>{
 let made=0;const revoked=[];const c=new VideoCollection({create:()=>`blob:${++made}`,revoke:url=>revoked.push(url)})
 c.context(binding);for(let n=0;n<VIDEO_LIMITS.takes;n++)assert.equal(c.add(take(String(n))),true)
 assert.equal(c.add(take('extra')),false);assert.equal(c.items.length,VIDEO_LIMITS.takes);assert.equal(revoked.length,0)
 c.remove('0');c.remove('0');assert.equal(revoked.length,1);c.context({...binding,sessionId:'two'});assert.equal(c.items.length,0);assert.equal(revoked.length,VIDEO_LIMITS.takes)
})
test('empty, oversized and wrong-session recordings are refused before URL allocation',()=>{
 const c=new VideoCollection({create:()=>{throw Error('must not allocate')},revoke:()=>{}});c.context(binding)
 assert.equal(c.add({...take(),blob:new Blob([])}),false);assert.equal(c.add({...take(),blob:{size:VIDEO_LIMITS.bytes+1}}),false)
 assert.equal(c.add(take('wrong',{...binding,sessionId:'wrong'})),false);c.clear()
})
