import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const root = process.cwd()
const base = process.env.FILEMATE_WEB_URL || 'http://127.0.0.1:5174'
const api = process.env.FILEMATE_API_URL || 'http://127.0.0.1:8002'
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR || '_working/v2-3-20261001/ui')
assert.ok(out.startsWith(path.join(root, '_working') + path.sep))
fs.mkdirSync(out, { recursive: true })
const solutions = JSON.parse(fs.readFileSync(path.join(root, 'scripts/acceptance/fixtures/cpp_solutions.json'), 'utf8'))
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
const page = await context.newPage()
page.setDefaultTimeout(15000)
const errors = []
page.on('pageerror', error => errors.push(String(error)))
const results = []
const button = name => page.getByRole('button', { name, exact: true })
const overview = async () => (await (await context.request.get(api + '/api/programming/overview')).json()).data
async function check(name, kind, run) {
  console.log('RUN', name)
  try { const evidence = await run(); results.push({ name, kind, passed: true, evidence }); console.log('PASS', name) }
  catch (error) { results.push({ name, kind, passed: false, error: String(error) }); console.log('FAIL', name, String(error)) }
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 2))
}
async function open() {
  await page.goto(base + '/programming', { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.getByRole('heading', { name: '编程练习', exact: true }).waitFor({ timeout: 60000 })
  await page.getByRole('textbox', { name: 'C++代码', exact: true }).waitFor({ timeout: 60000 })
  await page.waitForFunction(() => !document.querySelector('.editor-loading'), null, { timeout: 60000 })
  await page.getByText('隔离评测已就绪', { exact: true }).waitFor({ timeout: 60000 })
}
async function setCode(code) { await page.locator('.monaco-editor .view-lines').click(); await page.keyboard.press('Control+A'); await page.keyboard.insertText(code) }
async function submit(code, expected) {
  await setCode(code)
  const created = page.waitForResponse(response => response.url() === api + '/api/programming/submissions' && response.request().method() === 'POST')
  await button('提交并评测').click()
  const response = await created
  assert.equal(response.status(), 200)
  assert.equal(response.request().postDataJSON().code, code, 'UI editor must submit the actual typed code')
  const row = (await response.json()).data
  await page.waitForFunction(() => document.querySelector('.result-panel .state-text')?.textContent === '已完成', null, { timeout: 60000 })
  const data = (await (await context.request.get(api + '/api/programming/submissions/' + row.submission_id)).json()).data
  assert.equal(data.result.verdict, expected)
  return data
}
let wrongId, acceptedId
try {
  await check('empty profile and mature editor load', 'real_ui_api', async () => {
    await open()
    const data = await overview()
    assert.equal(data.profile.categories.find(item => item.tag === '图').accept_rate, null)
    assert.equal(await page.locator('.monaco-editor').count(), 1)
    assert.equal(await page.getByLabel('选择题目', { exact: true }).locator('option').count(), 8)
    assert.equal(await button('提交并评测').isEnabled(), true)
  })
  await check('filters and empty combination preserve draft safety', 'real_ui', async () => {
    await page.getByLabel('题目难度', { exact: true }).selectOption('困难')
    await page.waitForFunction(() => document.querySelector('[aria-label="选择题目"]')?.options.length === 2)
    assert.equal(await page.getByLabel('选择题目', { exact: true }).locator('option').count(), 2)
    await page.getByLabel('知识分类', { exact: true }).selectOption('栈')
    assert.equal(await button('提交并评测').isDisabled(), true)
    await page.getByLabel('知识分类', { exact: true }).selectOption('')
    await page.getByLabel('题目难度', { exact: true }).selectOption('')
    await page.getByLabel('选择题目', { exact: true }).selectOption('array-sum')
    await page.waitForFunction(() => document.querySelector('[aria-label="选择题目"]')?.value === 'array-sum')
  })
  await check('wrong submission produces real per-test evidence and wrongbook', 'real_cpp_ui_api', async () => {
    const data = await submit('#include <iostream>\nint main(){std::cout<<"WRONG";}\n', 'WA')
    wrongId = data.submission_id
    assert.equal(data.result.tests.length, 6)
    assert.equal(data.result.passed, 0)
    await page.locator('.test-list details').first().locator('summary').click()
    assert.match(await page.locator('.test-list details').first().innerText(), /15/)
    await page.getByRole('tab', { name: '编程错题', exact: true }).click()
    assert.match(await page.locator('.wrong-row').innerText(), /1 次错误/)
    await page.getByRole('tab', { name: '题目练习', exact: true }).click()
    return { submission_id: wrongId, verdict: data.result.verdict, test_count: 6 }
  })
  await check('successful code passes all normal and maximum boundary tests', 'real_cpp_ui_api', async () => {
    const data = await submit(solutions['array-sum'], 'AC')
    acceptedId = data.submission_id
    assert.equal(data.result.score, 100)
    assert.equal(data.result.tests.at(-1).name, '最大规模边界')
    assert.equal(data.result.tests.at(-1).actual, '100000000000000')
    assert.equal(data.result.tests.at(-1).input_truncated, true)
    return { submission_id: acceptedId, passed: data.result.passed, score: data.result.score }
  })
  await check('two separate accepted submissions mark the programming wrong question reviewed', 'real_cpp_ui_api', async () => {
    const data = await submit(solutions['array-sum'], 'AC')
    assert.notEqual(data.submission_id, acceptedId)
    acceptedId = data.submission_id
    await page.getByRole('tab', { name: '编程错题', exact: true }).click()
    assert.match(await page.locator('.wrong-row').innerText(), /已复习/)
    assert.match(await page.locator('.wrong-row').innerText(), /连续通过 2 次/)
    await page.getByRole('tab', { name: '题目练习', exact: true }).click()
  })
  await check('local review notes persist across page reload', 'real_ui_api', async () => {
    assert.equal(await button('AI 代码复盘').isDisabled(), true)
    await button('保存本地复盘').click()
    await page.getByText('代码复盘已保存。', { exact: true }).waitFor()
    await page.getByRole('textbox', { name: '我的复盘笔记', exact: true }).fill('用 long long，检查 n=0 与 64 位总和。')
    await button('保存复盘笔记').click()
    await page.getByText('复盘笔记已保存。', { exact: true }).waitFor()
    await open()
    await page.getByRole('tab', { name: '提交记录', exact: true }).click()
    await page.locator('.history-row').first().getByRole('button', { name: '查看提交', exact: true }).click()
    assert.equal(await page.getByRole('textbox', { name: '我的复盘笔记', exact: true }).inputValue(), '用 long long，检查 n=0 与 64 位总和。')
    assert.match(await page.locator('.feedback').innerText(), /本地规则提示/)
  })
  await check('undo and restore update evidence without removing original code', 'real_ui_api', async () => {
    const before = await overview()
    await button('撤销这次提交').click()
    await button('确认撤销').click()
    await button('恢复这次提交').waitFor()
    assert.equal((await overview()).profile.attempt_count, before.profile.attempt_count - 1)
    await button('恢复这次提交').click()
    await button('撤销这次提交').waitFor()
    const after = await overview()
    assert.equal(after.profile.attempt_count, before.profile.attempt_count)
    assert.equal(after.submissions.find(s => s.submission_id === acceptedId).code, solutions['array-sum'])
  })
  await check('syntax error is CE with real compiler diagnostics', 'real_cpp_ui_api', async () => {
    await page.getByRole('tab', { name: '题目练习', exact: true }).click()
    const row = await submit('int main() { missing syntax; }\n', 'CE')
    assert.ok(!row.result.compile_log.includes('\ufffd'), 'compiler diagnostics must decode the installed MSVC language')
    assert.ok(row.result.compile_log.includes('error'))
    assert.equal(row.result.tests.length, 0)
    return { verdict: row.result.verdict, compile_log: row.result.compile_log }
  })
  await check('cancellation persists and is excluded from practice statistics', 'real_cpp_ui_api', async () => {
    const count = (await overview()).profile.attempt_count
    await setCode('int main(){volatile unsigned long long i=0;for(;;)++i;}\n')
    await button('提交并评测').click()
    await button('取消评测').waitFor()
    await page.waitForFunction(() => document.querySelector('.compile-log') && document.querySelector('.result-panel .state-text')?.textContent === '评测中')
    await button('取消评测').click()
    await page.waitForFunction(() => document.querySelector('.result-panel .state-text')?.textContent === '已取消')
    await page.waitForFunction(() => !document.querySelector('.coding-page .primary')?.textContent.includes('正在编译'))
    const after = await overview()
    assert.equal(after.profile.attempt_count, count)
    assert.equal(after.submissions[0].status, 'cancelled')
    return { status: after.submissions[0].status }
  })
  await check('request-key retry never duplicates persisted submission', 'real_api', async () => {
    const key = crypto.randomUUID()
    const payload = { problem_id: 'array-sum', code: solutions['array-sum'], request_key: key }
    const first = (await (await context.request.post(api + '/api/programming/submissions', { data: payload })).json()).data
    const second = (await (await context.request.post(api + '/api/programming/submissions', { data: payload })).json()).data
    assert.equal(first.submission_id, second.submission_id)
    await context.request.post(api + '/api/programming/submissions/' + first.submission_id + '/cancel')
    return { same_submission: first.submission_id }
  })
  await check('weekly and category statistics use all active completed evidence', 'real_ui_api', async () => {
    await page.getByRole('tab', { name: '练习证据', exact: true }).click()
    const data = await overview()
    assert.equal(data.profile.attempt_count, 4)
    assert.equal(data.profile.weekly.submissions, 4)
    assert.equal(data.profile.weekly.verdicts.AC, 2)
    assert.equal(data.profile.weekly.verdicts.CE, 1)
    assert.equal(data.profile.average_submissions_per_problem, 4)
    assert.match(await page.locator('.coding-page').innerText(), /本周练习 1 道题/)
    await page.screenshot({ path: path.join(out, 'practice-profile.png'), fullPage: true })
    return { count: data.profile.attempt_count, weekly: data.profile.weekly }
  })
  await check('model failure preserves accepted verdict and existing local review', 'injected_model_failure', async () => {
    await page.getByRole('tab', { name: '提交记录', exact: true }).click()
    await page.locator('.history-row').filter({ has: page.locator('.verdict.accepted') }).first().getByRole('button', { name: '查看提交', exact: true }).click()
    assert.equal(await button('AI 代码复盘').isDisabled(), true)
    await page.locator('.consent input').check()
    await page.route('**/api/programming/submissions/' + acceptedId + '/review', route => route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ detail: '模型复盘失败，判题与已有复盘均已保留，可稍后重试' }) }))
    await button('AI 代码复盘').click()
    await page.getByRole('alert').filter({ hasText: '模型复盘失败' }).waitFor()
    await page.unroute('**/api/programming/submissions/' + acceptedId + '/review')
    const row = (await (await context.request.get(api + '/api/programming/submissions/' + acceptedId)).json()).data
    assert.equal(row.result.verdict, 'AC')
    assert.equal(row.result.score, 100)
    assert.equal(row.review.provider, 'local_rules')
  })
  await check('read failure exposes retry and preserves server history', 'injected_network_fault', async () => {
    const before = (await overview()).submissions.length
    await page.route('**/api/programming/overview', route => route.abort('failed'))
    await open()
    await page.getByRole('alert').filter({ hasText: 'Network Error' }).waitFor()
    await page.unroute('**/api/programming/overview')
    await button('刷新记录').click()
    await page.waitForFunction(() => !document.querySelector('.coding-page [role="alert"]'))
    assert.equal((await overview()).submissions.length, before)
  })
  await check('responsive layouts and editor disposal on navigation', 'real_ui', async () => {
    await page.getByRole('tab', { name: '题目练习', exact: true }).click()
    for (const width of [375, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 1000 })
      await page.waitForTimeout(350)
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
      assert.equal(overflow, false, 'no horizontal page overflow at ' + width)
      await page.screenshot({ path: path.join(out, `programming-${width}.png`), fullPage: true })
    }
    await page.goto(base + '/ai-tools')
    await page.locator('.learning-workspace').getByRole('heading', { level: 1 }).waitFor()
    await open()
    assert.equal(await page.locator('.monaco-editor').count(), 1)
    assert.deepEqual(errors, [])
  })
} finally {
  fs.writeFileSync(path.join(out, 'summary.json'), JSON.stringify({ passed: results.filter(r => r.passed).length, total: results.length, page_errors: errors, results }, null, 2))
  await browser.close()
}
if (results.some(r => !r.passed)) process.exitCode = 1
