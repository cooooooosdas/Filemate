import assert from 'node:assert/strict'
import test from 'node:test'

async function helpers(){ return import('../src/interview/assessment.ts') }
const dimensions = [80, 60, 70, null, null, 90].map((score, i) => ({ id: `d${i}`, name: `维度${i+1}`, score }))

test('partial radar has only real score points and never connects missing axes through zero', async () => {
  const { radarGeometry, scoreLabel } = await helpers()
  const chart = radarGeometry(dimensions)
  assert.equal(chart.points.length, 4)
  assert.equal(chart.polygon, '')
  assert.equal(scoreLabel(null), '待评测')
  assert.equal(scoreLabel(0), '0')
  assert.ok(radarGeometry(dimensions.map(d => ({ ...d, score: 80 }))).polygon)
})

test('late context from a previous session cannot replace current report', async () => {
  const { createAssessmentFlow } = await helpers()
  let release
  const flow = createAssessmentFlow({
    context: async id => id === 'old' ? new Promise(r => release = r) : ({ input_digest:'new', history:[] }),
    read: async () => { throw Error('unexpected') },
  })
  const old = flow.load('old')
  await flow.load('new')
  release({ input_digest:'old', history:[] })
  await old
  assert.equal(flow.state.context.input_digest, 'new')
  assert.equal(flow.state.sessionId, 'new')
})

test('lost response retries identical command; stale evidence invalidates it and clears consent', async () => {
  const { createAssessmentFlow } = await helpers()
  let digest='hash-one', fail=true
  const sent=[]
  const flow=createAssessmentFlow({
    context: async()=>({input_digest:digest,enabled:true,answered:1,history:[]}),
    create: async (id, body)=>{sent.push(structuredClone(body));if(fail){fail=false;throw Error('offline')}return {assessment_id:'a',status:'succeeded',report:{}}},
  })
  await flow.load('one')
  await flow.generate('model', true)
  assert.match(flow.state.error,/offline/)
  await flow.generate('model', true)
  assert.deepEqual(sent[0],sent[1])
  digest='hash-two';await flow.load('one')
  await flow.generate('model', false)
  assert.equal(sent.length,2)
  await flow.generate('local', false)
  assert.notEqual(sent[2].request_key,sent[0].request_key)
  assert.equal(sent[2].expected_digest,'hash-two')
})

test('failed new assessment preserves readable old report and surfaces failure without fake score', async () => {
  const { createAssessmentFlow }=await helpers()
  const old={assessment_id:'old',report:{version:'2.6'},status:'succeeded'}
  const flow=createAssessmentFlow({context:async()=>({input_digest:'x',enabled:true,answered:1,history:[{assessment_id:'old',interview_id:'one',status:'succeeded'}]}),
    read:async()=>old,create:async()=>({status:'failed',report:null,error_code:'invalid_evidence'})})
  await flow.load('one')
  await flow.generate('model',true)
  assert.equal(flow.state.selected.assessment_id,'old')
  assert.match(flow.state.error,/核验|证据/)
})

test('history selection race and disposal suppress late updates', async () => {
  const { createAssessmentFlow }=await helpers()
  let release
  const flow=createAssessmentFlow({context:async()=>({input_digest:'x',history:[]}),
    read:async(id,key)=>key==='slow'?new Promise(r=>release=r):({assessment_id:key,report:{}})})
  await flow.load('one')
  const slow=flow.select('one','slow')
  await flow.select('one','fast')
  release({assessment_id:'slow',report:{}});await slow
  assert.equal(flow.state.selected.assessment_id,'fast')
  flow.dispose()
  await flow.load('two')
  assert.equal(flow.state.sessionId,'one')
})
