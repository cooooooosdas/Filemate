import type { ReviewRef } from '../types/wrongbook.ts'
import type { PlanSelection, AdoptionSelection, LearningPreview, LearningReceipt, LearningConfirmation } from '../types/reviewLearning.ts'
import { stableReviewJSON } from './submission.ts'
type LearningApi = {
  previewReviewLearningPlan(id:string,b:PlanSelection):Promise<LearningPreview>;confirmReviewLearningPlan(id:string,b:PlanSelection & LearningConfirmation):Promise<LearningReceipt>
  previewReviewAdoption(id:string,aid:string,b:AdoptionSelection):Promise<LearningPreview>;confirmReviewAdoption(id:string,aid:string,b:AdoptionSelection & LearningConfirmation):Promise<LearningReceipt>
  previewReviewLearningUndo(id:string,event:string):Promise<LearningPreview>;confirmReviewLearningUndo(id:string,event:string,b:LearningConfirmation):Promise<LearningReceipt>
}
export function createReviewLearningController(api:LearningApi,observe=<T extends object>(s:T):T=>s) {
  const state=observe({selection:null as PlanSelection|null,preview:null as LearningPreview|null,receipt:null as LearningReceipt|null,busy:false,uncertain:false,error:''})
  let epoch=0,ref:ReviewRef|null=null,kind:'plan'|'adopt'|'undo'='plan',target='',adoption:AdoptionSelection|null=null,signature='',key='',baseline=''
  const current=()=>stableReviewJSON(kind==='plan'?state.selection:kind==='adopt'?adoption:{event_id:target})
  function invalidate(){++epoch;ref=null;key='';signature='';baseline='';adoption=null;Object.assign(state,{selection:null,preview:null,receipt:null,busy:false,uncertain:false,error:''})}
  function open(value:ReviewRef){invalidate();ref={...value}}
  async function preview(next:typeof kind,id='') {
    if(!ref||state.busy||state.uncertain)return false
    const e=++epoch;kind=next;target=id;state.preview=null;state.error='';state.busy=true;key='';signature=current()
    try {
      const p=kind==='plan'?await api.previewReviewLearningPlan(ref.wrong_id,state.selection!):kind==='adopt'?await api.previewReviewAdoption(ref.wrong_id,target,adoption!):await api.previewReviewLearningUndo(ref.wrong_id,target)
      if(e!==epoch)return false
      if(current()!==signature){state.error='编辑内容已变化，请重新预览。';return false}
      state.preview=p;key=crypto.randomUUID();return true
    }catch(error){if(e===epoch)state.error=(error as {status?:number}).status===409?'证据已变化，请保留编辑内容并重新读取。':'预览失败，请重试；没有创建或修改任务。';return false}
    finally{if(e===epoch)state.busy=false}
  }
  async function confirm(){
    if(!ref||state.busy||!state.preview)return false
    if(current()!==signature){state.error='编辑内容已变化，请恢复原输入核验待确认操作，或重新预览。';if(!state.uncertain)state.preview=null;return false}
    const e=epoch;state.busy=true;state.error=''
    const body:LearningConfirmation={confirmation_token:state.preview.confirmation_token,request_key:key,confirmed:true}
    try{
      const r=kind==='plan'?await api.confirmReviewLearningPlan(ref.wrong_id,{...state.selection!,...body}):kind==='adopt'?await api.confirmReviewAdoption(ref.wrong_id,target,{...adoption!,...body}):await api.confirmReviewLearningUndo(ref.wrong_id,target,body)
      if(e!==epoch)return false
      if(r.wrong_id!==ref.wrong_id||!r.review_event_id)throw Error('invalid_receipt')
      state.receipt=r;state.preview=null;state.uncertain=false;key='';if(kind==='plan')baseline=stableReviewJSON(state.selection);return true
    }catch(error){
      if(e===epoch){const status=(error as {status?:number}).status;if(status&&[400,403,409,410,422,429].includes(status)){state.preview=null;state.uncertain=false;key='';state.error='预览或证据已失效，请重新读取后再预览；原有数据保留。'}else{state.uncertain=true;state.error='确认结果待核验，请原样重试；使用相同键，不会重复写入。'}}return false
    }finally{if(e===epoch)state.busy=false}
  }
  return {state,open,invalidate,setSelection(value:PlanSelection){state.selection=value;baseline=stableReviewJSON(value)},previewPlan:()=>state.selection?preview('plan'):Promise.resolve(false),previewAdoption:(id:string,b:AdoptionSelection)=>{if(state.uncertain||state.busy)return Promise.resolve(false);adoption=JSON.parse(JSON.stringify(b));return preview('adopt',id)},previewUndo:(id:string)=>preview('undo',id),confirm,cancelPreview(){if(!state.busy&&!state.uncertain){state.preview=null;key='';signature=''}},dirty:()=>state.busy||state.uncertain||!!state.preview||!!baseline&&baseline!==stableReviewJSON(state.selection)}
}
