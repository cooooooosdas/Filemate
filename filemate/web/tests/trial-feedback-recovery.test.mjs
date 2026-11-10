import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { parse, compileScript } from '@vue/compiler-sfc'
import ts from 'typescript'
import * as vue from 'vue'

async function setup(kind = 'feedback') {
  const source = await readFile(new URL('../src/components/TrialFeedback.vue', import.meta.url), 'utf8')
  const script = compileScript(parse(source).descriptor, { id:'feedback-recovery' }).content.replace(/import\.meta\.env\.\w+/g, '"true"')
  const code = ts.transpileModule(script, { compilerOptions:{ module:ts.ModuleKind.CommonJS } }).outputText
  const module = { exports:{} }, scope = vue.effectScope()
  const runtime = { ...vue, onMounted(){}, onBeforeUnmount(){} }
  new Function('require','module','exports',code)(name => name === 'vue' ? runtime : name === 'vue-router' ? {onBeforeRouteLeave(){}} : {}, module,module.exports)
  let state
  scope.run(() => { state = module.exports.default.setup({}, {expose(){},emit(){}}) })
  const stored = { ...state.form, description:'原始提交的问题描述，已保存到服务器的反馈正文。' }
  state.form.description = '查询原请求之前，用户又修改了当前尚未保存的反馈内容。'
  state.writer.value = { state:{receipt:null}, async recover(){ this.state.receipt={kind,status:'saved',record_id:'one'} } }
  state.client.value = { async detail(){ return {record_id:'one',kind,content:stored} } }
  return {state,stored,close(){scope.stop()} }
}

test('recovered receipt marks only persisted feedback as saved and preserves later edits', async () => {
  const x = await setup()
  await x.state.recover()
  assert.equal(x.state.saved.value,JSON.stringify(x.stored))
  assert.equal(x.state.dirty(),true)
  x.close()
})

test('recovering a reflection receipt does not mark feedback text as saved', async () => {
  const x = await setup('reflection')
  await x.state.recover()
  assert.equal(x.state.saved.value,'')
  assert.equal(x.state.dirty(),true)
  x.close()
})
