import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const base = process.env.FILEMATE_WEB_URL
assert.ok(['127.0.0.1','localhost'].includes(new URL(base).hostname))
const out = path.resolve(process.env.FILEMATE_EVIDENCE_DIR)
assert.ok(out.startsWith(path.resolve('_working') + path.sep))
fs.mkdirSync(out,{recursive:true})
const browser = await chromium.launch({channel:'msedge',headless:true})
const context = await browser.newContext({viewport:{width:1440,height:1100},ignoreHTTPSErrors:true,
  httpCredentials:{username:process.env.FILEMATE_ACCEPTANCE_BASIC_USER,password:process.env.FILEMATE_ACCEPTANCE_BASIC_PASSWORD}})
const page = await context.newPage()
const checks=[], errors=[], external=[], poetryChecks=[]
await page.route('https://v1.hitokoto.cn/?c=i&encode=json&min_length=8&max_length=22', async route=>{
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
    uuid:'11111111-1111-4111-8111-111111111111',hitokoto:'会当凌绝顶，一览众山小。',type:'i',from:'望岳',from_who:'杜甫'
  })})
})
page.on('pageerror',error=>errors.push(String(error)))
page.on('request',request=>{
  if(['127.0.0.1','localhost'].includes(new URL(request.url()).hostname))return
  if(request.url()==='https://v1.hitokoto.cn/?c=i&encode=json&min_length=8&max_length=22') {
    poetryChecks.push(Promise.race([request.allHeaders(),new Promise((_,reject)=>setTimeout(()=>reject(new Error('Poetry headers could not be observed within 5 seconds')),5000))]).then(headers=>({
      method:request.method(), type:request.resourceType(), body:request.postData()!==null,
      privateHeaders:['cookie','authorization','referer'].some(name=>Boolean(headers[name]))
    })))
  } else external.push(request.url())
})
async function check(name,run) {
  try { await run(); checks.push({name,passed:true}) }
  catch(error) { checks.push({name,passed:false,error:String(error)}); await page.screenshot({path:path.join(out,`failure-${checks.length}.png`),fullPage:true}) }
  fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(checks,null,2))
  console.log(`${checks.at(-1).passed?'PASS':'FAIL'} ${name}`)
}
async function api(route, data) {
  const response=data?await context.request.post(base+route,data):await context.request.get(base+route)
  assert.ok(response.ok(),`${route}: ${response.status()}`)
  const body=await response.json(); assert.equal(body.success,true); return body.data
}
async function library() { await page.goto(base+'/knowledge');await page.getByRole('heading',{name:'我的资料',exact:true}).waitFor();await page.locator('.library .empty').filter({hasText:'正在读取'}).waitFor({state:'hidden'}) }
const card=name=>page.locator('.source-card').filter({has:page.getByRole('heading',{name,exact:true})})
async function expand(name) { const row=card(name); const open=row.getByRole('button',{name:'学习链与产物',exact:true}); if(await open.isVisible())await open.click();await row.locator('.lineage-rail').waitFor();return row }
const dialog=()=>page.getByRole('dialog',{name:/合成.*笔记/})
let a,b,an,bn,questions
const firstName='工程合成-栈与队列.txt',secondName='工程合成-网络通信.txt'
try {
  await check('empty library provides one main search and honest learning entries',async()=>{
    await library();await page.getByText('知识库还是空的',{exact:true}).waitFor()
    assert.equal(await page.locator('.knowledge-page select,.knowledge-page .el-select').count(),0)
    assert.equal(await page.locator('.evidence-entries a').count(),3)
    assert.equal(await page.locator('.sidebar .nav-item .tabler-icon').count(),9)
    const license=await context.request.get(base+'/licenses/tabler-icons.txt');assert.ok(license.ok());assert.ok((await license.text()).includes('Copyright (c) 2020-2026 Paweł Kuna'))
    assert.equal(await page.locator('.context-navigation .task-current').getAttribute('href'),'/knowledge')
    await page.screenshot({path:path.join(out,'knowledge-empty-1440.png'),fullPage:true})
  })
  await check('original synthetic sources persist through the actual import API',async()=>{
    a=await api('/knowledge/import',{multipart:{file:{name:firstName,mimeType:'text/plain',buffer:Buffer.from('原创工程合成资料，不是真实学生资料。\n栈遵循后进先出。队列遵循先进先出。栈使用 push 入栈，pop 出栈。')}}})
    b=await api('/knowledge/import',{multipart:{file:{name:secondName,mimeType:'text/plain',buffer:Buffer.from('原创工程合成资料，不是真实学生资料。\n网络通信：TCP提供可靠传输。UDP提供数据报传输。网络协议用来约定通信方式。')}}})
    an=await api(`/knowledge/sources/${a.source_id}/artifacts`,{data:{artifact_type:'notes',allow_external_model:true}})
    bn=await api(`/knowledge/sources/${b.source_id}/artifacts`,{data:{artifact_type:'notes',allow_external_model:true}})
    questions=await api(`/knowledge/sources/${a.source_id}/artifacts`,{data:{artifact_type:'questions',count:5,allow_external_model:true}})
    await library();assert.equal(await page.locator('.source-card').count(),2)
  })
  await check('filename filtering, visible scope selection and source citations work without dropdowns',async()=>{
    await page.getByRole('textbox',{name:'按资料名筛选'}).fill('栈');assert.equal(await page.locator('.source-card').count(),1)
    await page.getByRole('textbox',{name:'按资料名筛选'}).fill('不存在');await page.getByText('没有匹配的资料，换个名称试试。',{exact:true}).waitFor()
    await page.getByRole('textbox',{name:'按资料名筛选'}).fill('')
    await card(firstName).getByRole('button',{name:'检索此资料',exact:true}).click()
    await page.getByRole('textbox',{name:'检索知识库'}).fill('栈')
    const searched=page.waitForResponse(r=>new URL(r.url()).pathname==='/knowledge/search')
    await page.getByRole('button',{name:'开始检索',exact:true}).click()
    const response=await searched;assert.equal(new URL(response.url()).searchParams.get('source_id'),a.source_id)
    const body=await response.json();assert.ok(body.data.length>0 && body.data.every(item=>item.source_id===a.source_id))
    await page.locator('.results .result-list article').first().waitFor()
    assert.ok((await page.locator('.result-foot a').first().getAttribute('href')).includes(a.source_id))
  })
  await check('feedback refers to the searched query even after the draft input changes',async()=>{
    await page.getByRole('textbox',{name:'检索知识库'}).fill('未提交的新问题')
    const saved=page.waitForResponse(r=>r.request().method()==='POST' && new URL(r.url()).pathname==='/evaluation/feedback')
    await page.locator('.relevance').first().getByRole('button',{name:'相关',exact:true}).click()
    const response=await saved;assert.ok(response.ok());const data=response.request().postDataJSON()
    assert.equal(data.context.query_length,1)
    await page.getByRole('button',{name:`清除检索范围：${firstName}`,exact:true}).click()
    await page.getByRole('textbox',{name:'检索知识库'}).fill('')
  })
  await check('learning chain displays actual counts and persisted artifacts in readable panels',async()=>{
    const row=await expand(firstName)
    assert.equal(await row.locator('.lineage-rail article').count(),6)
    const lineage=await api(`/knowledge/sources/${a.source_id}/lineage`)
    assert.equal(await row.locator('.lineage-head>b').innerText(),`${lineage.completed_stage_count}/${lineage.total_stage_count} 环已形成`)
    assert.equal(await row.locator('.artifact-items button').count(),2)
    await page.locator('.content-scroll').evaluate(node=>{node.scrollTop=0});await page.screenshot({path:path.join(out,'knowledge-chain-1440.png'),fullPage:true})
  })
  await check('late responses from a previously selected source cannot populate the current source',async()=>{
    await card(firstName).getByRole('button',{name:'收起学习链',exact:true}).click()
    let delayed=false
    await page.route(`**/knowledge/sources/${a.source_id}/artifacts`,async route=>{const response=await route.fetch();delayed=true;await new Promise(resolve=>setTimeout(resolve,1100));await route.fulfill({response})})
    await card(firstName).getByRole('button',{name:'学习链与产物',exact:true}).click()
    for(let attempt=0;!delayed && attempt<100;attempt++)await page.waitForTimeout(20)
    assert.equal(delayed,true)
    const row=await expand(secondName)
    await page.waitForTimeout(1300)
    assert.equal(await row.locator('.artifact-items b').innerText(),bn.title)
    assert.equal(await row.getByText(an.title,{exact:true}).count(),0)
    await page.unroute(`**/knowledge/sources/${a.source_id}/artifacts`)
  })
  await check('failed learning-chain reads expose retry and recover using actual API data',async()=>{
    await card(secondName).getByRole('button',{name:'收起学习链',exact:true}).click()
    await page.route(`**/knowledge/sources/${b.source_id}/lineage`,route=>route.abort('failed'))
    await card(secondName).getByRole('button',{name:'学习链与产物',exact:true}).click()
    await card(secondName).locator('.artifact-error').waitFor()
    await page.unroute(`**/knowledge/sources/${b.source_id}/lineage`)
    await page.getByRole('button',{name:'重新读取',exact:true}).click()
    await card(secondName).locator('.lineage-rail').waitFor()
  })
  await check('artifact reading uses a keyboard focus trap and guards unsaved dismissal',async()=>{
    await card(secondName).locator('.artifact-items button').click()
    await dialog().waitFor();await page.getByRole('button',{name:'编辑',exact:true}).click()
    await dialog().getByRole('textbox',{name:'标题',exact:true}).fill('暂未保存的标题')
    for(let index=0;index<8;index++){await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>Boolean(document.activeElement?.closest('[role="dialog"]'))),true)}
    await page.keyboard.press('Escape');await page.getByRole('button',{name:'继续编辑',exact:true}).click()
    assert.equal(await dialog().getByRole('textbox',{name:'标题',exact:true}).inputValue(),'暂未保存的标题')
    const handler=async dialog=>dialog.dismiss();page.on('dialog',handler)
    assert.equal(await page.evaluate(()=>window.dispatchEvent(new Event('filemate:before-refresh',{cancelable:true}))),false)
    page.off('dialog',handler)
    assert.equal((await api(`/knowledge/artifacts/${bn.artifact_id}`)).title,bn.title)
    await page.getByRole('button',{name:'取消',exact:true}).click()
  })
  await check('editing, reloading and downloading retain the actual persisted artifact',async()=>{
    await page.getByRole('button',{name:'编辑',exact:true}).click()
    const title='网络通信 · 已核对笔记',content={title:'网络通信',sections:[{title:'TCP与UDP',content:'原创工程测试修改：TCP和UDP的区别。'}]}
    await dialog().getByRole('textbox',{name:'标题',exact:true}).fill(title)
    await dialog().getByRole('textbox',{name:/内容/}).fill('{无效JSON')
    await page.getByRole('button',{name:'保存修改',exact:true}).click()
    await page.getByText('JSON 格式不正确，请检查逗号和引号',{exact:true}).waitFor()
    assert.equal((await api(`/knowledge/artifacts/${bn.artifact_id}`)).title,bn.title)
    await dialog().getByRole('textbox',{name:/内容/}).fill(JSON.stringify(content))
    await page.getByRole('button',{name:'保存修改',exact:true}).click()
    await page.getByRole('heading',{name:title,exact:true}).waitFor()
    assert.deepEqual((await api(`/knowledge/artifacts/${bn.artifact_id}`)).content,content)
    await page.locator('.artifact-reading').getByText(content.sections[0].content,{exact:true}).waitFor()
    const download=page.waitForEvent('download');await page.getByRole('button',{name:'导出',exact:true}).click()
    const file=await download;await file.saveAs(path.join(out,'edited-artifact.json'));assert.deepEqual(JSON.parse(fs.readFileSync(path.join(out,'edited-artifact.json'),'utf8')),content)
    await page.getByRole('button',{name:'关闭学习产物',exact:true}).click();await library()
    const row=await expand(secondName);assert.equal(await row.locator('.artifact-items b').innerText(),title)
  })
  await check('the artifact reader remains usable on mobile and presents note paragraphs rather than raw JSON',async()=>{
    await page.setViewportSize({width:375,height:1000});await card(secondName).locator('.artifact-items button').click()
    await page.locator('.artifact-reading').waitFor()
    assert.equal(await page.locator('.artifact-reading h3').innerText(),'TCP与UDP')
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
    await page.screenshot({path:path.join(out,'artifact-reading-375.png'),fullPage:true})
    await page.getByRole('button',{name:'关闭学习产物',exact:true}).click()
  })
  for(const width of [375,768,1024,1440])await check(`large typography, source controls and moving navigation remain usable at ${width}px`,async()=>{
    await page.setViewportSize({width,height:1100});await library();await expand(firstName);await page.waitForTimeout(500)
    const facts=await page.evaluate(()=>{
      const active=document.querySelector('.task-current').getBoundingClientRect(),indicator=document.querySelector('.task-indicator').getBoundingClientRect()
      return {overflow:document.documentElement.scrollWidth>innerWidth,title:parseFloat(getComputedStyle(document.querySelector('.source-copy h3')).fontSize),search:parseFloat(getComputedStyle(document.querySelector('[name="knowledge_query"]')).fontSize),control:[...document.querySelectorAll('.source-actions button')].every(node=>node.getBoundingClientRect().height>=44),indicator:Math.abs(active.x-indicator.x)<2 && Math.abs(active.y-indicator.y)<2 && Math.abs(active.width-indicator.width)<2}
    })
    assert.equal(facts.overflow,false);assert.ok(facts.title>=20 && facts.search>=18 && facts.control && facts.indicator,JSON.stringify(facts))
    fs.writeFileSync(path.join(out,`layout-${width}.json`),JSON.stringify(facts,null,2))
    await page.locator('.content-scroll').evaluate(node=>{node.scrollTop=0});await page.locator('.page-head h1').click();await page.screenshot({path:path.join(out,`knowledge-${width}.png`),fullPage:true})
  })
  await check('reduced motion disables the new effects without hiding content',async()=>{
    await page.emulateMedia({reducedMotion:'reduce'});await library();await page.waitForTimeout(500)
    const facts=await page.evaluate(()=>({opacity:getComputedStyle(document.querySelector('.motion-surface')).opacity,animations:document.querySelector('.motion-surface').getAnimations().length,transition:getComputedStyle(document.querySelector('.task-indicator')).transitionDuration}))
    assert.equal(facts.opacity,'1');assert.equal(facts.animations,0);assert.ok(parseFloat(facts.transition)<=.00001)
    await page.emulateMedia({reducedMotion:'no-preference'})
  })
  await check('new learning entries reach the actual graph, review and evidence pages',async()=>{
    for(const [label,route] of [['连接知识','/knowledge-graph'],['继续复习','/today'],['回看成长','/growth']]){
      await library();await page.locator('.evidence-entries').getByRole('link',{name:new RegExp(label)}).click();await page.waitForURL(base+route)
    }
  })
  await check('delete cancellation preserves data; confirmation clears scope and dependent artifacts',async()=>{
    await library();await card(secondName).getByRole('button',{name:'检索此资料',exact:true}).click()
    await page.getByRole('button',{name:`删除资料：${secondName}`,exact:true}).click();await page.getByRole('button',{name:'取消',exact:true}).click()
    assert.ok(await api(`/knowledge/sources/${b.source_id}`))
    await page.getByRole('button',{name:`删除资料：${secondName}`,exact:true}).click();await page.locator('.el-message-box').getByRole('button',{name:'删除',exact:true}).click()
    await card(secondName).waitFor({state:'hidden'});await page.getByText('范围：全部资料',{exact:true}).waitFor()
    assert.equal((await context.request.get(base+`/knowledge/artifacts/${bn.artifact_id}`)).status(),404)
  })
  await check('no page exceptions, unexpected external assets or accumulating surface nodes; public poetry carries no private data',async()=>{
    for(let index=0;index<3;index++){await page.goto(base+'/');await page.locator('.welcome').waitFor();await library();assert.equal(await page.locator('.motion-surface').count(),1)}
    assert.deepEqual(errors,[]);assert.deepEqual(external,[])
    for(const request of await Promise.all(poetryChecks))assert.deepEqual(request,{method:'GET',type:'fetch',body:false,privateHeaders:false})
  })
} finally {
  fs.writeFileSync(path.join(out,'summary.json'),JSON.stringify({passed:checks.every(item=>item.passed),checks,errors,externalRequests:external,publicPoetryRequestCount:poetryChecks.length,scope:'Actual compiled Vue and TLS API; original synthetic materials and explicitly local model HTTP fixture; only the public poetry response uses a declared fixture, with outgoing requests checked for no credentials, body or referrer; real Hitokoto availability checked separately; no real learners or model-quality conclusion'},null,2))
  await browser.close()
}
if(checks.some(item=>!item.passed))process.exitCode=1
