import { computed, shallowRef, watch } from 'vue'
import { getInterviewCoach, submitInterviewCoachAnswer, analyzeInterviewCoachAttempt, advanceInterviewCoach, setInterviewCoachConsent, getInterviewAttempts, focusInterviewCoach, commandInterviewRuntime } from '../services/api'
import { initialCoachState, createCoachController, projectCoach } from './coach-state'
import { createRuntimeAdapter } from './runtime'
export function useInterviewCoach() {
 const state=shallowRef(initialCoachState())
 const adapter=createRuntimeAdapter({get:getInterviewCoach,submit:submitInterviewCoachAnswer,analyze:analyzeInterviewCoachAttempt,advance:advanceInterviewCoach,consent:setInterviewCoachConsent,attempts:getInterviewAttempts,focus:focusInterviewCoach},commandInterviewRuntime)
 const controller=createCoachController({...adapter.api,runtime:adapter.command},undefined,value=>{state.value=value})
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
  snapshot:computed(()=>state.value.snapshot),view:computed(()=>state.value.snapshot?projectCoach(state.value.snapshot,state.value.pending):null),
  draft:computed(()=>state.value.draft),pending:computed(()=>state.value.pending),error:computed(()=>state.value.error),composing:computed(()=>state.value.composing)}
}
