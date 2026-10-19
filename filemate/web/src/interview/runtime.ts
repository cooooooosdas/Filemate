import type { CoachApi, CoachMutationResult, CoachSnapshot } from '../types/interviewCoach'
import type { InterviewRuntime, RuntimeCommand, RuntimeKind } from '../types/interviewRuntime'

export function remainingSeconds(runtime:Pick<InterviewRuntime,'status'|'remaining_seconds'>,received:number,now:number):number {
  if(runtime.status==='finished'||runtime.status==='expired')return 0
  return Math.max(0,Math.ceil(runtime.remaining_seconds-(runtime.status==='prepared'?0:Math.max(0,now-received)/1000)))
}
export function formatRemaining(seconds:number):string {
  const n=Math.max(0,Math.ceil(seconds))
  return `${Math.floor(n/60).toString().padStart(2,'0')}:${(n%60).toString().padStart(2,'0')}`
}

export function createRuntimeAdapter(base:CoachApi,post:(id:string,command:RuntimeCommand)=>Promise<CoachMutationResult>,key=()=>crypto.randomUUID()) {
  const sessions=new Map<string,InterviewRuntime>()
  const requests=new Map<string,RuntimeCommand>()
  let pending:{id:string;kind:RuntimeKind;input:RuntimeCommand}|null=null
  const remember=(s:CoachSnapshot)=>{if(s.session.runtime)sessions.set(s.session.interview_id,s.session.runtime);return s}
  function input(id:string,kind:RuntimeKind,requestKey:string):RuntimeCommand {
    const runtime=sessions.get(id)
    if(!runtime)throw Error('实战状态未读取，请重新读取并保留草稿')
    return {kind,request_key:requestKey,expected_revision:runtime.revision,expected_token:runtime.version_token,task_index:runtime.current_task}
  }
  const send=async(id:string,command:RuntimeCommand)=>{
    const result=await post(id,command);remember(result.snapshot);return result
  }
  const api:CoachApi={...base,
    get:async id=>remember(await base.get(id)),
    submit:async(id,answer)=>{
      if(!sessions.has(id))return base.submit(id,answer)
      let cmd=requests.get(answer.request_key)
      if(!cmd){cmd={...input(id,'submit',answer.request_key),task_index:answer.question_index,answer:answer.answer,expected_attempt_id:answer.expected_attempt_id,fluency_metrics:answer.fluency_metrics,visual_metrics:answer.visual_metrics};requests.set(answer.request_key,cmd)}
      const result=await send(id,cmd);requests.delete(answer.request_key);return result
    },
    advance:async(id,advance)=>{
      if(!sessions.has(id))return base.advance(id,advance)
      return send(id,{...input(id,'advance',advance.request_key),task_index:advance.from_index,expected_attempt_id:advance.expected_attempt_id})
    },
  }
  return {api,
    async command(id:string,kind:RuntimeKind){
      if(pending?.id!==id||pending.kind!==kind)pending={id,kind,input:input(id,kind,key())}
      try{const result=await send(id,pending.input);pending=null;return result}
      catch(error){const e=error as {status?:number};if(e.status===409||e.status===422||e.status===429)pending=null;throw error}
    },
    reset(){sessions.clear();requests.clear();pending=null},
  }
}
