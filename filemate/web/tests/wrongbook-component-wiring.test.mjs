import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { parse, compileScript } from '@vue/compiler-sfc'
import ts from 'typescript'
import * as vue from 'vue'

test('session planner invalidates preview on budget and applied filter changes',async()=>{
 let invalidations=0
 const c={state:vue.reactive({preview:null,loading:false,checking:false,error:''}),invalidate(){invalidations++},dispose(){}}
 const x=await setup('components/wrongbook/ReviewSessionPlanner.vue',{filters:{sort:'due'},scope:'a'.repeat(64)},{'../../wrongbook/session-state':{createReviewSessionController:()=>c}})
 x.state.minutes.value=30;await vue.nextTick();assert.equal(invalidations,1)
 x.props.filters={sort:'recommended'};await vue.nextTick();assert.equal(invalidations,2);x.scope.stop()
})

test('mounted focus resumes only, or consumes exact checked references, never auto-starts another page',async()=>{
 for(const initialRefs of [undefined,[{wrong_id:'chosen'}]]){
  let resumed=0,started=0,received
  const c={state:vue.reactive({items:[],loading:false}),resume:async()=>{resumed++;return false},start:async()=>{started++},startChecked:async refs=>{received=refs},question:()=>null,dispose(){}}
  const deps={'../../wrongbook/focus-state':{createFocusReviewController:()=>c},'../../wrongbook/submission':{createReviewSubmission:()=>({state:{}}),browserReviewStorage:()=>({})},'../../wrongbook/browse-state':{createReviewPreferences:()=>({})}}
  const x=await setup('components/wrongbook/FocusReview.vue',{scope:'a'.repeat(64),filters:{},enabled:true,initialRefs},deps)
  for(const fn of x.mounted)await fn()
  assert.equal(started,0);assert.equal(resumed,initialRefs?0:1);assert.deepEqual(received,initialRefs);x.scope.stop()
 }
})

