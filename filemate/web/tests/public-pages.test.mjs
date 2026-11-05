import assert from 'node:assert/strict'
import test from 'node:test'
import { publicPages, decoratePage, validateSnapshot, captureOrFallback } from '../scripts/public-pages.mjs'
test('public pages carry crawlable metadata and both truthful schemas',()=>{
 for(const route of publicPages){const html=decoratePage('<html><head><title>x</title></head><body><div id="app"></div></body></html>',route);assert.ok((html.match(/property="og:/g)||[]).length>=5);assert.match(html,/twitter:card/);assert.ok(html.includes(`https://filemate.asia${route.path}`));assert.match(html,/"@type":"Organization"/);assert.match(html,/"@type":"WebSite"/);assert.doesNotMatch(html,/aggregateRating|ratingValue|userCount/)}
})
test('capture rejects personalized or incomplete snapshots',()=>{
 assert.throws(()=>validateSnapshot('<div>loading</div>'),/heading/)
 assert.throws(()=>validateSnapshot('<h1>Title</h1><p>Text</p><input value="secret">'),/private/)
 assert.doesNotThrow(()=>validateSnapshot('<h1>今天</h1><p>读原文</p>'))
})
test('browser failure warns and preserves SPA HTML',async()=>{
 const warnings=[];assert.equal(await captureOrFallback('spa',async()=>{throw new Error('no browser')},m=>warnings.push(m)),'spa');assert.equal(warnings.length,1);assert.match(warnings[0],/SPA/)
})
