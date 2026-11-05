import { createServer } from 'node:http'
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { resolve, extname } from 'node:path'
import { publicPages, decoratePage, validateSnapshot, captureOrFallback } from './public-pages.mjs'
const dist=resolve('dist'), original=await readFile(resolve(dist,'index.html'),'utf8')
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.webp':'image/webp','.png':'image/png','.woff2':'font/woff2'}
const server=createServer(async(req,res)=>{try{const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname),target=resolve(dist,'.'+pathname);if(!target.startsWith(dist+'/')&&!target.startsWith(dist+'\\')&&target!==dist)throw new Error('path');const file=extname(target)?target:resolve(dist,'index.html');res.setHeader('Content-Type',mime[extname(file)]||'application/octet-stream');res.end(await readFile(file))}catch{res.statusCode=404;res.end()}})
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
const base=`http://127.0.0.1:${server.address().port}`
let browser
const report={isolation:'Fresh browser context; no backend; all API and third-party requests withheld. No cookies or local storage reused.',pages:[]}
try{
 for(const config of publicPages){
  const spa=decoratePage(original,config)
  const html=await captureOrFallback(spa,async()=>{
   if(!browser){const {chromium}=await import('playwright-core');browser=await chromium.launch({headless:true,...(process.platform==='win32'?{channel:'msedge'}:{})})}
   const context=await browser.newContext({viewport:{width:1440,height:900},serviceWorkers:'block'}),held=[]
   try{
    await context.route('**/*',route=>{const url=new URL(route.request().url());if(url.origin!==base)return route.abort();if(url.pathname==='/'||publicPages.some(p=>p.path===url.pathname)||/^\/(assets|interview-vision)\//.test(url.pathname)||['/favicon.svg','/theme-init.js'].includes(url.pathname))return route.continue();held.push(route)})
    const page=await context.newPage();await page.goto(base+config.path,{waitUntil:'load',timeout:20000});await page.locator('#app[data-v-app]').waitFor({timeout:10000});await page.locator('h1').waitFor({timeout:10000});await page.waitForTimeout(150)
    const snapshot=await page.evaluate(()=>{const app=document.querySelector('#app').cloneNode(true);app.querySelectorAll('input,textarea').forEach(n=>{n.removeAttribute('value');n.textContent=''});app.querySelectorAll('.welcome-meta time').forEach(n=>n.remove());const styles=[...document.querySelectorAll('link[rel="stylesheet"]')].map(n=>`<link rel="stylesheet" href="${new URL(n.href).pathname}">`);return {markup:app.innerHTML,styles}})
    validateSnapshot(snapshot.markup)
    const extraStyles=snapshot.styles.filter(link=>!spa.includes(link)).join('\n')
    return spa.replace('<div id="app"></div>',`<div id="app" data-prerender-path="${config.path}">${snapshot.markup}</div>`).replace('</head>',extraStyles+'\n</head>')
   }finally{await Promise.allSettled(held.map(r=>r.abort()));await context.close()}
  })
  const target=resolve(dist,config.path.slice(1),'index.html');await mkdir(resolve(target,'..'),{recursive:true});await writeFile(target,html);report.pages.push({path:config.path,prerendered:html.includes('data-prerender-path=')})
 }
 await writeFile(resolve(dist,'prerender-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report))
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve))}
