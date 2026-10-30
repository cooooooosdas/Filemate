import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const out=path.resolve(process.env.FILEMATE_EVIDENCE_DIR),base=process.env.FILEMATE_WEB_URL,api=process.env.FILEMATE_API_URL,password=process.env.FILEMATE_AUDIT_PASSWORD
for(const url of [base,api])assert.equal(new URL(url).hostname,'127.0.0.1')
const root=fs.readFileSync(path.join(out,'fixture-path.txt'),'utf8').trim(),fixture=JSON.parse(fs.readFileSync(path.join(root,'manifest.json'),'utf8'))
assert.ok(fixture.synthetic&&fs.existsSync(path.join(root,'.synthetic-wrongbook'))&&password)
const browser=await chromium.launch({channel:'msedge',headless:true}),ctx=await browser.newContext({viewport:{width:1366,height:1100},reducedMotion:'reduce'}),page=await ctx.newPage(),checks=[],errors=[]
page.setDefaultTimeout(15000);page.on('dialog',d=>d.accept());page.on('pageerror',e=>errors.push(String(e)))
const b=name=>page.getByRole('button',{name,exact:true}),planner=page.locator('.review-session-planner')
async function login(c,user){const r=await c.request.post(api+'/api/auth/login',{headers:{Origin:base,'X-FileMate-Action':'account'},data:{email:user.email,password,remember:false}});assert.equal(r.status(),200)}
async function data(url,c=ctx){const r=await c.request.get(api+url);assert.equal(r.status(),200);return(await r.json()).data}
async function open(query=''){await page.goto(base+'/wrongbook'+query);await page.locator('.review-catalog').waitFor({state:'attached'});if(query.includes('focus='))await page.locator('.review-question h2').waitFor();else await page.locator('.review-list>li').first().waitFor()}
async function preview(minutes=12){await b('开始本次复习').click();await planner.getByLabel('可用时间（分钟）',{exact:true}).fill(String(minutes));await b('预览本次题目').click();await planner.locator('.session-plan-summary').waitFor()}
async function check(name,run){console.log('RUN '+name);try{checks.push({name,passed:true,evidence:await run()});console.log('PASS '+name)}catch(e){checks.push({name,passed:false,error:String(e)});console.log('FAIL '+name+': '+e);await page.screenshot({path:path.join(out,'failure-'+checks.length+'.png'),fullPage:true}).catch(()=>{})}fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({synthetic:true,checks,errors},null,2))}
const lum=c=>c.slice(0,3).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0)
try{
 await login(ctx,fixture.users[0])
 await check('recommended explicit choice, due default, bounded list and reasons',async()=>{
  await open('?sort=due');assert.equal(await page.getByLabel('排序',{exact:true}).inputValue(),'due')
  await page.getByLabel('排序',{exact:true}).selectOption('recommended');await b('查找').click();await page.waitForURL('**sort=recommended**');await page.locator('.priority-reason').first().waitFor()
  assert.ok(await page.locator('.review-list>li').count()<=30);assert.match(await page.locator('.priority-reason').first().innerText(),/错误|到期|逾期/)
  return{url:page.url(),count:await page.locator('.review-list>li').count()}
 })
 await check('zero budget, input invalidation, no writes and exact checked handoff',async()=>{
  const before=await data('/wrongbook/v2/summary');await preview(0);assert.equal(await planner.locator('.session-plan-list li').count(),0);assert.equal(await b('核验并开始本次复习').isDisabled(),true)
  await planner.getByLabel('可用时间（分钟）',{exact:true}).fill('12');assert.equal(await planner.locator('.session-plan-summary').count(),0)
  const response=page.waitForResponse(r=>r.url().includes('/session-preview')&&r.status()===200);await b('预览本次题目').click();const selected=(await(await response).json()).data
  assert.equal(selected.selected_count,3);assert.equal((await data('/wrongbook/v2/summary')).saved_review_attempt_count,before.saved_review_attempt_count)
  const checking=page.waitForRequest('**/wrongbook/v2/session-check');await b('核验并开始本次复习').click();const body=(await checking).postDataJSON();assert.deepEqual(body.refs,selected.items.map(i=>i.ref))
  await page.locator('.focus-review .review-question h2').waitFor();assert.equal(await page.locator('.focus-review .review-question h2').innerText(),selected.items[0].stem)
  assert.equal((await data('/wrongbook/v2/summary')).saved_review_attempt_count,before.saved_review_attempt_count);return{selected:selected.selected_count,first:selected.items[0].ref.wrong_id}
 })
 await check('save once, refresh original batch, verify receipt and advance',async()=>{
  let writes=0;await page.route('**/wrongbook/v2/attempts',r=>{writes++;return r.continue()})
  await page.getByLabel('你的回答',{exact:true}).fill('后进先出');await b('提交回答').click();await page.locator('.review-receipt').waitFor();await b('下一题').waitFor({state:'visible'});await page.waitForFunction(()=>!Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='下一题')?.disabled)
  const stem=await page.locator('.review-question h2').innerText();await page.reload();await page.locator('.focus-review .review-question h2').waitFor();assert.equal(await page.locator('.review-question h2').innerText(),stem);await page.getByText('此题已有经服务器核验的作答，不会重新提交。',{exact:true}).waitFor();assert.equal(writes,1)
  await b('下一题').click();await page.getByText(/第 2 \/ 3 题/).waitFor();assert.equal(writes,1);await page.unroute('**/wrongbook/v2/attempts');return{writes,resumed:true}
 })
 await check('unsaved draft survives cancelled navigation to checked new batch',async()=>{
  await page.getByLabel('你的回答',{exact:true}).fill('尚未提交的独立回答');await b('返回浏览').click();await page.getByRole('dialog').waitFor();await page.getByRole('button',{name:'继续复盘',exact:true}).click();assert.equal(await page.getByLabel('你的回答',{exact:true}).inputValue(),'尚未提交的独立回答')
  await b('返回浏览').click();await page.getByRole('button',{name:'离开',exact:true}).click();await page.locator('.review-catalog').waitFor();return{draft_preserved:true}
 })
 await check('409 clears preview, network failure preserves selection for explicit retry',async()=>{
  await open('?sort=recommended');await preview();await page.route('**/wrongbook/v2/session-check',r=>r.fulfill({status:409,contentType:'application/json',body:JSON.stringify({detail:'synthetic conflict'})}));await b('核验并开始本次复习').click();await planner.getByRole('alert').waitFor();assert.equal(await planner.locator('.session-plan-summary').count(),0);assert.ok(!page.url().includes('mode=focus'));await page.unroute('**/wrongbook/v2/session-check')
  await b('预览本次题目').click();await planner.locator('.session-plan-summary').waitFor();const text=await planner.locator('.session-plan-list').innerText();await page.route('**/wrongbook/v2/session-check',r=>r.abort('internetdisconnected'));await b('核验并开始本次复习').click();await planner.getByRole('alert').waitFor();assert.equal(await planner.locator('.session-plan-list').innerText(),text);await page.unroute('**/wrongbook/v2/session-check');return{conflict_repreview:true,offline_retained:true}
 })
 await check('late preview after budget change cannot revive obsolete selection',async()=>{
  let held,release;const gate=new Promise(r=>{release=r});await page.route('**/wrongbook/v2/session-preview?**',async r=>{held=true;const result=await r.fetch();await gate;await r.fulfill({response:result})})
  await b('预览本次题目').click();await page.waitForTimeout(150);assert.equal(held,true);await planner.getByLabel('可用时间（分钟）',{exact:true}).fill('20');release();await page.waitForTimeout(300);assert.equal(await planner.locator('.session-plan-summary').count(),0);await page.unroute('**/wrongbook/v2/session-preview?**');return{stale_rejected:true}
 })
 await check('five specified widths x four themes: long content, contrast and task first',async()=>{
  const rows=[]
  for(const width of [1920,1366,1024,390,375])for(const theme of ['blue-gray','mist','graphite','midnight']){
   await page.setViewportSize({width,height:1100});await page.evaluate(t=>{localStorage.setItem('filemate-appearance',t);window.dispatchEvent(new StorageEvent('storage',{key:'filemate-appearance',newValue:t}))},theme);await open('?focus=synthetic-wrong-00004')
   const m=await page.evaluate(()=>{const h=document.querySelector('.review-question h2'),panel=document.querySelector('.review-main'),s=getComputedStyle(h);return{theme:document.documentElement.dataset.theme,fg:s.color,bg:getComputedStyle(panel).backgroundColor,font:parseFloat(s.fontSize),overflow:document.documentElement.scrollWidth>innerWidth+1,questionY:h.getBoundingClientRect().top,headingVisible:!!document.querySelector('.workspace-heading')?.getBoundingClientRect().height,targets:[...panel.querySelectorAll('button')].filter(b=>b.getBoundingClientRect().width).map(b=>b.getBoundingClientRect().height)}})
   const a=lum(m.fg.match(/[\d.]+/g).map(Number)),c=lum(m.bg.match(/[\d.]+/g).map(Number)),contrast=(Math.max(a,c)+.05)/(Math.min(a,c)+.05)
   assert.equal(m.theme,theme);assert.equal(m.overflow,false);assert.ok(m.font>=24);assert.ok(contrast>=4.5,`${theme}: ${contrast}`);assert.ok(m.targets.every(n=>n>=43.9));if(width<=390){assert.equal(m.headingVisible,false);assert.ok(m.questionY<600,JSON.stringify(m))}
   await page.screenshot({path:path.join(out,`workspace-${width}-${theme}.png`),fullPage:true});rows.push({width,...m,contrast})
  }
  await page.setViewportSize({width:1366,height:1100});return rows
 })
 await check('keyboard and reduced motion, no auto batch for new account, empty preview',async()=>{
  await open('?sort=due');await b('开始本次复习').focus();await page.keyboard.press('Enter');await planner.waitFor();await planner.getByLabel('可用时间（分钟）',{exact:true}).focus();await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement.type),'number');assert.equal(await page.evaluate(()=>matchMedia('(prefers-reduced-motion: reduce)').matches),true)
  const empty=await browser.newContext(),p=await empty.newPage();await login(empty,fixture.users.find(u=>!u.wrong_count));await p.goto(base+'/wrongbook?mode=focus');await p.getByText('先预览本次题目，再开始复习。',{exact:true}).waitFor();assert.equal(await p.locator('.review-question').count(),0);await p.getByRole('button',{name:'按可用时间预览下一批',exact:true}).click();await p.getByRole('button',{name:'预览本次题目',exact:true}).click();await p.getByText('当前预算与筛选下没有可安排的到期题。可调整时间或回到目录修改筛选。',{exact:true}).waitFor();await empty.close();return{keyboard:true,reduced_motion:true,empty:true}
 })
 await check('authenticated account boundary does not expose saved attempt from another workspace',async()=>{
  const owner=fixture.users[0],empty=fixture.users.find(u=>!u.wrong_count),c=await browser.newContext();await login(c,empty);const r=await c.request.get(api+'/wrongbook/v2/'+owner.last.wrong_id);assert.equal(r.status(),404);await c.close();return{status:404}
 })
 await check('post-save delayed summary failure preserves next question draft without identity refresh',async()=>{
  await open('?sort=recommended');await preview();await b('核验并开始本次复习').click();await page.locator('.focus-review .review-question h2').waitFor()
  let release,summaryCalls=0,capabilityCalls=0
  const gate=new Promise(r=>{release=r})
  await page.route('**/wrongbook/v2/capabilities',r=>{capabilityCalls++;return r.abort('internetdisconnected')})
  await page.route('**/wrongbook/v2/summary',async r=>{summaryCalls++;await gate;return r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'synthetic summary unavailable'})})})
  await page.getByLabel('你的回答',{exact:true}).fill('后进先出');await b('提交回答').click();await page.locator('.review-receipt').waitFor();await page.waitForFunction(()=>!Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='下一题')?.disabled);await b('下一题').click();await page.getByText(/第 2 \/ 3 题/).waitFor()
  await page.getByLabel('你的回答',{exact:true}).fill('下一题未提交的正文要保留');release();await page.getByText('复习概览暂未更新，已保存作答与当前输入保留。',{exact:false}).waitFor();assert.equal(await page.getByLabel('你的回答',{exact:true}).inputValue(),'下一题未提交的正文要保留');assert.equal(capabilityCalls,0);assert.ok(summaryCalls>=1)
  await page.unroute('**/wrongbook/v2/capabilities');await page.unroute('**/wrongbook/v2/summary');return{capabilityCalls,summaryCalls,draft_preserved:true}
 })
 assert.equal(checks.filter(c=>!c.passed).length,0,JSON.stringify(checks.filter(c=>!c.passed)));assert.deepEqual(errors,[])
}finally{fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({synthetic:true,checks,errors},null,2));await browser.close()}
