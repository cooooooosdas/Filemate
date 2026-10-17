import { computed, shallowRef, watch } from 'vue'
import { getInterviewCoach, submitInterviewCoachAnswer, analyzeInterviewCoachAttempt, advanceInterviewCoach, setInterviewCoachConsent, getInterviewAttempts, focusInterviewCoach } from '../services/api'
import { initialCoachState, createCoachController, projectCoach } from './coach-state'
export function useInterviewCoach() {
 const state=shallowRef(initialCoachState())
 const controller=createCoachController({get:getInterviewCoach,submit:submitInterviewCoachAnswer,analyze:analyzeInterviewCoachAttempt,advance:advanceInterviewCoach,consent:setInterviewCoachConsent,attempts:getInterviewAttempts,focus:focusInterviewCoach},undefined,value=>{state.value=value})
 let timer:ReturnType<typeof setTimeout>|undefined
 let observedRun='',started=0
 const clearTimer=()=>{if(timer!==undefined)clearTimeout(timer);timer=undefined}
 watch(()=>[state.value.snapshot,state.value.pending] as const,([snapshot,pending])=>{
  clearTimer()
  const id=snapshot?.active_run_id || ''
  if(id!==observedRun){observedRun=id;started=Date.now()}
  if(id && pending==='idle' && Date.now()-started<70000)timer=setTimeout(()=>{void controller.refresh()},1500)
 })
 function dispose(){clearTimer();controller.dispose()}
 return {...controller,open:controller.open,refresh:controller.refresh,submit:controller.submit,analyze:controller.analyze,advance:controller.advance,focus:controller.focus,consent:controller.consent,setDraft:controller.setDraft,dispose,
  snapshot:computed(()=>state.value.snapshot),view:computed(()=>state.value.snapshot?projectCoach(state.value.snapshot,state.value.pending):null),
  draft:computed(()=>state.value.draft),pending:computed(()=>state.value.pending),error:computed(()=>state.value.error),composing:computed(()=>state.value.composing)}
}
