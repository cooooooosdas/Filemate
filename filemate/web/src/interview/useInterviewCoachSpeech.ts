import { ref, watch } from 'vue'
import { MicrosoftSpeechProvider, NATURAL_VOICES } from '../digital-human/natural-speech.ts'
import type { SpeechEvents, SpeechOptions } from '../digital-human/provider'
interface SpeechProvider { speak(text:string,options:SpeechOptions,events:SpeechEvents):void;stop():void;setMotionEnabled(enabled:boolean):void }
export function useInterviewCoachSpeech(provider?:SpeechProvider) {
 const speaking=ref(false),error=ref(''),voiceConsent=ref(false)
 const speech=provider ?? new MicrosoftSpeechProvider(async(text,voice,signal)=>{const {synthesizeNaturalSpeech}=await import('../services/api');return synthesizeNaturalSpeech(text,voice,signal)})
 speech.setMotionEnabled(false)
 let epoch=0,active=false
 function stop(){epoch++;if(active){active=false;speech.stop()}speaking.value=false}
 function read(text:string,voiceId:string=NATURAL_VOICES[0].voiceURI){
  stop();error.value=''
  if(!voiceConsent.value){error.value='请先授权将本段文字发送给 Microsoft 自然语音服务。';return}
  if(Array.from(text).length>5000){error.value='本段超过5000字，请选择较短的反馈段朗读。';return}
  if(!text.trim())return
  active=true;const captured=++epoch
  speech.speak(text,{voiceId,rate:1,volume:1},{onStart:()=>{if(captured===epoch)speaking.value=true},onBoundary:()=>{},onEnd:()=>{if(captured===epoch){active=false;speaking.value=false}},onError:()=>{if(captured===epoch){active=false;speaking.value=false;error.value='自然语音暂时不可用，可继续阅读文字并稍后重试。'}}})
 }
 watch(voiceConsent,allowed=>{if(!allowed)stop()},{flush:'sync'})
 return {speaking,error,voiceConsent,read,stop}
}
