import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { chromium } from 'playwright'

const root = process.cwd()
const graphUrl = /\/api\/knowledge-graph(?:\?.*)?$/
const base = process.env.FILEMATE_WEB_URL || 'http://127.0.0.1:5173'
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR || '_working/v2-2-20261001')
const db = path.resolve(process.env.FILEMATE_ACCEPTANCE_DB || '_working/v2-2-20261001/acceptance.db')
assert.ok(db.startsWith(path.join(root, '_working') + path.sep), 'Use an isolated _working database')
fs.mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || (process.platform === 'win32' ? 'msedge' : undefined), headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
const page = await context.newPage()
page.setDefaultTimeout(12000)
const errors = []
page.on('pageerror', error => errors.push(String(error)))
const results = []
const button = name => page.getByRole('button', { name, exact: true })
const graphData = async () => (await (await context.request.get(base + '/api/knowledge-graph')).json()).data
const open = async () => { await page.goto(base + '/knowledge-graph'); await page.getByRole('heading', { name: '我的知识图谱', exact: true }).waitFor(); await page.waitForFunction(() => !document.querySelector('.loading')) }
let sourceId, batchId, artifactId, nodeId, savedPlanId
async function check(name, kind, run) {
  console.log(`RUN ${name}`)
  try { const evidence = await run(); results.push({ name, kind, passed: true, evidence }); console.log(`PASS ${name}`) }
  catch (error) { results.push({ name, kind, passed: false, error: String(error) }); console.log(`FAIL ${name}: ${error}`) }
}
async function waitText(selector, text) { await page.waitForFunction(({ selector, text }) => document.querySelector(selector)?.textContent.includes(text), { selector, text }) }
async function practice(answer) {
  await page.goto(`${base}/ai-tools?source=${sourceId}&artifact=${artifactId}`)
  await page.getByLabel('练习答案', { exact: true }).fill(answer)
  await button('提交答案').click()
  await page.locator('.answer-feedback').waitFor()
}

