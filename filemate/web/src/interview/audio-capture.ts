import type { AudioBinding, AudioSummary, LocalAudioTake } from '../types/interviewAudio'
import { analyzeAudio } from './audio-evidence.ts'

export interface CaptureState {phase:'idle'|'requesting'|'recording'|'stopping';error:string|null;take:LocalAudioTake|null}
interface Dependencies {
  getMedia:()=>Promise<MediaStream>;makeRecorder:(stream:MediaStream)=>MediaRecorder
  now:()=>number;analyze:(blob:Blob,signal:AbortSignal)=>Promise<AudioSummary|null>
}
interface Run {
  epoch:number;binding:AudioBinding;stream:MediaStream|null;recorder:MediaRecorder|null
  chunks:Blob[];bytes:number;started:number;stopped:number|null;partial:boolean;issue:string|null
  permission?:ReturnType<typeof setTimeout>;limit?:ReturnType<typeof setTimeout>;stopTimer?:ReturnType<typeof setTimeout>
  resolve:((take:LocalAudioTake|null)=>void)[];settling:boolean;abort:AbortController
}
export const AUDIO_LIMITS={seconds:600,bytes:20*1024*1024,pageBytes:60*1024*1024,takes:30}
function defaultRecorder(stream:MediaStream):MediaRecorder{
  const mimeType=['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'].find(type=>MediaRecorder.isTypeSupported(type))
  return new MediaRecorder(stream,{...(mimeType?{mimeType}:{}),audioBitsPerSecond:64000})
}
export class AudioCapture {
  state:CaptureState={phase:'idle',error:null,take:null}
  private epoch=0;private run:Run|null=null;private deps:Dependencies
  private changed:(state:CaptureState)=>void
  constructor(deps:Partial<Dependencies>={},changed:(state:CaptureState)=>void=()=>{}){
    this.changed=changed
    this.deps={getMedia:()=>navigator.mediaDevices.getUserMedia({audio:{channelCount:1},video:false}),makeRecorder:defaultRecorder,now:()=>performance.now(),analyze:analyzeAudio,...deps}
  }
  private publish(patch:Partial<CaptureState>){this.state={...this.state,...patch};this.changed(this.state)}
  private live(run:Run){return this.run===run&&run.epoch===this.epoch}
  private release(run:Run){
    clearTimeout(run.permission);clearTimeout(run.limit);clearTimeout(run.stopTimer)
    for(const track of run.stream?.getTracks()??[]){track.onended=null;track.stop()}
    run.stream=null
  }
  async start(binding:AudioBinding):Promise<void>{
    if(this.run)return
    const run:Run={epoch:++this.epoch,binding:{...binding},stream:null,recorder:null,chunks:[],bytes:0,started:0,stopped:null,partial:false,issue:null,resolve:[],settling:false,abort:new AbortController()}
    this.run=run;this.publish({phase:'requesting',error:null,take:null})
    run.permission=setTimeout(()=>{if(this.live(run)){this.run=null;this.epoch++;this.publish({phase:'idle',error:'permission_timeout'})}},15000)
    try{
      const stream=await this.deps.getMedia()
      if(!this.live(run)){stream.getTracks().forEach(track=>track.stop());return}
      run.stream=stream;clearTimeout(run.permission)
      const recorder=this.deps.makeRecorder(stream);run.recorder=recorder
      recorder.ondataavailable=event=>{
        if(!this.live(run)||run.settling||!event.data.size)return
        if(run.bytes+event.data.size>AUDIO_LIMITS.bytes){run.partial=true;run.issue='size_limit';void this.stop();return}
        run.chunks.push(event.data);run.bytes+=event.data.size
      }
      recorder.onstop=()=>{void this.finish(run)}
      recorder.onerror=()=>{run.partial=true;run.issue='recording_error';void this.stop()}
      for(const track of stream.getTracks())track.onended=()=>{run.partial=true;run.issue='device_disconnected';void this.stop()}
      run.started=this.deps.now();recorder.start(1000);this.publish({phase:'recording'})
      run.limit=setTimeout(()=>{run.issue='duration_limit';void this.stop()},AUDIO_LIMITS.seconds*1000)
    }catch(error){
      if(!this.live(run))return
      this.release(run);this.run=null
      this.publish({phase:'idle',error:(error as {name?:string}).name==='NotAllowedError'?'permission_denied':'capture_unavailable'})
    }
  }
  async stop():Promise<LocalAudioTake|null>{
    const run=this.run;if(!run)return this.state.take
    if(this.state.phase==='requesting'){this.dispose();return null}
    const result=new Promise<LocalAudioTake|null>(resolve=>run.resolve.push(resolve))
    if(this.state.phase==='stopping')return result
    run.stopped=this.deps.now()
    this.publish({phase:'stopping'})
    run.stopTimer=setTimeout(()=>{run.partial=true;run.issue='stop_timeout';void this.finish(run)},5000)
    try{if(run.recorder?.state==='recording')run.recorder.stop();else void this.finish(run)}catch{run.partial=true;run.issue='recording_error';void this.finish(run)}
    return result
  }
  private async finish(run:Run){
    if(!this.live(run)||run.settling)return
    run.settling=true;this.publish({phase:'stopping'});this.release(run)
    run.stopped??=this.deps.now()
    const blob=new Blob(run.chunks,{type:run.recorder?.mimeType||'audio/webm'});run.chunks=[]
    let summary:AudioSummary|null=null
    if(blob.size){
      let timeout:ReturnType<typeof setTimeout>|undefined
      try{summary=await Promise.race([this.deps.analyze(blob,run.abort.signal),new Promise<null>(resolve=>{timeout=setTimeout(()=>{run.abort.abort();resolve(null)},12000)})])}catch{/* 音频解码失败仍保留可导出的原录音。 */}finally{clearTimeout(timeout)}
    }
    if(!this.live(run)){run.resolve.splice(0).forEach(resolve=>resolve(null));return}
    const take=blob.size?{id:crypto.randomUUID(),binding:run.binding,blob,captureSeconds:Math.min(600,Math.max(0,(run.stopped-run.started)/1000)),summary,partial:run.partial,issue:run.issue}:null
    this.run=null;this.publish({phase:'idle',take,error:take?run.issue:'no_samples'});run.resolve.splice(0).forEach(resolve=>resolve(take))
  }
  dispose(){
    this.epoch++;const run=this.run;this.run=null
    if(run){run.abort.abort();if(run.recorder){run.recorder.onstop=run.recorder.ondataavailable=run.recorder.onerror=null;try{if(run.recorder.state==='recording')run.recorder.stop()}catch{/* 已断开的录音器仍释放轨道。 */}}this.release(run);run.resolve.splice(0).forEach(resolve=>resolve(null))}
    this.publish({phase:'idle',error:null,take:null})
  }
}
