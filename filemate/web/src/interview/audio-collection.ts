import { AUDIO_LIMITS } from './audio-capture.ts'
import type { AudioBinding, LocalAudioTake, MediaEvidence, TranscriptionEvidence } from '../types/interviewAudio'
export interface StoredAudio extends LocalAudioTake {url:string;attemptId:string|null}
export interface FrozenAudio {key:string;sessionId:string;takeId:string|null;metrics:MediaEvidence|undefined}
export const bindingKey=(b:AudioBinding|null)=>JSON.stringify(b)
export class AudioCollection {
  items:StoredAudio[]=[]
  private binding:AudioBinding|null=null;private frozen:FrozenAudio|null=null
  private urls:{create:(blob:Blob)=>string;revoke:(url:string)=>void}
  constructor(urls={create:(blob:Blob)=>URL.createObjectURL(blob),revoke:(url:string)=>URL.revokeObjectURL(url)}){this.urls=urls}
  get canRecord(){return this.items.length<AUDIO_LIMITS.takes&&this.items.reduce((n,t)=>n+t.blob.size,0)<=AUDIO_LIMITS.pageBytes-AUDIO_LIMITS.bytes}
  context(binding:AudioBinding|null){
    if(this.binding?.sessionId!==binding?.sessionId)this.clear()
    this.binding=binding?{...binding}:null
  }
  add(take:LocalAudioTake){
    if(this.items.some(t=>t.id===take.id))return true
    if(!take.blob.size||take.blob.size>AUDIO_LIMITS.bytes||take.binding.sessionId!==this.binding?.sessionId||this.items.length>=AUDIO_LIMITS.takes||this.items.reduce((n,t)=>n+t.blob.size,0)+take.blob.size>AUDIO_LIMITS.pageBytes)return false
    this.items=[...this.items,{...take,url:this.urls.create(take.blob),attemptId:null}];return true
  }
  invalidate(){this.frozen=null}
  freeze(text:string,transcription:TranscriptionEvidence|null):FrozenAudio{
    // 请求结果不明时保留同一份指标，和原保存命令一起重放。
    if(this.frozen?.key===text&&this.frozen.sessionId===this.binding?.sessionId)return this.frozen
    const take=[...this.items].reverse().find(t=>!t.attemptId&&bindingKey(t.binding)===bindingKey(this.binding))
    const usable=transcription&&!['idle','permission_required','starting','listening'].includes(transcription.status)?transcription:null
    const metrics:MediaEvidence|undefined=take||usable?{source:'browser_media_v1',duration_seconds:take?.captureSeconds??0,audio:take?{status:take.summary?'measured':'unavailable',summary:take.summary}:null,transcription:usable?{provider:usable.provider,status:usable.status,language:usable.language,segments:usable.segments,confidence:usable.confidence}:null}:undefined
    this.frozen={key:text,sessionId:this.binding?.sessionId??'',takeId:take?.id??null,metrics:metrics?structuredClone(metrics):undefined};return this.frozen
  }
  receipt(frozen:FrozenAudio,attemptId:string,sessionId:string){
    if(this.frozen!==frozen||sessionId!==frozen.sessionId||sessionId!==this.binding?.sessionId)return false
    this.items=this.items.map(t=>t.id===frozen.takeId?{...t,attemptId}:t);this.frozen=null;return true
  }
  remove(id:string){this.items=this.items.filter(t=>{if(t.id!==id)return true;this.urls.revoke(t.url);return false})}
  clear(){for(const take of this.items)this.urls.revoke(take.url);this.items=[];this.invalidate()}
}
