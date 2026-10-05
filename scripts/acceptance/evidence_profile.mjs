import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { chromium } from 'playwright'

const base = process.env.FILEMATE_WEB_URL
const api = process.env.FILEMATE_API_URL
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR)
const db = path.resolve(process.env.FILEMATE_ACCEPTANCE_DB)
const working = path.resolve('_working') + path.sep
assert.ok(out.startsWith(working) && db.startsWith(working))
fs.mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1050 } })
const page = await context.newPage(), errors = [], results = []
page.on('pageerror', error => errors.push(String(error)))
const panel = () => page.locator('.learning-evidence')
const overview = async () => (await (await context.request.get(api + '/analytics/overview')).json()).data
async function open() { await page.goto(base + '/growth'); await panel().waitFor() }
async function check(name, kind, action) {
  try { await action(); results.push({ name, kind, passed: true }); console.log('PASS', name) }
  catch (error) { results.push({ name, kind, passed: false, error: String(error) }); console.log('FAIL', name, String(error)); await page.screenshot({ path: path.join(out, `failure-${results.length}.png`) }) }
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 2))
}
try {
  await check('empty records show pending assessment without percentages or bars', 'real_ui_api', async () => {
    await open()
    assert.equal(await panel().locator('[data-metric]').count(), 4)
    assert.match(await panel().innerText(), /待评测/)
    assert.equal(await page.locator('.ability .bars').count(), 0)
    assert.equal((await overview()).evidence_profile.metrics.quiz.value, null)
  })
  await check('actual storage fixtures produce precise sample counts and plan progress', 'synthetic_storage_fixture_real_ui', async () => {
    const script = `
from pathlib import Path
from datetime import datetime, timedelta, timezone
import json, sys
from filemate.execution.storage import SQLiteStorage
db=Path(sys.argv[1]).resolve()
assert db.is_relative_to(Path('_working').resolve())
s=SQLiteStorage(db); s.init_schema()
source=s.save_source(original_name='合成画像教材.txt',source_path='/synthetic/evidence.txt',raw_text='【合成工程资料】栈是后进先出的线性结构。')
a=s.save_artifact(source_id=source,artifact_type='questions',content=[{'question_type':'choice','stem':'栈遵循什么顺序？','options':['A. 后进先出','B. 先进先出'],'answer':'A','analysis':'栈是后进先出。'}])
for i in range(6):
    s.record_quiz_attempt(artifact_id=a,question_index=0,user_answer='B' if i<2 else 'A',is_correct=i>=2,score=0 if i<2 else 1,feedback='明确合成工程作答')
days=[{'day':i+1,'date':(datetime.now().date()+timedelta(days=i)).isoformat(),'topics':['栈'],'tasks':['工程复练']} for i in range(5)]
p=s.save_artifact(source_id=source,artifact_type='study_plan',content={'daily_plan':days})
plan=s.create_study_plan(artifact_id=p,source_id=source,plan={'title':'合成画像计划','exam_date':days[-1]['date'],'daily_minutes':30,'daily_plan':days})
for i in [0,1]: s.set_study_plan_day(plan['plan_id'],i,True)
session=s.create_interview(target_role='合成工程练习',scenario='求职面试',difficulty='标准',questions=['解释栈'])
s.save_interview_turn(interview_id=session['interview_id'],question_index=0,question='解释栈',answer='工程回放样本',score=None,dimensions={},feedback='没有模型评估',scoring_mode='local_fallback')
s.close()
print(json.dumps({'source_id':source,'artifact_id':a,'sample_kind':'synthetic'}))
`
    execFileSync(path.resolve('.venv/Scripts/python.exe'), ['-c', script, db], { encoding: 'utf8' })
    await open()
    const data = await overview()
    assert.equal(data.evidence_profile.metrics.quiz.sample_count, 6)
    assert.equal(data.evidence_profile.metrics.quiz.value, 66.67)
    assert.equal(data.evidence_profile.metrics.plan.value, 40)
    assert.equal(data.completed_study_days, 2)
    assert.match(await panel().locator('[data-metric="plan"]').innerText(), /40%/)
  })
  await check('fallback interview remains unassessed and one wrong record is insufficient', 'real_ui_api', async () => {
    const data = await overview()
    assert.equal(data.evidence_profile.metrics.interview.sample_count, 0)
    assert.equal(data.evidence_profile.unassessed_interview_turns, 1)
    assert.match(await panel().locator('[data-metric="wrong"]').innerText(), /样本不足，待评测/)
    assert.equal(await page.locator('.ability .bars').count(), 0)
  })
  await check('basis reveals formula and links restore the actual source question set', 'real_ui_api', async () => {
    const metric = panel().locator('[data-metric="quiz"]')
    await metric.locator('summary').click()
    assert.match(await metric.innerText(), /答对次数 \/ 作答次数/)
    const href = await metric.getByRole('link').first().getAttribute('href')
    assert.match(href, /^\/ai-tools\?artifact=/)
    await metric.getByRole('link').first().click()
    await page.locator('.learning-workspace').waitFor()
    await page.getByText('合成画像教材.txt', { exact: true }).first().waitFor()
    assert.match(await page.locator('main').innerText(), /合成画像教材/)
    await open()
  })
  await check('refresh is read only and does not duplicate evidence', 'real_ui_api', async () => {
    const before = await overview()
    await page.getByRole('button', { name: '刷新数据', exact: true }).click()
    await panel().waitFor()
    assert.deepEqual((await overview()).evidence_profile, before.evidence_profile)
  })
  await check('overview failure can be retried without replacing saved data', 'injected_network_failure', async () => {
    await page.route('**/analytics/overview', route => route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ success: false, error: '工程注入读取失败' }) }))
    await page.reload()
    await page.getByRole('button', { name: /重试/ }).waitFor()
    await page.unroute('**/analytics/overview')
    await page.getByRole('button', { name: /重试/ }).click()
    await panel().waitFor()
    assert.equal((await overview()).evidence_profile.metrics.quiz.sample_count, 6)
  })
  for (const width of [375, 768, 1440]) {
    await check(`evidence formulas and links fit ${width}px`, 'real_responsive_ui', async () => {
      await page.setViewportSize({ width, height: 1050 })
      await open()
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2), false)
      await page.screenshot({ path: path.join(out, `${width}.png`), fullPage: true })
    })
  }
  const summary = { passed: results.filter(item => item.passed).length, total: results.length, errors, results, sample_kind: 'synthetic' }
  fs.writeFileSync(path.join(out, 'summary.json'), JSON.stringify(summary, null, 2))
  if (summary.passed !== summary.total || errors.length) process.exitCode = 1
} finally { await browser.close() }
