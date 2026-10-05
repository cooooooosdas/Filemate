import assert from 'node:assert/strict'
import crypto from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'
import { createRequire } from 'node:module'
const require = createRequire(path.resolve('_working/a11y-tools/package.json'))
const { chromium } = require('playwright')
const base = process.env.FILEMATE_WEB_URL || 'https://filemate.asia'
const out = process.env.FILEMATE_EVIDENCE_DIR || '_working/llm-credentials'
const fixture = process.env.FILEMATE_SYNTHETIC_MODEL_TRANSPORT === '1'
assert.ok(fixture && new URL(base).hostname === 'filemate.test', 'Positive synthetic credentials require the isolated fixture, never production')
await fs.mkdir(out, { recursive: true })
const options = { channel: process.platform === 'win32' ? 'msedge' : undefined, ignoreHTTPSErrors: process.env.FILEMATE_ACCEPTANCE_INSECURE_TLS === '1', proxy: {server:'direct://'}, args: ['--no-proxy-server', '--host-resolver-rules=MAP filemate.test 127.0.0.1'], viewport: { width: 1440, height: 1000 } }
let context = await chromium.launchPersistentContext(path.resolve(out, 'profile'), options)
let page = context.pages()[0]
const key = 'synthetic-browser-valid-' + crypto.randomUUID()
const bad = 'synthetic-browser-invalid-' + crypto.randomUUID()
const email = `synthetic-key-${crypto.randomUUID()}@example.invalid`
const password = crypto.randomBytes(3).toString('hex') + 'Ab7'
const checks = [], errors = [], requests = []
let sourceId, scope
function observe() {
  page.on('pageerror', error => errors.push(String(error)))
  page.on('request', request => {
    const url = new URL(request.url())
    if (url.origin !== base) return
    requests.push({ path: url.pathname, method: request.method(), has_key_header: Boolean(request.headers()['x-filemate-llm-key']), key_in_url_or_body: request.url().includes(key) || (request.postData() || '').includes(key) })
  })
}
observe()
async function check(name, body) {
  await body()
  checks.push({ name, passed: true })
}
async function api(url, method = 'GET', data) {
  return page.evaluate(async ({url,method,data}) => {
    const response = await fetch(url, { method, credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-FileMate-Action': 'account' }, ...(data ? {body:JSON.stringify(data)} : {}) })
    return {status:response.status,body:await response.json()}
  }, { url, method, data })
}
async function settings() {
  await page.getByRole('button', { name: '打开设置', exact: true }).click()
  await page.locator('.model-settings').waitFor()
  await page.waitForFunction(() => !document.querySelector('.model-status')?.textContent?.includes('正在读取'))
  await page.waitForFunction(() => {
    let element=document.querySelector('.el-dialog')
    if(!element) return false
    for(;element;element=element.parentElement) if(Number(getComputedStyle(element).opacity)<1) return false
    return !document.querySelector('.dialog-fade-enter-active')
  })
}
async function closeSettings() {
  await page.getByRole('dialog', { name: '应用设置' }).getByRole('button', { name: '关闭', exact: true }).click()
  await page.getByRole('dialog', { name: '应用设置' }).waitFor({ state: 'hidden' })
}
async function record() {
  return page.evaluate(async scope => {
    const db = await new Promise((resolve,reject) => {const req=indexedDB.open('filemate-model-vault',1);req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(new Error('vault read failed'))})
    try { return await new Promise((resolve,reject)=>{const req=db.transaction('credentials').objectStore('credentials').get(scope);req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(new Error('record read failed'))}) }
    finally {db.close()}
  }, scope)
}
try {
  await page.goto(base)
  await check('synthetic account and model status use actual isolated HTTPS APIs', async () => {
    assert.equal((await api('/api/auth/register','POST',{email,display_name:'合成密钥验收',password,keep_guest_data:false,remember:true})).status,200)
    const status=(await api('/api/llm/status')).body.data
    scope=status.credential_scope
    assert.match(scope,/^[a-f0-9]{64}$/)
    assert.equal(status.configured,false)
    await page.reload()
    await settings()
    assert.ok((await page.locator('.model-settings').innerText()).includes('待配置'))
  })
  await check('invalid key is tested and cannot overwrite local storage', async () => {
    await page.getByPlaceholder('粘贴你的 API 密钥').fill(bad)
    await page.getByRole('button',{name:'保存并测试',exact:true}).click()
    await page.locator('.model-message.error').waitFor()
    assert.match(await page.locator('.model-message.error').innerText(),/401/)
    assert.equal(await record(),undefined)
    assert.equal(new URL(page.url()).pathname,'/')
  })
  await check('valid synthetic key is encrypted only after transport verification', async () => {
    await page.getByPlaceholder('粘贴你的 API 密钥').fill(key)
    await page.getByRole('button',{name:'保存并测试',exact:true}).click()
    await page.waitForFunction(()=>document.querySelector('.model-status')?.textContent?.includes('连接正常'))
    assert.equal(await page.getByPlaceholder('粘贴你的 API 密钥').inputValue(),'')
    const secure = await page.evaluate(async ({scope,key}) => {
      const db=await new Promise(resolve=>{const req=indexedDB.open('filemate-model-vault');req.onsuccess=()=>resolve(req.result)})
      const row=await new Promise(resolve=>{const req=db.transaction('credentials').objectStore('credentials').get(scope);req.onsuccess=()=>resolve(req.result)})
      db.close()
      let exportRejected=false
      try {await crypto.subtle.exportKey('raw',row.key)} catch {exportRejected=true}
      return {nonextractable:!row.key.extractable,algorithm:row.key.algorithm.name,exportRejected,encrypted:!new TextDecoder().decode(row.ciphertext).includes(key),plainFields:JSON.stringify(row).includes(key),webStorage:[...Object.values(localStorage),...Object.values(sessionStorage)].some(value=>value.includes(key))}
    },{scope,key})
    assert.deepEqual(secure,{nonextractable:true,algorithm:'AES-GCM',exportRejected:true,encrypted:true,plainFields:false,webStorage:false})
  })
  await check('invalid replacement preserves the previously verified credential', async () => {
    await page.getByPlaceholder('粘贴你的 API 密钥').fill(bad)
    await page.getByRole('button',{name:'保存并测试',exact:true}).click()
    await page.locator('.model-message.error').waitFor()
    await page.getByRole('button',{name:'测试连接',exact:true}).click()
    await page.waitForFunction(()=>document.querySelector('.model-status')?.textContent?.includes('连接正常')&&!document.querySelector('.model-message.error'))
    await closeSettings()
  })
  await check('encrypted CryptoKey survives a complete browser restart', async () => {
    await context.close()
    context=await chromium.launchPersistentContext(path.resolve(out,'profile'),options)
    page=context.pages()[0];observe()
    await page.goto(base)
    await settings()
    assert.ok((await page.locator('.model-settings').innerText()).includes('当前浏览器 · 本机加密'))
    await page.getByRole('button',{name:'测试连接',exact:true}).click()
    await page.waitForFunction(()=>document.querySelector('.model-status')?.textContent?.includes('连接正常'))
    await closeSettings()
  })
  await check('current account credential reaches the real generation route with synthetic model transport', async () => {
    const imported=await page.evaluate(async()=>{
      const form=new FormData();form.append('file',new File(['# 合成凭据工程资料\n\n栈是后进先出（LIFO），队列先进先出（FIFO）。仅供工程测试。'],'凭据回归.md',{type:'text/markdown'}))
      const response=await fetch('/knowledge/import',{method:'POST',body:form,credentials:'include'});return response.json()
    })
    sourceId=imported.data.source_id
    await page.goto(base+'/ai-tools?source='+sourceId)
    await page.locator('.generation-kinds button').filter({hasText:'摘要'}).click()
    await page.locator('.model-consent input').check()
    await page.locator('.generation-submit button').click()
    await page.waitForFunction(()=>document.body.innerText.includes('合成资料摘要'))
    const artifacts=(await api(`/knowledge/sources/${sourceId}/artifacts`)).body.data
    assert.ok(artifacts.some(item=>item.artifact_type==='summary'))
    assert.ok(requests.some(item=>item.path===`/knowledge/sources/${sourceId}/artifacts`&&item.method==='POST'&&item.has_key_header))
  })
  await check('logout hides previous account credential and login restores its own scope', async () => {
    await api('/api/auth/logout','POST',{})
    await page.goto(base)
    await settings()
    assert.ok((await page.locator('.model-settings').innerText()).includes('待配置'))
    await closeSettings()
    await api('/api/auth/login','POST',{email,password,remember:true})
    await page.reload();await settings()
    assert.ok((await page.locator('.model-settings').innerText()).includes('当前浏览器 · 本机加密'))
  })
  await check('settings maintain four layouts and accessibility', async () => {
    const axe=await fs.readFile(require.resolve('axe-core/axe.min.js'),'utf8')
    for(const width of [375,768,1024,1440]) {
      await page.setViewportSize({width,height:1000})
      await page.evaluate(axe)
      const violations=await page.evaluate(async()=> (await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}})).violations.map(item=>({id:item.id,nodes:item.nodes.map(node=>({target:node.target,summary:node.failureSummary}))})))
      assert.deepEqual(violations,[],`settings ${width}`)
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
      await page.screenshot({path:`${out}/settings-${width}.png`,mask:[page.getByPlaceholder('粘贴你的 API 密钥')]})
    }
  })
  await check('remove deletes only this account browser credential', async () => {
    await page.getByRole('button',{name:'移除本机密钥',exact:true}).click()
    await page.locator('.el-message-box').getByRole('button',{name:'确认移除',exact:true}).click()
    await page.waitForFunction(()=>document.querySelector('.model-status')?.textContent?.includes('待配置'))
    assert.equal(await record(),undefined)
    assert.ok(!requests.some(item=>item.path==='/settings/llm'||item.key_in_url_or_body))
    assert.ok(requests.filter(item=>item.has_key_header).every(item=>item.path==='/api/llm/test'||item.path.endsWith('/artifacts')))
  })
} catch(error) {
  errors.push(error.stack || String(error))
  await fs.writeFile(`${out}/failure-text.txt`, await page.locator('body').innerText())
  await page.screenshot({path:`${out}/failure.png`,mask:[page.getByPlaceholder('粘贴你的 API 密钥')]})
  await fs.writeFile(`${out}/failure-requests.json`,JSON.stringify(requests,null,2))
}
finally {
  if(sourceId) { const preview=await api(`/knowledge/sources/${sourceId}/delete-preview`); await api(`/knowledge/sources/${sourceId}`,'DELETE',{confirmed:true,confirmation_token:preview.body.data.confirmation_token}).catch(()=>{}) }
  await api('/api/auth/logout','POST',{}).catch(()=>{})
  await context.close()
  const report={passed:!errors.length,checks,errors,sample_kind:'synthetic_account_real_browser_crypto_and_HTTPS_with_explicit_synthetic_model_transport',scope:'Only self-created account, key and material; no production or real user credential read; positive model response injected in isolated server transport, not evidence of real DeepSeek connectivity.'}
  await fs.writeFile(`${out}/summary.json`,JSON.stringify(report,null,2))
  console.log(JSON.stringify(report,null,2))
  if(!report.passed) process.exitCode=1
}
