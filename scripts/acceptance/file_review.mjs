import assert from 'node:assert/strict'
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const base = process.env.FILEMATE_WEB_URL
assert.ok(new URL(base).protocol === 'https:' && ['127.0.0.1', 'localhost'].includes(new URL(base).hostname))
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR)
const runtime = path.resolve(process.env.FILEMATE_DATA_DIR)
for (const folder of [out, runtime]) assert.ok(folder.startsWith(path.resolve('_working') + path.sep))
fs.mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 },
  ignoreHTTPSErrors: process.env.FILEMATE_ACCEPTANCE_INSECURE_TLS === '1', httpCredentials: {
    username: process.env.FILEMATE_ACCEPTANCE_BASIC_USER, password: process.env.FILEMATE_ACCEPTANCE_BASIC_PASSWORD,
  } })
const page = await context.newPage()
page.setDefaultTimeout(15000)
const results = [], errors = [], traffic = []
page.on('pageerror', error => errors.push(String(error)))
page.on('request', request => traffic.push({ method: request.method(), url: request.url() }))
async function check(name, run, kind = 'actual_compiled_vue_tls_api_filesystem') {
  try { await run(); results.push({ name, kind, passed: true }) }
  catch (error) { results.push({ name, kind, passed: false, error: String(error) }); await page.screenshot({ path: path.join(out, `failure-${results.length}.png`), fullPage: true }) }
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 2))
  console.log(`${results.at(-1).passed ? 'PASS' : 'FAIL'} ${name}`)
}
async function api(route, method = 'get', data) {
  const response = await context.request[method](base + route, data ? { data } : {})
  assert.ok(response.ok(), `${method} ${route}: ${response.status()}`)
  const body = await response.json()
  assert.equal(body.success, true)
  return body.data
}
function ownFile(file) {
  const resolved = path.resolve(file)
  assert.ok(resolved.startsWith(runtime + path.sep), 'file assertions must stay inside the self-owned synthetic runtime')
  return resolved
}
function hash(file) { return crypto.createHash('sha256').update(fs.readFileSync(ownFile(file))).digest('hex') }
async function openSession(sessionId, route = '/classification') {
  await page.goto(`${base}${route}?session=${encodeURIComponent(sessionId)}`)
  await page.locator('.review-sheet').waitFor()
}
async function upload(index) {
  const name = `合成课件-${index}.txt`
  const content = Buffer.from(`原创工程夹具，非真实学生资料。\n课程：操作系统\n课件：进程和线程\n作业截止日期：2026-12-31\n${index}\n`, 'utf8')
  await page.goto(base + '/import?intent=archive')
  await page.locator('.archive-consent input').check()
  await page.locator('#primary-file-upload').setInputFiles({ name, mimeType: 'text/plain', buffer: content })
  await page.getByRole('button', { name: '核对并归档', exact: true }).waitFor()
  await page.getByRole('button', { name: '核对并归档', exact: true }).click()
  await page.locator('.review-sheet').waitFor()
  const id = new URL(page.url()).searchParams.get('session')
  assert.ok(id)
  const uploaded = await api('/sessions/' + id)
  // 审核/日程专项使用明确手工填写的合成草稿，不依赖模型提取质量或本机凭据。
  const session = await api('/sessions/' + id, 'patch', {
    edits: { entities: { ...uploaded.entities, course_name: '操作系统', deadline: '2026-12-31' } },
  })
  await openSession(id)
  assert.equal(hash(session.source_path), crypto.createHash('sha256').update(content).digest('hex'))
  return { id, session, digest: hash(session.source_path) }
}
let first, archived, second, lost, readFailure
try {
  await check('legacy review routes retain clear empty state and merged three-stage workflow', async () => {
    for (const route of ['/classification', '/naming']) {
      await page.goto(base + route)
      await page.getByText('选一份资料，开始核对', { exact: true }).waitFor()
      assert.equal(await page.locator('.workflow-steps li').count(), 3)
      assert.equal(await page.locator('.review-sheet').count(), 0)
    }
  })
  await check('real browser upload opens classification and naming together without moving the file', async () => {
    first = await upload(1)
    assert.equal(await page.locator('.category-grid input').count(), 7)
    assert.equal(await page.locator('.file-review-page .el-select').count(), 0)
    assert.ok(await page.locator('#review-filename').isEditable())
    assert.notEqual(first.session.status, 'confirmed')
    assert.equal(fs.existsSync(ownFile(first.session.source_path)), true)
  })
  await check('combined draft persists category, name and calendar choice without archive side effects', async () => {
    await page.getByRole('radio', { name: '参考资料', exact: true }).check()
    await page.locator('#review-filename').fill('集成审核-首份.txt')
    const calendar = page.getByRole('checkbox', { name: '同时生成学习日程', exact: true })
    await calendar.waitFor()
    await calendar.uncheck()
    assert.match(await page.locator('.archive-preview').innerText(), /参考资料[\s\S]*集成审核-首份.txt/)
    await page.getByRole('button', { name: '保存草稿', exact: true }).click()
    await page.getByRole('button', { name: '保存草稿', exact: true }).waitFor({ state: 'visible' })
    await page.waitForFunction(() => document.querySelector('.review-status')?.textContent === '待核对')
    const saved = await api('/sessions/' + first.id)
    assert.equal(saved.category, '参考资料')
    assert.equal(saved.suggested_name, '集成审核-首份.txt')
    assert.equal(saved.entities.calendar_enabled, false)
    assert.notEqual(saved.status, 'confirmed')
    assert.equal(hash(saved.source_path), first.digest)
    await openSession(first.id, '/naming')
    assert.equal(await page.locator('#review-filename').inputValue(), '集成审核-首份.txt')
    assert.equal(await calendar.isChecked(), false)
  })
  await check('leaving unsaved edits offers an actual keyboard-accessible cancel and preserves the draft', async () => {
    await page.locator('#review-filename').fill('集成审核-最终.txt')
    await page.locator('.context-navigation a[href="/history"]').click()
    await page.getByRole('button', { name: '继续核对', exact: true }).click()
    assert.ok(page.url().includes('/naming?session='))
    assert.equal(await page.locator('#review-filename').inputValue(), '集成审核-最终.txt')
    assert.equal((await api('/sessions/' + first.id)).suggested_name, '集成审核-首份.txt')
  })
  await check('shell refresh preserves unsaved edits and permits refresh after the archive is complete', async () => {
    await page.getByRole('button', { name: '刷新当前页面', exact: true }).click()
    await page.getByText('请先保存草稿，再刷新页面。', { exact: true }).waitFor()
    assert.equal(await page.locator('#review-filename').inputValue(), '集成审核-最终.txt')
    assert.equal((await api('/sessions/' + first.id)).suggested_name, '集成审核-首份.txt')
  })
  await check('single final confirmation archives both edits with actual byte preservation and idempotence', async () => {
    await page.getByRole('button', { name: '确认并归档', exact: true }).click()
    await page.getByRole('heading', { name: '资料已归档', exact: true }).waitFor()
    archived = await api('/sessions/' + first.id)
    assert.equal(archived.category, '参考资料')
    assert.equal(archived.suggested_name, '集成审核-最终.txt')
    assert.equal(fs.existsSync(ownFile(archived.source_path)), false)
    assert.equal(hash(archived.execution.dest_path), first.digest)
    assert.ok(!archived.execution.ics_path)
    const again = await api(`/sessions/${first.id}/confirm`, 'post', { accepted: true })
    assert.equal(again.execution.execution_id, archived.execution.execution_id)
    assert.equal(again.execution.idempotent, true)
    assert.equal((await api(`/sessions/${first.id}/executions`)).filter(item => item.status === 'applied').length, 1)
    await page.getByRole('button', { name: '刷新当前页面', exact: true }).click()
    await page.getByText('工作台已刷新', { exact: true }).waitFor()
    await page.getByRole('heading', { name: '资料已归档', exact: true }).waitFor()
  })
  await check('reload of either legacy link locks the archived fields and retains undo', async () => {
    await openSession(first.id)
    assert.equal(await page.locator('#review-filename').isDisabled(), true)
    assert.ok((await page.locator('.category-grid input').evaluateAll(nodes => nodes.every(node => node.matches(':disabled')))))
    assert.equal(await page.getByRole('button', { name: '确认并归档', exact: true }).count(), 0)
    await page.getByRole('button', { name: '撤销归档', exact: true }).waitFor()
  })
  await check('undo preview cancellation leaves files intact; confirmation and repeat undo restore once', async () => {
    await page.getByRole('button', { name: '撤销归档', exact: true }).click()
    await page.getByRole('button', { name: '保留归档', exact: true }).click()
    assert.equal(hash(archived.execution.dest_path), first.digest)
    await page.getByRole('button', { name: '撤销归档', exact: true }).click()
    await page.getByRole('button', { name: '确认撤销', exact: true }).click()
    await page.locator('#review-filename:enabled').waitFor()
    assert.equal(hash(first.session.source_path), first.digest)
    assert.equal(fs.existsSync(ownFile(archived.execution.dest_path)), false)
    const again = await api(`/sessions/${first.id}/undo`, 'post')
    assert.equal(again.execution.execution_id, archived.execution.execution_id)
    assert.equal(again.execution.status, 'undone')
  })
  await check('blank or changed extension cannot send a final confirmation', async () => {
    const before = traffic.filter(item => item.method === 'POST' && item.url.endsWith('/confirm')).length
    await page.locator('#review-filename').fill('')
    assert.equal(await page.getByRole('button', { name: '确认并归档', exact: true }).isDisabled(), true)
    await page.locator('#review-filename').fill('禁止改格式.pdf')
    await page.getByText('请保留 .txt 格式。', { exact: true }).waitFor()
    assert.equal(await page.getByRole('button', { name: '确认并归档', exact: true }).isDisabled(), true)
    assert.equal(traffic.filter(item => item.method === 'POST' && item.url.endsWith('/confirm')).length, before)
    assert.equal(hash(first.session.source_path), first.digest)
  })
  await check('calendar choice is confirmed in the same module and yields a real ICS download', async () => {
    await page.locator('#review-filename').fill('集成审核-日程.txt')
    await page.getByRole('checkbox', { name: '同时生成学习日程', exact: true }).check()
    await page.getByRole('button', { name: '确认并归档', exact: true }).click()
    await page.getByRole('heading', { name: '资料已归档', exact: true }).waitFor()
    archived = await api('/sessions/' + first.id)
    assert.equal(hash(archived.execution.dest_path), first.digest)
    assert.match(fs.readFileSync(ownFile(archived.execution.ics_path), 'utf8'), /BEGIN:VCALENDAR[\s\S]*20261231/)
    const [received] = await Promise.all([
      page.waitForEvent('download'), page.getByRole('button', { name: '下载日程', exact: true }).click(),
    ])
    await received.saveAs(path.join(out, 'synthetic-calendar.ics'))
    assert.match(fs.readFileSync(path.join(out, 'synthetic-calendar.ics'), 'utf8'), /BEGIN:VCALENDAR/)
    await page.getByRole('button', { name: '查看日程', exact: true }).click()
    const scheduled = page.getByRole('button', { name: '下载 .ics 文件', exact: true })
    await scheduled.waitFor()
    assert.equal(await scheduled.isEnabled(), true)
    const [fromSchedule] = await Promise.all([page.waitForEvent('download'), scheduled.click()])
    await fromSchedule.saveAs(path.join(out, 'synthetic-calendar-from-schedule.ics'))
    assert.equal(fs.readFileSync(path.join(out, 'synthetic-calendar.ics'), 'utf8'), fs.readFileSync(path.join(out, 'synthetic-calendar-from-schedule.ics'), 'utf8'))
  })
  await check('an existing archive target is preserved on conflict and edited retry succeeds separately', async () => {
    second = await upload(2)
    await page.getByRole('radio', { name: '参考资料', exact: true }).check()
    await page.locator('#review-filename').fill('集成审核-日程.txt')
    const response = page.waitForResponse(response => response.url().endsWith(`/sessions/${second.id}/confirm`))
    await page.getByRole('button', { name: '确认并归档', exact: true }).click()
    assert.equal((await response).status(), 409)
    await page.locator('.review-error').waitFor()
    assert.equal(hash(archived.execution.dest_path), first.digest)
    assert.equal(hash(second.session.source_path), second.digest)
    assert.equal(await page.locator('#review-filename').inputValue(), '集成审核-日程.txt')
    await page.locator('#review-filename').fill('集成审核-第二份.txt')
    await page.getByRole('button', { name: '确认并归档', exact: true }).click()
    await page.getByRole('heading', { name: '资料已归档', exact: true }).waitFor()
    assert.equal(hash((await api('/sessions/' + second.id)).execution.dest_path), second.digest)
    assert.equal(hash(archived.execution.dest_path), first.digest)
  })
  await check('a received confirmation with a deliberately lost response retries the same execution', async () => {
    lost = await upload(3)
    await page.locator('#review-filename').fill('集成审核-丢响应.txt')
    let receivedId
    await page.route(`**/sessions/${lost.id}/confirm`, async route => {
      const response = await route.fetch()
      assert.equal(response.status(), 200)
      receivedId = (await response.json()).data.execution.execution_id
      await route.abort('failed')
    }, { times: 1 })
    await page.getByRole('button', { name: '确认并归档', exact: true }).click()
    await page.locator('.review-error').waitFor()
    assert.equal(await page.locator('#review-filename').inputValue(), '集成审核-丢响应.txt')
    await page.getByRole('button', { name: '确认并归档', exact: true }).click()
    await page.getByRole('heading', { name: '资料已归档', exact: true }).waitFor()
    const restored = await api('/sessions/' + lost.id)
    assert.equal(restored.execution.execution_id, receivedId)
    assert.equal(hash(restored.execution.dest_path), lost.digest)
    assert.equal((await api(`/sessions/${lost.id}/executions`)).filter(item => item.status === 'applied').length, 1)
  }, 'explicit_response_loss_injection_after_actual_archive')
  await check('known archive success stays locked when the following read is deliberately interrupted', async () => {
    readFailure = await upload(4)
    await page.locator('#review-filename').fill('集成审核-读回故障.txt')
    await page.route(`**/sessions/${readFailure.id}`, route => route.abort('failed'), { times: 1 })
    await page.getByRole('button', { name: '确认并归档', exact: true }).click()
    await page.getByRole('heading', { name: '资料已归档', exact: true }).waitFor()
    await page.getByText('归档已成功，完整记录暂时未能读取。', { exact: true }).waitFor()
    assert.equal(await page.locator('#review-filename').isDisabled(), true)
    assert.equal(hash((await api('/sessions/' + readFailure.id)).execution.dest_path), readFailure.digest)
    await page.getByRole('button', { name: '重新读取记录', exact: true }).click()
    await page.locator('.review-sheet').waitFor()
    assert.equal(await page.locator('.review-error').count(), 0)
  }, 'explicit_read_interruption_after_actual_archive')
  for (const width of [375, 768, 1440]) await check(`combined review is readable and within the viewport at ${width}px`, async () => {
    await page.setViewportSize({ width, height: 1000 })
    await openSession(first.id)
    await page.waitForTimeout(300)
    const facts = await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth > innerWidth,
      title: parseFloat(getComputedStyle(document.querySelector('.review-heading h1')).fontSize),
      options: [...document.querySelectorAll('.category-grid label')].map(node => ({ font: parseFloat(getComputedStyle(node).fontSize), height: node.getBoundingClientRect().height })),
    }))
    assert.equal(facts.overflow, false)
    assert.ok(facts.title >= 36 && facts.options.every(option => option.font >= 17 && option.height >= 44))
    await page.screenshot({ path: path.join(out, `review-${width}.png`), fullPage: true })
    fs.writeFileSync(path.join(out, `layout-${width}.json`), JSON.stringify(facts, null, 2))
  })
  await check('classification overview uses real records and all checked requests remain local', async () => {
    await page.locator('.category-history summary').click()
    await page.locator('.distribution-row').first().waitFor()
    const history = await api('/sessions?limit=100')
    const counts = await page.locator('.distribution-row strong').allTextContents()
    assert.equal(counts.reduce((sum, value) => sum + Number(value), 0), history.length)
    assert.deepEqual(errors, [])
    assert.ok(traffic.every(item => new URL(item.url).origin === new URL(base).origin))
  })
} finally { await browser.close() }
const summary = { passed: results.every(result => result.passed), total: results.length, results, errors,
  scope: 'original synthetic TXT; actual compiled Vue, Caddy, anonymous FastAPI and owned files; network failures explicitly injected; no private data or external model' }
fs.writeFileSync(path.join(out, 'summary.json'), JSON.stringify(summary, null, 2))
console.log(JSON.stringify({ passed: summary.passed, total: summary.total }))
if (!summary.passed) process.exitCode = 1
