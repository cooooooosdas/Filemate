import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { parse, compileScript } from '@vue/compiler-sfc'
import ts from 'typescript'
import * as vue from 'vue'

test('same_work_recovers_ready_questions_without_overwriting_human_edits', async () => {
  const source = await readFile(new URL('../src/components/course-graph/CoursePractice.vue', import.meta.url), 'utf8')
  const { descriptor } = parse(source)
  const script = compileScript(descriptor, { id: 'practice-component-regression' }).content
  const executable = ts.transpileModule(script, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', executable)(name => { assert.equal(name, 'vue'); return vue }, module, module.exports)
  const props = vue.reactive({ work: { work_id: 'w', status: 'running', payload: {} }, preview: null, receipt: null, busy: false })
  const events = [], scope = vue.effectScope()
  let exposed
  scope.run(() => { exposed = module.exports.default.setup(props, { expose() {}, emit: (...args) => events.push(args) }) })
  const question = { stem: '原始问题', answer: '栈', citation_ids: ['q'] }
  props.work = { work_id: 'w', status: 'ready', payload: { questions: [question] } }; await vue.nextTick()
  assert.equal(exposed.edited.value.length, 1)
  exposed.toggle(0); exposed.edit(0, 'stem', '人工修订')
  props.work = structuredClone(vue.toRaw(props.work)); await vue.nextTick()
  assert.equal(exposed.edited.value[0].stem, '人工修订'); assert.equal(exposed.accepted.value.has(0), true)
  assert.equal(events.at(-1)[1][0].question.stem, '人工修订')
  props.work = { work_id: 'other', status: 'ready', payload: { questions: [question] } }; await vue.nextTick()
  assert.equal(exposed.edited.value[0].stem, '原始问题'); assert.equal(exposed.accepted.value.size, 0)
  scope.stop()
})
