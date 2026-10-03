import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const base = process.env.FILEMATE_WEB_URL
assert.ok(['127.0.0.1', 'localhost'].includes(new URL(base).hostname))
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR)
assert.ok(out.startsWith(path.resolve('_working') + path.sep))
fs.mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ channel: process.env.FILEMATE_BROWSER_CHANNEL || 'msedge', headless: true })
const context = await browser.newContext({ ignoreHTTPSErrors: process.env.FILEMATE_ACCEPTANCE_INSECURE_TLS === '1',
  viewport: { width: 1440, height: 1000 }, httpCredentials: {
    username: process.env.FILEMATE_ACCEPTANCE_BASIC_USER, password: process.env.FILEMATE_ACCEPTANCE_BASIC_PASSWORD,
  } })
const page = await context.newPage()
const checks = [], errors = []
page.on('pageerror', error => errors.push(String(error)))
async function check(name, run) {
  try { await run(); checks.push({ name, passed: true }) }
  catch (error) { checks.push({ name, passed: false, error: String(error) }); await page.screenshot({ path: path.join(out, `failure-${checks.length}.png`), fullPage: true }) }
}
async function home() { await page.goto(base + '/'); await page.locator('.overview').waitFor() }
try {
  await check('nine primary task entries and the complete tool finder remain reachable', async () => {
    await home()
    assert.equal(await page.locator('.sidebar .nav-item').count(), 9)
    await page.getByRole('button', { name: '查找功能', exact: true }).click()
    assert.equal(await page.locator('.finder-results a').count(), 19)
    await page.keyboard.press('Escape')
  })
  await check('task directions switch related actions and navigate to the actual review page', async () => {
    await page.getByRole('button', { name: '复习备考', exact: true }).click()
    await page.locator('.focus-body').getByRole('link', { name: '开始复习', exact: true }).click()
    await page.getByRole('heading', { name: '今日学习', exact: true }).waitFor()
    assert.ok(await page.locator('.context-navigation a[href="/wrongbook"]').isVisible())
    await home()
    await page.getByRole('button', { name: '面试求职', exact: true }).click()
    await page.locator('.study-shortcuts a[href="/career"]').waitFor()
    await page.getByRole('button', { name: '读懂资料', exact: true }).click()
    await page.locator('.study-shortcuts a[href="/knowledge-graph"]').waitFor()
    assert.equal(await page.locator('.dashboard .el-select').count(), 0)
  })
  await check('ambient motion pauses outside the visible workspace and resumes on return', async () => {
    await home()
    await page.locator('[data-motion-state="running"]').waitFor()
    await page.locator('.content-scroll').evaluate(node => { node.scrollTop = node.scrollHeight })
    await page.locator('[data-motion-state="paused"]').waitFor()
    await page.locator('.content-scroll').evaluate(node => { node.scrollTop = 0 })
    await page.locator('[data-motion-state="running"]').waitFor()
  })
  await check('reduced-motion preference disables ambient animation and leaves content visible', async () => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.locator('[data-motion-state="reduced"]').waitFor()
    assert.equal(await page.locator('.knowledge-folio').evaluate(node => getComputedStyle(node).opacity), '1')
    assert.equal(await page.locator('.knowledge-stream').evaluate(node => node.getAnimations().length), 0)
    await page.getByRole('button', { name: '复习备考', exact: true }).click()
    await page.locator('.focus-body').getByRole('link', { name: '开始复习', exact: true }).waitFor()
    await page.emulateMedia({ reducedMotion: 'no-preference' })
  })
  for (const width of [375, 768, 1024, 1440]) await check(`actual redesigned Home typography, hit areas and layout at ${width}px`, async () => {
    await page.setViewportSize({ width, height: 1000 })
    await home()
    await page.waitForTimeout(1100)
    const facts = await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth > innerWidth,
      title: parseFloat(getComputedStyle(document.querySelector('.welcome h1')).fontSize),
      copy: parseFloat(getComputedStyle(document.querySelector('.focus-body p')).fontSize),
      buttons: [...document.querySelectorAll('.intent-options button')].map(node => ({
        size: parseFloat(getComputedStyle(node).fontSize), height: node.getBoundingClientRect().height,
      })),
      canvas: getComputedStyle(document.querySelector('.content-scroll')).backgroundImage,
      accent: getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(),
      surface: getComputedStyle(document.documentElement).getPropertyValue('--bg-surface').trim(),
      sceneRatio: document.querySelector('.knowledge-scene').getBoundingClientRect().width / document.querySelector('.welcome').getBoundingClientRect().width,
      sceneHeight: document.querySelector('.knowledge-scene').getBoundingClientRect().height,
    }))
    assert.equal(facts.overflow, false)
    assert.ok(facts.title >= 44 && facts.copy >= 17)
    assert.ok(facts.buttons.every(button => button.size >= 16 && button.height >= 44))
    assert.ok(facts.canvas.includes('radial-gradient') && facts.accent === '#2352d3')
    assert.equal(facts.surface, '#f2f6ff')
    assert.ok(facts.sceneRatio >= .98 && facts.sceneHeight >= 440)
    await page.screenshot({ path: path.join(out, `home-${width}.png`), fullPage: true })
    fs.writeFileSync(path.join(out, `font-${width}.json`), JSON.stringify(facts, null, 2))
  })
  await check('foreground contrast remains readable on the colored canvas and reading surface', async () => {
    function luminance(hex) {
      const channels=hex.slice(1).match(/../g).map(value=>parseInt(value,16)/255)
        .map(value=>value<=.04045?value/12.92:((value+.055)/1.055)**2.4)
      return channels[0]*.2126+channels[1]*.7152+channels[2]*.0722
    }
    const tokens=await page.evaluate(()=>{
      const css=getComputedStyle(document.documentElement)
      return Object.fromEntries(['--bg-base','--bg-surface','--text-primary','--text-secondary','--text-muted','--accent','--hero-highlight','--hero-ink'].map(name=>[name,css.getPropertyValue(name).trim()]))
    })
    const pairs=[]
    for(const foreground of ['--text-primary','--text-secondary','--text-muted']) for(const background of ['--bg-base','--bg-surface']) pairs.push([foreground,background])
    pairs.push(['--hero-ink','--accent'],['--text-primary','--hero-highlight'])
    const measured=pairs.map(([foreground,background])=>{
      const values=[luminance(tokens[foreground]),luminance(tokens[background])].sort((a,b)=>b-a)
      return {foreground,background,contrast:(values[0]+.05)/(values[1]+.05)}
    })
    fs.writeFileSync(path.join(out,'contrast.json'),JSON.stringify(measured,null,2))
    assert.ok(measured.every(pair=>pair.contrast>=4.5),JSON.stringify(measured))
  })
  await check('the new full canvas follows task routes and login without horizontal overflow', async () => {
    await page.setViewportSize({width:1440,height:1000})
    for(const route of ['/import','/knowledge','/today','/growth','/ai-tools']) {
      await page.goto(base+route)
      await page.locator('.sidebar').waitFor()
      const facts=await page.evaluate(()=>({
        background:getComputedStyle(document.querySelector('.content-scroll')).backgroundImage,
        overflow:document.documentElement.scrollWidth>innerWidth,
      }))
      assert.ok(facts.background.includes('radial-gradient'))
      assert.equal(facts.overflow,false,route)
      await page.screenshot({path:path.join(out,`canvas-${route.slice(1)}-1440.png`),fullPage:true})
    }
    await page.goto(base+'/login')
    await page.getByRole('heading',{name:'登录 FileMate',exact:true}).waitFor()
    await page.screenshot({path:path.join(out,'login-1440.png'),fullPage:true})
    await page.setViewportSize({width:375,height:1000})
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
    await page.screenshot({path:path.join(out,'login-375.png'),fullPage:true})
  })
  await check('narrow screens retain contextual navigation and mobile keyboard escape', async () => {
    await page.setViewportSize({ width: 375, height: 1000 })
    await page.goto(base + '/knowledge')
    await page.locator('.context-navigation').waitFor()
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
    await page.getByRole('button', { name: '打开导航', exact: true }).click()
    await page.locator('.sidebar a[href="/today"]').waitFor()
    await page.keyboard.press('Escape')
    assert.equal(await page.getByRole('button', { name: '打开导航', exact: true }).getAttribute('aria-expanded'), 'false')
  })
  await check('repeated routes reconstruct the motion scene without page errors', async () => {
    await page.setViewportSize({ width: 1440, height: 1000 })
    await page.locator('.sidebar .nav-item[href="/ai-tools"]').waitFor({ state: 'visible' })
    for (let index = 0; index < 3; index++) {
      await page.locator('.sidebar .nav-item[href="/ai-tools"]').click()
      await page.locator('.learning-workspace').waitFor()
      await page.locator('.sidebar .nav-item[href="/"]').click()
      await page.locator('.overview').waitFor()
      assert.equal(await page.locator('.knowledge-scene').count(), 1)
      assert.equal(await page.locator('.knowledge-folio').count(), 1)
    }
    assert.deepEqual(errors, [])
  })
} finally { await browser.close() }
const summary = { passed: checks.every(check => check.passed), total: checks.length, checks, errors,
  scope: 'actual compiled Vue and HTTPS Caddy; synthetic empty tenant; cobalt full-canvas palette, full-bleed scene, typography, navigation and motion lifecycle' }
fs.writeFileSync(path.join(out, 'summary.json'), JSON.stringify(summary, null, 2))
console.log(JSON.stringify({ passed: summary.passed, total: summary.total }))
if (!summary.passed) process.exitCode = 1
