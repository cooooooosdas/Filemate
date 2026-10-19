import type { AudioSummary } from '../types/interviewAudio'

export function measureAudio(channels:Float32Array[],sampleRate:number):AudioSummary|null {
  const length=channels[0]?.length ?? 0
  if(!length||channels.length>2||sampleRate<8000||sampleRate>96000||length/sampleRate>601||channels.some(c=>c.length!==length))return null
  const width=Math.max(1,Math.round(sampleRate*.05));let energy=0,clipped=0,low=0
  for(let begin=0;begin<length;begin+=width){
    const end=Math.min(length,begin+width);let bin=0
    for(let index=begin;index<end;index++){
      let peak=0
      for(const channel of channels){const value=channel[index]!;if(!Number.isFinite(value)||Math.abs(value)>1.01)return null;peak=Math.max(peak,Math.abs(value))}
      bin+=peak*peak;if(peak>=.98)clipped++
    }
    energy+=bin;if(Math.sqrt(bin/(end-begin))<.01)low+=end-begin
  }
  return {method:'web_audio_energy_v1',duration_seconds:Number((length/sampleRate).toFixed(3)),sample_rate:sampleRate,sample_count:length,rms:Number(Math.sqrt(energy/length).toFixed(6)),low_energy_seconds:Number((low/sampleRate).toFixed(3)),clipping_ratio:Number((clipped/length).toFixed(6)),threshold:.01}
}

let decoding=false
export async function analyzeAudio(blob:Blob,signal:AbortSignal):Promise<AudioSummary|null>{
  if(decoding||signal.aborted||!blob.size||blob.size>20*1024*1024||typeof globalThis.OfflineAudioContext!=='function')return null
  decoding=true
  try{
    const context=new OfflineAudioContext(1,1,8000)
    const data=await blob.arrayBuffer();if(signal.aborted)return null
    const decoded=await context.decodeAudioData(data)
    if(signal.aborted||decoded.duration>601||decoded.numberOfChannels>2)return null
    return measureAudio(Array.from({length:decoded.numberOfChannels},(_,index)=>decoded.getChannelData(index)),decoded.sampleRate)
  }catch{return null}finally{decoding=false}
}
