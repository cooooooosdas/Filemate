import test from 'node:test'
import assert from 'node:assert/strict'
import { CameraPreview } from '../src/interview/video-devices.ts'
import { VideoCapture, VIDEO_LIMITS } from '../src/interview/video-capture.ts'

const binding={sessionId:'one',questionIndex:0,attemptId:null,token:'draft'}
function track(kind='video') {
 return {kind,readyState:'live',stops:0,onended:null,onmute:null,stop(){this.stops++;this.readyState='ended'},clone(){return track(kind)},getSettings(){return {deviceId:'camera-one'}}}
}
function stream(tracks=[track()]){return {getTracks:()=>tracks,getVideoTracks:()=>tracks.filter(t=>t.kind==='video'),getAudioTracks:()=>tracks.filter(t=>t.kind==='audio')}}
function recorder(){return {state:'inactive',mimeType:'video/webm',start(){this.state='recording'},stop(){this.state='inactive';this.ondataavailable?.({data:new Blob(['last'])});this.onstop?.()}}}
const devices=[{kind:'videoinput',deviceId:'camera-one',label:''},{kind:'audioinput',deviceId:'mic-one',label:''}]

test('camera opens video only with exact selected device and closes without microphone',async()=>{
 let request;const camera=track();const p=new CameraPreview({getMedia:async input=>{request=input;return stream([camera])},enumerate:async()=>devices})
 await p.refresh();assert.equal(p.state.devices.length,2);assert.equal(p.state.phase,'off')
 assert.equal(await p.open('camera-one'),true);assert.equal(request.audio,false);assert.deepEqual(request.video.deviceId,{exact:'camera-one'});assert.equal(request.video.frameRate.max,24)
 p.close();assert.equal(camera.stops,1);assert.equal(p.state.stream,null);p.dispose()
})
test('cancelled and timed-out permissions release late streams and cannot revive preview',async t=>{
 t.mock.timers.enable({apis:['setTimeout']})
 for(const cancel of [true,false]){
  let grant;const camera=track(),p=new CameraPreview({getMedia:()=>new Promise(resolve=>grant=resolve),enumerate:async()=>[]})
  const pending=p.open();if(cancel)p.close();else t.mock.timers.tick(15000)
  await Promise.resolve();grant(stream([camera]));await pending;assert.equal(camera.stops,1);assert.equal(p.state.stream,null);assert.equal(p.state.phase,'off');p.dispose()
 }
})
test('denied preview and disconnected camera remain recoverable, no automatic reopening',async()=>{
 let calls=0;const d=track();const p=new CameraPreview({getMedia:async()=>{calls++;if(calls===1)throw {name:'NotAllowedError'};return stream([d])},enumerate:async()=>devices})
 await p.open();assert.equal(p.state.error,'permission_denied');await p.open();d.onended();assert.equal(p.state.phase,'off');assert.equal(p.state.error,'device_disconnected');await p.refresh();assert.equal(calls,2);p.dispose()
})
test('silent recording never acquires microphone, waits final chunk, releases clone not preview',async()=>{
 const base=track(),clone=track();base.clone=()=>clone;let micCalls=0,clock=0
 const c=new VideoCapture({getMedia:async()=>{micCalls++;throw Error()},makeStream:stream,makeRecorder:recorder,now:()=>clock})
 await c.start(binding,stream([base]),null);clock=2500;const take=await c.stop()
 assert.equal(micCalls,0);assert.equal(take.hasAudio,false);assert.equal(take.duration,2.5);assert.equal(await take.blob.text(),'last');assert.equal(base.stops,0);assert.equal(clone.stops,1);assert.deepEqual(take.binding,binding);c.dispose()
})
test('requested microphone is exact and rejection does not silently start silent recording',async()=>{
 let request,made=0;const c=new VideoCapture({getMedia:async input=>{request=input;throw {name:'NotAllowedError'}},makeStream:stream,makeRecorder:()=>{made++;return recorder()}})
 await c.start(binding,stream(),'mic-one');assert.deepEqual(request.audio.deviceId,{exact:'mic-one'});assert.equal(request.video,false);assert.equal(c.state.error,'microphone_denied');assert.equal(made,0);assert.equal(c.state.phase,'idle');c.dispose()
})
test('recording permission timeout releases late microphone and does not create recorder',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});let grant,made=0;const mic=track('audio')
 const c=new VideoCapture({getMedia:()=>new Promise(resolve=>grant=resolve),makeStream:stream,makeRecorder:()=>{made++;return recorder()}})
 const starting=c.start(binding,stream(),'');t.mock.timers.tick(15000);assert.equal(c.state.phase,'idle');grant(stream([mic]));await starting;assert.equal(mic.stops,1);assert.equal(made,0);c.dispose()
})
test('disconnect, recorder error and byte cap preserve prior chunks and settle once',async()=>{
 for(const cause of ['ended','error','size']){
  const base=track(),clone=track(),r=recorder();base.clone=()=>clone
  const c=new VideoCapture({makeStream:stream,makeRecorder:()=>r});await c.start(binding,stream([base]),null,10)
  r.ondataavailable({data:new Blob(['prior'])})
  if(cause==='ended')clone.onended();else if(cause==='error')r.onerror();else r.ondataavailable({data:{size:11}})
  const take=await c.stop();assert.equal(take.partial,true);assert.match(await take.blob.text(),/prior/);assert.ok(take.blob.size<=10);assert.equal(clone.stops,1);assert.equal(base.stops,0);c.dispose()
 }
})
test('missing onstop releases hardware after5seconds and ignores late callbacks',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});const r=recorder();r.stop=function(){this.state='inactive'}
 const c=new VideoCapture({makeStream:stream,makeRecorder:()=>r});await c.start(binding,stream(),null)
 r.ondataavailable({data:new Blob(['prior'])});const late=r.ondataavailable;const stopping=c.stop();t.mock.timers.tick(5000)
 const take=await stopping;assert.equal(take.issue,'stop_timeout');late({data:new Blob(['late'])});assert.equal(await take.blob.text(),'prior');assert.equal(c.state.phase,'idle');c.dispose()
})
test('duration limit, hidden interruption and dispose preserve resource bounds',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});const c=new VideoCapture({makeStream:stream,makeRecorder:recorder});await c.start(binding,stream(),null)
 t.mock.timers.tick(VIDEO_LIMITS.seconds*1000);assert.equal((await c.stop()).issue,'duration_limit')
 await c.start(binding,stream(),null);const take=await c.stop('page_hidden');assert.equal(take.partial,true);assert.equal(take.issue,'page_hidden');c.dispose();assert.equal(c.state.take,null)
})


