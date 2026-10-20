import assert from 'node:assert/strict'
import test from 'node:test'
import { AudioCapture } from '../src/interview/audio-capture.ts'
import { measureAudio } from '../src/interview/audio-evidence.ts'
import { BrowserTranscription } from '../src/interview/transcription.ts'
const binding={sessionId:'one',questionIndex:0,attemptId:null,token:'token'}
const device=()=>{const track={stopped:0,stop(){this.stopped++},onended:null};return {track,stream:{getTracks:()=>[track]}}}
const recorder=()=>({state:'inactive',mimeType:'audio/webm',start(){this.state='recording';this.onstart?.()},stop(){this.state='inactive';this.ondataavailable?.({data:new Blob(['final-audio'])});this.onstop?.()}})

test('permission denial and late grant after disposal never leak microphone tracks',async()=>{
 const denied=new AudioCapture({getMedia:async()=>{throw Object.assign(Error('denied'),{name:'NotAllowedError'})}})
 await denied.start(binding);assert.equal(denied.state.error,'permission_denied')
 let grant;const d=device();const c=new AudioCapture({getMedia:()=>new Promise(resolve=>grant=resolve),makeRecorder:recorder})
 const pending=c.start(binding);c.dispose();grant(d.stream);await pending;assert.equal(d.track.stopped,1);assert.equal(c.state.phase,'idle')
})

test('stop waits for final audio chunk and releases microphone once',async()=>{
 const d=device(),r=recorder();let clock=0
 const c=new AudioCapture({getMedia:async()=>d.stream,makeRecorder:()=>r,now:()=>clock,analyze:async()=>null})
 await c.start(binding);clock=2000;const take=await c.stop();assert.equal(await take.blob.text(),'final-audio');assert.equal(take.captureSeconds,2);assert.deepEqual(take.binding,binding);assert.equal(d.track.stopped,1);await c.stop();assert.equal(d.track.stopped,1);c.dispose()
})

test('known PCM measures real low energy and clipping without an ability score',()=>{
 const pcm=new Float32Array(8000);pcm.fill(.2,0,4000);pcm[0]=1
 const evidence=measureAudio([pcm],8000)
 assert.equal(evidence.duration_seconds,1);assert.equal(evidence.low_energy_seconds,.5);assert.ok(evidence.rms>0);assert.ok(evidence.clipping_ratio>0);assert.equal(evidence.score,undefined)
 assert.equal(measureAudio([],8000),null);assert.equal(measureAudio([new Float32Array()],8000),null)
 assert.equal(measureAudio([Float32Array.of(NaN)],8000),null)
})

test('final-only transcription preserves typed prefix, deduplicates callbacks and unknown confidence',()=>{
 let r;const texts=[];const t=new BrowserTranscription(()=>r={start(){this.onstart?.()},stop(){this.onend?.()},abort(){}} ,text=>texts.push(text))
 t.start('zh-CN','已写前缀');assert.equal(texts.length,0);assert.equal(t.state.status,'permission_required')
 t.setAllowed(true);t.start('zh-CN','已写前缀')
 const result=(text,final,confidence)=>Object.assign([{transcript:text,confidence}],{isFinal:final})
 r.onresult({results:[result('临时猜测',false,.8)]});assert.equal(texts.length,0)
 r.onresult({results:[result('最后文本',true,undefined)]});r.onresult({results:[result('最后文本',true,undefined)]})
 assert.equal(texts.at(-1),'已写前缀最后文本');assert.equal(t.state.segments.length,1);assert.equal(t.state.segments[0].confidence,null)
 const late=r.onresult;t.setAllowed(false);late({results:[result('不能串题',true,.9)]});assert.equal(texts.at(-1),'已写前缀最后文本')
})

