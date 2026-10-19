export interface AudioBinding { sessionId:string; questionIndex:number; attemptId:string|null; token:string }
export interface AudioSummary {
  method:'web_audio_energy_v1'; duration_seconds:number; sample_rate:number; sample_count:number
  rms:number; low_energy_seconds:number; clipping_ratio:number; threshold:number
}
export interface TranscriptSegment { text:string; confidence:number|null; callback_seconds:number }
export type TranscriptionStatus='idle'|'permission_required'|'unsupported'|'starting'|'listening'|'completed'|'interrupted'|'denied'|'no_speech'
export interface TranscriptionEvidence {
  provider:'browser_web_speech'; status:TranscriptionStatus; language:'zh-CN'|'en-US'
  segments:TranscriptSegment[]; confidence:number|null
}
export interface MediaEvidence {
  source:'browser_media_v1'; duration_seconds:number
  audio:{status:'measured'|'unavailable'; summary:AudioSummary|null}|null
  transcription:TranscriptionEvidence|null
}
export interface LocalAudioTake {
  id:string; binding:AudioBinding; blob:Blob; captureSeconds:number; summary:AudioSummary|null
  partial:boolean; issue:string|null
}
