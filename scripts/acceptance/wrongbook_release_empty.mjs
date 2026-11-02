import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import {chromium} from 'playwright'
const out=path.resolve(process.env.FILEMATE_EVIDENCE_DIR),root=fs.readFileSync(path.join(out,'fixture-path.txt'),'utf8').trim()
const fixture=JSON.parse(fs.readFileSync(path.join(root,'manifest.json'),'utf8')),user=fixture.users.find(u=>u.wrong_count===1000)
const base='http://127.0.0.1:5200',api='http://127.0.0.1:8040'
assert.ok(fixture.synthetic&&fs.existsSync(path.join(root,'.synthetic-wrongbook')))
const browser=await chromium.launch({channel:'msedge',headless:true}),ctx=await browser.newContext(),p=await ctx.newPage()
try {
 const login=await ctx.request.post(api+'/api/auth/login',{headers:{Origin:base,'X-FileMate-Action':'account'},data:{email:user.email,password:process.env.FILEMATE_AUDIT_PASSWORD,remember:false}})
 assert.equal(login.status(),200)
 await p.goto(base+'/wrongbook?focus='+user.last.wrong_id)
 await p.locator('.review-question h2').waitFor()
 const question=await p.locator('.review-question h2').innerText()
 await p.getByLabel('你的回答',{exact:true}).fill('离开前尚未提交的合成草稿')
 await p.getByRole('searchbox',{name:'搜索全部错题'}).fill('空筛选回归没有匹配项')
 await p.getByRole('button',{name:'查找',exact:true}).click()
 await p.getByRole('button',{name:'继续复盘',exact:true}).click()
 assert.equal(await p.getByLabel('你的回答',{exact:true}).inputValue(),'离开前尚未提交的合成草稿')
 await p.getByRole('button',{name:'查找',exact:true}).click()
 await p.getByRole('button',{name:'离开',exact:true}).click()
 await p.waitForFunction(()=>document.querySelector('.catalog-heading')?.textContent.includes('0 道'))
 await p.waitForFunction(()=>!document.querySelector('.review-question'),undefined,{timeout:5000})
 assert.equal(await p.locator('.review-question').count(),0,'zero results must not retain a writable old question')
 assert.equal(await p.getByRole('button',{name:'提交回答',exact:true}).count(),0)
 await p.goBack()
 await p.locator('.review-question h2').waitFor()
 assert.equal(await p.locator('.review-question h2').innerText(),question)
 assert.equal(await p.getByLabel('你的回答',{exact:true}).inputValue(),'')
 fs.writeFileSync(path.join(out,'empty-filter.json'),JSON.stringify({synthetic:true,passed:true,checks:['cancel keeps draft','confirm clears empty selection','back loads clean question']},null,2))
 console.log('PASS empty-filter draft protection and clean return')
} catch(error) {console.log(JSON.stringify({url:p.url(),questions:await p.locator('.review-question h2').allTextContents()}));throw error} finally {await browser.close()}
