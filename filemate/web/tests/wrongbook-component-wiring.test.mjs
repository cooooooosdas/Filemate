import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { parse, compileScript } from '@vue/compiler-sfc'
import ts from 'typescript'
import * as vue from 'vue'

async function setup(file,props={},deps={}){
 const mounted=[],listeners=new Map(),scope=vue.effectScope()
 const source=await readFile(new URL('../src/'+file,import.meta.url),'utf8')
 const {descriptor}=parse(source),script=compileScript(descriptor,{id:'wrongbook-wiring'}).content.replace(/import\.meta\.env\.\w+/g,'true')
 const code=ts.transpileModule(script,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,module={exports:{}}
 const runtime={...vue,onMounted:fn=>mounted.push(fn),onUnmounted(){},onBeforeUnmount(){},onActivated(){},onDeactivated(){}}
 new Function('require','module','exports',code)(name=>name==='vue'?runtime:deps[name]||{},module,module.exports)
 let state;scope.run(()=>{state=module.exports.default.setup(vue.reactive(props),{expose(){},emit(){}})})
 return {state,mounted,scope,listeners}
}

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

test('mounted question allows exact input recovery after refresh but locks an in-memory unknown request',async()=>{
 const submission={state:vue.reactive({answer:'',busy:false,stale:false,receipt:null,uncertain:true,retryNeedsInput:true})}
 const x=await setup('components/wrongbook/ReviewQuestion.vue',{question:{},identity:'q',submission},{'../../wrongbook/presentation':{presentReviewQuestion:()=>({options:[]})}})
 assert.equal(x.state.locked.value,false);submission.state.retryNeedsInput=false;assert.equal(x.state.locked.value,true);x.scope.stop()
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
