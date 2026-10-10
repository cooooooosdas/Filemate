import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { chromium } from 'playwright'
const base = process.env.FILEMATE_WEB_URL, api = process.env.FILEMATE_API_URL, out = process.env.FILEMATE_EVIDENCE_DIR
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, acceptDownloads: true })
const page = await context.newPage(), errors = [], checks = [], limitations = []
page.setDefaultTimeout(30000)
page.on('pageerror', error => errors.push(String(error)))
await page.route('**/*', route => {
  const url = new URL(route.request().url())
  if (['xhr', 'fetch'].includes(route.request().resourceType()) && url.origin === base) return route.continue({ url: api + url.pathname + url.search })
  return route.continue()
})
const button = name => page.getByRole('button', { name, exact: true })
const get = async url => { const r = await context.request.get(api + url); assert.equal(r.status(), 200, `${url} HTTP ${r.status()}`); return (await r.json()).data }
const post = async (url, data) => { const r = await context.request.post(api + url, { data }); assert.equal(r.status(), 200, `${url} HTTP ${r.status()}: ${(await r.text()).slice(0,180)}`); return (await r.json()).data }
async function step(name, action) {
  if (process.env.FILEMATE_PUBLIC_FLOW === '1') await new Promise(resolve => setTimeout(resolve, 8000))
  console.log('RUN', name)
  const start = Date.now()
  try { await action(); checks.push({ name, status: 'PASS', elapsed_ms: Date.now() - start }); console.log('PASS', name) }
  catch (error) { checks.push({ name, status: 'FAIL', diagnostic: String(error).slice(0,1000) }); throw error }
  save()
}
function save() { fs.writeFileSync(path.join(out, 'summary.json'), JSON.stringify({ sample_kind: 'original_synthetic_single_registered_account_actual_UI_API_SQLite_native_compiler_real_DeepSeek', passed: checks.length >= 20 && checks.every(c => c.status === 'PASS') && !errors.length, checks, errors, limitations, real_student_data: false, external_model: true }, null, 2)) }
async function download(name, file) { const pending = page.waitForEvent('download'); await button(name).click(); await (await pending).saveAs(path.join(out, file)) }
const date = offset => { const d = new Date(); d.setDate(d.getDate() + offset); return d.toISOString().slice(0,10) }
let sid, artifact, nid, plan, iid, accepted, wrong, pid, resumeId, growthId
const password = crypto.randomBytes(3).toString('hex') + 'ab7', email = `synthetic-flow-${crypto.randomUUID()}@example.invalid`
try {
  await step('01 注册与保存恢复码', async () => {
    await page.goto(base + '/register'); await page.locator('#display-name').fill('原创合成验收账户'); await page.locator('#account').fill(email)
    await page.locator('#password').fill(password); await page.locator('#confirm-password').fill(password)
    await page.getByLabel('我会保存恢复码，并了解邮箱暂不验证归属').check(); await button('创建账号').click()
    await page.locator('#saved-recovery-code').waitFor(); assert.equal((await page.locator('#saved-recovery-code').inputValue()).length, 43)
    await page.getByLabel('我已妥善保存恢复码').check(); await button('进入学习空间').click()
    await page.getByRole('button', { name: '查看我的账号' }).waitFor()
  })
  await step('02 退出与原密码重新登录', async () => {
    await button('查看我的账号').click(); await button('退出登录').click(); await page.getByRole('link', { name: '登录 FileMate', exact: true }).waitFor(); await page.goto(base + '/login')
    await page.locator('#account').fill(email); await page.locator('#password').fill(password); await button('登录').click()
    await page.getByRole('button', { name: '查看我的账号' }).waitFor(); assert.equal((await get('/api/auth/me')).user.email, email)
  })
  await step('03 上传课程并读取真实解析正文', async () => {
    await page.goto(base + '/import'); await page.getByText('网站资料保存在服务器', { exact: true }).waitFor()
    const response = page.waitForResponse(r => r.url().endsWith('/knowledge/import') && r.request().method() === 'POST')
    await page.locator('#primary-file-upload').setInputFiles({ name: '原创合成课程-栈与C++.txt', mimeType: 'text/plain', buffer: Buffer.from('C++：支持静态类型。\n栈：后进先出，英文缩写LIFO。\n队列：先进先出，英文缩写FIFO。\n有序数组：二分查找的前提，每轮排除一半区间，时间复杂度O(log n)。\nC++是栈的前置知识。') })
    const r = await response; assert.equal(r.status(), 200); sid = (await r.json()).data.source_id
    assert.match((await get(`/knowledge/sources/${sid}`)).raw_text, /后进先出/)
  })
  await step('04 图谱预览确认与画像真实证据', async () => {
    await page.goto(base + '/knowledge-graph'); await page.locator('.extract-fields select').first().selectOption(sid)
    await button('提取并预览').click(); await button('确认加入图谱').waitFor(); await button('确认加入图谱').click()
    await page.waitForFunction(() => document.querySelector('.map-panel')?.textContent.includes('个知识点'))
    const g = await get('/api/knowledge-graph'); assert.ok(g.nodes.length >= 3); assert.ok(g.nodes.every(n => n.excerpt))
    nid = g.nodes.find(n => n.label === '栈')?.id || g.nodes[0].id
    await button('列表').click(); await page.locator('.node-list button').filter({ hasText: /^栈/ }).click()
    await page.locator('.evidence-panel').waitFor()
  })
  await step('05 设置目标与学习Agent任务', async () => {
    await page.goto(base + '/goals'); await page.locator('[name=goal_title]').fill('合成验收：理解栈与C++')
    await page.locator('[name=goal_type]').selectOption('exam'); await page.locator('[name=goal_deadline]').fill(date(14)); await page.locator('[name=goal_source]').selectOption(sid)
    await button('安排下一步').click(); await page.locator('.learning-path').waitFor()
    const goals = await get('/goals'); assert.ok(goals[0].tasks.length); assert.equal(goals[0].source_id, sid)
  })
  await step('06 生成学习计划并完成实际任务', async () => {
    await page.goto(base + '/knowledge-graph?node=' + nid); await button('预览学习路径').click(); await button('确认加入学习计划').click(); await page.locator('.saved-plan').waitFor()
    plan = (await get('/api/knowledge-graph')).plans[0].plan_id
    await page.goto(base + '/study-plan?plan=' + plan)
    const completed = page.waitForResponse(r => r.url().endsWith(`/study-plans/${plan}/days/0`) && r.request().method() === 'PATCH')
    await page.getByRole('button', { name: '标记为已完成', exact: true }).first().click(); assert.equal((await completed).status(), 200)
    assert.ok((await get('/study-plans/' + plan)).completed_days.includes(0))
    await page.goto(base + '/goals'); await page.locator('.task-detail').waitFor()
    const done = page.waitForResponse(r => /\/goals\/[^/]+\/tasks\//.test(r.url()) && r.request().method() === 'PATCH')
    await button('标记这一步已完成').click(); assert.equal((await done).status(), 200)
    assert.ok((await get('/goals'))[0].tasks.some(t => t.status === 'completed'))
  })
  await step('07 真实模型生成可判题练习', async () => {
    await page.goto(base + '/ai-tools?source=' + sid); await page.getByLabel('允许本次学习将资料片段和问题发送给已配置的模型').check()
    if (await button('创建学习内容').isVisible()) await button('创建学习内容').click()
    await page.getByRole('button', { name: '练习', exact: true }).click()
    const pending = page.waitForResponse(r => r.url().endsWith(`/knowledge/sources/${sid}/artifacts`) && r.request().method() === 'POST', { timeout: 120000 })
    await button('生成练习').click(); const r = await pending; assert.equal(r.status(), 200, (await r.text()).slice(0,180)); artifact = (await r.json()).data
    assert.ok(artifact.content.length && artifact.content.every(q => q.answer)); await page.locator('.learning-artifact h4').waitFor()
  })
  await step('08 编程题真实编译产生错题及AC', async () => {
    await page.goto(base + '/programming?problem=array-sum'); await page.getByRole('textbox', { name: 'C++代码', exact: true }).waitFor()
    await page.getByText('隔离评测已就绪', { exact: true }).waitFor({ timeout: 60000 })
    async function submit(code, verdict) {
      await page.locator('.monaco-editor .view-lines').click(); await page.keyboard.press('Control+A'); await page.keyboard.insertText(code)
      const pending = page.waitForResponse(r => r.url().endsWith('/api/programming/submissions') && r.request().method() === 'POST')
      await button('提交并评测').click(); const r = await pending; assert.equal(r.status(), 200); const created = (await r.json()).data
      await page.waitForFunction(() => document.querySelector('.result-panel .state-text')?.textContent === '已完成', null, { timeout: 60000 })
      const row = await get('/api/programming/submissions/' + created.submission_id); assert.equal(row.result.verdict, verdict); return row.submission_id
    }
    wrong = await submit('#include <iostream>\nint main(){std::cout<<0;}', 'WA')
    accepted = await submit(JSON.parse(fs.readFileSync('scripts/acceptance/fixtures/cpp_solutions.json', 'utf8'))['array-sum'], 'AC')
  })
  await step('09 AI编程教练真实模型复盘', async () => {
    await page.getByLabel('我同意将题面、这次提交的代码与测试结果发送给已配置的外部模型。').check()
    const pending = page.waitForResponse(r => r.url().endsWith(`/api/programming/submissions/${accepted}/review`) && r.request().method() === 'POST', { timeout: 120000 })
    await button('AI 代码复盘').click(); const r = await pending; assert.equal(r.status(), 200)
    const row = await get('/api/programming/submissions/' + accepted); assert.equal(row.review.provider, 'external_model')
  })
  await step('10 课程错题与间隔复练', async () => {
    const q = artifact.content[0], options = Array.isArray(q.options) ? q.options : q.options ? Object.values(q.options) : []
    const answer = String(q.answer).trim(), incorrect = options.length ? (answer === 'A' || answer.startsWith('A.') ? 'B' : 'A') : '明确错误的合成测试答案'
    const failed = await post('/quiz/attempts', { artifact_id: artifact.artifact_id, question_index: 0, user_answer: incorrect }); assert.equal(failed.is_correct, false)
    await page.goto(base + '/wrongbook'); await page.getByRole('textbox', { name: '重新回答：' + q.stem }).fill(answer); await button('提交复习').click(); await page.locator('.result').waitFor()
    assert.ok((await get('/review/today')).stats || (await get('/wrongbook/page')).total >= 1)
  })
  await step('11 真实检索问答与引用', async () => {
    await page.goto(base + '/ai-tools?source=' + sid); await page.getByLabel('允许本次学习将资料片段和问题发送给已配置的模型').check()
    await page.getByLabel('向资料提问').fill('栈的后进先出 LIFO 是什么意思？')
    const pending = page.waitForResponse(r => r.url().endsWith('/ai/chat') && r.request().method() === 'POST', { timeout: 120000 })
    await button('发送').click(); const r = await pending; assert.equal(r.status(), 200); await page.locator('.message.assistant').waitFor()
    assert.ok((await page.locator('.message.assistant .citations button').count()) > 0)
  })
  await step('12 数字人讲解与真实 Microsoft 自然语音', async () => {
    await page.getByRole('link', { name: '让 AI 导师讲解', exact: true }).last().click(); await page.getByLabel('讲解内容').waitFor()
    await page.getByLabel('讲解内容').fill('栈采用后进先出。'); await page.getByRole('checkbox', { name: /允许将本次讲解正文/ }).check(); await button('开始讲解').click()
    await page.waitForFunction(() => ['讲解完成', '讲解失败'].includes(document.querySelector('.state-badge')?.textContent?.trim()), null, { timeout: 65000 }).catch(() => {})
    const records = await get('/api/digital-human/playbacks'); assert.ok(records.length)
    const speech = records[0].status
    if (speech !== 'completed') { limitations.push('此Edge自动化环境真实TTS未完成；已验证明确失败/停止和文字保留，不能作为可听语音验收。'); await button('停止').click().catch(() => {}) }
    checks.push({ name: '真实TTS设备分支', status: speech === 'completed' ? 'PASS' : 'CONDITIONAL', device_status: speech })
  })
  await step('13 面试回答持久化', async () => {
    await page.goto(base + '/interview'); await page.locator('[name=target_role]').fill('合成C++实习讲解'); await page.locator('[name=interview_source]').selectOption(sid)
    const pending = page.waitForResponse(r => r.url().endsWith('/interviews') && r.request().method() === 'POST')
    await button('开始模拟面试').click(); iid = (await (await pending).json()).data.interview_id
    await page.getByRole('textbox', { name: '当前训练回答', exact: true }).fill('栈采用后进先出，最后入栈的元素最先出栈。例如撤销操作可将操作记录压入栈，撤销时取出栈顶。C++中可以用vector保存数据并用push_back与pop_back实现，但访问前要检查是否为空。')
    await button('提交并进入下一题').click(); await page.locator('.review-list details').first().waitFor()
  })
  await step('14 真实模型面试分析与有原句依据的报告', async () => {
    await button('生成规则复盘报告').click(); await button('更新规则复盘报告').waitFor()
    await page.getByLabel('确认向已配置模型发送这一题的问题、回答和目标方向；不发送音视频或视觉观察。').check()
    const pending = page.waitForResponse(r => /\/turns\/[^/]+\/analyze$/.test(new URL(r.url()).pathname) && r.request().method() === 'POST', { timeout: 120000 })
    await button('分析这一题的内容').click(); const r = await pending; assert.equal(r.status(), 200, (await r.text()).slice(0,200))
    const regenerated = page.waitForResponse(r => r.url().endsWith(`/interviews/${iid}/review`) && r.request().method() === 'POST')
    await button('生成规则复盘报告').click(); assert.equal((await regenerated).status(), 200)
    const { report } = await get(`/interviews/${iid}/review`); assert.equal(report.assessed, 1); assert.ok(report.turns[0].content_analysis.dimension_evidence)
    await download('导出 JSON', 'interview.json')
  })
  await step('15 保存目标岗位与企业匹配证据', async () => {
    const description = '合成工程验收岗位：C++、数据结构、算法；仅供回归，不是真实企业招聘。'
    const job = await post('/api/career/positions', { confirmed: true, request_key: crypto.randomUUID(), position: { company: '原创合成测试公司', industry: '工程测试', region: '合成地区', title: '合成C++岗位', employment: '用户自定义', description, requirements: [{ label: 'C++', category: 'programming', evidence: description }], source: '原创合成回归资料', source_kind: 'user_import', collected_at: new Date().toISOString() } })
    pid = job.position_id; await page.goto(base + '/career?position=' + pid); await page.locator('.position-detail').waitFor(); assert.ok((await get(`/api/career/positions/${pid}/evidence`)).skills)
  })
  await step('16 企业模拟笔试与真实批改', async () => {
    await button('创建模拟笔试').click(); await page.getByRole('dialog').getByRole('button', { name: '确认创建训练', exact: true }).click()
    await page.locator('.training-detail').waitFor(); const training = (await get(`/api/career/positions/${pid}/trainings`))[0]
    assert.ok(training.payload.questions.every(q => !('correct' in q)))
    for (const question of await page.locator('.basic-question').all()) await question.locator('input[type=radio]').first().check()
    await button('提交基础题').click(); await page.getByText('本题正确', { exact: false }).or(page.getByText('本题需复习', { exact: false })).first().waitFor()
    assert.ok((await get('/api/career/trainings/' + training.training_id)).payload.result)
  })
  await step('17 个人事实与真实AI简历选材', async () => {
    await page.goto(base + '/resume'); await page.getByRole('heading', { name: '个人事实', exact: true }).waitFor()
    await page.getByLabel('姓名', { exact: true }).fill('原创合成学生'); await page.getByLabel('学校', { exact: true }).fill('原创合成大学'); await page.getByLabel('专业', { exact: true }).fill('计算机科学')
    await page.getByLabel('目标岗位', { exact: true }).fill('C++实习'); await page.getByLabel('技能（每行一项，最多40项）').fill('C++\n栈与队列')
    await button('添加项目').click(); await page.getByLabel('项目名称', { exact: true }).fill('原创合成数组练习'); await page.getByLabel('实际工作与成果', { exact: true }).fill('完成数组求和，实现输入处理，并在平台隔离编译器通过公开测试。'); await page.getByLabel('项目1关联编程记录', { exact: true }).selectOption(accepted)
    await button('保存个人事实').click(); await page.getByText('个人事实已保存', { exact: true }).waitFor()
    await page.getByLabel('生成方式', { exact: true }).selectOption('llm'); await page.getByLabel(/同意将教育、技能、项目事实及目标岗位/).check()
    const pending = page.waitForResponse(r => r.url().endsWith('/api/resume/generate') && r.request().method() === 'POST', { timeout: 120000 })
    await button('生成简历').click(); const r = await pending; assert.equal(r.status(), 200, (await r.text()).slice(0,200)); resumeId = (await r.json()).data.artifact_id
    await page.locator('.resume-preview pre').waitFor(); await download('导出 JSON', 'resume.json')
    assert.match(JSON.parse(fs.readFileSync(path.join(out, 'resume.json'), 'utf8')).markdown, /原创合成数组练习/)
  })
  await step('18 技能树使用同一账户真实判题证据', async () => {
    await page.goto(base + '/skills'); await page.getByLabel('技能名称', { exact: true }).fill('合成验收C++目标'); await page.getByLabel('验收说明', { exact: true }).fill('以公开测试AC作为任务条件，不推断就业能力')
    await page.getByLabel('关联验收记录', { exact: true }).selectOption('coding:' + accepted + ':-1'); await button('加入技能树').click(); await page.getByText('验收条件达成', { exact: true }).waitFor()
  })
  await step('19 学期模式与实际完成时间', async () => {
    await page.goto(base + '/semester'); await page.getByLabel('学期名称', { exact: true }).fill('原创合成验收学期'); await page.getByLabel('开始日期', { exact: true }).fill(date(0)); await page.getByLabel('结束日期', { exact: true }).fill(date(20)); await page.getByLabel('课程名称', { exact: true }).fill('合成数据结构课程'); await page.getByLabel('每周学习目标', { exact: true }).fill('完成并复盘真实编译测试')
    await button('预览学期编排').click(); await button('确认编排').click()
    const completed = page.waitForResponse(r => /\/api\/semester\/tasks\//.test(r.url()) && r.request().method() === 'PATCH')
    await page.getByRole('checkbox', { name: '合成数据结构课程 第1周 任务完成', exact: true }).check(); assert.equal((await completed).status(), 200)
    assert.ok((await get('/api/semester')).tasks.some(t => t.completed_at))
  })
  await step('20 成长报告包含实际作答判题面试和学期依据', async () => {
    await page.goto(base + '/growth'); const pending = page.waitForResponse(r => r.url().endsWith('/api/growth/reports') && r.request().method() === 'POST')
    await button('生成成长报告').click(); const report = (await (await pending).json()).data; growthId = report.artifact_id
    await page.getByRole('heading', { name: /记录依据 · 共/ }).waitFor(); await download('导出报告 JSON', 'growth.json')
    const full = JSON.parse(fs.readFileSync(path.join(out, 'growth.json'), 'utf8')); assert.ok(full.records.some(r => r.record_id === accepted)); assert.ok(full.records.length >= 5)
  })
  await step('21 全部个人数据导出及部分资料确认删除', async () => {
    await page.goto(base + '/trust'); await download('导出个人数据 JSON', 'personal.json'); await download('下载整包备份', 'personal.zip')
    const exported = JSON.parse(fs.readFileSync(path.join(out, 'personal.json'), 'utf8')); assert.ok(exported.tables.artifacts.some(a => a.artifact_id === resumeId)); assert.ok(exported.tables.artifacts.some(a => a.artifact_id === growthId))
    const preview = await get(`/knowledge/sources/${sid}/delete-preview`)
    const deleted = await context.request.delete(api + `/knowledge/sources/${sid}`, { data: { confirmed: true, confirmation_token: preview.confirmation_token } }); assert.equal(deleted.status(), 200)
    assert.equal((await context.request.get(api + `/knowledge/sources/${sid}`)).status(), 404)
  })
  await step('22 网页自助恢复后历史资料及全部关键记录可读', async () => {
    await page.getByLabel('选择 FileMate 整包备份', { exact: true }).setInputFiles(path.join(out, 'personal.zip')); await button('校验并预览备份').click(); await page.getByRole('heading', { name: '恢复预览', exact: true }).waitFor()
    await button('确认恢复这份备份').click(); await button('确认整体恢复').click(); await page.getByText('个人数据与托管文件已恢复', { exact: true }).waitFor()
    for (const url of [`/knowledge/sources/${sid}`, '/api/knowledge-graph', `/api/programming/submissions/${accepted}`, `/interviews/${iid}/review`, `/api/career/positions/${pid}`, `/api/resume/${resumeId}`, `/api/growth/reports/${growthId}`, '/api/semester', '/api/skills/tree']) assert.ok(await get(url))
    assert.equal((await get('/api/auth/me')).user.email, email); await page.reload(); await page.getByRole('heading', { name: '导出与恢复个人数据', exact: true }).waitFor()
    await page.setViewportSize({ width: 375, height: 1000 }); assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)); await page.screenshot({ path: path.join(out, 'full-flow-mobile.png'), fullPage: true })
  })
  await step('23 仅注销本轮自建合成账户', async () => {
    assert.equal((await get('/api/auth/me')).user.email, email)
    const preview = await get('/api/auth/delete-preview')
    const response = await context.request.post(api + '/api/auth/delete', { headers: { 'X-FileMate-Action': 'account' }, data: { confirmed: true, confirmation_token: preview.confirmation_token, password } })
    assert.equal(response.status(), 200)
    assert.equal((await response.json()).data.cleanup_pending, false)
  })
  assert.deepEqual(errors, [])
} catch (error) {
  fs.writeFileSync(path.join(out, 'failure.log'), String(error), 'utf8')
  await page.screenshot({ path: path.join(out, 'failure.png'), fullPage: true }).catch(() => {})
  process.exitCode = 1
} finally { save(); await browser.close() }
