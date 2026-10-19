import assert from 'node:assert/strict'
import test from 'node:test'
import { reactive } from 'vue'
import { configurationForScenario, legacyScenario, createDraftController } from '../src/interview/configuration.ts'

test('legacy routes retain language and scenario distinctions', () => {
  assert.equal(legacyScenario(configurationForScenario('保研复试', '标准')), '保研复试')
  assert.equal(legacyScenario(configurationForScenario('英语面', '标准')), '英语面')
  assert.equal(legacyScenario(configurationForScenario('压力面', '标准')), '压力面')
  assert.equal(configurationForScenario('未知', '标准'), null)
  assert.equal(legacyScenario({...configurationForScenario('算法面', '标准'), language:'en-US'}), null)
  assert.equal(legacyScenario({...configurationForScenario('技术面', '标准'), question_strategy:'mixed'}), null)
})

test('loading remote draft never invokes a save or restores local inputs', async () => {
  let calls=0
  const c=createDraftController({read:async()=>({enabled:true,draft:{revision:2,content:{target_role:'旧草稿'}}}),save:async()=>{calls++}})
  await c.load()
  assert.equal(c.state.remote.content.target_role,'旧草稿')
  assert.equal(calls,0)
})

test('failed save retains original key and payload for retry; conflicts never erase input', async () => {
  const calls=[];let fail=true
  const c=createDraftController({read:async()=>({enabled:true,draft:{revision:0,content:null}}),save:async input=>{
    calls.push(structuredClone(input)); if(fail){fail=false;throw new Error('网络中断')}
    return {revision:1,content:input.content}
  }},()=> 'request-key-001')
  await c.load(); const content={target_role:'新草稿',configuration:configurationForScenario('技术面','标准')}
  await c.save(content);await c.save(content)
  assert.deepEqual(calls[0],calls[1])
  assert.equal(c.state.remote.content.target_role,'新草稿')
  assert.equal(c.state.error,'')
})

test('disposed controller ignores late read result',async()=>{
  let finish
  const c=createDraftController({read:()=>new Promise(r=>finish=r),save:async()=>{throw new Error('unused')}})
  const loading=c.load();c.dispose();finish({enabled:true,draft:{revision:9,content:{target_role:'late'}}});await loading
  assert.equal(c.state.remote.revision,0)
})

test('Vue reactive configuration can be saved as a stable plain snapshot',async()=>{
  let payload
  const c=createDraftController({read:async()=>({enabled:true,draft:{revision:0,content:null}}),save:async input=>{payload=input;return {revision:1,content:input.content}}})
  await c.load()
  const configuration=reactive(configurationForScenario('技术面','标准'))
  await c.save({configuration,target_role:'保存输入',source_id:'',project_name:'',project_details:''})
  configuration.duration_minutes=20
  assert.equal(payload.content.configuration.duration_minutes,10)
  assert.equal(c.state.remote.revision,1)
})
