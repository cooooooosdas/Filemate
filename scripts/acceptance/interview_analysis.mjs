import assert from 'node:assert/strict'
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const root = process.cwd()
const base = process.env.FILEMATE_WEB_URL || 'https://filemate.asia'
const api = process.env.FILEMATE_API_URL || base
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR || '_working/interview-analysis')
assert.ok(out.startsWith(path.join(root, '_working') + path.sep))
assert.equal(fs.existsSync(out), false, '使用新的证据目录，不覆盖旧运行')
fs.mkdirSync(out, { recursive: true })
const cases = [
  ['不会的短回答', '求职面试', '后端开发', '这个问题我暂时不会。'],
  ['概念短回答', '知识讲解', '数据库课程', '索引就像目录，能加快查询，但会增加写入成本。'],
  ['口语回答', '求职面试', '产品设计', '嗯，我先问同学哪里不好用，然后改页面，再找三个人试一下。最后大家说找资料更方便了。'],
  ['换行回答', '竞赛答辩', '学习平台', '我们先访谈了五位同学。\n大家的资料分散在不同文件夹。\n我负责整理需求，做了统一入口，并用三份合成资料验证上传和检索。'],
  ['英文回答', '保研复试', '软件工程', 'I built a small search tool. I wrote tests for empty files and duplicate imports. The tests passed, but I have not run a user study yet.'],
  ['项目回答', '求职面试', '后端开发', '首先分析项目背景，因为任务需要支持范围查询，例如用有序索引验证结果。我补充了边界测试，发现空结果时页面报错，修复后重新验证了十个输入。'],
  ['长回答', '求职面试', '软件工程', '先检查空输入、重复项和最大值，再对照结果修正错误。'.repeat(70)],
  ['无标点口语', '求职面试', '软件工程', '嗯那个我先看看需求问同学哪里不好用然后改了页面再找三个人试一下最后他们说找资料方便了'],
]
const direct = process.env.FILEMATE_BROWSER_DIRECT === '1'
const intervalMs = Number(process.env.FILEMATE_INTERVIEW_INTERVAL_MS || 20000)
assert.ok(Number.isFinite(intervalMs) && intervalMs >= 20000, '公开网站复测每例至少间隔20秒，保留生产限流')
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || 'msedge', headless: true,
  args: direct ? ['--no-proxy-server'] : [] })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true })
const stranger = await browser.newContext()
const page = await context.newPage()
page.setDefaultTimeout(20000)
const errors = [], results = [], owned = new Set()
let fixtureId = null
const network = [], startedRequests = new WeakMap()
page.on('pageerror', error => errors.push(String(error)))
page.on('request', request => startedRequests.set(request, performance.now()))
page.on('response', response => network.push({ path: new URL(response.url()).pathname, status: response.status(),
  elapsed_ms: Math.round(performance.now() - (startedRequests.get(response.request()) || performance.now())) }))
page.on('requestfailed', request => network.push({ path: new URL(request.url()).pathname,
  failure: request.failure()?.errorText, elapsed_ms: Math.round(performance.now() - (startedRequests.get(request) || performance.now())) }))
