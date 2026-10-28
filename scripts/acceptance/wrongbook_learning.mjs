import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import {chromium} from 'playwright'
import {themes} from '../../filemate/web/src/preferences/themes.ts'
const out=path.resolve(process.env.FILEMATE_EVIDENCE_DIR||'_working/wrongbook-d-20261028'),base=process.env.FILEMATE_WEB_URL||'http://127.0.0.1:5199',api=process.env.FILEMATE_API_URL||'http://127.0.0.1:8038',provider=process.env.FILEMATE_PROVIDER_URL||'http://127.0.0.1:8039'
for(const url of [base,api,provider])assert.equal(new URL(url).hostname,'127.0.0.1')
const root=fs.readFileSync(path.join(out,'fixture-path.txt'),'utf8').trim(),fixture=JSON.parse(fs.readFileSync(path.join(root,'manifest.json'),'utf8')),password=process.env.FILEMATE_AUDIT_PASSWORD
assert.ok(fixture.synthetic&&fs.existsSync(path.join(root,'.synthetic-wrongbook'))&&password)
const browser=await chromium.launch({channel:'msedge',headless:true}),ctx=await browser.newContext({viewport:{width:1440,height:1100}}),page=await ctx.newPage(),checks=[],errors=[]
page.setDefaultTimeout(15000);page.on('dialog',d=>d.accept());page.on('pageerror',e=>errors.push(String(e)))
const b=name=>page.getByRole('button',{name,exact:true}),wid='synthetic-wrong-00001'
async function login(c,user){const r=await c.request.post(api+'/api/auth/login',{headers:{Origin:base,'X-FileMate-Action':'account'},data:{email:user.email,password,remember:false}});assert.equal(r.status(),200,await r.text())}
async function data(url,c=ctx){const r=await c.request.get(api+url);assert.equal(r.status(),200,await r.text());return (await r.json()).data}
async function mode(value){const r=await ctx.request.post(provider+'/__mode',{data:{mode:value}});assert.equal(r.status(),200)}
const stats=async()=>await(await ctx.request.get(provider+'/__stats')).json()
async function open(){await page.goto(base+'/wrongbook?focus='+wid);await page.locator('.review-question h2').waitFor()}
async function hub(){if(await b('查看答案').count())await b('查看答案').click();await b('分析这次回答，安排下一步').click();await page.locator('.analysis-scope').waitFor()}
async function check(name,run){console.log('RUN '+name);try{const evidence=await run();checks.push({name,passed:true,evidence});console.log('PASS '+name)}catch(e){checks.push({name,passed:false,error:String(e)});console.log('FAIL '+name+': '+String(e));await page.screenshot({path:path.join(out,'failure-'+checks.length+'.png'),fullPage:true}).catch(()=>{})}fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({synthetic:true,checks,errors},null,2))}
function luminance(c){const v=c.slice(0,3).map(n=>{n/=255;return n<=.04045?n/12.92:((n+.055)/1.055)**2.4});return .2126*v[0]+.7152*v[1]+.0722*v[2]}
let analysisId,planId
try{
 await login(ctx,fixture.users[0]);await mode('success')
 await check('real answer, GET-only outbound preview, explicit single-call analysis and literal citations',async()=>{
  await open();assert.equal(await b('分析这次回答，安排下一步').isDisabled(),true);await page.locator('.review-question input[value=B]').check();await b('提交回答').click();await page.locator('.review-question .review-receipt').waitFor();const before=(await stats()).calls
  await hub();assert.equal((await stats()).calls,before);assert.equal(await b('分析这次回答').isDisabled(),true);await page.locator('.analysis-consent input').first().check();await b('分析这次回答').click();await page.locator('.analysis-hypothesis').waitFor();assert.equal((await stats()).calls,before+1);assert.equal(await page.locator('.analysis-consent input').first().isChecked(),false)
  const rows=await data('/wrongbook/v2/'+wid+'/analyses');analysisId=rows.items[0].analysis_id;const detail=await data('/wrongbook/v2/'+wid+'/analyses/'+analysisId);assert.equal(detail.result.kind,'supported_hypotheses');assert.ok(detail.result.uncertainties.length);return {calls:1,analysis_id:analysisId}
 })
 await check('adoption preview confirmation and separate undo preserve real answers',async()=>{
  const old=await data('/wrongbook/v2/'+wid+'/attempts');await page.locator('.analysis-hypothesis input').check();await b('预览采纳所选错因').click();await page.locator('.learning-confirm').waitFor();assert.equal(await page.locator('.learning-confirm').evaluate(el=>el===document.activeElement),true);await b('确认本次变更').click();await page.getByRole('heading',{name:'变更已保存'}).waitFor();assert.equal((await data('/wrongbook/v2/'+wid)).error_cause_source,'user');await b('预览撤销此次变更').click();await b('确认本次变更').click();await page.waitForTimeout(250);assert.equal((await data('/wrongbook/v2/'+wid+'/attempts')).total,old.total);return {attempts_preserved:old.total}
 })
 await check('editable task preview cancellation confirmation Today evidence and undo',async()=>{
  await page.locator('.learning-task').first().getByLabel('任务标题').fill('我来核对栈与队列');const count=(await data('/study-plans')).length
  await b('预览新增任务').click();await b('取消，保留原数据').click();assert.equal((await data('/study-plans')).length,count);await b('预览新增任务').click();await b('确认本次变更').click();await page.getByRole('link',{name:'打开新增学习计划',exact:true}).waitFor();const list=await data('/study-plans');assert.equal(list.length,count+1);planId=list[0].plan_id;assert.ok(JSON.stringify(list[0]).includes('我来核对栈与队列'))
  await page.getByRole('link',{name:'打开新增学习计划',exact:true}).click();await page.getByRole('link',{name:'回看生成此计划的作答与复盘证据',exact:true}).waitFor();const preference=await ctx.request.put(api+'/review/today/preferences',{headers:{Origin:base},data:{available_minutes:60,item_order:['plan:'+planId+':0']}});assert.equal(preference.status(),200,await preference.text());await page.goto(base+'/today');await page.getByText('我来核对栈与队列',{exact:false}).first().waitFor();await open();await hub();await page.getByRole('button',{name:/新增计划.*预览撤销/}).first().click();await b('确认本次变更').click();await page.waitForTimeout(200);assert.equal((await data('/study-plans')).some(p=>p.plan_id===planId),false);return {created_then_removed:planId}
 })
 await check('lost response, refresh and relogin recover the same request without another model call',async()=>{
  await open();await hub();let lost=false;await page.route('**/wrongbook/v2/*/analyses',async route=>{if(route.request().method()==='POST'&&!lost){lost=true;await route.fetch();await route.abort('failed')}else await route.continue()})
  const before=(await stats()).calls;await page.locator('.analysis-consent input').first().check();await b('分析这次回答').click();await b('查询原请求').waitFor();await page.unroute('**/wrongbook/v2/*/analyses');await ctx.clearCookies();await login(ctx,fixture.users[0]);await open();await hub();await page.getByRole('heading',{name:'分析已保存',exact:true}).waitFor();assert.equal((await stats()).calls,before+1);return {additional_calls:1,recovered_after_relogin:true}
 })
 await check('graph precise round trip preserves course and node and warns on an unsaved answer',async()=>{
  const links=await data('/wrongbook/v2/'+wid+'/connections');assert.ok(links.items.length);const link=links.items[0];await page.goto(base+link.route);await b('开始学习与练习').click();await page.locator('.cl-root').getByRole('button',{name:/合成复盘00001/}).first().click();await page.getByRole('link',{name:'打开此题复盘',exact:true}).waitFor();assert.ok(page.url().includes(encodeURIComponent(link.course_id)));await page.locator('.cl-question input[value=B]').check();await page.getByRole('link',{name:'打开此题复盘',exact:true}).click();await b('留在这里').click();assert.ok(await page.locator('.cl-question input[value=B]').isChecked());await page.getByRole('link',{name:'打开此题复盘',exact:true}).click();await b('继续离开').click();await page.locator('.review-question h2').waitFor();assert.ok(page.url().includes('focus='+wid));return {route:link.route}
 })
 await check('new real answer makes earlier analysis historical and prevents adoption',async()=>{
  await open();await page.locator('.review-question input[value=B]').check();await b('提交回答').click();await page.locator('.review-question .review-receipt').waitFor();const old=await data('/wrongbook/v2/'+wid+'/analyses/'+analysisId);assert.equal(old.stale,true);return {historical:analysisId}
 })
 await check('real worker failure matrix returns safe states and retains independent practice evidence',async()=>{
  const attempts=await data('/wrongbook/v2/'+wid+'/attempts'),aid=attempts.items[0].attempt_id,results=[]
  for(const [m,expected] of [['401','provider_unavailable'],['429','quota_exceeded'],['bad_json','invalid_output'],['no_refs','invalid_output'],['false_refs','invalid_output'],['dribble','timeout']]){
   await mode(m);const c=await data('/wrongbook/v2/'+wid+'/learning-context?attempt_id='+aid),start=Date.now(),r=await ctx.request.post(api+'/wrongbook/v2/'+wid+'/analyses',{timeout:25000,headers:{Origin:base},data:{attempt_id:aid,input_digest:c.input_digest,request_key:crypto.randomUUID(),force_refresh:true,allow_external_model:true}});assert.equal(r.status(),200,await r.text());const a=(await r.json()).data;assert.equal(a.status,'failed');assert.equal(a.error_code,expected);assert.equal(a.result,null);assert.equal((await data('/wrongbook/v2/'+wid+'/attempts')).total,attempts.total);assert.ok(Date.now()-start<23000);results.push({mode:m,error:expected,elapsed_ms:Date.now()-start})
  }await mode('success');return results
 })
 await check('cross-account analyses and evidence remain inaccessible',async()=>{
  const other=await browser.newContext();await login(other,fixture.users[1]);for(const route of ['/wrongbook/v2/'+wid,'/wrongbook/v2/'+wid+'/analyses/'+analysisId]){const r=await other.request.get(api+route);assert.equal(r.status(),404)}await other.close();return {status:404}
 })
 await check('cancel the real slow worker without changing independent answer history',async()=>{
  const attempts=await data('/wrongbook/v2/'+wid+'/attempts'),aid=attempts.items[0].attempt_id,c=await data('/wrongbook/v2/'+wid+'/learning-context?attempt_id='+aid),key=crypto.randomUUID();await mode('dribble');const start=Date.now(),work=ctx.request.post(api+'/wrongbook/v2/'+wid+'/analyses',{timeout:25000,headers:{Origin:base},data:{attempt_id:aid,input_digest:c.input_digest,request_key:key,force_refresh:true,allow_external_model:true}});let row;for(let n=0;n<40;n++){const r=await ctx.request.get(api+'/wrongbook/v2/analysis-requests/'+key);if(r.status()===200){row=(await r.json()).data;break}await page.waitForTimeout(50)}assert.equal(row.status,'running');const cancel=await ctx.request.post(api+'/wrongbook/v2/'+wid+'/analyses/'+row.analysis_id+'/cancel',{headers:{Origin:base},data:{request_key:crypto.randomUUID()}});assert.equal(cancel.status(),200);assert.equal((await(await work).json()).data.status,'cancelled');assert.ok(Date.now()-start<5000);assert.equal((await data('/wrongbook/v2/'+wid+'/attempts')).total,attempts.total);await mode('success');return {cancelled_in_ms:Date.now()-start}
 })
 await check('network failure and component read errors leave answer and base history usable',async()=>{
  await open();await page.route('**/learning-context?**',r=>r.abort('failed'));await hub().catch(()=>{});assert.ok(await page.locator('.review-question h2').isVisible());await page.unroute('**/learning-context?**');assert.ok((await data('/wrongbook/v2/'+wid+'/attempts')).items.length)
 })
 await check('four widths and themes, 44px controls, readable text, long results, 200 percent and keyboard',async()=>{
  await mode('long');await open();await hub();await page.locator('.analysis-consent input').first().check();await b('分析这次回答').click();await page.locator('.analysis-hypothesis').waitFor();const measures=[]
  for(const width of [1440,1024,768,375])for(const theme of ['blue-gray','mist','graphite','midnight']){await page.setViewportSize({width,height:1100});await page.evaluate(t=>{const root=document.documentElement;root.dataset.theme=t.id;for(const [key,value] of Object.entries(t.colors))root.style.setProperty('--'+key,value)},themes.find(t=>t.id===theme));assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);const dimensions=await b('分析这次回答').boundingBox();assert.ok(dimensions.height>=44);const font=await page.locator('.learning-section p').first().evaluate(el=>parseFloat(getComputedStyle(el).fontSize));assert.ok(font>=18);const colors=await page.locator('.learning-section p').first().evaluate(el=>{const rgb=s=>s.match(/[\d.]+/g)?.slice(0,3).map(Number);let p=el,bg='';while(p){bg=getComputedStyle(p).backgroundColor;if(bg!=='rgba(0, 0, 0, 0)'&&bg!=='transparent')break;p=p.parentElement}return {fg:rgb(getComputedStyle(el).color),bg:rgb(bg)}});const ratio=(Math.max(luminance(colors.fg),luminance(colors.bg))+.05)/(Math.min(luminance(colors.fg),luminance(colors.bg))+.05);assert.ok(ratio>=4.5,`${theme}: ${ratio}`);measures.push({width,theme,button_height:dimensions.height,font,contrast:ratio});await page.screenshot({path:path.join(out,`learning-${width}-${theme}.png`),fullPage:true})}
  await page.setViewportSize({width:1440,height:1100});await page.evaluate(()=>document.documentElement.style.zoom='2');assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);await page.evaluate(()=>document.documentElement.style.zoom='');await b('分析这次回答').focus();await page.keyboard.press('Tab');assert.ok(await page.evaluate(()=>document.activeElement?.tagName==='BUTTON'));return measures
 })
 assert.equal(errors.length,0,errors.join('\n'))
}finally{fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({synthetic:true,checks,errors},null,2));await browser.close()}
if(checks.some(item=>!item.passed)||errors.length)process.exitCode=1
