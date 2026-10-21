import { computed, shallowRef, watch } from 'vue'
import { getInterviewCoach, submitInterviewCoachAnswer, analyzeInterviewCoachAttempt, advanceInterviewCoach, setInterviewCoachConsent, getInterviewAttempts, focusInterviewCoach, commandInterviewRuntime } from '../services/api'
import { initialCoachState, createCoachController, projectCoach, draftMatches } from './coach-state'
import { createRuntimeAdapter } from './runtime'
import { createRuntimeDraftStore } from './runtime-drafts'
export function useInterviewCoach() {
 const state=shallowRef(initialCoachState())
 const adapter=createRuntimeAdapter({get:getInterviewCoach,submit:submitInterviewCoachAnswer,analyze:analyzeInterviewCoachAttempt,advance:advanceInterviewCoach,consent:setInterviewCoachConsent,attempts:getInterviewAttempts,focus:focusInterviewCoach},commandInterviewRuntime)
 let storage:Storage|null=null;try{storage=window.sessionStorage}catch{/* 浏览器可能禁用存储。 */}
 const draftStore=createRuntimeDraftStore(storage)
 const controller=createCoachController({...adapter.api,runtime:adapter.command},undefined,value=>{state.value=value},draftStore)
 let timer:ReturnType<typeof setTimeout>|undefined
 let observedRun='',started=0
 const clearTimer=()=>{if(timer!==undefined)clearTimeout(timer);timer=undefined}
 watch(()=>[state.value.snapshot,state.value.pending] as const,([snapshot,pending])=>{
  clearTimer()
  const id=snapshot?.active_run_id || ''
  if(id!==observedRun){observedRun=id;started=Date.now()}
  if(id && pending==='idle' && Date.now()-started<70000)timer=setTimeout(()=>{void controller.refresh()},1500)
  else if(snapshot?.session.runtime && ['running','interrupted'].includes(snapshot.session.runtime.status) && pending==='idle')timer=setTimeout(()=>{void controller.refresh()},5000)
 })
 const recover=()=>{if(state.value.snapshot?.session.runtime && !document.hidden)void controller.refresh()}
 window.addEventListener('online',recover);document.addEventListener('visibilitychange',recover)
 function dispose(){clearTimer();window.removeEventListener('online',recover);document.removeEventListener('visibilitychange',recover);controller.dispose();adapter.reset()}
 return {...controller,open:controller.open,refresh:controller.refresh,submit:controller.submit,analyze:controller.analyze,advance:controller.advance,focus:controller.focus,consent:controller.consent,setDraft:controller.setDraft,dispose,
  snapshot:computed(()=>state.value.snapshot),view:computed(()=>state.value.snapshot?projectCoach(state.value.snapshot,state.value.pending,state.value.draftContext,controller.canReplaySave):null),
  draftConflict:computed(()=>!!state.value.draft.trim() && !controller.canReplaySave && !!state.value.snapshot && !draftMatches(state.value.snapshot,state.value.draftContext)),draftRecoveryAvailable:computed(()=>{void state.value.draft;return draftStore.available}),
  replaySave:computed(()=>{void state.value.draft;void state.value.snapshot;return controller.canReplaySave}),
  draft:computed(()=>state.value.draft),pending:computed(()=>state.value.pending),error:computed(()=>state.value.error),composing:computed(()=>state.value.composing)}
}
