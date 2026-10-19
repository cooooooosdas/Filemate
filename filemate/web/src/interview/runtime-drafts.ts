import type { CoachDraftStore, DraftContext } from '../types/interviewCoach'

type DraftStorage = Pick<Storage, 'getItem'|'setItem'|'removeItem'>
export function createRuntimeDraftStore(storage: DraftStorage | null): CoachDraftStore & {available:boolean} {
 const prefix='filemate.interview-runtime.draft.v1:'
 const store={available:!!storage,
  load(id:string){
   try {
    const raw=storage?.getItem(prefix+id)
    if(!raw)return null
    const value=JSON.parse(raw) as {text?:unknown;context?:Partial<DraftContext>}
    const c=value.context
    if(typeof value.text!=='string'||!value.text.trim()||value.text.length>12000||!c||!Number.isInteger(c.questionIndex)||c.questionIndex!<0||c.questionIndex!>100||typeof c.versionToken!=='string'||c.versionToken.length>200||!(c.attemptId===null||typeof c.attemptId==='string'))return null
    return {text:value.text,context:c as DraftContext}
   }catch{store.available=false;return null}
  },
  save(id:string,value:{text:string;context:DraftContext}){try{storage?.setItem(prefix+id,JSON.stringify(value))}catch{store.available=false}},
  remove(id:string){try{storage?.removeItem(prefix+id)}catch{store.available=false}},
 }
 return store
}
