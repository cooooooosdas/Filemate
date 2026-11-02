import { createReviewSubmission, type ReviewStorage, type ReviewSubmissionState } from './submission.ts'
import type { ReviewAnswer, ReviewAnswerResult, ReviewCapabilities, ReviewRef } from '../types/wrongbook.ts'
export type EntryApi = {
  getReviewBrowserScope():Promise<string|null>;getReviewCapabilities():Promise<ReviewCapabilities>
  getReviewQuestionAccess(aid:string,index:number):Promise<{legacy_writable:boolean;read_only_snapshot:boolean;question_digest?:string;wrong_id?:string|null;review_route?:string|null}>
  submitReviewAnswer(b:ReviewAnswer):Promise<ReviewAnswerResult>;getReviewReceipt(k:string):Promise<unknown>
  submitQuizAttempt(aid:string,index:number,answer:string,question?:Record<string,unknown>,key?:string):Promise<{is_correct:boolean|null;feedback?:string;reference_answer?:string;attempt_id?:string}>
}
export function createReviewEntry(api:EntryApi,options:{enabled:boolean;storage?:ReviewStorage;observe?:<T extends object>(s:T)=>T}) {
  const observe=options.observe??(<T extends object>(s:T)=>s)
  const state=observe({loading:false,readonly:true,mode:'readonly' as 'readonly'|'v2'|'legacy',message:'',reviewRoute:null as string|null})
  let epoch=0,disposed=false
  const submission=createReviewSubmission({getReviewReceipt:api.getReviewReceipt,async submitReviewAnswer(body){
    if(state.mode==='v2')return api.submitReviewAnswer(body)
    if(state.mode!=='legacy')throw Object.assign(Error('当前题目只读或服务能力尚未确认。'),{status:503})
    if(body.action==='dont_know'||body.answer_revealed)throw Object.assign(Error('旧版仅支持独立回答，请在新工作台使用辅助练习。'),{status:422})
    const result=await api.submitQuizAttempt(body.artifact_id,body.question_index,body.user_answer||'',body.expected_question,body.request_key)
    return {...result,attempt_id:result.attempt_id||'',wrong_id:null,score:null,feedback:result.feedback||'作答已保存',judgement_method:'legacy_rule',judgement_status:result.is_correct===null?'pending':'legacy',rule_version:'legacy-v1',reference_answer:result.reference_answer||'',eligible:false,reason:'legacy',before:{},after:{},review_event_id:''}
  }},{storage:options.storage,observe:observe as (s:ReviewSubmissionState)=>ReviewSubmissionState})
  async function open(ref:Pick<ReviewRef,'artifact_id'|'question_index'>,raw:Record<string,unknown>,readonly=false) {
    const e=++epoch;state.loading=true;state.readonly=true;state.mode='readonly';state.message='';state.reviewRoute=null;submission.resetIdentity(null)
    try{
      const [scope,access,cap]=await Promise.all([api.getReviewBrowserScope().catch(()=>null),api.getReviewQuestionAccess(ref.artifact_id,ref.question_index),options.enabled?api.getReviewCapabilities():Promise.resolve(null)])
      if(disposed||e!==epoch)return false
      state.reviewRoute=options.enabled&&access.wrong_id&&access.review_route?.startsWith('/wrongbook?')?access.review_route:null
      submission.resetIdentity(scope);await submission.open({...ref,question_digest:access.question_digest},raw)
      if(disposed||e!==epoch)return false
      if(readonly||access.read_only_snapshot)state.message='历史题集只读，不能保存新作答。'
      else if(options.enabled){if(cap?.write_enabled)state.mode='v2';else state.message='新规则写入暂未开启，可查看题目并稍后重连。'}
      else if(access.legacy_writable)state.mode='legacy'
      else state.message='此题已由新规则管理；当前旧界面只读，请启用新复盘工作台。'
      state.readonly=state.mode==='readonly'
      if(submission.state.uncertain&&state.mode==='v2')await submission.recover()
      return !state.readonly
    }catch{if(e===epoch&&!disposed)state.message='暂时无法核验题目与服务能力，请重连后再答。';return false}
    finally{if(e===epoch&&!disposed)state.loading=false}
  }
  function invalidate(){++epoch;state.loading=false;state.readonly=true;state.mode='readonly';state.reviewRoute=null;submission.resetIdentity(null)}
  return {state,submission,open,invalidate,dirty:()=>submission.dirty(),dispose(){invalidate();disposed=true;submission.dispose()}}
}
