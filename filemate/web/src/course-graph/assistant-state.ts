import type { CourseOperation, GraphConfirmation, GraphPage } from '../types/courseGraph.ts'
import type { LearningReceipt, PathOptions, PathPreview } from '../types/courseLearning.ts'

export interface AssistantPayload {
  mode: 'rule' | 'llm'; question: string; explanation: string
  textbook_evidence: { evidence_id: string; concept_id: string; source_id: string; quote: string }[]
  personal_facts: { fact_id: string; concept_id: string; label: string; status: string; counts: Record<string, number> }[]
  suggestions: string[]; limitations: string[]
  coverage: { total_course_concepts: number; concepts_in_context: number; quote_characters: number; quotes_in_context: number }
}
export interface AssistantWork { work_id: string; kind: string; status: string; stale: boolean; error_code?: string | null; payload: Partial<AssistantPayload> }
export interface AssistantInput { question: string; concept_ids: string[]; mode: 'rule' | 'llm'; allow_external_model: boolean; request_key: string }
interface AssistantApi {
  answerGraphCourse(cid: string, body: AssistantInput): Promise<AssistantWork>
  getCourseLearningWork(cid: string, wid: string): Promise<AssistantWork>
  getCourseOperations(cid: string, offset?: number): Promise<GraphPage<CourseOperation>>
  previewGraphAssistantPlan(cid: string, body: PathOptions): Promise<PathPreview & { tool_steps?: { name: string; writes_learning_data: boolean }[] }>
  confirmCoursePath(cid: string, body: PathOptions & GraphConfirmation): Promise<LearningReceipt>
  cancelCourseLearningWork(cid: string, wid: string, key: string): Promise<AssistantWork>
}
interface AssistantState {
  scope: string; cid: string; nid: string; question: string; mode: 'rule' | 'llm'; consent: boolean
  busy: string; error: string; uncertain: boolean; work: AssistantWork | null; history: GraphPage<CourseOperation>
  planOptions: PathOptions; planPreview: (PathPreview & { tool_steps?: { name: string; writes_learning_data: boolean }[] }) | null
  receipt: LearningReceipt | null
}
export function createGraphAssistantController(api: AssistantApi, observe: (s: AssistantState) => AssistantState = s => s) {
  const initial = (): AssistantState => ({ scope: '', cid: '', nid: '', question: '', mode: 'rule', consent: false,
    busy: '', error: '', uncertain: false, work: null, history: { items: [], total: 0, limit: 50, offset: 0 },
    planOptions: { goal: '巩固当前知识点', daily_minutes: 20, days: 3 }, planPreview: null, receipt: null })
  const state = observe(initial())
  let epoch = 0, serial = 0, disposed = false, pending: AssistantInput | null = null, confirmKey = ''
  function resetIdentity() { ++epoch; ++serial; pending = null; confirmKey = ''; Object.assign(state, initial()) }
  function open(scope: string, cid: string, nid: string) { if (scope !== state.scope || cid !== state.cid || nid !== state.nid) { resetIdentity(); Object.assign(state, { scope, cid, nid }) } }
  const current = (e: number, s: number) => !disposed && e === epoch && s === serial
  async function run<T>(kind: string, execute: () => Promise<T>, apply: (r: T) => void) {
    if (state.busy || disposed || !state.cid) return false
    const e = epoch, s = ++serial; state.busy = kind; state.error = ''
    try { const r = await execute(); if (!current(e, s)) return false; apply(r); return true }
    catch (cause) { if (current(e, s)) state.error = (cause as { status?: number }).status === 503 ? '图谱助手尚未启用或服务暂不可用，已有资料与结果保留。' : '操作未完成，输入已保留。可读取原请求，或刷新已保存历史。'; return false }
    finally { if (current(e, s)) state.busy = '' }
  }
  function setQuestion(value: string) { if (!state.busy) { state.question = value; state.consent = false; pending = null; state.uncertain = false; state.planPreview = null } }
  function setMode(mode: 'rule' | 'llm') { if (!state.busy) { state.mode = mode; state.consent = false; pending = null; state.uncertain = false } }
  function setConsent(value: boolean) { state.consent = value }
  async function send() {
    if (!state.question.trim() || state.busy) return false
    if (!pending && state.mode === 'llm' && !state.consent) { state.error = '请授权本次将所选课程原文与训练摘要发送给模型。'; return false }
    pending ??= { question: state.question, concept_ids: [state.nid], mode: state.mode, allow_external_model: state.consent, request_key: crypto.randomUUID() }
    const body = pending, e = epoch; state.consent = false
    const ok = await run('answer', () => api.answerGraphCourse(state.cid, body), r => { state.work = r; state.uncertain = false; pending = null })
    if (!ok && e === epoch && pending === body) state.uncertain = true
    return ok
  }
  async function loadHistory(offset = 0) { return run('history', () => api.getCourseOperations(state.cid, offset), r => { state.history = { ...r, items: r.items.filter(op => op.work_kind === 'answer' && !!op.work_id) } }) }
  async function reopen(wid: string) { return run('read', () => api.getCourseLearningWork(state.cid, wid), r => { if (r.kind !== 'answer') throw new Error('not_an_answer'); state.work = r; state.consent = false }) }
  function setPlanOptions(options: Partial<PathOptions>) { if (!state.busy) { state.planOptions = { ...state.planOptions, ...options }; state.planPreview = null; state.receipt = null; confirmKey = '' } }
  const options = () => ({ ...state.planOptions, concept_ids: [state.nid] })
  async function previewPlan() { return run('preview', () => api.previewGraphAssistantPlan(state.cid, options()), r => { state.planPreview = r; state.receipt = null; confirmKey = crypto.randomUUID() }) }
  async function confirmPlan() {
    const preview = state.planPreview
    if (!preview || state.receipt) return false
    return run('confirm', () => api.confirmCoursePath(state.cid, { ...options(), confirmed: true, confirmation_token: preview.confirmation_token, request_key: confirmKey }), r => { state.receipt = r; state.planPreview = null })
  }
  async function cancel() {
    if (state.busy && state.busy !== 'answer') return false
    const cid = state.cid, key = pending?.request_key, e = epoch
    ++serial; state.busy = ''
    return run('cancel', async () => {
      let wid = state.work?.status === 'running' ? state.work.work_id : ''
      if (!wid && key) { const history = await api.getCourseOperations(cid); wid = history.items.find(op => op.request_key === key)?.work_id || '' }
      if (!wid || e !== epoch) throw new Error('request_not_claimed')
      return api.cancelCourseLearningWork(cid, wid, crypto.randomUUID())
    }, r => { state.work = r; pending = null; state.uncertain = false; state.consent = false })
  }
  const dirty = () => !!state.busy || state.uncertain || !!state.planPreview || !!(state.question.trim() && !state.work)
  return { state, open, setQuestion, setMode, setConsent, send, loadHistory, reopen, setPlanOptions, previewPlan, confirmPlan, cancel, dirty, resetIdentity, dispose() { resetIdentity(); disposed = true } }
}
