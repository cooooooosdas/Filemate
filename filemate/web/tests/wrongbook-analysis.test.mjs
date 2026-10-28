import assert from 'node:assert/strict'
import test from 'node:test'
import { memoryReviewStorage } from '../src/wrongbook/submission.ts'
const mod = await import('../src/wrongbook/analysis-state.ts').catch(()=>({}))
const ref = id=>({wrong_id:id,artifact_id:'artifact',question_index:0,question_digest:'d'.repeat(64)})
const context = id=>({ref:ref(id),attempt:{attempt_id:'attempt',user_answer:'原回答'},question:{stem:'原题'},related_attempts:[{user_answer:'历史'}],source_evidence:[{quote:'原文'}],input_digest:'b'.repeat(64),context_revision:'c'.repeat(64),review_state:{revision:1}})
const result = (id,key)=>({ref:ref(id),attempt_id:'attempt',request_key:key,input_digest:'b'.repeat(64),analysis_id:'analysis',status:'ready',stale:false,result:{kind:'insufficient_evidence',possible_causes:[],uncertainties:['待补证']}})
function setup(overrides={},storage=memoryReviewStorage()) {
 assert.equal(typeof mod.createReviewAnalysisController,'function')
 const calls=[];const api={getReviewBrowserScope:async()=> 'a'.repeat(64),getReviewLearningContext:async id=>context(id),getReviewAnalyses:async()=>({items:[]}),startReviewAnalysis:async(id,b)=>{calls.push(b);return result(id,b.request_key)},getReviewAnalysisRequest:async key=>result('w',key),cancelReviewAnalysis:async(id,aid,b)=>({...result(id,b.request_key),status:'cancelled'}),...overrides}
 return {c:mod.createReviewAnalysisController(api,s=>s,storage),calls,storage}
}
test('opening reads exact outbound question answers history and quotes without model or authorization',async()=>{
 const {c,calls}=setup();await c.open(ref('w'),'attempt');assert.equal(calls.length,0);assert.equal(c.state.authorized,false);assert.deepEqual(c.state.context,context('w'))
 assert.equal(await c.authorizeAndAnalyze(),false);c.state.authorized=true;assert.equal(await c.authorizeAndAnalyze(),true);assert.equal(calls.length,1);assert.equal(c.state.authorized,false)
 assert.equal(await c.authorizeAndAnalyze(),false);assert.equal(calls.length,1)
})
test('actual full review detail is narrowed to the four identity fields before context checks',async()=>{
 const {c}=setup();await c.open({...ref('w'),revision:7,question:{stem:'当前题目'},latest_answer:'不会进入pending的正文'},'attempt');assert.ok(c.state.context);assert.equal(c.state.error,'')
})
test('unknown POST is recovered through same-key GET only, no body or key persisted',async()=>{
 let key;const x=setup({startReviewAnalysis:async(id,b)=>{key=b.request_key;throw Error('network lost')}});await x.c.open(ref('w'),'attempt');x.c.state.authorized=true;await x.c.authorizeAndAnalyze();assert.equal(x.c.state.uncertain,true)
 const raw=x.storage.getItem('filemate-review-analysis-pending-v1:'+'a'.repeat(64));assert.ok(raw.includes(key));assert.ok(!raw.includes('原回答')&&!raw.includes('原文'))
 let posts=0;const y=setup({startReviewAnalysis:async()=>{posts++},getReviewAnalysisRequest:async k=>{assert.equal(k,key);return result('w',k)}},x.storage);await y.c.open(ref('w'),'attempt');assert.equal(y.c.state.analysis.status,'ready');assert.equal(posts,0);assert.equal(y.c.state.uncertain,false)
})
test('identity restore or new answer rejects late context and model responses',async()=>{
 let finish;const {c}=setup({startReviewAnalysis:(id,b)=>new Promise(r=>{finish=()=>r(result(id,b.request_key))})});await c.open(ref('old'),'attempt');c.state.authorized=true;const pending=c.authorizeAndAnalyze();await new Promise(r=>setImmediate(r));c.invalidate();await c.open(ref('new'),'attempt');finish();await pending;assert.equal(c.state.context.ref.wrong_id,'new');assert.equal(c.state.analysis,null);assert.equal(c.state.authorized,false)
})
test('multi-instance pending merges, seven-day TTL and twenty-entry bound preserve unresolved requests',async()=>{
 const store=memoryReviewStorage(),xs=[];for(let i=0;i<20;i++){const x=setup({startReviewAnalysis:async()=>{throw Error('offline')}},store);await x.c.open(ref('w'+i),'attempt');x.c.state.authorized=true;await x.c.authorizeAndAnalyze();xs.push(x)}
 let posts=0;const last=setup({startReviewAnalysis:async()=>{posts++}},store);await last.c.open(ref('overflow'),'attempt');last.c.state.authorized=true;await last.c.authorizeAndAnalyze();assert.equal(posts,0);assert.match(last.c.state.error,/20|核验/)
 const key='filemate-review-analysis-pending-v1:'+'a'.repeat(64),items=JSON.parse(store.getItem(key));assert.equal(Object.keys(items).length,20);for(const item of Object.values(items))item.created_at=Date.now()-8*86400000;store.setItem(key,JSON.stringify(items));const clean=setup({},store);await clean.c.open(ref('fresh'),'attempt');clean.c.state.authorized=true;await clean.c.authorizeAndAnalyze();assert.equal(clean.c.state.analysis.status,'ready')
})
test('mismatched receipt cannot become a success and cancellation invalidates late publication',async()=>{
 const x=setup({getReviewAnalysisRequest:async k=>result('other',k),startReviewAnalysis:async()=>{throw Error('offline')}});await x.c.open(ref('w'),'attempt');x.c.state.authorized=true;await x.c.authorizeAndAnalyze();await x.c.recover();assert.equal(x.c.state.analysis,null);assert.equal(x.c.state.uncertain,true)
})
