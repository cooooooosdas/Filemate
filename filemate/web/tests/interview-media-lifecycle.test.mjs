import test from 'node:test'
import assert from 'node:assert/strict'
import { FrameWatchdog, watchMediaEnvironment } from '../src/interview/media-lifecycle.ts'

test('stalled frame times out once, releases its slot and rejects late responses',t=>{
 t.mock.timers.enable({apis:['setTimeout']});let timeouts=0;const gate=new FrameWatchdog()
 assert.equal(gate.begin(1,()=>timeouts++),true);assert.equal(gate.begin(1,()=>timeouts++),false)
 t.mock.timers.tick(4000);assert.equal(timeouts,1);assert.equal(gate.pending,false);assert.equal(gate.release(1),false);gate.clear()
})
test('stale frame cannot unlock a new observation epoch',t=>{
 t.mock.timers.enable({apis:['setTimeout']});const gate=new FrameWatchdog()
 gate.begin(1,()=>assert.fail('cancelled timeout'));gate.clear();gate.begin(2,()=>{})
 assert.equal(gate.release(1),false);assert.equal(gate.pending,true);assert.equal(gate.release(2),true);assert.equal(gate.pending,false);gate.clear()
})
test('hidden page stops resources, visible page never automatically restarts devices',()=>{
 const doc=new EventTarget(),devices=new EventTarget();doc.visibilityState='visible';let hidden=0,refresh=0
 const dispose=watchMediaEnvironment(doc,devices,{hidden:()=>hidden++,devicesChanged:()=>refresh++})
 doc.visibilityState='hidden';doc.dispatchEvent(new Event('visibilitychange'));assert.equal(hidden,1)
 doc.visibilityState='visible';doc.dispatchEvent(new Event('visibilitychange'));assert.equal(hidden,1)
 devices.dispatchEvent(new Event('devicechange'));assert.equal(refresh,1);dispose()
 doc.visibilityState='hidden';doc.dispatchEvent(new Event('visibilitychange'));devices.dispatchEvent(new Event('devicechange'));assert.equal(hidden,1);assert.equal(refresh,1)
})
