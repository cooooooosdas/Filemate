import type { ConfigurationStatus, InterviewCategory, InterviewConfiguration, InterviewDraft, InterviewDraftContent, SaveInterviewDraft } from '../types/interviewConfiguration'

export const interviewDirections: { id: InterviewCategory; label: string; description: string; tracks: {id:string;label:string;scenario:string|null}[] }[] = [
  {id:'general',label:'通用求职',description:'自我介绍、沟通与职业选择',tracks:[{id:'general',label:'综合面试',scenario:'求职面试'},{id:'hr',label:'HR 沟通',scenario:'HR面'}]},
  {id:'technical',label:'专业技术',description:'岗位知识与算法思路',tracks:[{id:'technical',label:'岗位技术',scenario:'技术面'},{id:'algorithm',label:'算法表达',scenario:'算法面'}]},
  {id:'project',label:'项目与答辩',description:'围绕亲身经历讲清证据',tracks:[{id:'project',label:'项目经历',scenario:'项目面'},{id:'competition',label:'竞赛答辩',scenario:'竞赛答辩'},{id:'academic',label:'保研复试',scenario:'保研复试'}]},
  {id:'creator',label:'主播与表达',description:'知识 / 电商任务 · 筹备中',tracks:[{id:'knowledge',label:'知识主播',scenario:null},{id:'commerce',label:'电商主播',scenario:null}]},
  {id:'learning_expression',label:'学习表达训练',description:'结合课程资料讲清知识',tracks:[{id:'explain',label:'知识讲解',scenario:'知识讲解'}]},
]
export function configurationForScenario(scenario:string, difficulty:string):InterviewConfiguration|null {
  const special=scenario==='英语面'||scenario==='压力面'
  for(const direction of interviewDirections) for(const track of direction.tracks) {
    if(track.scenario===scenario || (special && direction.id==='general' && track.id==='general')) {
      return {schema_version:1,category:direction.id,track:track.id,language:scenario==='英语面'?'en-US':'zh-CN',
        difficulty:difficulty==='入门'||difficulty==='压力面'?difficulty:'标准',duration_minutes:10,
        difficulty_strategy:scenario==='压力面'?'challenge':'standard',question_strategy:'fixed',
        media_preferences:{camera:false,microphone:false,transcription:false,local_recording:false,post_analysis:false}}
    }
  }
  return null
}
export function legacyScenario(config:InterviewConfiguration):string|null {
  if(!Number.isInteger(config.duration_minutes)||config.duration_minutes<1||config.duration_minutes>60)return null
  if(config.question_strategy!=='fixed' || config.category==='creator')return null
  if(config.language==='en-US')return config.category==='general'&&config.track==='general'&&config.difficulty_strategy==='standard'?'英语面':null
  if(config.difficulty_strategy==='challenge')return config.category==='general'&&config.track==='general'?'压力面':null
  return interviewDirections.find(d=>d.id===config.category)?.tracks.find(t=>t.id===config.track)?.scenario??null
}
export function unavailableReason(config:InterviewConfiguration):string {
  if(!Number.isInteger(config.duration_minutes)||config.duration_minutes<1||config.duration_minutes>60)return '目标时长需为 1–60 分钟的整数。'
  if(legacyScenario(config))return ''
  if(config.category==='creator')return '主播任务引擎正在筹备。本次可保存配置，暂不能开始主播训练。'
  if(config.question_strategy!=='fixed')return '当前支持固定题训练；随机、AI 与混合选题尚未启用。'
  return '英文与挑战追问目前仅支持通用求职的综合面试；请调整专项或策略。'
}
export interface DraftClientState { ready:boolean; enabled:boolean; busy:boolean; remote:InterviewDraft; error:string }
export function createDraftController(api:{read:()=>Promise<ConfigurationStatus>;save:(input:SaveInterviewDraft)=>Promise<InterviewDraft>}, key=()=>crypto.randomUUID(), notify:(state:DraftClientState)=>void=()=>{}) {
  let state:DraftClientState={ready:false,enabled:false,busy:false,remote:{revision:0,content:null},error:''}
  let disposed=false, pending:SaveInterviewDraft|null=null
  const update=(patch:Partial<DraftClientState>)=>{if(!disposed){state={...state,...patch};notify(state)}}
  return {
    get state(){return state},
    async load(){
      if(disposed||state.busy)return
      update({busy:true,error:''})
      try{const result=await api.read();if(disposed)return;pending=null;update({ready:true,enabled:result.enabled,remote:result.draft,error:result.draft.error||''})}
      catch{update({error:'配置读取失败，当前输入仍保留。请重试读取。'})}
      finally{update({busy:false})}
    },
    async save(content:InterviewDraftContent){
      if(disposed||state.busy||!state.ready||!state.enabled)return
      if(!pending||JSON.stringify(pending.content)!==JSON.stringify(content))pending={content:JSON.parse(JSON.stringify(content)),expected_revision:state.remote.revision,request_key:key()}
      update({busy:true,error:''})
      try{const result=await api.save(pending);if(disposed)return;pending=null;update({remote:result})}
      catch(e){update({error:e instanceof Error?e.message:'保存失败，当前输入仍保留。可重试；如有版本冲突请读取最新草稿。'})}
      finally{update({busy:false})}
    },
    dispose(){disposed=true},
  }
}
