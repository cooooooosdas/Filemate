import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const root = process.cwd()
const base = process.env.FILEMATE_WEB_URL || 'http://127.0.0.1:5187'
const api = process.env.FILEMATE_API_URL || 'http://127.0.0.1:8016'
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR || '_working/v2-5-20261001/ui')
assert.ok(out.startsWith(path.join(root, '_working') + path.sep))
fs.mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true })
const page = await context.newPage()
page.setDefaultTimeout(20000)
const errors = [], requests = [], results = []
page.on('pageerror', error => errors.push(String(error)))
page.on('request', request => requests.push({ url: request.url(), method: request.method() }))
const button = name => page.getByRole('button', { name, exact: true })
const data = async path => (await (await context.request.get(api + path)).json()).data
const jobs = () => data('/api/career/positions')
const rounds = () => data(`/api/career/positions/${pid}/trainings`)
const dialog = () => page.getByRole('dialog')
let pid, written, interview, review, codingId, importedId
const correctAnswers = { stack: 1, search: 2, cpp: 2, network: 2 }
async function open(training = '') {
  await page.goto(`${base}/career${pid ? `?position=${pid}${training ? `&training=${training}` : ''}` : ''}`)
  await page.locator('.catalog-row').first().waitFor()
  if (pid) await page.locator('.position-detail').waitFor()
  if (training) await page.locator('.training-detail').waitFor()
}
async function check(name, kind, run) {
  console.log('RUN', name)
  try { const evidence = await run(); results.push({ name, kind, passed: true, evidence }); console.log('PASS', name) }
  catch (error) { results.push({ name, kind, passed: false, error: String(error) }); console.log('FAIL', name, String(error)); await page.screenshot({ path: path.join(out, `failure-${results.length}.png`) }) }
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 2))
}
async function create(kind, name) {
  await button(name).click()
  const response = page.waitForResponse(r => r.url() === api + `/api/career/positions/${pid}/trainings` && r.request().method() === 'POST')
  await dialog().getByRole('button', { name: '确认创建训练', exact: true }).click()
  const accepted = await response
  assert.equal(accepted.status(), 200)
  const row = (await accepted.json()).data
  assert.equal(row.kind, kind)
  await page.locator('.training-detail').waitFor()
  await page.waitForFunction(id => new URL(location.href).searchParams.get('training') === id, row.training_id)
  await page.getByRole('heading', { name: { written: '模拟笔试', interview: '岗位面试', review: '训练对比快照' }[kind], exact: true }).waitFor()
  return row
}

