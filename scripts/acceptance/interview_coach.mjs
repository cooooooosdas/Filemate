import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

function localUrl(name){const value=process.env[name];assert.ok(value,`${name} must explicitly name an isolated local candidate`);const url=new URL(value);assert.ok(['127.0.0.1','localhost','[::1]'].includes(url.hostname));return url.origin}
const base=localUrl('FILEMATE_WEB_URL'),api=localUrl('FILEMATE_API_URL')
assert.ok(process.env.FILEMATE_EVIDENCE_DIR,'FILEMATE_EVIDENCE_DIR required')
const out=path.resolve(process.env.FILEMATE_EVIDENCE_DIR)
assert.ok(out.split(path.sep).includes('_working'),'evidence must be inside _working')
const control=path.resolve(process.env.FILEMATE_FIXTURE_CONTROL || '')
assert.ok(process.env.FILEMATE_FIXTURE_CONTROL && control.split(path.sep).includes('_working') && fs.existsSync(control),'explicit isolated synthetic fixture control required; never inject production')
const callsFile=path.join(path.dirname(control),'calls.jsonl')
const mode=(name,extra={})=>{fs.writeFileSync(control+'.tmp',JSON.stringify({mode:name,delay:0,...extra}));fs.renameSync(control+'.tmp',control)}
const calls=()=>fs.existsSync(callsFile)?fs.readFileSync(callsFile,'utf8').trim().split('\n').filter(Boolean).length:0
fs.mkdirSync(out,{recursive:true})
mode('success')
const browser=await chromium.launch({channel:process.env.FILEMATE_BROWSER_CHANNEL || 'msedge',headless:true})
const context=await browser.newContext({viewport:{width:1440,height:1080},acceptDownloads:true})
await context.addInitScript(()=>{
 window.__cameraDenied=true;window.__stoppedRecorders=[]
 navigator.mediaDevices.getUserMedia=async options=>{
  if(window.__cameraDenied)throw new DOMException('synthetic denial','NotAllowedError')
  if(!options.video)return new MediaStream()
  const canvas=document.createElement('canvas');canvas.width=320;canvas.height=240
  canvas.getContext('2d').fillRect(0,0,320,240);return canvas.captureStream(5)
 }
 window.MediaRecorder=class {
  static isTypeSupported(){return true}
  state='inactive';mimeType='video/webm'
  start(){this.state='recording'}
  stop(){this.state='inactive';window.__stoppedRecorders.push(()=>{this.ondataavailable?.({data:new Blob(['synthetic-video'],{type:'video/webm'})});this.onstop?.()})}
 }
 window.__flushRecorders=()=>{for(const fn of window.__stoppedRecorders.splice(0))fn()}
 const create=URL.createObjectURL.bind(URL);window.__createdUrls=[];URL.createObjectURL=blob=>{const url=create(blob);window.__createdUrls.push(url);return url}
})
const page=await context.newPage();page.setDefaultTimeout(15000)
const errors=[];page.on('pageerror',e=>errors.push(String(e)))
const results=[]
const button=name=>page.getByRole('button',{name,exact:true})
let sid,firstAttempt,lastAttempt
async function check(name,run){console.log('RUN',name);try{const evidence=await run();results.push({name,passed:true,evidence});console.log('PASS',name)}catch(e){results.push({name,passed:false,error:String(e).slice(0,800)});console.log('FAIL',name,String(e).slice(0,500));await page.screenshot({path:path.join(out,`${name}-failure.png`),fullPage:true})}fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(results,null,2))}
async function get(url){const response=await context.request.get(api+url);assert.equal(response.status(),200);return (await response.json()).data}
const snapshot=()=>get(`/interviews/${sid}/coach`)
async function data(){return (await context.request.get(api+'/api/privacy/export?format=json')).json()}
async function waitFor(predicate){for(let i=0;i<60;i++){const value=await predicate();if(value)return value;await page.waitForTimeout(200)}throw new Error('condition timeout')}
async function newInterview(target){const response=await context.request.post(api+'/interviews',{data:{target_role:target,scenario:'技术面',difficulty:'标准',allow_external_analysis:false}});assert.equal(response.status(),200);return (await response.json()).data.interview_id}
async function answer(text,label='保存回答'){await page.locator('#coach-answer').fill(text);await button(label).click()}
try{
 await check('first_saved_before_analysis',async()=>{
  await page.goto(base+'/interview');await page.getByLabel('这次想练什么？').fill('合成验收：后端工程');await button('技术面').click();await button('开始模拟面试').click();await page.locator('#coach-answer').waitFor();sid=new URL(page.url()).searchParams.get('interview');assert.ok(sid)
  mode('success',{delay:4});await page.getByLabel('本场提交后自动分析问题与文字回答；不发送音视频。可随时关闭。').check();await waitFor(async()=> (await snapshot()).external_consent)
  const text='我通过真实测试验证了索引，记录环境、基线和查询结果。';await answer(text)
  const saved=await waitFor(async()=>{const s=await snapshot();return s.current_attempt?.answer===text && s.current_attempt.analysis_status==='running'?s:null})
  firstAttempt=saved.current_attempt.attempt_id;assert.equal(saved.displayed_index,0);assert.equal((await context.request.get(api+'/api/health')).status(),200)
  await page.getByLabel('本场提交后自动分析问题与文字回答；不发送音视频。可随时关闭。').uncheck()
  await waitFor(async()=> !(await snapshot()).external_consent)
  await waitFor(async()=> (await snapshot()).current_attempt.analysis_status==='cancelled')
  assert.equal((await snapshot()).current_attempt.score,null)
  await waitFor(()=>page.getByLabel('本场提交后自动分析问题与文字回答；不发送音视频。可随时关闭。').isEnabled())
  mode('success');await page.getByLabel('本场提交后自动分析问题与文字回答；不发送音视频。可随时关闭。').check();await button('重试本次分析').click()
  await waitFor(async()=> (await snapshot()).current_attempt?.analysis_status==='succeeded');await page.getByText('80 分 · 模型参考',{exact:true}).waitFor()
  await button('生成规则复盘报告').click();await page.locator('.report-body').waitFor()
  const oldReport=(await get(`/interviews/${sid}/review`)).report
  mode('success',{delay:4,feedback:'请补充重复实验的次数，再解释对照组。'});await button('重新分析本次回答').click()
  await waitFor(()=>page.locator('.report-body').count().then(n=>n===0))
  assert.equal(await button('生成规则复盘报告').isDisabled(),true)
  await waitFor(()=>page.getByText('80 分 · 模型参考',{exact:true}).isVisible())
  await button('生成规则复盘报告').click();await page.locator('.report-body').waitFor()
  assert.notEqual((await get(`/interviews/${sid}/review`)).report.artifact_id,oldReport.artifact_id)
  const exported=await data();assert.ok(exported.tables.interview_answer_attempts.some(a=>a.attempt_id===firstAttempt && a.answer===text));return {attempt:firstAttempt,saved_before_model_return:true}
 })
 await check('reanswer_latest_failure',async()=>{
  mode('timeout');await button('修改后再答').click();await answer('我重新检查了测试环境，补充了失败条件和索引对照。','保存这次重答')
  const failed=await waitFor(async()=>{const s=await snapshot();return s.current_attempt?.analysis_status==='failed'?s:null});lastAttempt=failed.current_attempt.attempt_id
  assert.notEqual(lastAttempt,firstAttempt);assert.equal(failed.current_attempt.score,null);await page.getByText('这次回答尚无有效分析；原文已保存，可以重试。',{exact:true}).waitFor();assert.equal(await page.getByText('80 分 · 模型参考',{exact:true}).count(),0)
  const report=await context.request.post(api+`/interviews/${sid}/review`,{data:{}});assert.equal(report.status(),200);assert.equal((await report.json()).data.assessed,0)
  return {latest:lastAttempt,score:null}
 })
 await check('history_comparison',async()=>{
  await page.getByText('查看重答历史与首末对照',{exact:true}).click();await button(/第 1 版/).waitFor()
  let s=await snapshot();const history=await get(`/interviews/${sid}/turns/${s.current_attempt.turn_id}/attempts?limit=1`);assert.equal(history.items.length,1);assert.equal(history.items[0].attempt_id,lastAttempt);assert.ok(history.next_before_version)
  const all=await get(`/interviews/${sid}/turns/${s.current_attempt.turn_id}/attempts`);assert.equal(all.items.find(a=>a.attempt_id===firstAttempt).score,80)
  await button(/第 1 版/).click();await page.getByRole('heading',{name:'第 1 版 · 历史回答'}).waitFor()
  for(const failure of ['badjson','429','budget','503']){mode(failure);await button('重试本次分析').click();await waitFor(async()=>{const current=await snapshot();return current.current_attempt.analysis_status==='failed' && !current.active_run_id});await waitFor(()=>button('重试本次分析').isEnabled())}
  mode('success');await button('重试本次分析').click();await page.getByText('80 分 · 模型参考',{exact:true}).waitFor();s=await snapshot();assert.equal(s.current_attempt.attempt_id,lastAttempt);assert.equal(s.current_attempt.version,2)
  await page.screenshot({path:path.join(out,'feedback-and-history.png'),fullPage:true});return {versions:2,failed_modes:['badjson','429','budget','503'],explicit_retry_succeeded:true}
 })
 await check('next_is_explicit',async()=>{
  const before=await snapshot();assert.equal(before.displayed_index,0);assert.equal(before.phase,'feedback');await button('继续下一题').click();await page.locator('#coach-answer').waitFor();const after=await snapshot();assert.equal(after.displayed_index,1);assert.equal(after.current_attempt,null);return {from:0,to:1}
 })
 await check('refresh_no_auto_ai',async()=>{
  const before=calls();await page.reload();await page.locator('#coach-answer').waitFor();await page.waitForTimeout(700);assert.equal(calls(),before);return {provider_calls:before}
 })
 await check('route_cancel_preserves_input',async()=>{
  const text='这段尚未提交的中文草稿\nExplain the boundary.';await page.locator('#coach-answer').fill(text)
  await page.locator('a[href="/"]').first().click();await button('继续练习').click();assert.equal(await page.locator('#coach-answer').inputValue(),text);assert.equal(new URL(page.url()).pathname,'/interview')
  await page.route('**/coach/answers',route=>route.abort('internetdisconnected'));await button('保存回答').click();await page.getByRole('alert').filter({hasText:'Network Error'}).waitFor();assert.equal(await page.locator('#coach-answer').inputValue(),text);await page.unroute('**/coach/answers')
  await page.locator('#coach-answer').fill('[DB_FAILURE] 合成数据库故障');await button('保存回答').click();await waitFor(()=>button('保存回答').isEnabled());assert.equal((await snapshot()).current_attempt,null);assert.equal(await page.locator('#coach-answer').inputValue(),'[DB_FAILURE] 合成数据库故障')
  assert.equal((await context.request.get(api+'/knowledge/sources')).status(),200);await page.locator('#coach-answer').fill('');return {draft_preserved:true,network_and_database_failures_isolated:true}
 })
 await check('stale_media_does_not_attach',async()=>{
  await button('开启摄像头').click();await page.getByText('当前无法访问摄像头，将跳过视频分析；可继续文字或语音回答。',{exact:true}).waitFor()
  await page.evaluate(()=>{window.__cameraDenied=false});await button('开启摄像头').click();await button('开始本地录像（含声音）').click();await button(/停止本地录像/).click()
  const nextId=await newInterview('合成第二场：媒体归属-'+sid);await page.locator('a[href="/"]').first().click();await button('离开').click();await page.waitForURL(base+'/');await page.locator('a[href="/interview"]').first().click();await page.getByText('接着上次练',{exact:true}).click();await button(new RegExp('合成第二场：媒体归属-'+sid)).click();await page.locator('#coach-answer').fill('新场次草稿不可覆盖')
  const urls=await page.evaluate(()=>window.__createdUrls.length);await page.evaluate(()=>window.__flushRecorders());assert.equal(await page.locator('#coach-answer').inputValue(),'新场次草稿不可覆盖');assert.equal(await page.evaluate(()=>window.__createdUrls.length),urls);assert.equal(new URL(page.url()).searchParams.get('interview'),nextId)
  await page.locator('#coach-answer').fill('');await page.goto(base+`/interview?interview=${sid}`);await page.locator('#coach-answer').waitFor();return {late_recording_discarded:true,next_session:nextId}
 })
 await check('flags_and_long_mobile_content',async()=>{
  const long=('长回答 English boundary.\n'.repeat(700)).slice(0,12000);await page.locator('#coach-answer').fill(long);assert.equal((await page.locator('#coach-answer').inputValue()).length,12000)
  await page.emulateMedia({reducedMotion:'reduce'});await page.keyboard.press('Tab');assert.notEqual(await page.evaluate(()=>document.activeElement.tagName),'BODY')
  for(const width of [390,768,1280,1440]){await page.setViewportSize({width,height:1080});const d=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,size:parseFloat(getComputedStyle(document.getElementById('coach-question')).fontSize)}));assert.ok(d.scroll<=d.width);assert.ok(d.size>=24);await page.screenshot({path:path.join(out,`long-${width}.png`),fullPage:true})}
  await page.locator('#coach-answer').fill('');await page.route('**/api/digital-human/speech',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'synthetic TTS failure'})}));await page.getByLabel('允许将点击朗读的文字发给 Microsoft 自然语音服务').check();await button('朗读当前问题').click();await page.getByText('自然语音暂时不可用，可继续阅读文字并稍后重试。',{exact:true}).waitFor();assert.ok(await page.locator('#coach-question').innerText());await page.unroute('**/api/digital-human/speech')
  mode('success',{coach:0,review:0});const legacy=await browser.newPage();await legacy.goto(api+`/interview?interview=${sid}`);await legacy.getByRole('button',{name:'提交并进入下一题',exact:true}).waitFor();await legacy.close();assert.equal((await context.request.get(api+`/interviews/${sid}/coach`)).status(),200);assert.equal((await context.request.get(api+`/interviews/${sid}/delete-preview`)).status(),200)
  mode('success')
  for(const voice of ['zh-CN-XiaoxiaoNeural','zh-CN-YunxiaNeural']){
   await page.locator('.coach-voice-select select').selectOption(voice);await button('朗读当前问题').click();await button('停止朗读').waitFor({timeout:60000});await page.locator('#coach-answer').fill('输入时停止朗读');await waitFor(()=>button('停止朗读').count().then(n=>n===0));await page.locator('#coach-answer').fill('')
  }
  return {widths:[390,768,1280,1440],long_text:12000,tts_failure_keeps_question:true,legacy_build_available:true,real_voices_play_and_stop:['晓晓','云夏']}
 })
 if(results.every(r=>r.passed)){
  const s=await snapshot();if(s.external_consent){const r=await context.request.post(api+`/interviews/${sid}/coach/consent`,{data:{allowed:false,request_key:crypto.randomUUID(),expected_revision:s.revision}});assert.equal(r.status(),200);await page.reload()}
  while((await snapshot()).phase!=='summary'){const before=await snapshot();await page.locator('#coach-answer').waitFor();await answer('合成验收回答：说明前提、行动和验证边界。');await button(before.displayed_index+1===before.session.questions.length?'完成并查看汇总':'继续下一题').click();await waitFor(async()=>{const after=await snapshot();return after.phase==='summary' || after.displayed_index!==before.displayed_index})}
  await button('生成规则复盘报告').click();await page.getByText('已回答',{exact:false}).first().waitFor();const report=await context.request.get(api+`/interviews/${sid}/review`);assert.equal(report.status(),200);const payload=(await report.json()).data.report;assert.equal(payload.assessed,1);assert.equal(payload.turns[0].attempt_id,lastAttempt)
  await button('回看第 1 题').click();await button('修改后再答').waitFor();await button('修改后再答').click();await answer('整场结束后重新核对首题，保留原题和提交进度。','保存这次重答')
  const revised=await snapshot();assert.equal(revised.session.status,'completed');assert.equal(revised.session.current_index,revised.session.questions.length);assert.equal(revised.current_attempt.version,3)
  await button('整场汇总').click();await page.getByRole('heading',{name:'本场回答已保存',exact:true}).waitFor()
  await button('生成规则复盘报告').click();await page.locator('.report-body').waitFor()
  for(const format of ['json','markdown','pdf'])assert.equal((await context.request.get(api+`/interviews/${sid}/review/export?format=${format}`)).status(),200)
  const raw=await context.request.get(api+'/api/privacy/export');assert.equal(raw.status(),200);const bytes=await raw.body();const preview=await context.request.post(api+'/api/privacy/restore-preview',{multipart:{file:{name:'synthetic.zip',mimeType:'application/zip',buffer:bytes}}});assert.equal(preview.status(),200);const restore=(await preview.json()).data
  assert.equal((await context.request.post(api+'/api/privacy/restore',{data:{backup_id:restore.backup_id,confirmation_token:restore.confirmation_token,confirmed:true}})).status(),200)
  assert.equal((await snapshot()).external_consent,false)
  assert.equal((await context.request.post(api+`/interviews/${sid}/analysis/clear`,{data:{confirmed:true}})).status(),200);assert.equal((await snapshot()).session.overall_score,null)
  const impact=await get(`/interviews/${sid}/delete-preview`);assert.ok(impact.answer_attempts>impact.answers);assert.equal((await context.request.delete(api+`/interviews/${sid}`,{data:{confirmed:true,confirmation_token:impact.confirmation_token}})).status(),200)
  results.push({name:'report_export_clear_delete_restore',passed:true,evidence:{assessed:payload.assessed,attempts:impact.answer_attempts}})
 }
 assert.deepEqual(errors,[]);assert.ok(results.length>=8 && results.every(r=>r.passed),'some acceptance groups failed')
}finally{mode('success');fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({results,errors,provider_calls:calls(),scope:'isolated synthetic provider and delayed media; not external service or real student evidence'},null,2));await browser.close()}
