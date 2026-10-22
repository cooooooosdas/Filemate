import type { CourseCandidate, CourseDecision, CourseDraft, CourseReviewPreview, GraphConfirmation, GraphCourse, GraphMode } from '../types/courseGraph.ts'

interface FlowApi {
  getCourse(id: string): Promise<GraphCourse>
  getDraft(cid: string, did: string): Promise<CourseDraft>
  createDraft(cid: string, ids: string[], mode: GraphMode, key: string): Promise<CourseDraft>
  extract(cid: string, did: string, sid: string, mode: GraphMode, consent: boolean, key: string): Promise<CourseDraft>
  cancel(cid: string, did: string, key: string): Promise<CourseDraft>
  saveDecisions(cid: string, did: string, revision: string, decisions: CourseDecision[]): Promise<CourseDraft>
  preview(cid: string, did: string): Promise<CourseReviewPreview>
  confirm(cid: string, did: string, body: GraphConfirmation): Promise<unknown>
}
export interface ReviewState {
  courseId: string; draftId: string; epoch: number; busy: string; error: string; course: GraphCourse | null
  snapshot: CourseDraft | null; selectedSources: string[]; choices: Record<string, CourseDecision>; dirty: boolean
  preview: CourseReviewPreview | null; pendingCommand: { kind: string; signature: string; key: string } | null
}
export function coursePanelEnabled(value?: string): boolean { return value === 'true' }
export function createCourseReviewFlow(api: FlowApi, observe: (state: ReviewState) => ReviewState = s => s) {
  const state = observe({ courseId: '', draftId: '', epoch: 0, busy: '', error: '', course: null,
    snapshot: null, selectedSources: [], choices: {}, dirty: false, preview: null, pendingCommand: null })
  const changed = new Map<string, CourseDecision>()
  const items = (): CourseCandidate[] => state.snapshot?.sources.flatMap(s => [...(s.payload.nodes || []), ...(s.payload.edges || [])]) || []
  function apply(snapshot: CourseDraft) {
    state.snapshot = snapshot; state.draftId = snapshot.draft_id; state.choices = {}; changed.clear(); state.dirty = false
    for (const item of items()) if (typeof item.decision === 'object') state.choices[item.item_id] = item.decision
  }
  async function command<T>(kind: string, body: unknown, run: (key: string) => Promise<T>): Promise<T> {
    const signature = JSON.stringify(body)
    if (state.pendingCommand?.kind !== kind || state.pendingCommand.signature !== signature)
      state.pendingCommand = { kind, signature, key: crypto.randomUUID() }
    const pending = state.pendingCommand
    try { const result = await run(pending.key); if (state.pendingCommand === pending) state.pendingCommand = null; return result }
    catch (cause) {
      if ((cause as { status?: number }).status) state.pendingCommand = null
      throw cause
    }
  }
  function fail(cause: unknown) {
    const status = (cause as { status?: number }).status
    state.error = status === 409 ? '数据或确认已变化，请重新加载草稿、核对并预览。' : cause instanceof Error ? cause.message : '请求失败，请重试'
    if (status === 409) state.preview = null
  }
  async function guard(kind: string, run: (epoch: number) => Promise<void>) {
    const epoch = state.epoch; state.busy = kind; state.error = ''
    try { await run(epoch) } catch (cause) { if (epoch === state.epoch) fail(cause) }
    finally { if (epoch === state.epoch) state.busy = '' }
  }
  async function loadCourse(cid: string, did = '') {
    ++state.epoch; state.courseId = cid; state.draftId = ''; state.course = null; state.snapshot = null
    state.choices = {}; changed.clear(); state.dirty = false; state.preview = null; state.pendingCommand = null; state.selectedSources = []
    if (!cid) return
    await guard('load', async epoch => {
      const course = await api.getCourse(cid)
      if (epoch !== state.epoch) return
      state.course = course
      if (did) { const snapshot = await api.getDraft(cid, did); if (epoch === state.epoch) apply(snapshot) }
    })
  }
  function selectSources(ids: string[]) { if (!state.busy) state.selectedSources = [...new Set(ids)].slice(0, 10) }
  function setDecision(choice: CourseDecision): boolean {
    if (state.busy) return false
    const item = items().find(i => i.item_id === choice.item_id)
    if (!item || ['confirmed', 'revoked'].includes(item.review_status || '')) return false
    if (item.validation === 'invalid' && choice.verdict !== 'reject') return false
    state.choices = { ...state.choices, [choice.item_id]: choice }; changed.set(choice.item_id, choice)
    state.dirty = true; state.preview = null; return true
  }
  function canPreview() {
    return !state.busy && !state.dirty && items().some(i => ['accept', 'revise'].includes(state.choices[i.item_id]?.verdict || '') && !['confirmed', 'revoked'].includes(i.review_status || ''))
      && items().every(i => !['accept', 'revise'].includes(state.choices[i.item_id]?.verdict || '') ||
        (i.validation !== 'invalid' && (i.validation !== 'needs_semantic_review' || state.choices[i.item_id]?.semantic_checked)))
  }
  function canConfirm() { return !state.busy && !state.dirty && Boolean(state.preview && state.preview.revision_digest === state.snapshot?.revision_digest) }
  async function saveDecisions() {
    if (!state.dirty || state.busy) return
    await guard('save', async epoch => {
      const snapshot = await api.saveDecisions(state.courseId, state.draftId, state.snapshot!.revision_digest, [...changed.values()])
      if (epoch === state.epoch) apply(snapshot)
    })
  }
  async function preview() {
    if (!canPreview()) return
    await guard('preview', async epoch => {
      const result = await api.preview(state.courseId, state.draftId)
      if (epoch === state.epoch) state.preview = result
    })
  }
  async function confirm() {
    if (!canConfirm()) return
    await guard('confirm', async epoch => {
      const cid = state.courseId, did = state.draftId, token = state.preview!.confirmation_token
      await command('confirm', { cid, did, token }, key => api.confirm(cid, did, { request_key: key, confirmed: true, confirmation_token: token }))
      if (epoch !== state.epoch) return
      state.preview = null
      const snapshot = await api.getDraft(cid, did); if (epoch === state.epoch) apply(snapshot)
    })
  }
  async function extract(mode: GraphMode, consent: boolean, retry = false) {
    if (state.busy || state.dirty || (mode === 'llm' && !consent)) return
    await guard('extract', async epoch => {
      const cid = state.courseId
      if (!state.snapshot || state.snapshot.status === 'cancelled') {
        const result = await command('draft', { cid, ids: state.selectedSources, mode }, key => api.createDraft(cid, state.selectedSources, mode, key))
        if (epoch !== state.epoch) return
        apply(result)
      }
      const did = state.draftId
      for (const source of state.snapshot!.sources) {
        if (epoch !== state.epoch) return
        if (!['pending', ...(retry ? ['failed', 'interrupted'] : [])].includes(source.status)) continue
        try {
          const result = await command('extract', { cid, did, sid: source.source_id, mode }, key => api.extract(cid, did, source.source_id, mode, consent, key))
          if (epoch === state.epoch) apply(result)
        } catch (cause) {
          // 读取持久失败状态；网络未知结果保留原请求键，重试不会重复计费。
          if (epoch === state.epoch) {
            try { const result = await api.getDraft(cid, did); if (epoch === state.epoch) apply(result) } catch { /* 原快照与重试键保留。 */ }
          }
          throw cause
        }
      }
    })
  }
  async function cancel() {
    if (!state.draftId) return
    ++state.epoch
    await guard('cancel', async epoch => {
      const cid = state.courseId, did = state.draftId
      const result = await command('cancel', { cid, did }, key => api.cancel(cid, did, key))
      if (epoch === state.epoch) apply(result)
    })
  }
  return { state, loadCourse, selectSources, setDecision, saveDecisions, preview, confirm, extract, cancel, canPreview, canConfirm }
}
