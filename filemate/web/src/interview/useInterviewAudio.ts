import { computed, shallowRef, ref } from 'vue'
import { AudioCapture } from './audio-capture'
import { AudioCollection, bindingKey, type FrozenAudio } from './audio-collection'
import { BrowserTranscription } from './transcription'
import type { AudioBinding, TranscriptionEvidence } from '../types/interviewAudio'
import { saveDownload } from '../services/downloads'

export function useInterviewAudio(onText:(text:string)=>void,stopSpeech:()=>void){
  const collection=new AudioCollection()
  const items=shallowRef(collection.items),captureState=shallowRef({phase:'idle' as string,error:null as string|null})
  const allowed=ref(false),error=ref('')
  let binding:AudioBinding|null=null,disposed=false,asr:BrowserTranscription
  const transcription=shallowRef<TranscriptionEvidence&{preview:string}>({provider:'browser_web_speech',status:'idle',language:'zh-CN',segments:[],confidence:null,preview:''})
  const publish=()=>{items.value=[...collection.items]}
  const capture=new AudioCapture({},state=>{
    if(disposed)return
    captureState.value=state
    if(state.take){if(!collection.add(state.take))error.value='录音已达本页容量上限，请先导出并删除部分录音。';publish()}
  })
  function newAsr(){return new BrowserTranscription(undefined,text=>{if(!disposed)onText(text)},()=>{if(!disposed)transcription.value={...asr.state}})}
  asr=newAsr()
  const asrBusy=computed(()=>['starting','listening'].includes(transcription.value.status))
  const busy=computed(()=>captureState.value.phase!=='idle'||asrBusy.value)
  function pausePlayback(){document.querySelectorAll<HTMLAudioElement>('.interview-audio-panel audio').forEach(audio=>audio.pause())}
  function stopOthers(){stopSpeech();pausePlayback()}
  async function stop(){asr.stop();await capture.stop()}
  function context(next:AudioBinding|null){
    if(bindingKey(binding)===bindingKey(next))return
    const changedSession=binding?.sessionId!==next?.sessionId
    if(changedSession)capture.dispose();else if(captureState.value.phase!=='idle')void capture.stop()
    asr.dispose();asr=newAsr();asr.setAllowed(allowed.value&&!changedSession)
    if(changedSession)allowed.value=false
    transcription.value={...asr.state};pausePlayback();collection.context(next);binding=next?{...next}:null;publish()
  }
  async function record(){
    if(!binding||busy.value)return
    if(!collection.canRecord){error.value='本页最多30段、60MiB；请先导出并删除部分录音。';return}
    // 新录音由界面先确认旧草稿；已保存版本不会被替换。
    collection.invalidate();stopOthers();error.value='';await capture.start(binding)
  }
  function consent(value:boolean){allowed.value=value;asr.setAllowed(value)}
  function transcribe(language:'zh-CN'|'en-US',prefix:string){if(busy.value||!binding)return;stopOthers();collection.invalidate();asr.start(language,prefix)}
  function freeze(text:string){return collection.freeze(text,transcription.value)}
  function receipt(value:FrozenAudio,attemptId:string,sessionId:string){collection.receipt(value,attemptId,sessionId);publish()}
  function remove(id:string){collection.remove(id);publish()}
  async function download(id:string){
    const take=collection.items.find(t=>t.id===id);if(!take)return
    const extension=take.blob.type.includes('mp4')?'m4a':take.blob.type.includes('ogg')?'ogg':'webm'
    try{await saveDownload(take.blob,`filemate-audio-q${take.binding.questionIndex+1}-${take.id}.${extension}`)}catch{error.value='导出未完成，可重试；录音仍保留。'}
  }
  function clear(){capture.dispose();asr.dispose();asr=newAsr();allowed.value=false;transcription.value={...asr.state};pausePlayback();collection.clear();publish();binding=null}
  function dispose(){clear();disposed=true}
  return {items,captureState,transcription,allowed,error,busy,asrBusy,context,record,stop,consent,transcribe,freeze,receipt,remove,download,clear,dispose,pausePlayback,stopOthers,invalidate:()=>collection.invalidate()}
}