const button = name => page.getByRole('button', { name, exact: true })
async function request(route, method = 'get', data) {
  const response = await context.request[method](api + route, data ? { data } : {})
  assert.equal(response.status(), 200, method + ' ' + route)
  return (await response.json()).data
}
async function check(name, action) {
  console.log('RUN', name)
  try { results.push({ name, passed: true, evidence: await action() }); console.log('PASS', name) }
  catch (error) { results.push({ name, passed: false, fixture_id: fixtureId, error: String(error) }); console.log('FAIL', name, String(error)); await page.screenshot({ path: path.join(out, `failure-${results.length}.png`), fullPage: true }) }
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 2))
}
try {
  // 先串行初始化本轮游客，避免测试写入与首屏无 Cookie 的并发请求竞争。
  await request('/api/auth/me')
  for (const [name, scenario, targetRole, answer] of cases) {
    fixtureId = null
    await check(name + '：真实页面分析、原句及持久报告', async () => {
      const created = await request('/interviews', 'post', { target_role: targetRole, scenario, allow_external_analysis: false })
      const id = created.interview_id
      fixtureId = id
      owned.add(id)
      await page.goto(base + '/interview?interview=' + id, { waitUntil: 'domcontentloaded', timeout: 45000 })
      await page.getByRole('textbox', { name: '当前训练回答', exact: true }).fill(answer)
      const answered = page.waitForResponse(r => r.url() === api + `/interviews/${id}/answers` && r.request().method() === 'POST')
      await button('提交并进入下一题').click()
      assert.equal((await answered).status(), 200)
      await button('生成规则复盘报告').click()
      await button('更新规则复盘报告').waitFor()
      const saved = await request(`/interviews/${id}`)
      const turn = saved.turns[0]
      const analyzePath = `/interviews/${id}/turns/${turn.turn_id}/analyze`
      assert.equal(turn.scoring_mode, 'local_fallback')
      if (name === cases[0][0]) {
        const original = (await request(`/interviews/${id}/review`)).report
        const reject = route => route.continue({ headers: { ...route.request().headers(),
          'X-FileMate-Action': 'model', 'X-FileMate-LLM-Key': `invalid-fixture-${crypto.randomUUID()}` } })
        await page.route(api + analyzePath, reject)
        await page.locator('.consent input').check()
        const rejected = page.waitForResponse(r => r.url() === api + analyzePath)
        await button('分析这一题的内容').click()
        assert.equal((await rejected).status(), 502)
        await page.getByRole('alert').filter({ hasText: '密钥、余额和调用权限' }).waitFor()
        assert.deepEqual((await request(`/interviews/${id}/review`)).report, original)
        assert.equal(await button('导出 PDF').isEnabled(), true)
        await page.unroute(api + analyzePath, reject)
      }
      await page.locator('.consent input').check()
      const analyzed = page.waitForResponse(r => r.url() === api + analyzePath && r.request().method() === 'POST', { timeout: 65000 })
      await button('分析这一题的内容').click()
      const response = await analyzed
      assert.equal(response.status(), 200, 'POST ' + analyzePath)
      const updated = (await response.json()).data
      assert.equal(updated.turns[0].answer, answer)
      assert.equal(updated.turns[0].scoring_mode, 'llm')
      const content = updated.turns[0].content_analysis
      assert.equal(Object.keys(content.areas).length, 6)
      assert.equal(Object.keys(content.dimension_evidence).length, 4)
      for (const quote of Object.values(content.dimension_evidence)) assert.ok(quote.length && answer.includes(quote))
      for (const area of Object.values(content.areas)) {
        if (area.evidence) assert.ok(answer.includes(area.evidence))
        if (['covered', 'partial'].includes(area.status)) assert.ok(area.evidence.length)
      }
      assert.ok(content.keywords.every(term => answer.includes(term)))
      await button('生成规则复盘报告').click()
      await button('更新规则复盘报告').waitFor()
      const report = (await request(`/interviews/${id}/review`)).report
      assert.equal(report.assessed, 1)
      assert.equal(report.turns[0].answer, answer)
      assert.deepEqual((await request(analyzePath, 'post', { external_consent: true })).turns[0].content_analysis, content)
      assert.equal((await stranger.request.get(api + `/interviews/${id}`)).status(), 404)
      await page.reload({ waitUntil: 'domcontentloaded', timeout: 45000 })
      await button('更新规则复盘报告').waitFor()
      assert.equal((await request(`/interviews/${id}/review`)).report.assessed, 1)
      if (name === '换行回答') {
        for (const format of ['PDF', 'JSON', 'Markdown']) {
          const pending = page.waitForEvent('download')
          await button('导出 ' + format).click()
          const download = await pending
          const destination = path.join(out, download.suggestedFilename())
          await download.saveAs(destination)
          assert.ok(fs.statSync(destination).size > 200)
        }
      }
      return { interview_id: id, actual_model: true, verified_dimensions: 4, verified_areas: 6,
        answer_length: answer.length, persisted: true, cached_repeat: true, other_guest_denied: true }
    })
    await page.waitForTimeout(intervalMs)
  }
  fixtureId = null
  await check('清理仅本轮合成面试，预览确认后删除', async () => {
    for (const id of [...owned]) {
      const preview = await request(`/interviews/${id}/delete-preview`)
      await request(`/interviews/${id}`, 'delete', { confirmed: true, confirmation_token: preview.confirmation_token })
      assert.equal((await context.request.get(api + `/interviews/${id}`)).status(), 404)
      owned.delete(id)
    }
  })
} finally {
  for (const id of owned) {
    try {
      const preview = await request(`/interviews/${id}/delete-preview`)
      await request(`/interviews/${id}`, 'delete', { confirmed: true, confirmation_token: preview.confirmation_token })
    } catch (error) { results.push({ name: 'own fixture cleanup', passed: false, error: String(error) }) }
  }
  await browser.close()
  fs.writeFileSync(path.join(out, 'summary.json'), JSON.stringify({ passed: results.every(item => item.passed) && !errors.length,
    results, errors, network, browser_direct: direct, interval_ms: intervalMs,
    guest_initialized_before_fixture_writes: true, sample_kind: 'synthetic_original_answers',
    transport: 'actual production model; invalid own fixture header only, no response mocks' }, null, 2))
}
if (results.some(item => !item.passed) || errors.length) process.exitCode = 1
