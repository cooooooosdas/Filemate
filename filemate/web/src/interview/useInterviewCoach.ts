import { computed, shallowRef } from 'vue'
import { getInterviewCoach, submitInterviewCoachAnswer, analyzeInterviewCoachAttempt, advanceInterviewCoach, setInterviewCoachConsent, getInterviewAttempts } from '../services/api'
import { initialCoachState, createCoachController, projectCoach } from './coach-state'
export function useInterviewCoach() {
 const state=shallowRef(initialCoachState())
 const controller=createCoachController({get:getInterviewCoach,submit:submitInterviewCoachAnswer,analyze:analyzeInterviewCoachAttempt,advance:advanceInterviewCoach,consent:setInterviewCoachConsent,attempts:getInterviewAttempts},undefined,value=>{state.value=value})
 return {...controller,open:controller.open,refresh:controller.refresh,submit:controller.submit,analyze:controller.analyze,advance:controller.advance,consent:controller.consent,setDraft:controller.setDraft,dispose:controller.dispose,
  snapshot:computed(()=>state.value.snapshot),view:computed(()=>state.value.snapshot?projectCoach(state.value.snapshot,state.value.pending):null),
  draft:computed(()=>state.value.draft),pending:computed(()=>state.value.pending),error:computed(()=>state.value.error),composing:computed(()=>state.value.composing)}
}
