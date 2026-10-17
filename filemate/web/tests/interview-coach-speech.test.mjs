import assert from 'node:assert/strict'
import test from 'node:test'
import { useInterviewCoachSpeech } from '../src/interview/useInterviewCoachSpeech.ts'
const mock=()=>{const p={calls:0,stops:0,events:null,available:()=>true,setMotionEnabled(){},speak(text,options,events){this.calls++;this.events=events;events.onStart()},stop(){this.stops++}};return p}
test('unconsented_read_never_sends_text',()=>{const p=mock(),s=useInterviewCoachSpeech(p);s.read('回答反馈','zh-CN-XiaoxiaoNeural');assert.equal(p.calls,0);assert.match(s.error.value,/授权/);s.stop()})
test('speech_stops_and_releases_url_on_input_recording_route',()=>{const p=mock(),s=useInterviewCoachSpeech(p);s.voiceConsent.value=true;s.read('回答反馈','zh-CN-XiaoxiaoNeural');const late=p.events;assert.equal(s.speaking.value,true);s.stop();s.stop();late.onStart();late.onEnd();assert.equal(s.speaking.value,false);assert.equal(p.stops,1)})
test('tts_failure_preserves_feedback_without_browser_voice_fallback',()=>{const feedback='原句需要补充证据';let browserSpeechCalls=0;globalThis.speechSynthesis={speak(){browserSpeechCalls++}};const p=mock(),s=useInterviewCoachSpeech(p);s.voiceConsent.value=true;s.read(feedback,'zh-CN-XiaoxiaoNeural');p.events.onError('服务失败');assert.equal(feedback,'原句需要补充证据');assert.equal(browserSpeechCalls,0);assert.equal(s.speaking.value,false);s.stop()})
test('revoking_voice_permission_stops_immediately',async()=>{const p=mock(),s=useInterviewCoachSpeech(p);s.voiceConsent.value=true;s.read('回答','zh-CN-XiaoxiaoNeural');s.voiceConsent.value=false;assert.equal(s.speaking.value,false);assert.equal(p.stops,1)})