test('unanswered permission settles start on timeout or cancellation and late grant cannot replace a new run',async t=>{
 t.mock.timers.enable({apis:['setTimeout']})
 for(const reason of ['timeout','stop','dispose']){
  let grant,settled=false;const late=track('audio');const c=new VideoCapture({getMedia:()=>new Promise(r=>grant=r),makeStream:stream,makeRecorder:recorder})
  const pending=c.start(binding,stream(),'').then(()=>{settled=true})
  if(reason==='timeout')t.mock.timers.tick(15000);else if(reason==='stop')await c.stop('page_hidden');else c.dispose()
  for(let i=0;i<8;i++)await Promise.resolve()
  assert.equal(settled,true,reason+' must settle without waiting for user permission')
  await c.start({...binding,token:'new'},stream(),null);assert.equal(c.state.phase,'recording')
  grant(stream([late]));await pending;for(let i=0;i<4;i++)await Promise.resolve()
  assert.equal(late.stops,1);assert.equal(c.state.phase,'recording');assert.equal((await c.stop()).binding.token,'new');c.dispose()
 }
})


test('cancellation between permission fulfillment and recorder continuation releases microphone exactly once',async()=>{
 let grant;const permission=new Promise(resolve=>grant=resolve),mic=track('audio')
 const c=new VideoCapture({getMedia:()=>permission,makeStream:stream,makeRecorder:recorder})
 const starting=c.start(binding,stream(),'');permission.then(()=>c.dispose());grant(stream([mic]));await starting
 assert.equal(mic.stops,1);assert.equal(c.state.phase,'idle');c.dispose();assert.equal(mic.stops,1)
})