async function setup(file,props={},deps={}){
 const mounted=[],listeners=new Map(),scope=vue.effectScope()
 const source=await readFile(new URL('../src/'+file,import.meta.url),'utf8')
 const {descriptor}=parse(source),script=compileScript(descriptor,{id:'wrongbook-wiring'}).content.replace(/import\.meta\.env\.\w+/g,'true')
 const code=ts.transpileModule(script,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,module={exports:{}}
 const runtime={...vue,onMounted:fn=>mounted.push(fn),onUnmounted(){},onBeforeUnmount(){},onActivated(){},onDeactivated(){}}
 new Function('require','module','exports',code)(name=>name==='vue'?runtime:deps[name]||{},module,module.exports)
 const input=vue.reactive(props)
 let state;scope.run(()=>{state=module.exports.default.setup(input,{expose(){},emit(){}})})
 return {state,props:input,mounted,scope,listeners}
}

test('new-answer revision clears old previews but preserves the real editable task draft',async()=>{
 const {createReviewLearningController}=await import('../src/wrongbook/learning-state.ts')
 const {createReviewAnalysisController}=await import('../src/wrongbook/analysis-state.ts')
 let revision=1
 const action={action_id:'b'.repeat(64),title:'原任务',instructions:'独立作答',duration_minutes:10,day_offset:0}
 const ref={wrong_id:'w',artifact_id:'a',question_index:0,question_digest:'d'.repeat(64)}
 const api={getReviewBrowserScope:async()=> 'a'.repeat(64),getReviewAttempts:async()=>({items:[{attempt_id:'attempt'}]}),getReviewConnections:async()=>({items:[]}),getReviewEvents:async()=>({items:[]}),getReviewAnalyses:async()=>({items:[]}),getReviewLearningContext:async()=>({ref,attempt:{attempt_id:'attempt'},review_state:{revision},next_actions:[action],related_attempts:[],source_evidence:[]})}
 const deps={'../../wrongbook/analysis-state':{createReviewAnalysisController},'../../wrongbook/learning-state':{createReviewLearningController},'../../wrongbook/submission':{browserReviewStorage:()=>({getItem:()=>null,setItem(){}})},'../../services/review-api':api,'../../services/api':{getReverseGoals:async()=>[]}}
 const x=await setup('components/wrongbook/ReviewLearningHub.vue',{detail:{...ref,revision},manualDirty:false,canWrite:true},deps)
 await new Promise(r=>setImmediate(r));x.state.l.state.selection.tasks[0].title='我的未保存任务';x.state.l.state.preview={confirmation_token:'old'};revision=2;x.props.detail={...ref,revision};await vue.nextTick();await new Promise(r=>setImmediate(r));assert.equal(x.state.l.state.preview,null);assert.equal(x.state.l.state.selection.tasks[0].title,'我的未保存任务');assert.equal(x.state.l.dirty(),true);x.scope.stop()
})

test('mounted learning hub preserves manual diagnosis and focuses its actual confirmation region',async()=>{
 let adopted=0,focused=0,confirmed=0
 const a={state:vue.reactive({context:null}),open:async()=>{},invalidate(){},dirty:()=>false}
 const l={state:vue.reactive({preview:null,receipt:null}),open(){},setSelection(){},invalidate(){},dirty:()=>false,previewAdoption:async()=>{adopted++},confirm:async()=>{confirmed++;return false}}
 const props={detail:{wrong_id:'w',revision:1},manualDirty:true,canWrite:true}
 const deps={'../../wrongbook/analysis-state':{createReviewAnalysisController:()=>a},'../../wrongbook/learning-state':{createReviewLearningController:()=>l},'../../wrongbook/submission':{browserReviewStorage:()=>({})},'../../services/review-api':{getReviewAttempts:async()=>({items:[]}),getReviewConnections:async()=>({items:[]}),getReviewEvents:async()=>({items:[]})},'../../services/api':{getReverseGoals:async()=>[]}}
 const x=await setup('components/wrongbook/ReviewLearningHub.vue',props,deps)
 await new Promise(r=>setImmediate(r));await x.state.adopt('analysis',['careless']);assert.equal(adopted,0)
 x.state.confirmation.value={focus(){focused++}};l.state.preview={confirmation_token:'t'};await vue.nextTick();await vue.nextTick();assert.equal(focused,1)
 x.state.mode.value='adopt';await x.state.confirm();assert.equal(confirmed,0);x.scope.stop()
})

test('the hub cannot start undo while evidence is still loading',async()=>{
 let attempted=0,finish
 const a={state:vue.reactive({context:null}),invalidate(){},dirty:()=>false},l={state:vue.reactive({preview:null}),invalidate(){},dirty:()=>false,previewUndo:async()=>{attempted++}}
 const deps={'../../wrongbook/analysis-state':{createReviewAnalysisController:()=>a},'../../wrongbook/learning-state':{createReviewLearningController:()=>l},'../../wrongbook/submission':{browserReviewStorage:()=>({})},'../../services/review-api':{getReviewAttempts:()=>new Promise(r=>{finish=r}),getReviewConnections:async()=>({items:[]}),getReviewEvents:async()=>({items:[]})},'../../services/api':{getReverseGoals:async()=>[]}}
 const x=await setup('components/wrongbook/ReviewLearningHub.vue',{detail:{wrong_id:'w'},canWrite:true},deps)
 await x.state.undo('saved');assert.equal(attempted,0);finish({items:[]});x.scope.stop()
})

test('mounted question allows exact input recovery after refresh but locks an in-memory unknown request',async()=>{
 const submission={state:vue.reactive({answer:'',busy:false,stale:false,receipt:null,uncertain:true,retryNeedsInput:true})}
 const x=await setup('components/wrongbook/ReviewQuestion.vue',{question:{},identity:'q',submission},{'../../wrongbook/presentation':{presentReviewQuestion:()=>({options:[]})}})
 assert.equal(x.state.locked.value,false);submission.state.retryNeedsInput=false;assert.equal(x.state.locked.value,true);x.scope.stop()
})

test('historical analysis renders its own quote even when the current context has different text',async()=>{
 const c={state:vue.reactive({analysis:{source_evidence:[{evidence_id:'quote',quote:'当时原文'}]},context:{source_evidence:[{evidence_id:'quote',quote:'现在的另一段原文'}]}})}
 const x=await setup('components/wrongbook/ReviewAnalysis.vue',{c},{'../../wrongbook/presentation':{}});assert.equal(x.state.quoteFor('quote'),'当时原文');x.scope.stop()
})

test('learning artifact switching and refresh both protect its real answer draft',async()=>{
 const route={query:{}},deps={'vue-router':{useRoute:()=>route,useRouter:()=>({replace:async()=>{}}),onBeforeRouteLeave(){},onBeforeRouteUpdate(){}},'element-plus':{ElMessage:{info(){}}}}
 const x=await setup('views/LearningWorkspace.vue',{},deps),s=x.state
 s.artifacts.value=[{artifact_id:'first'},{artifact_id:'second'}];s.activeArtifactId.value='first';s.artifactPanel.value={dirty:()=>true,canLeave:async()=>false}
 await s.selectArtifact('second');assert.equal(s.activeArtifactId.value,'first')
 let prevented=false;s.guardRefresh({preventDefault(){prevented=true}});assert.equal(prevented,true)
 prevented=false;const event={preventDefault(){prevented=true}};s.guardUnload(event);assert.equal(prevented,true);x.scope.stop()
})

test('mounted review entries invalidate before reopening after a restore or expired identity',async()=>{
 const listeners=new Map();let invalidations=0
 globalThis.window={addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener(){}}
 const c={state:{},submission:{},open:async()=>{},invalidate(){invalidations++},dispose(){},dirty:()=>false}
 const x=await setup('components/wrongbook/ReviewEntry.vue',{artifactId:'a',questionIndex:0,question:{}},{'../../wrongbook/entry-state':{createReviewEntry:()=>c},'../../wrongbook/submission':{browserReviewStorage:()=>({})}})
 for(const fn of x.mounted)fn()
 for(const event of ['filemate:data-restored','filemate:session-expired']){assert.equal(typeof listeners.get(event),'function');await listeners.get(event)()}
 assert.equal(invalidations,2);x.scope.stop();delete globalThis.window
})

test('graph leave permission is reset by the actual review answer, not the removed legacy input',async()=>{
 let confirmations=0;const state=vue.reactive({answer:'',selected:null,work:null,practicePreview:null,pathPreview:null,linksPreview:null,relatedPreview:null}),review={state:{},submission:{state:vue.reactive({answer:'',busy:false,uncertain:false,receipt:null})}}
 const controller={state,dirty:()=>!!review.submission.state.answer,open:async()=>{},chooseQuestion:async()=>{review.submission.state.answer=''},dispose(){}}
 const x=await setup('components/course-graph/CourseLearning.vue',{scope:'s',courseId:'c',nodeId:'n'}, {'element-plus':{ElMessageBox:{confirm:async()=>{confirmations++}}},'../../wrongbook/entry-state':{createReviewEntry:()=>review},'../../wrongbook/submission':{browserReviewStorage:()=>({})},'../../course-graph/learning-state':{createCourseLearningController:()=>controller},'../../services/api':{getReverseGoals:async()=>[]}})
 review.submission.state.answer='draft A';await x.state.choose({});await vue.nextTick();review.submission.state.answer='draft B';await vue.nextTick();await x.state.choose({})
 assert.equal(confirmations,2);x.scope.stop()
})