try {
  await check('empty database shows pending evidence and does not auto-save catalog', 'real_ui_api', async () => {
    await open()
    assert.equal((await jobs()).length, 0)
    assert.equal(await page.locator('.catalog-row').count(), 3)
    assert.match(await page.locator('.career-page').innerText(), /还没有保存岗位/)
    await page.getByLabel('搜索企业、岗位或地区').fill('未收录企业XYZ')
    assert.equal(await page.locator('.catalog-row').count(), 0)
    await page.getByLabel('搜索企业、岗位或地区').fill('')
    await page.getByLabel('岗位类别', { exact: true }).selectOption('社招参考')
    assert.equal(await page.locator('.catalog-row').count(), 1)
    assert.match(await page.locator('.catalog-row').innerText(), /腾讯/)
    await page.getByLabel('岗位类别', { exact: true }).selectOption('')
  })
  await check('official provenance review cancel and confirmed save', 'real_ui_api', async () => {
    await page.locator('.catalog-row').first().getByRole('button').click()
    assert.equal(await page.getByLabel('企业名称', { exact: true }).getAttribute('readonly'), '')
    assert.match(await page.getByRole('link', { name: '打开岗位来源' }).getAttribute('href'), /^https:\/\/talent.baidu.com\//)
    await button('确认保存岗位').click()
    await dialog().getByRole('button', { name: '继续核对', exact: true }).click()
    assert.equal((await jobs()).length, 0)
    const response = page.waitForResponse(r => r.url() === api + '/api/career/positions' && r.request().method() === 'POST')
    await button('确认保存岗位').click()
    await dialog().getByRole('button', { name: '确认保存', exact: true }).click()
    const saved = (await (await response).json()).data
    pid = saved.position_id
    await page.locator('.position-detail').waitFor()
    assert.equal((await jobs()).length, 1)
    const evidence = await data(`/api/career/positions/${pid}/evidence`)
    assert.ok(evidence.skills.every(s => s.status === '待评测'))
    return { position_id: pid, source_url: saved.position.source_url }
  })
  await check('cancelled training creates nothing and confirmed written hides answer keys', 'real_ui_api', async () => {
    await button('创建模拟笔试').click()
    await dialog().getByRole('button', { name: '取消', exact: true }).click()
    assert.equal((await rounds()).length, 0)
    written = await create('written', '创建模拟笔试')
    assert.equal(written.payload.questions.length, 4)
    assert.ok(written.payload.questions.every(q => !('correct' in q) && !('explanation' in q)))
    assert.equal(await button('提交基础题').isDisabled(), true)
    await open(written.training_id)
    assert.equal(await page.locator('.basic-question').count(), 4)
  })
  await check('actual answers score persist and duplicate submission does not create another result', 'real_ui_api', async () => {
    for (const [id, index] of Object.entries(correctAnswers)) await page.locator(`input[name="${id}"][value="${index}"]`).check()
    await button('提交基础题').click()
    await page.getByText('本轮基础题：4 / 4 正确。此项只描述本轮作答。', { exact: true }).waitFor()
    const response = await context.request.post(api + `/api/career/trainings/${written.training_id}/answers`, { data: { answers: correctAnswers } })
    assert.equal(response.status(), 200)
    const conflict = await context.request.post(api + `/api/career/trainings/${written.training_id}/answers`, { data: { answers: { ...correctAnswers, stack: 0 } } })
    assert.equal(conflict.status(), 409)
    await open(written.training_id)
    await page.getByText('本轮基础题：4 / 4 正确。此项只描述本轮作答。', { exact: true }).waitFor()
    const evidence = await data(`/api/career/positions/${pid}/evidence`)
    assert.equal(evidence.written.length, 1)
    assert.equal(evidence.skills.find(s => s.label === '数据结构').written_correct_count, 1)
  })
  await check('original algorithm link selects requested problem and runs real isolated C++', 'real_cpp_ui_api', async () => {
    await page.getByRole('link', { name: /成绩区间起点/ }).click()
    await page.getByLabel('选择题目', { exact: true }).waitFor({ timeout: 60000 })
    await page.waitForFunction(() => document.querySelector('[aria-label="选择题目"]')?.value === 'lower-bound', null, { timeout: 60000 })
    assert.equal(await page.getByLabel('选择题目', { exact: true }).inputValue(), 'lower-bound')
    await page.getByText('隔离评测已就绪', { exact: true }).waitFor({ timeout: 60000 })
    await page.waitForFunction(() => !document.querySelector('.editor-loading'), null, { timeout: 60000 })
    const solutions = JSON.parse(fs.readFileSync(path.join(root, 'scripts/acceptance/fixtures/cpp_solutions.json'), 'utf8'))
    await page.locator('.monaco-editor .view-lines').click()
    await page.keyboard.press('Control+A'); await page.keyboard.insertText(solutions['lower-bound'])
    const pending = page.waitForResponse(r => r.url() === api + '/api/programming/submissions' && r.request().method() === 'POST')
    await button('提交并评测').click()
    const response = await pending
    codingId = (await response.json()).data.submission_id
    await page.waitForFunction(() => document.querySelector('.result-panel .state-text')?.textContent === '已完成', null, { timeout: 60000 })
    const submission = await data(`/api/programming/submissions/${codingId}`)
    assert.equal(submission.result.verdict, 'AC')
    await open(written.training_id)
    const evidence = await data(`/api/career/positions/${pid}/evidence`)
    assert.equal(evidence.skills.find(s => s.label === '算法').coding_ac_count, 1)
    await page.getByRole('link', { name: `AC · 提交 ${codingId.slice(0, 8)}`, exact: true }).first().click()
    await page.getByText('隔离评测已就绪', { exact: true }).waitFor({ timeout: 60000 })
    assert.match(await page.locator('.result-panel').innerText(), /AC/)
    await open(written.training_id)
    return { submission_id: codingId, verdict: 'AC', tests: submission.result.tests.length }
  })
  await check('company interview reuses real local V2.4 session answer and report', 'real_ui_api', async () => {
    interview = await create('interview', '创建岗位面试')
    await page.getByRole('link', { name: '进入本场岗位面试与复盘', exact: true }).click()
    await page.getByRole('textbox', { name: '当前训练回答', exact: true }).waitFor()
    assert.match(await page.locator('.interview-page').innerText(), /百度/)
    await page.getByRole('textbox', { name: '当前训练回答', exact: true }).fill('合成训练：我负责校园查询系统的索引优化，先比较慢查询，再用执行计划检查。调整索引后对照相同输入验证延时与结果。')
    await button('提交并进入下一题').click()
    await page.getByText('第 2 / 5 题', { exact: true }).waitFor()
    await button('生成本地复盘报告').click()
    await page.getByRole('button', { name: '导出 JSON', exact: true }).waitFor()
    const stored = await data(`/interviews/${interview.interview_id}`)
    assert.equal(stored.turns.length, 1); assert.equal(stored.assessed_turn_count, 0)
    await open(interview.training_id)
    assert.equal((await data(`/api/career/positions/${pid}/evidence`)).interviews[0].answered, 1)
    return { interview_id: interview.interview_id, answered: 1, assessed: 0 }
  })
  await check('persisted comparison snapshot and actual JSON Markdown downloads', 'real_ui_api', async () => {
    review = await create('review', '保存训练对比')
    assert.equal(review.payload.comparison.written.length, 1)
    assert.equal(review.payload.comparison.interviews[0].answered, 1)
    for (const [name, extension] of [['导出训练 JSON', 'json'], ['导出训练 Markdown', 'md']]) {
      const download = page.waitForEvent('download'); await button(name).click(); const file = await download
      const target = path.join(out, 'career-report.' + extension); await file.saveAs(target)
      const content = fs.readFileSync(target, 'utf8'); assert.match(content, /百度/); assert.match(content, /correct_rate/)
      if (extension === 'json') assert.equal(JSON.parse(content).payload.position_revision, 1)
    }
    await page.screenshot({ path: path.join(out, 'comparison-desktop.png') })
  })
  await check('edit preserves old snapshot and stale version returns conflict', 'real_ui_api', async () => {
    await button('修改本地岗位').click()
    await page.getByLabel('岗位名称', { exact: true }).fill('用户核对后端训练岗位')
    await button('确认保存岗位修改').click()
    await dialog().getByRole('button', { name: '确认保存', exact: true }).click()
    await page.getByRole('heading', { name: '用户核对后端训练岗位', exact: true }).waitFor()
    const row = await data(`/api/career/positions/${pid}`); assert.equal(row.revision, 2)
    assert.equal((await data(`/api/career/trainings/${review.training_id}`)).payload.position_revision, 1)
    const stale = await context.request.post(api + `/api/career/positions/${pid}/trainings`, { data: { kind: 'review', confirmed: true, expected_revision: 1, request_key: 'stale_version_12345678' } })
    assert.equal(stale.status(), 409)
    await open(review.training_id)
  })
  await check('undo cancel restore preserve all completed evidence', 'real_ui_api', async () => {
    await button('撤销岗位').click(); await dialog().getByRole('button', { name: '取消', exact: true }).click()
    assert.equal((await data(`/api/career/positions/${pid}`)).active, 1)
    await button('撤销岗位').click(); await dialog().getByRole('button', { name: '确认变更', exact: true }).click()
    await button('恢复岗位').waitFor()
    assert.equal(await button('创建模拟笔试').count(), 0)
    assert.equal((await rounds()).length, 3)
    await button('恢复岗位').click(); await dialog().getByRole('button', { name: '确认变更', exact: true }).click()
    await button('创建模拟笔试').waitFor()
    assert.equal((await data(`/api/career/positions/${pid}`)).active, 1)
  })
  await check('read failure preserves existing evidence and retry recovers', 'injected_network_ui', async () => {
    await page.route('**/api/career/positions/*/evidence', route => route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"合成读取故障"}' }))
    await button('刷新训练证据').click()
    await page.getByRole('alert').waitFor()
    assert.match(await page.locator('.position-detail').innerText(), /用户核对后端训练岗位/)
    await page.unroute('**/api/career/positions/*/evidence')
    await button('重试读取').click()
    await page.waitForFunction(() => !document.querySelector('[role="alert"]'))
  })
  await check('local file import cancel preserves draft and lost save response retry is idempotent', 'real_ui_injected_transport', async () => {
    await button('导入岗位').click()
    await page.getByLabel('企业名称', { exact: true }).fill('合成测试企业')
    await page.getByLabel('岗位名称', { exact: true }).fill('数据库训练')
    await page.getByLabel('地区', { exact: true }).fill('本地回归')
    await page.locator('input[type=file]').setInputFiles({ name: '岗位.txt', mimeType: 'text/plain', buffer: Buffer.from('岗位要求：理解数据库事务与SQL查询，并熟悉Python编程。') })
    await button('提取待核对要求').click()
    await page.getByText('已提取待核对要求，请检查原句后确认保存。', { exact: true }).waitFor()
    await button('导入岗位').click(); await dialog().getByRole('button', { name: '继续核对', exact: true }).click()
    assert.equal(await page.getByLabel('企业名称', { exact: true }).inputValue(), '合成测试企业')
    let lost = false
    await page.route('**/api/career/positions', async route => {
      if (route.request().method() === 'POST' && !lost) { lost = true; await route.fetch(); await route.abort('failed') } else await route.continue()
    })
    await button('确认保存岗位').click(); await dialog().getByRole('button', { name: '确认保存', exact: true }).click()
    await page.getByRole('alert').waitFor()
    assert.equal(await page.getByLabel('企业名称', { exact: true }).inputValue(), '合成测试企业')
    assert.equal((await jobs()).filter(p => p.position.company === '合成测试企业').length, 1)
    await button('确认保存岗位').click(); await dialog().getByRole('button', { name: '确认保存', exact: true }).click()
    await page.locator('.position-detail').waitFor()
    importedId = (await jobs()).find(p => p.position.company === '合成测试企业').position_id
    assert.equal((await jobs()).length, 2)
    await page.unroute('**/api/career/positions')
    await open(review.training_id)
    return { accepted_response_lost: lost, unique_saved_positions: 2 }
  })
  await check('mobile tablet desktop have no horizontal overflow and no runtime error', 'real_responsive_ui', async () => {
    for (const width of [375, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 1000 })
      await page.evaluate(async () => { await Promise.all(document.getAnimations().filter(animation => animation.effect?.getTiming().iterations !== Infinity).map(animation => animation.finished.catch(() => {}))) })
      await page.locator('.position-detail').waitFor()
      const overflow = await page.evaluate(() => {
        const root = document.querySelector('.career-page')
        return { body: document.documentElement.scrollWidth > innerWidth, career: root.scrollWidth > root.clientWidth + 1, left: root.getBoundingClientRect().left, right: root.getBoundingClientRect().right }
      })
      assert.equal(overflow.body, false, `${width}: body`); assert.equal(overflow.career, false, `${width}: career`); assert.ok(overflow.left >= 0 && overflow.right <= width, `${width}: visible bounds`)
      await page.evaluate(() => { const scroll = document.querySelector('.content-scroll'); if (scroll) scroll.scrollTop = 0 })
      await page.screenshot({ path: path.join(out, `career-${width}.png`) })
    }
    assert.deepEqual(errors, [])
  })
  await check('preview cancel and confirmed deletion keep programming and interview', 'real_ui_api', async () => {
    await button('预览删除岗位').click(); await dialog().getByRole('button', { name: '保留岗位', exact: true }).click()
    assert.equal((await rounds()).length, 3)
    await button('预览删除岗位').click(); await dialog().getByRole('button', { name: '确认删除岗位', exact: true }).click()
    await page.getByRole('heading', { name: '先选一个你要训练的岗位', exact: true }).waitFor()
    assert.equal((await jobs()).length, 1)
    assert.equal((await jobs())[0].position_id, importedId)
    assert.equal((await context.request.get(api + `/interviews/${interview.interview_id}`)).status(), 200)
    assert.equal((await context.request.get(api + `/api/programming/submissions/${codingId}`)).status(), 200)
    assert.equal((await context.request.get(api + `/api/career/trainings/${written.training_id}`)).status(), 404)
  })
  assert.equal(requests.filter(r => !r.url.startsWith(api) && !r.url.startsWith(base) && /^https?:/.test(r.url)).length, 0)
  const summary = { passed: results.filter(r => r.passed).length, total: results.length, errors, external_network_requests: 0, results }
  fs.writeFileSync(path.join(out, 'summary.json'), JSON.stringify(summary, null, 2))
  console.log(JSON.stringify({ passed: summary.passed, total: summary.total, errors }))
  if (summary.passed !== summary.total || errors.length) process.exitCode = 1
} finally { await browser.close() }
