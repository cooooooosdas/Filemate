import assert from 'node:assert/strict'
import crypto from 'node:crypto'
import fs from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.FILEMATE_WEB_URL || 'https://filemate.asia'
const out = process.env.FILEMATE_EVIDENCE_DIR || '_working/account-auth/live-api'
await fs.mkdir(out, { recursive: true })
const browser = await chromium.launch({ channel: process.platform === 'win32' ? 'msedge' : undefined })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
const other = await browser.newContext()
const page = await context.newPage()
const checks = [], dependencies = [], errors = []
page.on('pageerror', error => errors.push(String(error)))
const headers = { Origin: base, 'X-FileMate-Action': 'account' }
let source, interview, questionSet, graphDraft
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
async function check(name, action) {
  const started = Date.now()
  try { const detail = await action(); checks.push({ name, passed: true, elapsed_ms: Date.now() - started, ...(detail || {}) }) }
  catch (error) { checks.push({ name, passed: false, elapsed_ms: Date.now() - started, error: String(error) }) }
}
async function api(path, method = 'get', data) {
  const response = await context.request[method](base + path, { headers, ...(data ? { data } : {}), timeout: 150000 })
  const json = await response.json()
  assert.equal(response.status(), 200, `${method} ${path}: ${json.error || response.status()}`)
  assert.equal(json.success, true)
  return json.data
}
try {
  await check('synthetic account logs in using actual production session', async () => {
    const email = `synthetic-api-${crypto.randomUUID()}@example.invalid`
    await api('/api/auth/register', 'post', { email, display_name: '合成接口验收', password: crypto.randomBytes(24).toString('base64url'), keep_guest_data: false, remember: false })
    assert.equal((await api('/api/auth/me')).user.email, email)
    assert.equal((await api('/api/health')).version, process.env.FILEMATE_EXPECTED_VERSION || '1.3.0-alpha.4')
  })
  for (const path of ['/sessions', '/knowledge/sources', '/wrongbook', '/review/today', '/study-plans', '/interview/questions', '/analytics/overview', '/evaluation/feedback/summary', '/api/knowledge-graph', '/api/career/status', '/api/career/catalog', '/api/career/positions', '/api/career/overview', '/api/programming/status', '/api/programming/problems', '/api/programming/overview', '/api/digital-human/playbacks', '/interview/review/status', '/trust/overview', '/goals']) {
    await check(`actual API ${path}`, async () => {
      const result = await api(path)
      if (path === '/api/programming/status' && !result.ready) dependencies.push({ feature: 'C++ execution', ready: false, provider: result.provider, reason: result.error })
      if (result?.enabled === false) dependencies.push({ feature: path, ready: false, reason: 'Module disabled in deployed configuration' })
      assert.notEqual(result, undefined)
    })
    await delay(1000)
  }
  await check('original synthetic Markdown imports and retrieves citation chunks', async () => {
    const text = '# 栈、队列与二分查找\n\n【原创合成工程资料】不代表真实学生学习效果。\n\n## 栈\n栈是一种后进先出的线性结构。后进先出简称LIFO；依次将1、2、3入栈，再连续出栈，顺序是3、2、1。\n\n## 队列\n队列是一种先进先出的线性结构。先进先出简称FIFO；元素在队尾加入，在队首取出。\n\n## 二分查找\n二分查找是在有序数组中定位目标的算法。每次比较中间值，并将候选区间减半，时间复杂度为O(log n)。数组访问前必须检查下标，测试应覆盖空数组、单元素、首尾目标及目标不存在。\n\n## 关系\n栈用于深度优先搜索。队列用于广度优先搜索。二分查找依赖数组有序。'
    const response = await context.request.post(base + '/knowledge/import', { headers, multipart: { file: { name: `合成接口验收-${crypto.randomUUID()}.md`, mimeType: 'text/markdown', buffer: Buffer.from(text) } } })
    assert.equal(response.status(), 200)
    source = (await response.json()).data
    assert.equal((await api(`/knowledge/sources/${source.source_id}`)).raw_text, text)
    assert.ok((await api('/knowledge/search?q=' + encodeURIComponent('栈 后进先出') + '&source_id=' + source.source_id)).length)
  })
  if (source) {
    for (const kind of ['summary', 'notes', 'knowledge_cards', 'questions']) {
      await check(`actual configured model generates and persists ${kind}`, async () => {
        const result = await api(`/knowledge/sources/${source.source_id}/artifacts`, 'post', { artifact_type: kind, count: 3, allow_external_model: true })
        assert.ok(result.artifact_id)
        if (kind === 'summary') assert.ok(typeof result.content === 'string' && result.content.length > 20)
        if (kind === 'notes') assert.ok(result.content.sections.length)
        if (kind === 'knowledge_cards') assert.ok(result.content.every(card => card.front && card.back))
        if (kind === 'questions') assert.ok(result.content.length && result.content.every(question => question.stem && question.answer && question.question_type))
        assert.deepEqual((await api(`/knowledge/artifacts/${result.artifact_id}`)).content, result.content)
        assert.equal((await other.request.get(base + `/knowledge/artifacts/${result.artifact_id}`)).status(), 404)
        if (kind === 'questions') questionSet = result
        return { artifact_type: kind, persisted: true, other_device_status: 404 }
      })
      await delay(1500)
    }
    if (questionSet) await check('actual generated question records a wrong answer and successful re-practice', async () => {
      const question = questionSet.content[0]
      const request = { artifact_id: questionSet.artifact_id, question_index: 0, expected_question: question }
      const wrong = await api('/quiz/attempts', 'post', { ...request, user_answer: '【合成接口验收错误答案】' })
      assert.equal(wrong.is_correct, false)
      assert.ok((await api('/wrongbook')).length)
      for (let attempt = 0; attempt < 2; attempt++) {
        const correct = await api('/quiz/attempts', 'post', { ...request, user_answer: question.answer })
        assert.equal(correct.is_correct, true)
      }
      assert.ok((await api('/wrongbook?mastered=true')).some(item => item.mastered === true || item.mastered === 1))
      return { persisted: true, sample_kind: 'synthetic engineered answers; not student mastery' }
    })
    await check('actual model answers with valid citations and persisted context', async () => {
      const contextRecord = await api(`/knowledge/sources/${source.source_id}/contexts`, 'post', {})
      const answer = await api('/ai/chat', 'post', { ctx_id: contextRecord.ctx_id, question: '栈遵循什么顺序？将1、2、3入栈后，连续出栈的顺序是什么？' })
      assert.equal(answer.answerable, true)
      assert.ok(answer.citations.length && /后进先出|LIFO/.test(answer.answer))
      const restored = await api('/ai/contexts/' + contextRecord.ctx_id)
      assert.ok(restored.chat_history.some(message => message.role === 'assistant' && message.content === answer.answer))
      return { cited: true, persisted: true }
    })
    await check('actual model creates a source-grounded graph draft without applying it silently', async () => {
      const draft = await api('/api/knowledge-graph/drafts', 'post', { source_id: source.source_id, mode: 'llm', allow_external_model: true })
      assert.equal(draft.status, 'draft')
      assert.ok(draft.payload.nodes.length)
      assert.equal((await api('/api/knowledge-graph')).nodes.length, 0)
      graphDraft = draft
      return { status: draft.status, node_count: draft.payload.nodes.length }
    })
    if (graphDraft) await check('own graph confirmation, undo and restore persist and repeat idempotently', async () => {
      for (const [action, status] of [['confirm', 'confirmed'], ['undo', 'undone'], ['restore', 'confirmed']]) {
        const path = `/api/knowledge-graph/batches/${graphDraft.batch_id}/${action}`
        const changed = await api(path, 'post', {})
        assert.equal(changed.status, status)
        assert.deepEqual(await api(path, 'post', {}), changed)
        const graph = await api('/api/knowledge-graph')
        assert.equal(graph.nodes.length, action === 'undo' ? 0 : graphDraft.payload.nodes.length)
      }
      return { persisted: true, idempotent: true }
    })
    await check('source-grounded simulated interview and actual model scoring are persisted', async () => {
      interview = await api('/interviews', 'post', { target_role: '合成软件开发测试岗位', scenario: '求职面试', difficulty: '入门', source_id: source.source_id, allow_external_analysis: true })
      assert.ok(interview.interview_id && interview.questions.length)
      const answer = await api(`/interviews/${interview.interview_id}/answers`, 'post', { answer: '这是一份原创合成验收资料。栈是后进先出的线性结构，用于深度优先搜索；队列先进先出，用于广度优先搜索。二分查找依赖数组有序，逐次比较中间值并减半候选区间，复杂度为O(log n)。我会验证空数组、单元素、首尾目标和不存在目标，并先检查下标。', question_index: 0, request_key: crypto.randomUUID() })
      assert.equal(answer.turns.length, 1)
      const mode = answer.turns[0].scoring_mode
      assert.equal(mode, 'llm', `Expected actual model scoring; received ${mode}`)
      assert.deepEqual((await api(`/interviews/${interview.interview_id}`)).turns, answer.turns)
      return { scoring_mode: mode, persisted: true }
    })
  }
} finally {
  if (interview) await check('own synthetic interview deletion uses confirmation token', async () => {
    const preview = await api(`/interviews/${interview.interview_id}/delete-preview`)
    await api(`/interviews/${interview.interview_id}`, 'delete', { confirmed: true, confirmation_token: preview.confirmation_token })
  })
  if (source) await check('only own synthetic source is deleted after UI confirmation', async () => {
    await page.goto(base + '/knowledge')
    await page.getByRole('button', { name: `删除资料：${source.original_name}`, exact: true }).click()
    const dialog = page.locator('.el-message-box')
    await dialog.waitFor()
    assert.ok((await dialog.innerText()).includes(source.original_name))
    await dialog.getByRole('button', { name: '删除', exact: true }).click()
    await page.getByRole('button', { name: `删除资料：${source.original_name}`, exact: true }).waitFor({ state: 'detached' })
    assert.equal((await context.request.get(base + `/knowledge/sources/${source.source_id}`)).status(), 404)
  })
  await context.request.post(base + '/api/auth/logout', { headers, data: {} }).catch(() => {})
  await browser.close()
  const report = { passed: checks.every(check => check.passed) && !errors.length, all_features_ready: !dependencies.length, sample_kind: 'original_synthetic_material_actual_production_API_and_model', base, checks, dependencies, errors, scope: 'Only self-created synthetic account and materials; no request mocks, API bridge or real student records; engineering connectivity does not measure learning benefit.' }
  await fs.writeFile(`${out}/summary.json`, JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report, null, 2))
  if (!report.passed) process.exitCode = 1
}
