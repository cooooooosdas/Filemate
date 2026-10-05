import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const base = process.env.FILEMATE_WEB_URL, api = process.env.FILEMATE_API_URL, out = process.env.FILEMATE_EVIDENCE_DIR
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
const errors = [], checks = []
page.on('pageerror', error => errors.push(String(error)))
await page.route('**/*', route => {
  const url = new URL(route.request().url())
  if (['xhr', 'fetch'].includes(route.request().resourceType()) && url.origin === base)
    return route.continue({ url: api + url.pathname + url.search })
  return route.continue()
})
try {
  await page.goto(base + '/skills')
  await page.getByRole('heading', { name: '我的技能树', exact: true }).waitFor()
  await page.getByLabel('技能名称', { exact: true }).fill('原创合成能力目标')
  await page.getByLabel('验收说明', { exact: true }).fill('仅用于UI验收，不是真实学生实验')
  await page.getByLabel('查找全部验收记录', { exact: true }).fill('知识点00000')
  await page.getByRole('button', { name: '搜索验收记录', exact: true }).click()
  const targets = (await (await page.request.get(api + '/api/skills/targets?q=知识点00000')).json()).data
  assert.equal(targets.length, 1)
  const target = targets[0], key = `${target.kind}:${target.target_id}:${target.question_index ?? -1}`
  await page.getByLabel('关联验收记录', { exact: true }).selectOption(key)
  await page.getByRole('button', { name: '加入技能树', exact: true }).click()
  await page.getByRole('heading', { name: '原创合成能力目标', exact: true }).waitFor()
  await page.getByText('继续练习', { exact: true }).waitFor()
  const attempt = await page.request.post(api + '/quiz/attempts', { data: { artifact_id: target.target_id, question_index: target.question_index, user_answer: '容量审计中的原创合成定义' } })
  assert.equal(attempt.status(), 200)
  assert.equal((await attempt.json()).data.is_correct, true)
  await page.getByRole('button', { name: '刷新证据', exact: true }).click()
  await page.getByText('验收条件达成', { exact: true }).waitFor()
  checks.push('UI creates persistent skill with actual quiz evidence; state changes after actual answer')
  await page.reload()
  await page.getByText('验收条件达成', { exact: true }).waitFor()
  await page.getByRole('button', { name: '调整目标与先修', exact: true }).click()
  await page.getByLabel('技能名称', { exact: true }).fill('修订后的合成目标')
  await page.getByRole('button', { name: '保存目标调整', exact: true }).click()
  await page.getByRole('heading', { name: '修订后的合成目标', exact: true }).waitFor()
  await page.setViewportSize({ width: 375, height: 900 })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
  await page.screenshot({ path: path.join(out, 'skills-mobile.png'), fullPage: true })
  checks.push('reload preserves state; editing and 375px layout work')
  assert.deepEqual(errors, [])
} finally {
  fs.writeFileSync(path.join(out, 'browser.json'), JSON.stringify({ checks, errors, sample_kind: 'synthetic_actual_api' }, null, 2))
  await browser.close()
}
console.log(JSON.stringify(checks))