test('device disconnect and size cap preserve partial audio and settle once',async()=>{
 for(const mode of ['device','size']){
  const d=device(),r=recorder();const c=new AudioCapture({getMedia:async()=>d.stream,makeRecorder:()=>r,analyze:async()=>null})
  await c.start(binding);r.ondataavailable({data:new Blob(['earlier'])})
  if(mode==='device')d.track.onended();else r.ondataavailable({data:{size:21*1024*1024}})
  const take=await c.stop();assert.equal(take.partial,true);assert.match(await take.blob.text(),/earlier/);assert.equal(d.track.stopped,1);c.dispose()
 }
})

test('permission timeout and missing final stop callback cannot hold a microphone forever',async t=>{
 t.mock.timers.enable({apis:['setTimeout']})
 let grant;const d=device();const c=new AudioCapture({getMedia:()=>new Promise(resolve=>grant=resolve),makeRecorder:recorder})
 const starting=c.start(binding);t.mock.timers.tick(15000);assert.equal(c.state.error,'permission_timeout');grant(d.stream);await starting;assert.equal(d.track.stopped,1)
 const next=device(),r=recorder();r.stop=function(){this.state='inactive'}
 const stuck=new AudioCapture({getMedia:async()=>next.stream,makeRecorder:()=>r,analyze:async()=>null});await stuck.start(binding);r.ondataavailable({data:new Blob(['partial'])});const stopping=stuck.stop();t.mock.timers.tick(5000)
 assert.equal((await stopping).issue,'stop_timeout');assert.equal(next.track.stopped,1);stuck.dispose()
})

test('transcription start timeout and network error keep final text and release vendor session',()=>{
 let r;const texts=[];const t=new BrowserTranscription(()=>r={start(){this.onstart?.()},stop(){this.onend?.()},abort(){}},text=>texts.push(text));t.setAllowed(true);t.start('en-US','typed')
 r.onresult({results:[Object.assign([{transcript:'final',confidence:.2}],{isFinal:true})]});const late=r.onresult;r.onerror({error:'network'});late({results:[Object.assign([{transcript:'late',confidence:.99}],{isFinal:true})]})
 assert.equal(t.state.status,'interrupted');assert.equal(t.state.confidence,.2);assert.equal(texts.at(-1),'typed final');t.dispose()
})

test('transcription provider that never starts is released after15seconds',t=>{
 t.mock.timers.enable({apis:['setTimeout']});let aborted=0
 const tr=new BrowserTranscription(()=>({start(){},stop(){},abort(){aborted++}}));tr.setAllowed(true);tr.start('zh-CN','prefix');t.mock.timers.tick(15000)
 assert.equal(tr.state.status,'interrupted');assert.equal(aborted,1);tr.dispose()
})


test('permission or no-speech errors after final text retain interrupted evidence',()=>{
 for(const error of ['not-allowed','no-speech']){
  let r;const factory=()=>r={start(){},stop(){},abort(){}}
  const asr=new BrowserTranscription(factory);asr.setAllowed(true);asr.start('zh-CN','')
  r.onresult({results:[{isFinal:true,0:{transcript:'已识别',confidence:0.3}}]})
  r.onerror({error});assert.equal(asr.state.status,'interrupted');assert.equal(asr.state.segments[0].text,'已识别');asr.dispose()
 }
})

test('hard transcription limit aborts atomically before actions unlock',t=>{
 t.mock.timers.enable({apis:['setTimeout']});let r,text='prefix',aborts=0
 const asr=new BrowserTranscription(()=>r={start(){this.onstart?.()},stop(){},abort(){aborts++}},value=>text=value)
 asr.setAllowed(true);asr.start('zh-CN','prefix');const callback=r.onresult
 callback({results:[{isFinal:true,0:{transcript:'saved'}}]});t.mock.timers.tick(600000)
 assert.equal(asr.state.status,'interrupted');assert.equal(aborts,1)
 callback({results:[{isFinal:true,0:{transcript:'late'}}]});assert.equal(text,'prefixsaved');assert.equal(asr.state.segments[0].text,'saved');asr.dispose()
})
