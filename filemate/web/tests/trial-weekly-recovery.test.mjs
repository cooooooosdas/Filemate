import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { parse, compileScript } from '@vue/compiler-sfc'
import ts from 'typescript'
import * as vue from 'vue'
import { createTrialRecordState } from '../src/today/trial-record-state.ts'

test('recovering saved reflection preserves the edited draft and ignores late identity replies', async () => {
  const source = await readFile(new URL('../src/components/today/WeeklyReflection.vue', import.meta.url), 'utf8')
  const script = compileScript(parse(source).descriptor,{id:'weekly-recovery'}).content
  const code = ts.transpileModule(script,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText
  const module={exports:{}}, scope=vue.effectScope(), values=new Map()
  const storage={getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)}
  const runtime={...vue,onMounted(){},onBeforeUnmount(){}}
  const selected={goal_id:'goal',course_id:null,source_ids:[]}
  let finishDetail
  const client={readWeekly:async()=>({revision:'rev'}),findRequest:async()=>({record_id:'one',kind:'reflection',status:'saved'}),detail:()=>new Promise(resolve=>{finishDetail=resolve})}
  const deps={'../../services/trial-api':client,'../../today/trial-record-state':{createTrialRecordState,trialSessionStorage:()=>storage,trialEpoch:()=>''}}
  new Function('require','module','exports',code)(name=>name==='vue'?runtime:deps[name]??{},module,module.exports)
  let state
  const props=vue.reactive({scope:selected,identity:'one',bundle:{}})
  scope.run(()=>{state=module.exports.default.setup(props,{expose(){},emit(){}})})
  await new Promise(resolve=>setImmediate(resolve))
  state.notes.value='新的未保存反思';state.reason.value='difficulty'
  state.controller.state.pending={kind:'reflection',request_key:'request_key_long_enough'}
  const recovering=state.recover()
  await new Promise(resolve=>setImmediate(resolve))
  finishDetail({record_id:'one',kind:'reflection',content:{scope:selected,notes:'原来已保存的反思',reason:'time'}})
  await recovering
  assert.equal(state.notes.value,'新的未保存反思')
  assert.equal(state.dirty(),true)
  assert.equal(state.ready.value,false)
  state.controller.state.pending={kind:'reflection',request_key:'request_key_long_enough'}
  const late=state.recover()
  await new Promise(resolve=>setImmediate(resolve))
  props.identity='two';await vue.nextTick()
  finishDetail({record_id:'one',kind:'reflection',content:{scope:selected,notes:'原空间私密反思',reason:'time'}})
  await late
  assert.equal(state.notes.value,'')
  assert.equal(state.saved.value,'')
  scope.stop()
})
