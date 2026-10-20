import type { CoachDraftStore, DraftContext, CoachApi, CoachAnswer, CoachClientState, CoachEvent, CoachMutationResult, CoachSnapshot, CoachView } from '../types/interviewCoach'
export const initialCoachState = ():CoachClientState => ({sessionId:null,epoch:0,snapshot:null,draft:'',draftContext:null,composing:false,pending:'idle',error:null})
export function reduceCoach(state:CoachClientState,event:CoachEvent):CoachClientState {
 switch(event.type) {
  case 'open': return {...initialCoachState(),sessionId:event.id,epoch:event.epoch}
  case 'snapshot': return state.sessionId===event.id && state.epoch===event.epoch && (!state.snapshot || event.value.revision>=state.snapshot.revision) ? {...state,snapshot:event.value} : state
  case 'draft': return {...state,draft:event.text,draftContext:event.text.trim() ? (event.context ?? state.draftContext) : null,composing:event.composing}
  case 'pending': return {...state,pending:event.value}
  case 'error': return state.sessionId===event.id && state.epoch===event.epoch ? {...state,error:event.value} : state
  case 'dispose': return {...initialCoachState(),epoch:state.epoch+1}
 }
}
export function draftMatches(snapshot:CoachSnapshot,context:DraftContext|null):boolean {
 if(!context)return true
 return snapshot.displayed_index===context.questionIndex && snapshot.session.runtime?.version_token===context.versionToken && (snapshot.current_attempt?.attempt_id ?? null)===context.attemptId
}
export function projectCoach(snapshot:CoachSnapshot,pending:CoachClientState['pending']='idle',context:DraftContext|null=null,replay=false):CoachView {
 const a=snapshot.current_attempt
 const valid=pending!=='analysis' && a?.analysis_status==='succeeded' && !a.data_error && typeof a.score==='number' && Number.isFinite(a.score) && a.score>=0 && a.score<=100
 const free=pending==='idle' && !snapshot.data_error
 return {phase:snapshot.phase,questionIndex:snapshot.displayed_index,question:a?.question ?? snapshot.session.questions[snapshot.displayed_index] ?? '',attemptId:a?.attempt_id ?? null,
 analysisStatus:pending==='analysis'?'running':(a?.analysis_status ?? 'unrequested'),score:valid?a!.score:null,feedback:valid?(a?.evaluation.feedback || '已完成参考分析'):'回答保存后可主动分析；未分析内容不计分。',analysis:valid?(a?.evaluation.content_analysis ?? null):null,
 canSubmit:free && (draftMatches(snapshot,context)||replay) && snapshot.phase!=='summary' && (!snapshot.session.runtime || snapshot.session.runtime.status==='running'),canAdvance:free && snapshot.phase==='feedback' && !!a && !snapshot.active_run_id && (!snapshot.session.runtime || snapshot.session.runtime.status==='running'),canRetry:free && !!a && !snapshot.active_run_id && snapshot.external_consent && (!snapshot.session.runtime || snapshot.session.runtime.status==='running')}
}
export function createCoachController(api:CoachApi,key:()=>string=()=>crypto.randomUUID(),changed:(state:CoachClientState)=>void=()=>{},draftStore?:CoachDraftStore) {
 let state=initialCoachState()
 const autoAnalyzed=new Set<string>()
 let savedRequest:{fingerprint:string;input:CoachAnswer}|null=null
 const send=(event:CoachEvent)=>{state=reduceCoach(state,event);changed(state)}
 const draftContext=():DraftContext|null=>state.snapshot?.session.runtime ? {questionIndex:state.snapshot.displayed_index,attemptId:state.snapshot.current_attempt?.attempt_id ?? null,versionToken:state.snapshot.session.runtime.version_token} : null
 const persist=()=>{if(!state.sessionId||!state.snapshot?.session.runtime||!draftStore)return;try{if(state.draft.trim()&&state.draftContext)draftStore.save(state.sessionId,{text:state.draft,context:state.draftContext});else draftStore.remove(state.sessionId)}catch{/* 禁用存储不阻止本场作答。 */}}
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
 async function mutate(kind:CoachClientState['pending'],operation:(s:CoachSnapshot)=>Promise<CoachMutationResult>) {
  if(!state.snapshot || state.pending!=='idle') return null
  const c=capture();send({type:'pending',value:kind});send({type:'error',...c,value:null})
  try {const result=await operation(state.snapshot);if(!current(c))return null;apply(c,result.snapshot);return result}
  catch(e){if(current(c)){if(kind==='save' && [400,401,403,404,409,422,429].includes((e as {status?:number}).status ?? 0))savedRequest=null;fail(c,e);try{apply(c,await api.get(c.id))}catch{/* 原错误与草稿保留。 */}}return null}
  finally{if(current(c))send({type:'pending',value:'idle'})}
 }
 async function analyze() {
  return (await mutate('analysis',s=>api.analyze(s.session.interview_id,{request_key:key(),expected_revision:s.revision,attempt_id:s.current_attempt!.attempt_id,consent_revision:s.consent_revision})))?.snapshot ?? null
 }
 return {
  get state(){return state},
  get canReplaySave(){return !!savedRequest && savedRequest.input.answer===state.draft && savedRequest.input.question_index===(state.draftContext?.questionIndex ?? state.snapshot?.displayed_index)},
  async open(id:string){savedRequest=null;autoAnalyzed.clear();send({type:'open',id,epoch:state.epoch+1});await refresh();if(state.sessionId===id && state.snapshot?.session.runtime && draftStore){try{const restored=draftStore.load(id);if(restored)send({type:'draft',text:restored.text,context:restored.context,composing:false})}catch{/* 恢复草稿失败不影响已保存回答。 */}}},refresh,
  setDraft(text:string,composing=false){send({type:'draft',text,composing,context:state.draftContext ?? draftContext()});persist()},
  async submit(metrics:Pick<CoachAnswer,'fluency_metrics'|'visual_metrics'>={}) {
   if(!state.snapshot || state.composing || !state.draft.trim() || state.draft.length>12000) return null
   const s=state.snapshot;const text=state.draft;const c=capture()
   // 同一次保存丢失响应后继续使用原版本和请求键，不能在GET后悄悄制造新版本。
   const fingerprint=JSON.stringify([c.id,state.draftContext?.questionIndex ?? s.displayed_index,text,metrics])
   if(!draftMatches(s,state.draftContext) && savedRequest?.fingerprint!==fingerprint){fail(c,{code:'draft_context_changed',message:'这段草稿属于原任务或原回答版本。已为你保留，请复制后清空旧草稿，再回答当前任务。'});return null}
   if(savedRequest?.fingerprint!==fingerprint) savedRequest={fingerprint,input:{...metrics,request_key:key(),expected_revision:s.revision,question_index:s.displayed_index,expected_attempt_id:s.current_attempt?.attempt_id ?? null,answer:text}}
   const request=savedRequest.input
   const saved=await mutate('save',()=>api.submit(c.id,request))
   if(!saved || !current(c))return null
   const receipt=saved.receipt
   if(receipt.kind!=='submit' || receipt.request_key!==request.request_key || typeof receipt.attempt_id!=='string'){
    fail(c,{code:'invalid_receipt',message:'保存回执无法核对，请保留草稿并重新读取。'});return null
   }
   savedRequest=null
   if(saved.snapshot.current_attempt?.attempt_id!==receipt.attempt_id){
    fail(c,{code:'saved_attempt_superseded',message:'这次回答已保存为历史版本；另一处已有新回答。草稿保留，请对照后决定是否再次提交。'});return saved
   }
   if(state.draft===text){send({type:'draft',text:'',composing:false});persist()}
   if(saved.snapshot.external_consent && !saved.snapshot.active_run_id && !autoAnalyzed.has(request.request_key)){
    autoAnalyzed.add(request.request_key);void analyze()
   }
   return saved
  },analyze,
  async runtimeAction(kind:import('../types/interviewRuntime').RuntimeKind){
   if(kind==='finish' && state.pending==='analysis' && state.sessionId && api.runtime){
    const c=capture()
    try{const result=await api.runtime(c.id,kind);apply(c,result.snapshot);return result.snapshot}catch(e){fail(c,e);return null}
   }
   return (await mutate('advance',s=>{
    if(!api.runtime)throw Error('实战接口未启用')
    return api.runtime(s.session.interview_id,kind)
   }))?.snapshot ?? null
  },
  advance:async()=>(await mutate('advance',s=>api.advance(s.session.interview_id,{request_key:key(),expected_revision:s.revision,from_index:s.displayed_index,expected_attempt_id:s.current_attempt!.attempt_id})))?.snapshot ?? null,
  focus:async(question_index:number|null)=>(await mutate('advance',s=>api.focus(s.session.interview_id,{request_key:key(),expected_revision:s.revision,question_index})))?.snapshot ?? null,
  async consent(allowed:boolean){
   if(allowed || state.pending!=='analysis')return (await mutate('consent',s=>api.consent(s.session.interview_id,{request_key:key(),expected_revision:s.revision,allowed})))?.snapshot ?? null
   const s=state.snapshot;if(!s)return null
   const c=capture()
   try{const result=await api.consent(c.id,{request_key:key(),expected_revision:s.revision,allowed:false});apply(c,result.snapshot);return result.snapshot}catch(e){fail(c,e);return null}
  },
  dispose(){savedRequest=null;send({type:'dispose'})},
 }
}
