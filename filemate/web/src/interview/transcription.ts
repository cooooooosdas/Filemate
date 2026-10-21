import type { TranscriptSegment, TranscriptionEvidence, TranscriptionStatus } from '../types/interviewAudio'
interface RecognitionResult {isFinal:boolean;[index:number]:{transcript:string;confidence?:number}}
interface Recognition {
  lang:string;continuous:boolean;interimResults:boolean
  onstart:(()=>void)|null;onend:(()=>void)|null;onerror:((event:{error?:string})=>void)|null
  onresult:((event:{results:ArrayLike<RecognitionResult>})=>void)|null
  start():void;stop():void;abort():void
}
export class BrowserTranscription {
  state:TranscriptionEvidence&{preview:string}={provider:'browser_web_speech',status:'idle',language:'zh-CN',segments:[],confidence:null,preview:''}
  private allowed=false;private epoch=0;private recognition:Recognition|null=null
  private timer:ReturnType<typeof setTimeout>|undefined;private started=0
  private startTimer:ReturnType<typeof setTimeout>|undefined;private stopTimer:ReturnType<typeof setTimeout>|undefined
  private factory:()=>Recognition|null;private text:(text:string)=>void;private changed:()=>void
  constructor(factory:()=>Recognition|null=()=>{
    const ctor=(window as unknown as {SpeechRecognition?:new()=>Recognition;webkitSpeechRecognition?:new()=>Recognition}).SpeechRecognition||(window as unknown as {webkitSpeechRecognition?:new()=>Recognition}).webkitSpeechRecognition
    return ctor?new ctor():null
  },text:(text:string)=>void=()=>{},changed:()=>void=()=>{}){this.factory=factory;this.text=text;this.changed=changed}
  private status(status:TranscriptionStatus){this.state={...this.state,status,preview:''};this.changed()}
  private clearTimers(){clearTimeout(this.timer);clearTimeout(this.startTimer);clearTimeout(this.stopTimer)}
  setAllowed(allowed:boolean){this.allowed=allowed;if(!allowed)this.dispose()}
  start(language:'zh-CN'|'en-US',prefix:string){
    if(!this.allowed){this.status('permission_required');return}
    if(this.recognition)return
    let r:Recognition|null;try{r=this.factory()}catch{r=null}
    if(!r){this.status('unsupported');return}
    const epoch=++this.epoch;this.recognition=r;this.started=performance.now()
    const current=()=>this.epoch===epoch&&this.recognition===r
    this.state={provider:'browser_web_speech',status:'starting',language,segments:[],confidence:null,preview:''};this.changed()
    r.lang=language;r.continuous=true;r.interimResults=true
    this.timer=setTimeout(()=>{if(current()){this.dispose();this.status('interrupted')}},600000)
    this.startTimer=setTimeout(()=>{if(current()){this.dispose();this.status('interrupted')}},15000)
    r.onstart=()=>{if(current()){clearTimeout(this.startTimer);this.status('listening')}}
    r.onresult=event=>{
      if(!current())return
      const segments:TranscriptSegment[]=[],interim:string[]=[];let budget=Math.max(0,12000-prefix.length-100)
      for(const result of Array.from(event.results).slice(0,100)){
        const raw=result[0];if(!raw?.transcript)continue
        if(!result.isFinal){interim.push(raw.transcript);continue}
        const confidence=typeof raw.confidence==='number'&&Number.isFinite(raw.confidence)&&raw.confidence>=0&&raw.confidence<=1?raw.confidence:null
        const text=raw.transcript.slice(0,Math.min(1000,budget));if(!text)break;budget-=text.length
        const old=this.state.segments[segments.length]
        segments.push({text,confidence,callback_seconds:old?.text===text?old.callback_seconds:Math.min(600,(performance.now()-this.started)/1000)})
      }
      const join=language==='en-US'?' ':''
      const final=segments.map(s=>s.text).join(join).slice(0,Math.max(0,12000-prefix.length-(prefix?join.length:0)))
      const changed=final!==this.state.segments.map(s=>s.text).join(join)
      const confidences=segments.flatMap(s=>s.confidence===null?[]:[s.confidence])
      this.state={...this.state,segments,confidence:confidences.length?confidences.reduce((a,b)=>a+b,0)/confidences.length:null,preview:interim.join(join).slice(0,1000)};this.changed()
      if(changed&&segments.length)this.text(prefix+(prefix?join:'')+final)
    }
    r.onend=()=>{if(current()){this.recognition=null;this.clearTimers();this.status(this.state.segments.length?'completed':'no_speech')}}
    r.onerror=event=>{if(current()){this.recognition=null;this.clearTimers();this.epoch++;try{r.abort()}catch{/* 回调失效后终止供应商会话。 */}this.status(this.state.segments.length?'interrupted':event.error==='not-allowed'||event.error==='service-not-allowed'?'denied':event.error==='no-speech'?'no_speech':'interrupted')}}
    try{r.start()}catch{this.recognition=null;this.epoch++;this.clearTimers();this.status('interrupted')}
  }
  stop(){const r=this.recognition;if(!r)return;clearTimeout(this.stopTimer);this.stopTimer=setTimeout(()=>{this.dispose();this.status('interrupted')},5000);try{r.stop()}catch{this.dispose();this.status('interrupted')}}
  dispose(){this.epoch++;const r=this.recognition;this.recognition=null;this.clearTimers();try{r?.abort()}catch{/* 厂商断连后不重开识别。 */}if(r){r.onstart=r.onend=r.onerror=r.onresult=null}this.status(this.state.segments.length?'completed':'idle')}
}
