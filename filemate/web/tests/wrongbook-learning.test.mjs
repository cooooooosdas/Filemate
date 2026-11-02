import assert from 'node:assert/strict'
import test from 'node:test'
const mod=await import('../src/wrongbook/learning-state.ts').catch(()=>({}))
const ref={wrong_id:'w',artifact_id:'a',question_index:0,question_digest:'d'.repeat(64)}
function setup(overrides={}){assert.equal(typeof mod.createReviewLearningController,'function');const calls=[],api={previewReviewLearningPlan:async(id,b)=>({wrong_id:id,confirmation_token:'token',plan:b}),confirmReviewLearningPlan:async(id,b)=>{calls.push(b);return {wrong_id:id,review_event_id:'event',plan_id:'plan',route:'/study-plan?plan=plan'}},previewReviewAdoption:async()=>({confirmation_token:'token'}),confirmReviewAdoption:async()=>({wrong_id:'w',review_event_id:'event'}),previewReviewLearningUndo:async()=>({confirmation_token:'undo',changes:{kind:'plan'}}),confirmReviewLearningUndo:async()=>({wrong_id:'w',review_event_id:'undo-event'}),...overrides};return {c:mod.createReviewLearningController(api,s=>s),calls}}
const selection=()=>({expected_revision:1,start_date:'2026-10-28',tasks:[{action_id:'b'.repeat(64),title:'重练',instructions:'独立作答',duration_minutes:10,day_offset:0}]})
test('saved edited plan releases the navigation guard while unsaved task text remains protected',async()=>{
 const {c}=setup();c.open(ref);c.setSelection(selection());c.state.selection.tasks[0].title='我自己的行动标题';assert.equal(c.dirty(),true);await c.previewPlan();await c.confirm();assert.equal(c.dirty(),false)
})
test('edit requires fresh preview, cancel and conflict never mutate original goal or show success',async()=>{
 const {c,calls}=setup();c.open(ref);c.state.selection=selection();await c.previewPlan();c.state.selection.tasks[0].title='新的标题';assert.equal(await c.confirm(),false);assert.equal(calls.length,0);await c.previewPlan();c.cancelPreview();assert.equal(c.state.preview,null);assert.equal(c.state.receipt,null);assert.equal(calls.length,0)
 await c.previewPlan();assert.equal(await c.confirm(),true);assert.equal(c.state.receipt.plan_id,'plan');assert.equal(calls[0].confirmed,true)
})
test('late previews after identity invalidation cannot replace new state',async()=>{
 let done;const {c}=setup({previewReviewLearningPlan:()=>new Promise(r=>{done=r})});c.open(ref);c.state.selection=selection();const pending=c.previewPlan();c.invalidate();c.open({...ref,wrong_id:'new'});done({confirmation_token:'old'});await pending;assert.equal(c.state.preview,null)
})
test('unknown confirmation retains exact key and preview, edits blocked until receipt is recovered',async()=>{
 let fail=true;const keys=[];const {c}=setup({confirmReviewLearningPlan:async(id,b)=>{keys.push(b.request_key);if(fail)throw Error('lost');return {wrong_id:id,review_event_id:'saved',plan_id:'plan'}}});c.open(ref);c.state.selection=selection();await c.previewPlan();await c.confirm();assert.equal(c.state.uncertain,true);c.cancelPreview();assert.ok(c.state.preview);fail=false;await c.confirm();assert.equal(keys[0],keys[1]);assert.equal(c.state.receipt.review_event_id,'saved')
})
test('undo is separately previewed and confirmed and server conflict preserves current data',async()=>{
 const {c}=setup({confirmReviewLearningUndo:async()=>{throw {status:409}}});c.open(ref);await c.previewUndo('event');assert.ok(c.state.preview);assert.equal(await c.confirm(),false);assert.match(c.state.error,/变化|失效/);assert.equal(c.state.receipt,null)
})
test('evidence refresh preserves unknown confirmation identity and original command',async()=>{
 let lost=true;const bodies=[];const {c}=setup({confirmReviewLearningPlan:async(id,b)=>{bodies.push(structuredClone(b));if(lost)throw Error('lost');return {wrong_id:id,review_event_id:'saved'}}});c.open(ref);c.setSelection(selection());await c.previewPlan();await c.confirm();assert.equal(c.state.uncertain,true)
 c.refresh(ref,{...selection(),expected_revision:2});assert.equal(c.state.uncertain,true);assert.ok(c.state.preview);lost=false;await c.confirm();assert.deepEqual(bodies[1],bodies[0]);assert.equal(c.state.receipt.review_event_id,'saved')
})
test('evidence refresh invalidates preview but retains edited task text and a dirty guard',async()=>{
 const {c}=setup();c.open(ref);c.setSelection(selection());c.state.selection.tasks[0].title='我编辑的任务';await c.previewPlan();c.refresh(ref,{...selection(),expected_revision:2});assert.equal(c.state.preview,null);assert.equal(c.state.selection.expected_revision,2);assert.equal(c.state.selection.tasks[0].title,'我编辑的任务');assert.equal(c.dirty(),true)
})
