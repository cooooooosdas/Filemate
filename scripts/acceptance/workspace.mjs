import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const base = process.env.FILEMATE_WEB_URL
const fixture = process.env.FILEMATE_UI_FIXTURE_BASE
assert.ok(new URL(base).protocol === 'https:' && ['localhost', '127.0.0.1'].includes(new URL(base).hostname))
assert.equal(new URL(fixture).hostname, '127.0.0.1')
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR)
assert.ok(out.startsWith(path.resolve('_working') + path.sep))
fs.mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1100 },
  ignoreHTTPSErrors: process.env.FILEMATE_ACCEPTANCE_INSECURE_TLS === '1',
  httpCredentials: { username: process.env.FILEMATE_ACCEPTANCE_BASIC_USER, password: process.env.FILEMATE_ACCEPTANCE_BASIC_PASSWORD } })
const page = await context.newPage()
page.setDefaultTimeout(15000)
const checks = [], errors = [], externalRequests = []
page.on('pageerror', error => errors.push(String(error)))
page.on('request', request => { if (!['127.0.0.1', 'localhost'].includes(new URL(request.url()).hostname)) externalRequests.push(request.url()) })
page.on('dialog', dialog => dialog.dismiss())
async function check(name, run, kind = 'actual_compiled_vue_tls_api_with_synthetic_model_http') {
  try { await run(); checks.push({ name, kind, passed: true }) }
  catch (error) { checks.push({ name, kind, passed: false, error: String(error) }); await page.screenshot({ path: path.join(out, `failure-${checks.length}.png`), fullPage: true }) }
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(checks, null, 2))
  console.log(`${checks.at(-1).passed ? 'PASS' : 'FAIL'} ${name}`)
}
async function api(route) {
  const response = await context.request.get(base + route)
  assert.ok(response.ok(), `${route}: ${response.status()}`)
  const body = await response.json()
  assert.equal(body.success, true)
  return body.data
}
async function model(route, data) {
  const headers = { Authorization: 'Bearer ' + process.env.FILEMATE_UI_FIXTURE_TOKEN }
  const response = data ? await context.request.post(fixture + route, { headers, data }) : await context.request.get(fixture + route, { headers })
  assert.ok(response.ok())
  return response.json()
}
const pane = name => page.locator('.mobile-panes').getByRole('button', { name, exact: true })
async function openSource(source, artifact) {
  await page.goto(`${base}/ai-tools?source=${source}${artifact ? '&artifact=' + artifact : ''}`)
  await page.locator('.model-consent').waitFor()
  await page.waitForFunction(() => Boolean(new URL(location.href).searchParams.get('ctx')))
  await page.locator('.composer textarea:not(:disabled)').waitFor({ state: 'attached' })
}
async function generate(label, count) {
  await pane('学习内容').click()
  const create = page.getByRole('button', { name: '创建学习内容', exact: true })
  if (await create.isVisible()) await create.click()
  await page.locator('.generation-kinds').getByRole('button', { name: label, exact: true }).click()
  if (count) await page.locator('.generation-count').getByRole('radio', { name: `${count}${label === '练习' ? '题' : '张'}`, exact: true }).check()
  const response = page.waitForResponse(response => response.request().method() === 'POST' && /\/knowledge\/sources\/[^/]+\/artifacts$/.test(new URL(response.url()).pathname))
  await page.getByRole('button', { name: '生成' + label, exact: true }).click()
  const body = await (await response).json()
  assert.equal(body.success, true)
  const item = body.data
  await page.waitForFunction(id => new URL(location.href).searchParams.get('artifact') === id, item.artifact_id)
  await page.locator('.learning-artifact h3').getByText(item.title, { exact: true }).waitFor()
  return item
}
async function select(item) {
  await pane('学习内容').click()
  await page.locator('.artifact-picker button').filter({ has: page.getByText(item.title, { exact: true }) }).click()
  await page.waitForFunction(id => new URL(location.href).searchParams.get('artifact') === id, item.artifact_id)
}
async function importSource(file) {
  if (new URL(page.url()).pathname !== '/import') {
    await page.locator('.global-import').click()
    await page.waitForURL('**/import?intent=study')
  }
  await page.locator('#primary-file-upload').setInputFiles(file)
  await page.getByRole('link', { name: '开始学习', exact: false }).click()
  await page.locator('.model-consent').waitFor()
  await page.waitForFunction(() => Boolean(new URL(location.href).searchParams.get('ctx')))
}
const original = '原创合成资料，仅用于工程回归，非真实学生资料。\n数据结构：栈与队列\n栈遵循后进先出（LIFO）。push 入栈，pop 出栈。\n队列遵循先进先出（FIFO）。enqueue 入队，dequeue 出队。\n'
let sourceId, ctxId, notes, cards, questions, summary, secondSource
try {
  await check('empty workspace has one large entry and no console dropdowns', async () => {
    await page.goto(base + '/ai-tools')
    await page.getByRole('link', { name: '添加第一份资料', exact: false }).waitFor()
    assert.equal(await page.locator('.learning-workspace select, .learning-workspace .el-select').count(), 0)
    assert.equal(await page.locator('.mobile-panes button').count(), 3)
    assert.equal((await model('/stats')).calls.length, 0)
    await page.screenshot({ path: path.join(out, 'workspace-empty.png'), fullPage: true })
  })
  await check('browser import creates real Source and Context without model calls', async () => {
    await importSource({ name: '工程合成-栈与队列.txt', mimeType: 'text/plain', buffer: Buffer.from(original) })
    await page.locator('.model-consent').waitFor()
    await page.waitForFunction(() => Boolean(new URL(location.href).searchParams.get('ctx')))
    sourceId = new URL(page.url()).searchParams.get('source'); ctxId = new URL(page.url()).searchParams.get('ctx')
    assert.ok(sourceId && ctxId)
    const source = await api('/knowledge/sources/' + sourceId)
    assert.match(source.raw_text, /后进先出（LIFO）/)
    assert.equal((await api('/ai/contexts/' + ctxId)).source_id, sourceId)
    assert.equal((await model('/stats')).calls.length, 0)
    assert.equal(await page.locator('.generation-kinds button').count(), 4)
  })
  await check('shared explicit model permission gates both explanation and generation', async () => {
    const consent = page.locator('.model-consent input')
    assert.equal(await consent.isChecked(), false)
    await page.locator('.composer textarea').fill('栈为什么后进先出（LIFO）？')
    assert.equal(await page.getByRole('button', { name: '发送', exact: true }).isDisabled(), true)
    assert.equal(await page.getByRole('button', { name: '生成笔记', exact: true }).isDisabled(), true)
    await consent.check()
    assert.equal(await page.getByRole('button', { name: '发送', exact: true }).isEnabled(), true)
    assert.equal((await model('/stats')).calls.length, 0)
  })
  await check('task switching retains the unsent question and original context; refresh and leaving protect it', async () => {
    const text = await page.locator('.composer textarea').inputValue()
    await pane('学习内容').click()
    await page.locator('.generation-kinds').getByRole('button', { name: '卡片', exact: true }).click()
    await pane('对话').click()
    assert.equal(await page.locator('.composer textarea').inputValue(), text)
    assert.equal(new URL(page.url()).searchParams.get('ctx'), ctxId)
    await page.getByRole('button', { name: '刷新当前页面', exact: true }).click()
    await page.getByText('问题尚未发送，请先发送或清空后再刷新。', { exact: true }).waitFor()
    await page.locator('.sidebar .nav-item[href="/"]').click()
    await page.getByRole('button', { name: '继续编辑', exact: true }).click()
    await page.getByRole('dialog', { name: '切换学习内容？', exact: true }).waitFor({ state: 'hidden' })
    assert.equal(await page.locator('.composer textarea').inputValue(), text)
    assert.equal(new URL(page.url()).pathname, '/ai-tools')
  })
  await check('retrieval uses the real model adapter and persists a verifiable citation', async () => {
    await model('/control', { delay: 2 })
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await page.getByRole('button', { name: '刷新当前页面', exact: true }).click()
    await page.getByText('请等当前学习操作完成后再刷新。', { exact: true }).waitFor()
    await page.locator('.message.assistant').waitFor()
    await page.locator('.citations button').first().click()
    assert.match(await page.locator('.citation-focus').innerText(), /后进先出/)
    const persisted = await api('/ai/contexts/' + ctxId)
    assert.equal(persisted.chat_history.length, 2)
    assert.equal(persisted.chat_history[1].citations[0].source_id, sourceId)
    assert.equal((await model('/stats')).calls.at(-1).kind, 'chat')
    await page.getByRole('button', { name: '关闭引用片段', exact: true }).click()
  })
  await check('notes generate once and save to the same Source with a recoverable artifact URL', async () => {
    notes = await generate('笔记')
    assert.equal(notes.source_id, sourceId)
    assert.equal(notes.metadata.external_model_authorized, true)
    assert.equal((await api(`/knowledge/sources/${sourceId}/artifacts`)).length, 1)
    assert.equal((await api('/ai/contexts/' + ctxId)).chat_history.length, 2)
    assert.equal(await page.locator('.note-content section').count(), 2)
    assert.equal((await model('/stats')).calls.at(-1).kind, 'notes')
  })
  await check('saved content opens in reading mode; generation expands only when requested', async () => {
    assert.equal(await page.locator('.generation-controls').count(), 0)
    const reader = await page.locator('.learning-artifact h3').boundingBox()
    assert.ok(reader.y < page.viewportSize().height && reader.width > 100)
    await page.getByRole('button', { name: '创建学习内容', exact: true }).click()
    assert.equal(await page.locator('.generation-kinds button').count(), 4)
    await page.getByRole('button', { name: '返回阅读', exact: true }).click()
    assert.equal(await page.locator('.generation-controls').count(), 0)
  })
  await check('card count is sent through the real adapter; readable flip and paging keep recall unscored', async () => {
    cards = await generate('卡片', 10)
    assert.equal(cards.content.length, 10)
    assert.equal((await model('/stats')).calls.at(-1).requested_count, 10)
    const flip = page.locator('.flashcard')
    assert.equal(await flip.getAttribute('aria-expanded'), 'false')
    await flip.click()
    await page.getByText('参考解释', { exact: true }).waitFor()
    assert.equal(await flip.getAttribute('aria-expanded'), 'true')
    await page.getByRole('button', { name: '下一张卡片', exact: true }).click()
    assert.equal(await flip.getAttribute('aria-expanded'), 'false')
    assert.match(await page.locator('.pager').innerText(), /2 \/ 10/)
    assert.equal((await api('/analytics/overview')).quiz_attempt_count, 0)
  })
  await check('practice shares the generation flow and uses actual deterministic marking and wrongbook persistence', async () => {
    questions = await generate('练习', 5)
    assert.equal(questions.content.length, 5)
    assert.equal((await model('/stats')).calls.at(-1).requested_count, 5)
    await page.locator('.choice input[value="B"]').check()
    await page.getByRole('button', { name: '提交答案', exact: true }).click()
    await page.getByText('已记录到错题本', { exact: true }).waitFor()
    const wrong = await api('/wrongbook')
    assert.equal(wrong.length, 1)
    assert.equal(wrong[0].artifact_id, questions.artifact_id)
    await page.getByRole('button', { name: '下一题', exact: true }).click()
    await page.locator('.choice input[value="A"]').check()
    await page.getByRole('button', { name: '提交答案', exact: true }).click()
    await page.locator('.answer-feedback > strong').getByText('回答正确', { exact: true }).waitFor()
    const analytics = await api('/analytics/overview')
    assert.equal(analytics.quiz_attempt_count, 2)
    assert.equal((await api('/wrongbook')).length, 1)
  })
  await check('summary uses the fourth visible task and all saved contents open directly', async () => {
    summary = await generate('摘要')
    assert.equal(summary.artifact_type, 'summary')
    assert.match(await page.locator('.read-content').innerText(), /合成资料摘要/)
    assert.equal(await page.locator('.artifact-picker button').count(), 4)
    for (const item of [notes, cards, questions, summary]) await select(item)
    assert.equal(await page.locator('.learning-workspace select').count(), 0)
  })
  await check('artifact switching preserves unsent questions and current-round exercise feedback', async () => {
    await pane('对话').click()
    await page.locator('.composer textarea').fill('先留在这里的问题')
    await select(notes)
    await select(questions)
    await page.locator('.answer-feedback > strong').getByText('回答正确', { exact: true }).waitFor()
    assert.equal(await page.locator('.composer textarea').inputValue(), '先留在这里的问题')
    assert.equal(new URL(page.url()).searchParams.get('ctx'), ctxId)
    await pane('对话').click()
    await page.locator('.composer textarea').fill('')
  })
  await check('actual export downloads the saved artifact bytes', async () => {
    await select(notes)
    const downloading = page.waitForEvent('download')
    await page.locator('.learning-artifact').getByRole('button', { name: '导出', exact: true }).click()
    const download = await downloading
    const file = path.join(out, 'synthetic-notes.txt')
    await download.saveAs(file)
    assert.deepEqual(JSON.parse(fs.readFileSync(file, 'utf8')), notes.content)
  })
  await check('invalid fixture output and temporary model failure create no artifact; retry saves a real result', async () => {
    const before = (await api(`/knowledge/sources/${sourceId}/artifacts`)).length
    await page.getByRole('button', { name: '创建学习内容', exact: true }).click()
    for (const mode of ['invalid', 'unavailable']) {
      await model('/control', { mode })
      await page.locator('.generation-kinds').getByRole('button', { name: '摘要', exact: true }).click()
      await page.getByRole('button', { name: '生成摘要', exact: true }).click()
      await page.locator('.artifact-workbench > .inline-error').waitFor()
      assert.equal((await api(`/knowledge/sources/${sourceId}/artifacts`)).length, before)
      assert.equal(new URL(page.url()).searchParams.get('artifact'), notes.artifact_id)
    }
    await page.locator('.artifact-workbench > .inline-error').getByRole('button', { name: '重试', exact: true }).click()
    await page.waitForFunction(id => new URL(location.href).searchParams.get('artifact') !== id, notes.artifact_id)
    assert.equal((await api(`/knowledge/sources/${sourceId}/artifacts`)).length, before + 1)
  }, 'explicit_local_model_http_fault_injection_actual_api_persistence')
  await check('hard reload restores saved content and complete chat while model permission resets', async () => {
    await openSource(sourceId, questions.artifact_id)
    assert.equal(await page.locator('.model-consent input').isChecked(), false)
    assert.equal(await page.locator('.learning-artifact .choice input').count(), 4)
    assert.equal(await page.locator('.message').count(), 2)
    assert.equal((await api('/wrongbook')).length, 1)
    assert.equal(new URL(page.url()).searchParams.get('artifact'), questions.artifact_id)
  })
  await check('source catalog and new conversation reuse stored text without invoking the model', async () => {
    const before = (await model('/stats')).calls.length
    await pane('资料').click()
    await page.locator('.source-search input').fill('队列')
    assert.equal(await page.locator('.source-list button').count(), 1)
    await page.getByRole('button', { name: '新建对话', exact: true }).click()
    await page.waitForFunction(id => new URL(location.href).searchParams.get('ctx') !== id, ctxId)
    assert.equal((await api('/ai/contexts/' + ctxId)).chat_history.length, 2)
    assert.equal((await api(`/knowledge/sources/${sourceId}/artifacts`)).length, 5)
    assert.equal((await model('/stats')).calls.length, before)
  })
  await check('import and source change cancellation preserve the draft without creating a new Source', async () => {
    await page.locator('.composer textarea').fill('不要丢掉这个问题')
    const before = (await api('/knowledge/sources')).length
    await page.locator('.global-import').click()
    await page.getByRole('button', { name: '继续编辑', exact: true }).click()
    await page.getByRole('dialog', { name: '切换学习内容？', exact: true }).waitFor({ state: 'hidden' })
    assert.equal((await api('/knowledge/sources')).length, before)
    assert.equal(await page.locator('.composer textarea').inputValue(), '不要丢掉这个问题')
    await page.locator('.global-import').click()
    await page.getByRole('button', { name: '舍弃问题并切换', exact: true }).click()
    await page.getByRole('dialog', { name: '切换学习内容？', exact: true }).waitFor({ state: 'hidden' })
    await page.waitForURL('**/import?intent=study')
    await importSource({ name: '工程合成-第二份.txt', mimeType: 'text/plain', buffer: Buffer.from(original + '另一份原创工程资料。') })
    await page.waitForFunction(id => new URL(location.href).searchParams.get('source') !== id, sourceId)
    secondSource = new URL(page.url()).searchParams.get('source')
    assert.equal((await api(`/knowledge/sources/${secondSource}/artifacts`)).length, 0)
    assert.equal(await page.locator('.model-consent input').isChecked(), false)
    await page.locator('.composer textarea').fill('第二份的草稿')
    await pane('资料').click()
    await page.locator('.source-search input').fill('栈与队列')
    await page.locator('.source-list button').click()
    await page.getByRole('button', { name: '继续编辑', exact: true }).click()
    await page.getByRole('dialog', { name: '切换学习内容？', exact: true }).waitFor({ state: 'hidden' })
    assert.equal(new URL(page.url()).searchParams.get('source'), secondSource)
    await pane('对话').click()
    assert.equal(await page.locator('.composer textarea').inputValue(), '第二份的草稿')
    await page.locator('.composer textarea').fill('')
  })
  for (const width of [375, 768, 1024, 1440]) await check(`reading, direct tasks and all three panes stay readable within ${width}px`, async () => {
    await page.setViewportSize({ width, height: 1100 })
    await openSource(sourceId, notes.artifact_id)
    for (const name of ['资料', '对话', '学习内容']) {
      await pane(name).click()
      await page.waitForTimeout(300)
      const facts = await page.evaluate(() => {
        const workspace = document.querySelector('.learning-workspace')
        const visible = [...workspace.querySelectorAll('.source-pane, .conversation-pane, .resource-pane')].filter(node => getComputedStyle(node).display !== 'none')
        return { overflow: document.documentElement.scrollWidth > innerWidth,
          title: parseFloat(getComputedStyle(workspace.querySelector('h1')).fontSize),
          panes: visible.map(node => ({ left: node.getBoundingClientRect().left, right: node.getBoundingClientRect().right })),
          controls: [...workspace.querySelectorAll('.mobile-panes button, .generation-kinds button')].filter(node => node.getClientRects().length).map(node => ({ font: parseFloat(getComputedStyle(node).fontSize), height: node.getBoundingClientRect().height })),
        }
      })
      assert.equal(facts.overflow, false)
      assert.ok(facts.title >= 36 && facts.panes.length >= 1)
      assert.ok(facts.panes.every(rect => rect.left >= -1 && rect.right <= width + 1))
      assert.ok(facts.controls.every(control => control.font >= 17 && control.height >= 48))
      fs.writeFileSync(path.join(out, `layout-${width}-${name}.json`), JSON.stringify(facts, null, 2))
      await page.screenshot({ path: path.join(out, `workspace-${width}-${name}.png`), fullPage: true })
    }
    assert.ok(parseFloat(await page.locator('.note-content p').first().evaluate(node => getComputedStyle(node).fontSize)) >= 18)
  })
  await check('reduced-motion leaves card recall and pane transitions fully usable', async () => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await select(cards)
    await page.locator('.flashcard').click()
    await page.getByText('参考解释', { exact: true }).waitFor()
    assert.equal(await page.locator('.resource-pane').evaluate(node => getComputedStyle(node).animationName), 'none')
    await page.locator('.flashcard').click()
    await pane('资料').click()
    assert.equal(await page.locator('.source-pane').evaluate(node => getComputedStyle(node).animationName), 'none')
    await page.emulateMedia({ reducedMotion: 'no-preference' })
  })
  await check('missing Source gives a retryable real error and never fabricates study records', async () => {
    await page.goto(base + '/ai-tools?source=synthetic-missing-source')
    await page.locator('.workspace-error').waitFor()
    assert.equal(await page.locator('.learning-artifact').count(), 0)
    assert.equal(await page.locator('.model-consent').count(), 0)
    await page.locator('.workspace-error').getByRole('button', { name: '重新读取', exact: true }).click()
    await page.locator('.workspace-error').waitFor()
    await openSource(sourceId, notes.artifact_id)
    assert.equal(await page.locator('.note-content section').count(), 2)
  })
  await check('Markdown browser import preserves markup as source text, citations and hash reuse without model calls', async () => {
    await page.setViewportSize({width:1440,height:1100})
    await page.goto(base+'/ai-tools')
    const beforeCalls=(await model('/stats')).calls.length
    const markdown='# 工程合成：栈\n\n```cpp\npush(value); // 入栈\n```\n栈遵循后进先出。\n<script>window.__learningScriptExecuted=true</script>'
    await page.locator('.global-import').click(); await page.waitForURL('**/import?intent=study')
    assert.ok((await page.locator('#primary-file-upload').getAttribute('accept')).includes('.md'))
    await importSource({name:'原创代码笔记.md',mimeType:'text/markdown',buffer:Buffer.from(markdown)})
    await page.locator('.composer textarea:not(:disabled)').waitFor()
    const id=new URL(page.url()).searchParams.get('source')
    assert.ok(id)
    assert.equal((await api('/knowledge/sources/'+id)).raw_text,markdown)
    await pane('资料').click()
    assert.equal(await page.evaluate(()=>window.__learningScriptExecuted),undefined)
    const found=await api('/knowledge/search?q='+encodeURIComponent('栈')+'&source_id='+id)
    assert.ok(found.length>0 && found.every(result=>result.source_id===id))
    assert.equal((await model('/stats')).calls.length,beforeCalls)
    const reused=await context.request.post(base+'/knowledge/import',{multipart:{file:{name:'再次导入.md',mimeType:'text/markdown',buffer:Buffer.from(markdown)}}})
    assert.equal((await reused.json()).data.source_id,id)
    await page.screenshot({path:path.join(out,'markdown-source-1440.png'),fullPage:true})
  })
  await check('C++ learning source stays text through browser upload, reload and context restoration', async () => {
    await page.goto(base+'/ai-tools')
    const beforeCalls=(await model('/stats')).calls.length
    const code='// 原创工程合成源码，只作为学习资料\n#include <iostream>\nint main() { std::cout << "栈遵循后进先出"; }\n'
    await importSource({name:'学习栈.cpp',mimeType:'text/plain',buffer:Buffer.from(code)})
    await page.locator('.composer textarea:not(:disabled)').waitFor()
    const id=new URL(page.url()).searchParams.get('source'),ctx=new URL(page.url()).searchParams.get('ctx')
    assert.ok(id && ctx)
    assert.equal((await api('/knowledge/sources/'+id)).raw_text,code)
    assert.equal((await api('/ai/contexts/'+ctx)).source_id,id)
    await page.reload();await page.locator('.composer textarea:not(:disabled)').waitFor()
    assert.equal(new URL(page.url()).searchParams.get('ctx'),ctx)
    assert.equal((await model('/stats')).calls.length,beforeCalls)
    assert.equal(await page.locator('.learning-artifact').count(),0)
  })
  await check('no browser errors or external requests escape the self-owned synthetic run', async () => {
    assert.deepEqual(errors, [])
    assert.deepEqual(externalRequests, [])
  })
} finally { await browser.close() }
const report = { passed: checks.every(item => item.passed), total: checks.length, checks, errors, externalRequests,
  scope: 'synthetic engineering only: actual compiled Vue + Caddy HTTPS + FastAPI + SQLite + existing LLM HTTP adapter; model output is an explicit local fixture, not real model quality or student learning benefit' }
fs.writeFileSync(path.join(out, 'summary.json'), JSON.stringify(report, null, 2))
console.log(JSON.stringify({ passed: report.passed, total: report.total }))
if (!report.passed) process.exitCode = 1
