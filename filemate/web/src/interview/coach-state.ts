import type { CoachApi, CoachAnswer, CoachClientState, CoachEvent, CoachSnapshot, CoachView } from '../types/interviewCoach'
export const initialCoachState = ():CoachClientState => ({sessionId:null,epoch:0,snapshot:null,draft:'',composing:false,pending:'idle',error:null})
export function reduceCoach(state:CoachClientState,event:CoachEvent):CoachClientState {
 switch(event.type) {
  case 'open': return {...initialCoachState(),sessionId:event.id,epoch:event.epoch}
  case 'snapshot': return state.sessionId===event.id && state.epoch===event.epoch && (!state.snapshot || event.value.revision>=state.snapshot.revision) ? {...state,snapshot:event.value} : state
  case 'draft': return {...state,draft:event.text,composing:event.composing}
  case 'pending': return {...state,pending:event.value}
  case 'error': return state.sessionId===event.id && state.epoch===event.epoch ? {...state,error:event.value} : state
  case 'dispose': return {...initialCoachState(),epoch:state.epoch+1}
 }
}
export function projectCoach(snapshot:CoachSnapshot,pending:CoachClientState['pending']='idle'):CoachView {
 const a=snapshot.current_attempt
 const valid=pending!=='analysis' && a?.analysis_status==='succeeded' && !a.data_error && typeof a.score==='number' && Number.isFinite(a.score) && a.score>=0 && a.score<=100
 const free=pending==='idle' && !snapshot.data_error
 return {phase:snapshot.phase,questionIndex:snapshot.displayed_index,question:a?.question ?? snapshot.session.questions[snapshot.displayed_index] ?? '',attemptId:a?.attempt_id ?? null,
 analysisStatus:pending==='analysis'?'running':(a?.analysis_status ?? 'unrequested'),score:valid?a!.score:null,feedback:valid?(a?.evaluation.feedback || '已完成参考分析'):'回答保存后可主动分析；未分析内容不计分。',analysis:valid?(a?.evaluation.content_analysis ?? null):null,
 canSubmit:free && snapshot.phase!=='summary',canAdvance:free && snapshot.phase==='feedback' && !!a && !snapshot.active_run_id,canRetry:free && !!a && !snapshot.active_run_id && snapshot.external_consent}
}
export function createCoachController(api:CoachApi,key:()=>string=()=>crypto.randomUUID(),changed:(state:CoachClientState)=>void=()=>{}) {
 let state=initialCoachState()
 let savedRequest:{fingerprint:string;input:CoachAnswer}|null=null
 const send=(event:CoachEvent)=>{state=reduceCoach(state,event);changed(state)}
 const capture=()=>({id:state.sessionId!,epoch:state.epoch})
 const current=(c:{id:string;epoch:number})=>state.sessionId===c.id && state.epoch===c.epoch
 const apply=(c:{id:string;epoch:number},value:CoachSnapshot)=>send({type:'snapshot',...c,value})
 const fail=(c:{id:string;epoch:number},error:unknown)=>{
  const e=error as {code?:string;message?:string;status?:number}
  send({type:'error',...c,value:{code:e.code || (e.status===409?'revision_conflict':'network_error'),message:e.message || '操作未完成，回答仍保留。请重新读取后重试。'}})
 }
 async function refresh() {
  if(!state.sessionId) return
  const c=capture()
  try {apply(c,await api.get(c.id))} catch(e){fail(c,e)}
 }
 async function mutate(kind:CoachClientState['pending'],operation:(s:CoachSnapshot)=>Promise<{snapshot:CoachSnapshot}>) {
  if(!state.snapshot || state.pending!=='idle') return null
  const c=capture();send({type:'pending',value:kind});send({type:'error',...c,value:null})
  try {const result=await operation(state.snapshot);if(!current(c))return null;apply(c,result.snapshot);return result.snapshot}
  catch(e){if(current(c)){fail(c,e);try{apply(c,await api.get(c.id))}catch{/* 原错误与草稿保留。 */}}return null}
  finally{if(current(c))send({type:'pending',value:'idle'})}
 }
 async function analyze() {
  return mutate('analysis',s=>api.analyze(s.session.interview_id,{request_key:key(),expected_revision:s.revision,attempt_id:s.current_attempt!.attempt_id,consent_revision:s.consent_revision}))
 }
 return {
  get state(){return state},
  async open(id:string){savedRequest=null;send({type:'open',id,epoch:state.epoch+1});await refresh()},refresh,
  setDraft(text:string,composing=false){send({type:'draft',text,composing})},
  async submit(metrics:Pick<CoachAnswer,'fluency_metrics'|'visual_metrics'>={}) {
   if(!state.snapshot || state.composing || !state.draft.trim() || state.draft.length>12000) return null
   const s=state.snapshot;const text=state.draft;const c=capture()
   // 同一次保存丢失响应后继续使用原版本和请求键，不能在GET后悄悄制造新版本。
   const fingerprint=JSON.stringify([c.id,s.displayed_index,text,metrics])
   if(savedRequest?.fingerprint!==fingerprint) savedRequest={fingerprint,input:{...metrics,request_key:key(),expected_revision:s.revision,question_index:s.displayed_index,expected_attempt_id:s.current_attempt?.attempt_id ?? null,answer:text}}
   const request=savedRequest.input
   const saved=await mutate('save',()=>api.submit(c.id,request))
   if(!saved || !current(c))return null
   savedRequest=null
   if(state.draft===text)send({type:'draft',text:'',composing:false})
   if(saved.external_consent && saved.current_attempt?.attempt_id && !saved.active_run_id)await analyze()
   return saved
  },analyze,
  advance:()=>mutate('advance',s=>api.advance(s.session.interview_id,{request_key:key(),expected_revision:s.revision,from_index:s.displayed_index,expected_attempt_id:s.current_attempt!.attempt_id})),
  async consent(allowed:boolean){
   if(allowed || state.pending!=='analysis')return mutate('consent',s=>api.consent(s.session.interview_id,{request_key:key(),expected_revision:s.revision,allowed}))
   const s=state.snapshot;if(!s)return null
   const c=capture()
   try{const result=await api.consent(c.id,{request_key:key(),expected_revision:s.revision,allowed:false});apply(c,result.snapshot);return result.snapshot}catch(e){fail(c,e);return null}
  },
  dispose(){savedRequest=null;send({type:'dispose'})},
 }
}