try {
  await check('empty graph shows no invented profile', 'real_ui_api', async () => {
    await open()
    const data = await graphData()
    assert.equal(data.nodes.length, 0)
    assert.equal(data.profile.attempt_count, 0)
    assert.equal(data.profile.study_time, null)
    assert.match(await page.locator('.profile-panel').innerText(), /还没有有效作答记录/)
    assert.equal(await button('提取并预览').isDisabled(), true)
  })
  await check('real licensed material import parse extract confirm', 'real_material_ui_api', async () => {
    await page.goto(base + '/import?intent=study')
    const uploaded = page.waitForResponse(response => response.url().endsWith('/knowledge/import') && response.request().method() === 'POST')
    await page.locator('#primary-file-upload').setInputFiles(path.join(root, 'scripts/acceptance/fixtures/hello_algo_heap_excerpt.txt'))
    const response = await uploaded
    assert.equal(response.status(), 200)
    sourceId = (await response.json()).data.source_id
    const source = (await (await context.request.get(`${base}/knowledge/sources/${sourceId}`)).json()).data
    assert.match(source.raw_text, /堆作为完全二叉树的一个特例/)
    await open()
    await page.locator('.extract-fields select').first().selectOption(sourceId)
    await button('提取并预览').click()
    await button('确认加入图谱').waitFor()
    let data = await graphData()
    batchId = data.batches[0].batch_id
    assert.equal(data.nodes.length, 0)
    assert.ok(data.batches[0].edge_count >= 2)
    const batchDetail = (await (await context.request.get(`${base}/api/knowledge-graph/batches/${batchId}`)).json()).data
    assert.ok(batchDetail.payload.edges.length >= 2)
    await button('确认加入图谱').click()
    await waitText('.map-panel', '3 个知识点')
    data = await graphData()
    assert.deepEqual(data.nodes.map(node => node.label).sort(), ['堆', '完全二叉树', '优先队列'].sort())
    assert.equal(data.edges.length, 2)
    assert.ok(data.nodes.every(node => node.chunk_id && source.raw_text.includes(node.excerpt)))
    nodeId = data.nodes.find(node => node.label === '堆').id
    await button('列表').click()
    await page.locator('.node-list button').filter({ hasText: /^堆/ }).click()
    assert.match(await page.locator('.evidence-panel').innerText(), /待评测/)
    return { sourceId, batchId, nodes: 3, edges: 2, material: 'Hello Algo, CC BY-NC-SA 4.0' }
  })
  await check('real exercise UI changes profile and wrongbook then recovers', 'real_self_authored_exercise_ui_api', async () => {
    const python = process.platform === 'win32' ? path.join(root, '.venv/Scripts/python.exe') : path.join(root, '.venv/bin/python')
    const seeded = spawnSync(python, ['scripts/acceptance/seed_graph_exercise.py', '--db', db, '--source', sourceId], { cwd: root, encoding: 'utf8', env: { ...process.env, PYTHONUTF8: '1' } })
    assert.equal(seeded.status, 0, seeded.stderr)
    artifactId = JSON.parse(seeded.stdout.trim()).artifact_id
    await practice('数组')
    assert.match(await page.locator('.answer-feedback').innerText(), /已记录到错题本/)
    await open()
    await waitText('.profile-panel', '1道错题尚未标记掌握')
    let data = await graphData()
    let heap = data.nodes.find(node => node.id === nodeId)
    assert.equal(heap.metrics.sample_count, 1)
    assert.equal(heap.metrics.correct_rate, 0)
    assert.equal(data.profile.pending_wrong_count, 1)
    await page.locator('.weakness-list button').filter({ hasText: '堆' }).click()
    assert.match(await page.locator('.evidence-panel').innerText(), /堆是哪种二叉树/)
    await button('预览学习路径').click()
    await button('确认加入学习计划').click()
    await page.locator('.saved-plan').waitFor()
    data = await graphData()
    savedPlanId = data.plans[0].plan_id
    assert.equal(data.plans.length, 1)
    await button('撤销此计划').click()
    await waitText('.plan-history', '已撤销')
    await button('恢复此计划').click()
    await waitText('.plan-history', '进行中')
    for (let i = 0; i < 2; i++) {
      await page.goto(base + '/wrongbook')
      await page.getByRole('textbox', { name: '重新回答：堆是哪种二叉树的一个特例？' }).fill('完全二叉树')
      await button('提交复习').click()
      await page.waitForFunction(() => document.querySelector('.result') || document.querySelector('.empty-state'))
    }
    await open()
    data = await graphData()
    heap = data.nodes.find(node => node.id === nodeId)
    assert.equal(heap.metrics.sample_count, 3)
    assert.equal(heap.metrics.wrong_count, 1)
    assert.equal(heap.metrics.pending_wrong_count, 0)
    assert.equal(data.profile.weaknesses.length, 0)
    assert.equal(data.profile.observed_node_count, 1)
    assert.ok(data.events.some(event => event.action === 'plan_create'))
    return { sample_count: 3, correct_rate: heap.metrics.correct_rate, pending_wrong_count: 0, savedPlanId }
  })
  await check('cancel undo and repeated restore preserve evidence', 'real_ui_api', async () => {
    await open()
    const details = page.locator('.batch').first()
    await details.locator('summary').click()
    await button('撤销此批图谱').click()
    await page.getByRole('button', { name: '取消', exact: true }).click()
    assert.equal((await graphData()).nodes.length, 3)
    await button('撤销此批图谱').click()
    await page.getByRole('button', { name: '撤销', exact: true }).last().click()
    await waitText('.map-panel', '0 个知识点')
    await button('恢复此批图谱').click()
    await waitText('.map-panel', '3 个知识点')
    const repeated = await context.request.post(`${base}/api/knowledge-graph/batches/${batchId}/restore`)
    assert.equal(repeated.status(), 200)
    const data = await graphData()
    assert.equal(data.nodes.find(node => node.id === nodeId).metrics.sample_count, 3)
    assert.equal(data.events.filter(event => event.action === 'restore').length, 1)
  })
  await check('search zoom drag and responsive layouts', 'real_ui', async () => {
    for (const width of [375, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 1000 })
      await open()
      await page.locator('.chart canvas').waitFor()
      await button('放大图谱').click()
      await button('缩小图谱').click()
      const box = await page.locator('.chart').boundingBox()
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
      await page.mouse.down(); await page.mouse.move(box.x + box.width / 2 + 40, box.y + box.height / 2 + 30, { steps: 5 }); await page.mouse.up()
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
      await page.screenshot({ path: path.join(out, `graph-${width}.png`), fullPage: true })
      await page.locator('.content-scroll').evaluate(element => { element.scrollTop = 0 })
      await page.screenshot({ path: path.join(out, `graph-profile-${width}.png`), fullPage: true })
    }
    await page.getByLabel('查找知识点或资料').fill('不存在的知识点')
    await page.getByRole('heading', { name: '没有找到匹配的知识点' }).waitFor()
    await button('清除搜索').click()
    await button('列表').click()
    await page.getByLabel('查找知识点或资料').fill('完全二叉树')
    await page.waitForFunction(() => document.querySelectorAll('.node-list button').length === 1)
    assert.equal(await page.locator('.node-list button').count(), 1)
    await page.locator('.node-list button').click()
    assert.match(await page.locator('.evidence-panel').innerText(), /完全二叉树/)
    await page.screenshot({ path: path.join(out, 'graph-evidence.png'), fullPage: true })
  })
  await check('network interruption keeps graph and retries real API', 'MOCK_network_fault_real_api', async () => {
    await open()
    await page.route(graphUrl, route => route.abort('failed'))
    await button('刷新证据').click()
    await page.locator('.message.error').waitFor()
    assert.match(await page.locator('.map-panel').innerText(), /3 个知识点/)
    await page.unroute(graphUrl)
    await button('重新加载').click()
    await page.waitForFunction(() => !document.querySelector('.message.error') && !document.querySelector('.loading'))
    assert.equal((await graphData()).nodes.length, 3)
  })
  await check('extraction interruption preserves graph and permits retry', 'MOCK_network_fault_real_api', async () => {
    await page.locator('.extract-fields select').first().selectOption(sourceId)
    await page.route('**/api/knowledge-graph/drafts', route => route.abort('failed'))
    await button('提取并预览').click()
    await page.locator('.message.error').waitFor()
    assert.equal((await graphData()).nodes.length, 3)
    await page.unroute('**/api/knowledge-graph/drafts')
    await button('提取并预览').click()
    await button('确认加入图谱').waitFor()
    await button('撤销草稿').click()
    await page.getByRole('button', { name: '撤销', exact: true }).last().click()
    await page.waitForFunction(() => !Array.from(document.querySelectorAll('.batch-actions button')).some(button => button.textContent === '确认加入图谱'))
    assert.equal((await graphData()).nodes.length, 3)
  })
  await check('no runtime errors', 'real_ui', async () => { assert.deepEqual(errors, []) })
} finally {
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify({ results, errors }, null, 2))
  await browser.close()
}
console.log(`${results.filter(item => item.passed).length}/${results.length} passed`)
if (results.some(item => !item.passed)) process.exitCode = 1
