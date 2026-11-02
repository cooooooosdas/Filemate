import test from 'node:test'
import assert from 'node:assert/strict'
import { createReviewSubmission, memoryReviewStorage } from '../src/wrongbook/submission.ts'
import { createReviewPreferences } from '../src/wrongbook/browse-state.ts'
const mod = await import('../src/wrongbook/focus-state.ts').catch(() => ({}))
const ref = {wrong_id:'w',artifact_id:'a',question_index:0,question_digest:'a'.repeat(64)}
const question = {type:'fill',question:'顺序？',answer:'SECRET',explanation:'SECRET EXPLANATION'}
const detail = {...ref,question,read_only_snapshot:false,data_error:false,schedule_status:'active',legacy_mastered:false}
const checked = {...ref,source_id:'s',revision:1,next_review_at:'2026-10-25T00:00:00Z'}
function setup({storage=memoryReviewStorage(),...overrides}={}) {
 assert.equal(typeof mod.createFocusReviewController,'function'); let posts=0;const limits=[]
 const api={getReviewPage:async p=>{limits.push(p.limit);return {items:[ref]}},getReviewDetail:async()=>detail,getReviewAttempts:async()=>({items:posts?[{attempt_id:'saved',artifact_id:'a',question_index:0}]:[],has_more:false}),submitReviewAnswer:async()=>{posts++;return {attempt_id:'saved',is_correct:null}},getReviewReceipt:async()=>({attempt_id:'saved'}),...overrides}
 const submission=createReviewSubmission(api,{storage,scope:'a'.repeat(64)})
 const prefs=createReviewPreferences(storage,'a'.repeat(64))
 return {c:mod.createFocusReviewController(api,submission,prefs),submission,prefs,limits,posts:()=>posts,storage}
}
test('default ten, upper twenty, empty queue; start and skip create no attempt',async()=>{
 const x=setup();await x.c.start({});assert.deepEqual(x.limits,[10]);assert.equal(x.posts(),0);await x.c.skip();assert.equal(x.posts(),0);assert.equal(await x.c.start({},21),false)
 const empty=setup({getReviewPage:async()=>({items:[]})});await empty.c.start({});assert.equal(empty.c.state.items.length,0);assert.match(empty.c.state.message,/没有/)
})
test('independent display has no reference or history; reveal remains assisted',async()=>{
 const x=setup();await x.c.start({});assert.ok(!JSON.stringify(x.c.question()).includes('SECRET'));assert.equal(await x.c.next(),false)
 x.submission.revealAnswer();assert.match(JSON.stringify(x.c.question()),/SECRET/);x.submission.setAnswer('answer');await x.submission.submit();await x.c.recordSaved();assert.equal(x.c.state.items[0].attempt_id,'saved');assert.equal(x.posts(),1)
})
test('resume verifies saved attempt against server, never trusts edited local completion',async()=>{
 const x=setup();x.prefs.saveBatch({created_at:new Date().toISOString(),position:0,items:[{...ref,attempt_id:'forged'}]});await x.c.resume();assert.equal(x.c.state.completed[ref.wrong_id],undefined)
 const y=setup({getReviewAttempts:async()=>({items:[{attempt_id:'real',artifact_id:'a',question_index:0}],has_more:false})});y.prefs.saveBatch({created_at:new Date().toISOString(),position:0,items:[{...ref,attempt_id:'real'}]});await y.c.resume();assert.equal(y.c.state.completed.w,'real');assert.equal(y.posts(),0)
})
test('changed digest, deleted question and paused question are unavailable without substitution',async()=>{
 for(const value of [{...detail,question_digest:'b'.repeat(64)},{...detail,schedule_status:'paused'},null]){const x=setup({getReviewDetail:async()=>{if(!value)throw {status:404};return value}});await x.c.start({});assert.equal(x.c.state.unavailable,true);assert.equal(x.c.question(),null);assert.equal(x.posts(),0)}
})
test('seven day expiry and identity reset never replay requests',async()=>{
 const x=setup();x.prefs.saveBatch({created_at:'2020-01-01T00:00:00Z',position:0,items:[ref]});assert.equal(await x.c.resume(),false);assert.equal(x.c.state.expired,true);assert.equal(x.posts(),0);await x.c.start({});x.c.resetIdentity(null);assert.equal(x.c.question(),null);assert.equal(x.c.state.items.length,0)
})
test('pending save recovery queries receipt; it never automatically submits',async()=>{
 const storage=memoryReviewStorage();let posts=0
 const a=setup({storage,submitReviewAnswer:async()=>{posts++;throw Error('offline')}});await a.c.start({});a.submission.setAnswer('private');await a.submission.submit();a.c.dispose()
 const b=setup({storage,getReviewReceipt:async()=>({...ref,attempt_id:'saved'}),getReviewAttempts:async()=>({items:[{attempt_id:'saved',artifact_id:'a',question_index:0}],has_more:false})});await b.c.resume();assert.equal(b.posts(),0);assert.equal(b.c.state.completed.w,'saved');assert.ok(!JSON.stringify([...Object.values(storage)]).includes('private'))
})

test('receipt reference survives refresh while server verification is still in flight',async()=>{
 const storage=memoryReviewStorage();let release
 const x=setup({storage,getReviewAttempts:()=>new Promise(resolve=>{release=resolve})})
 await x.c.start({});x.submission.setAnswer('answer');await x.submission.submit()
 const verifying=x.c.recordSaved()
 assert.equal(createReviewPreferences(storage,'a'.repeat(64)).getBatch().items[0].attempt_id,'saved')
 assert.equal(x.c.state.completed.w,undefined)
 x.c.dispose();release({items:[{attempt_id:'saved',artifact_id:'a',question_index:0}]});await verifying
 const y=setup({storage,getReviewAttempts:async()=>({items:[{attempt_id:'saved',artifact_id:'a',question_index:0}]})})
 await y.c.resume();assert.equal(y.c.state.completed.w,'saved');assert.equal(y.posts(),0)
})

test('checked selection starts exact references without querying another page',async()=>{
 const x=setup();assert.equal(await x.c.startChecked([checked]),true);assert.deepEqual(x.limits,[]);assert.equal(x.c.state.items[0].wrong_id,'w');assert.equal(x.posts(),0)
 x.submission.setAnswer('unsaved');assert.equal(await x.c.startChecked([{...checked,wrong_id:'other'}]),false);assert.equal(x.c.state.items[0].wrong_id,'w');assert.equal(x.submission.state.answer,'unsaved')
})
test('checked selection rejects duplicate, oversized and invalid references',async()=>{
 const x=setup();for(const refs of [[],[checked,checked],Array.from({length:21},(_,i)=>({...checked,wrong_id:String(i)})),[{...checked,revision:-1}],[{...checked,question_digest:'invalid'}]])assert.equal(await x.c.startChecked(refs),false)
 assert.equal(x.c.state.items.length,0);assert.deepEqual(x.limits,[])
})
test('checked selection retains unavailable references rather than substituting',async()=>{
 const x=setup({getReviewDetail:async()=>({...detail,question_digest:'b'.repeat(64)})});assert.equal(await x.c.startChecked([checked]),false);assert.equal(x.c.state.unavailable,true);assert.equal(x.c.state.items[0].wrong_id,'w');assert.deepEqual(x.limits,[])
})
