import type { ReviewRef } from '../types/wrongbook.ts'
import type { ReviewAnalysis, ReviewLearningContext, AnalysisCommand } from '../types/reviewLearning.ts'
import { memoryReviewStorage, validScope, type ReviewStorage } from './submission.ts'
export type AnalysisApi = {
  getReviewBrowserScope(): Promise<string | null>
  getReviewCredentialMode?(scope: string): Promise<'server' | 'browser'>
  getReviewLearningContext(id: string, p: { attempt_id: string; course_id?: string; credential_mode: 'server' | 'browser' }): Promise<ReviewLearningContext>
  getReviewAnalyses(id: string): Promise<{ items: ReviewAnalysis[] }>
  startReviewAnalysis(id: string, body: AnalysisCommand): Promise<ReviewAnalysis>
  getReviewAnalysisRequest(key: string): Promise<ReviewAnalysis>
  getReviewAnalysis(id: string, aid: string): Promise<ReviewAnalysis>
  cancelReviewAnalysis(id: string, aid: string, body: { request_key: string }): Promise<ReviewAnalysis>
}
type Pending = { ref: ReviewRef; attempt_id: string; request_key: string; input_digest: string; created_at: number }
export function createReviewAnalysisController(api: AnalysisApi, observe = <T extends object>(s: T): T => s, storage: ReviewStorage = memoryReviewStorage()) {
  const state = observe({ context: null as ReviewLearningContext | null, analysis: null as ReviewAnalysis | null, history: [] as ReviewAnalysis[], authorized: false, busy: false, loading: false, uncertain: false, error: '' })
  let epoch = 0, ref: ReviewRef | null = null, attempt = '', course: string | undefined, scope: string | null = null, pending: Pending | null = null
  const fresh = (e: number) => e === epoch
  const storeKey = () => validScope(scope) ? 'filemate-review-analysis-pending-v1:' + scope : null
  function records(): Record<string, Pending> {
    try {
      const key = storeKey(), all = JSON.parse(key ? storage.getItem(key) || '{}' : '{}'), clean: Record<string, Pending> = {}
      if (!all || typeof all !== 'object' || Array.isArray(all)) return clean
      for (const [id, r] of Object.entries(all)) {
        const p = r as Pending
        if (p && p.ref && typeof p.ref.wrong_id === 'string' && typeof p.ref.artifact_id === 'string' && Number.isInteger(p.ref.question_index) && /^[a-f0-9]{64}$/.test(p.ref.question_digest) && /^[A-Za-z0-9_-]{16,80}$/.test(p.request_key) && /^[a-f0-9]{64}$/.test(p.input_digest) && typeof p.attempt_id === 'string' && Date.now() - p.created_at < 7 * 86400000 && p.created_at <= Date.now()) clean[id] = p
      }
      return clean
    } catch { return {} }
  }
  function persist(value: Pending | null, key = pending?.request_key) {
    const name = storeKey(); if (!name) return
    const all = records(); if (key) delete all[key]; if (value) all[value.request_key] = value
    try { storage.setItem(name, JSON.stringify(all)) } catch { /* 页内保留键，刷新后需要从历史核验。 */ }
  }
  function matches(a: ReviewAnalysis, p: Pending) { return a.request_key === p.request_key && a.attempt_id === p.attempt_id && a.input_digest === p.input_digest && Object.entries(p.ref).every(([k,v])=>a.ref?.[k as keyof ReviewRef] === v) }
  function apply(a: ReviewAnalysis, p: Pending) {
    if (!matches(a, p)) throw Error('回执身份不符，请在分析历史核验。')
    state.analysis = a; state.uncertain = ['running', 'cancelling'].includes(a.status)
    if (!state.uncertain) { persist(null, p.request_key); pending = null }
  }
  async function loadContext() {
    if (!ref || !attempt) return false
    const e = epoch; state.loading = true; state.error = ''; state.authorized = false
    try {
      const mode = scope && api.getReviewCredentialMode ? await api.getReviewCredentialMode(scope) : 'server'
      if (!fresh(e)) return false
      const c = await api.getReviewLearningContext(ref.wrong_id, { attempt_id: attempt, course_id: course, credential_mode: mode })
      if (!fresh(e)) return false
      if (Object.entries(ref).some(([k,v])=>c.ref[k as keyof ReviewRef] !== v) || c.attempt.attempt_id !== attempt) throw Error('题目已变化，请重新打开复盘。')
      state.context = c; return true
    } catch (error) { if (fresh(e)) state.error = error instanceof Error ? error.message : '上下文读取失败，请重试。'; return false }
    finally { if (fresh(e)) state.loading = false }
  }
  async function recover() {
    if (!pending || state.busy) return false
    const e = epoch, p = pending; state.busy = true
    try { const a = await api.getReviewAnalysisRequest(p.request_key); if (!fresh(e)) return false; apply(a,p); state.error = ''; return true }
    catch { if (fresh(e)) { state.uncertain = true; state.error = '结果尚未核验，请查询原请求或查看历史；不会自动重新调用模型。' }; return false }
    finally { if (fresh(e)) state.busy = false }
  }
  async function open(target: ReviewRef, attemptId: string, courseId?: string) {
    invalidate(); ref = { wrong_id:target.wrong_id,artifact_id:target.artifact_id,question_index:target.question_index,question_digest:target.question_digest }; attempt = attemptId; course = courseId; const e = epoch
    try { const s = await api.getReviewBrowserScope(); if (!fresh(e)) return false; scope = s } catch { if (!fresh(e)) return false }
    pending = Object.values(records()).find(p=>p.ref.wrong_id===target.wrong_id && p.ref.question_digest===target.question_digest && p.attempt_id===attemptId) ?? null
    state.uncertain = !!pending
    await loadContext(); if (!fresh(e)) return false
    try { const page = await api.getReviewAnalyses(target.wrong_id); if (fresh(e)) state.history = page.items } catch { if (fresh(e)) state.error ||= '历史暂未读取，可重试；当前原答保留。' }
    if (fresh(e) && pending) await recover()
    return fresh(e)
  }
  async function authorizeAndAnalyze(forceRefresh = false) {
    if (!ref || !state.context || !state.authorized || state.busy || state.uncertain) return false
    state.authorized = false; state.error = ''
    if (Object.keys(records()).length >= 20) { state.error = '已有20项待确认分析，请先核验原请求。'; return false }
    const e = epoch, c = state.context
    const p: Pending = { ref: { ...ref }, attempt_id: attempt, request_key: crypto.randomUUID(), input_digest: c.input_digest, created_at: Date.now() }
    pending = p; persist(p); state.busy = true
    try {
      const a = await api.startReviewAnalysis(ref.wrong_id, { attempt_id: attempt, course_id: course, credential_mode: c.credential_mode || 'server', input_digest: c.input_digest, request_key: p.request_key, force_refresh: forceRefresh, allow_external_model: true })
      if (!fresh(e)) return false; apply(a,p); return true
    } catch (error) {
      if (!fresh(e)) return false
      const status = (error as { status?: number }).status
      if (status && [400,403,409,410,422,429].includes(status)) { persist(null); pending = null; state.error = status === 409 ? '证据已变化，请重新读取并授权；原答保留。' : '请求未被接受，请核对配置、输入或额度。' }
      else { state.uncertain = true; state.error = '分析结果待确认，可查询原请求；不会自动重发。' }
      return false
    } finally { if (fresh(e)) state.busy = false }
  }
  async function selectHistory(id: string) {
    if (!ref || state.busy) return false
    const e = epoch
    try { const a = await api.getReviewAnalysis(ref.wrong_id,id); if (!fresh(e)) return false; state.analysis=a; return true } catch { if (fresh(e)) state.error='这份历史分析暂不可读，请重试。'; return false }
  }
  async function cancel() {
    if (!ref || !pending) return false
    const e = epoch, p = pending
    try {
      const existing = state.analysis || await api.getReviewAnalysisRequest(p.request_key)
      if (!fresh(e) || !matches(existing,p)) return false
      const a = await api.cancelReviewAnalysis(ref.wrong_id, existing.analysis_id, {request_key:crypto.randomUUID()})
      if (!fresh(e)) return false
      ++epoch; state.busy=false; apply({...a,request_key:p.request_key},p); return true
    } catch { if (fresh(e)) state.error='取消尚未确认，请查询原请求；独立复习仍可继续。'; return false }
  }
  function invalidate() { ++epoch; ref=null; attempt=''; scope=null; course=undefined; pending=null; Object.assign(state,{context:null,analysis:null,history:[],authorized:false,busy:false,loading:false,uncertain:false,error:''}) }
  return {state,open,loadContext,authorizeAndAnalyze,recover,cancel,selectHistory,invalidate,dirty:()=>state.busy || state.uncertain}
}
