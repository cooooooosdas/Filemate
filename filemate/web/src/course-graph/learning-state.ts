import type { AnswerReceipt, LearningApi, LearningEvidence, LearningPreview, LearningReceipt, LearningWork, PathOptions, PathPreview, PracticeDecision, PracticeOptions, QuestionCandidate, QuestionRef, RelatedCourse, RelatedInput } from '../types/courseLearning.ts'
import type { GraphConfirmation, GraphPage } from '../types/courseGraph.ts'

const emptyPage = <T>(): GraphPage<T> => ({ items: [], total: 0, limit: 50, offset: 0 })
export interface LearningState {
  scope: string; cid: string; nid: string; busy: string; error: string; evidence: LearningEvidence | null
  candidates: GraphPage<QuestionCandidate>; related: GraphPage<RelatedCourse>; selected: QuestionCandidate | null
  answer: string; answerReceipt: AnswerReceipt | null; work: LearningWork | null; decisions: PracticeDecision[]
  practicePreview: LearningPreview | null; practiceReceipt: LearningReceipt | null
  pathOptions: PathOptions; pathPreview: PathPreview | null; planReceipt: LearningReceipt | null
  linksPreview: LearningPreview | null; relatedPreview: LearningPreview | null; lastReceipt: LearningReceipt | null
}
export function createCourseLearningController(api: LearningApi, observe: (s: LearningState) => LearningState = s => s) {
  const initial = (): LearningState => ({ scope: '', cid: '', nid: '', busy: '', error: '', evidence: null,
    candidates: emptyPage(), related: emptyPage(), selected: null, answer: '', answerReceipt: null, work: null,
    decisions: [], practicePreview: null, practiceReceipt: null, pathOptions: { goal: '巩固当前知识点', days: 3, daily_minutes: 20 },
    pathPreview: null, planReceipt: null, linksPreview: null, relatedPreview: null, lastReceipt: null })
  const state = observe(initial())
  let epoch = 0, abort = new AbortController(), disposed = false
  let links: { items: QuestionRef[]; active: boolean } | null = null, related: RelatedInput | null = null
  const pending = new Map<string, { signature: string; key: string }>()
  const dirty = () => !!state.busy || !!(state.answer.trim() && !state.answerReceipt) || !!state.practicePreview || !!state.pathPreview || !!state.linksPreview || !!state.relatedPreview || !!(state.work && ['running', 'ready'].includes(state.work.status))
  const fresh = (e: number) => !disposed && e === epoch
  const error = (cause: unknown) => (cause as { status?: number }).status === 409 ? '内容已变化，请刷新后重新预览；原回答保留。' : '操作暂未完成，输入已保留。可重试；重复确认沿用同一请求。'
  async function run<T>(kind: string, execute: () => Promise<T>, apply: (r: T) => void): Promise<boolean> {
    if (state.busy || disposed || !state.cid) return false
    const e = epoch; state.busy = kind; state.error = ''
    try { const r = await execute(); if (!fresh(e)) return false; apply(r); return true }
    catch (cause) { if (fresh(e)) state.error = error(cause); return false }
    finally { if (fresh(e)) state.busy = '' }
  }
  async function command<T>(kind: string, body: unknown, execute: (key: string) => Promise<T>): Promise<T> {
    const signature = JSON.stringify(body), e = epoch
    if (pending.get(kind)?.signature !== signature) pending.set(kind, { signature, key: crypto.randomUUID() })
    const item = pending.get(kind)!
    try { const r = await execute(item.key); if (fresh(e) && pending.get(kind) === item) pending.delete(kind); return r }
    catch (cause) { if (fresh(e) && (cause as { status?: number }).status && pending.get(kind) === item) pending.delete(kind); throw cause }
  }
  const confirmation = (token: string, key: string): GraphConfirmation => ({ confirmed: true, confirmation_token: token, request_key: key })
  function resetIdentity() { ++epoch; abort.abort(); abort = new AbortController(); pending.clear(); links = null; related = null; Object.assign(state, initial()) }
  async function open(scope: string, cid: string, nid: string, discard = false) {
    if (scope === state.scope && cid === state.cid && nid === state.nid) return true
    if (!discard && dirty()) return false
    resetIdentity(); Object.assign(state, { scope, cid, nid }); if (cid && nid) await loadEvidence(); return true
  }
  async function loadEvidence(offset = 0) {
    const { cid, nid } = state
    return run('read', () => Promise.all([api.getCourseLearning(cid, nid, offset, abort.signal), api.getCourseQuestions(cid, nid, '', 0, abort.signal), api.getCourseRelated(cid, nid, 0, abort.signal)]),
      ([evidence, candidates, related]) => { Object.assign(state, { evidence, candidates, related }) })
  }
  async function loadCandidates(q = '', offset = 0) {
    return run('questions', () => api.getCourseQuestions(state.cid, state.nid, q, offset, abort.signal), r => { state.candidates = r })
  }
  function chooseQuestion(item: QuestionCandidate) { if (state.busy) return; state.selected = structuredClone(item); state.answer = ''; state.answerReceipt = null }
  function setAnswer(value: string) { if (!state.busy && !state.answerReceipt) state.answer = value }
  async function submitAnswer() {
    const selected = state.selected
    if (!selected || !state.answer.trim() || state.answerReceipt) return false
    const { cid, nid } = state
    const ok = await run('answer', () => api.submitQuizAttempt(selected.artifact_id, selected.question_index, state.answer, selected.question), r => { state.answerReceipt = r })
    if (ok && cid === state.cid && nid === state.nid) await loadEvidence()
    return ok
  }
  async function generatePractice(options: PracticeOptions) {
    return run('generate', () => command('generate', options, key => api.generateCoursePractice(state.cid, state.nid, { ...options, request_key: key })), r => { state.work = r; state.decisions = []; state.practicePreview = null; state.practiceReceipt = null })
  }
  async function recoverWork(wid: string) { return run('recover', () => api.getCourseLearningWork(state.cid, wid), r => { state.work = r; state.practicePreview = null }) }
  function setDecisions(value: PracticeDecision[]) { if (!state.busy) { state.decisions = value; state.practicePreview = null; state.practiceReceipt = null } }
  async function reviewPractice() {
    if (!state.work) return false
    return run('review', () => api.previewCoursePractice(state.cid, state.work!.work_id, state.decisions), r => { state.practicePreview = r })
  }
  async function confirmPractice() {
    const preview = state.practicePreview, work = state.work
    if (!preview || !work || state.practiceReceipt) return false
    const ok = await run('confirm-practice', () => command('confirm-practice', [work.work_id, state.decisions, preview.confirmation_token], key => api.confirmCoursePractice(state.cid, work.work_id, state.decisions, confirmation(preview.confirmation_token, key))), r => { state.practiceReceipt = r; state.lastReceipt = r; state.practicePreview = null; state.work = { ...work, status: 'confirmed' } })
    if (ok) await loadEvidence(); return ok
  }
  function setPathOptions(options: Partial<PathOptions>) { if (!state.busy) { state.pathOptions = { ...state.pathOptions, ...options }; state.pathPreview = null; state.planReceipt = null } }
  async function previewPath() { return run('path-preview', () => api.previewCoursePath(state.cid, { ...state.pathOptions, concept_ids: state.pathOptions.concept_ids ?? [state.nid] }), r => { state.pathPreview = r; state.planReceipt = null }) }
  async function confirmPath() {
    const preview = state.pathPreview
    if (!preview || state.planReceipt) return false
    const body = { ...state.pathOptions, concept_ids: state.pathOptions.concept_ids ?? [state.nid] }
    const ok = await run('path-confirm', () => command('path-confirm', [body, preview.confirmation_token], key => api.confirmCoursePath(state.cid, { ...body, ...confirmation(preview.confirmation_token, key) })), r => { state.planReceipt = r; state.lastReceipt = r; state.pathPreview = null })
    if (ok) await loadEvidence(); return ok
  }
  async function previewLinks(items: QuestionRef[], active = true) {
    const body = { items, active }; links = body; state.linksPreview = null
    return run('links-preview', () => api.previewCourseLinks(state.cid, state.nid, items, active), r => { if (links === body) state.linksPreview = r })
  }
  async function confirmLinks() {
    const preview = state.linksPreview, body = links
    if (!preview || !body) return false
    const ok = await run('links-confirm', () => command('links-confirm', [body, preview.confirmation_token], key => api.confirmCourseLinks(state.cid, state.nid, body.items, body.active, confirmation(preview.confirmation_token, key))), r => { state.lastReceipt = r; state.linksPreview = null })
    if (ok) await loadEvidence(); return ok
  }
  async function previewRelated(body: RelatedInput) {
    related = body; state.relatedPreview = null
    return run('related-preview', () => api.previewCourseRelated(state.cid, state.nid, body), r => { if (related === body) state.relatedPreview = r })
  }
  async function confirmRelated() {
    const preview = state.relatedPreview, body = related
    if (!preview || !body) return false
    const ok = await run('related-confirm', () => command('related-confirm', [body, preview.confirmation_token], key => api.confirmCourseRelated(state.cid, state.nid, { ...body, ...confirmation(preview.confirmation_token, key) })), r => { state.lastReceipt = r; state.relatedPreview = null })
    if (ok) await loadEvidence(); return ok
  }
  async function cancel() {
    const work = state.work
    if (!work || state.busy) return false
    return run('cancel', () => command('cancel', work.work_id, key => api.cancelCourseLearningWork(state.cid, work.work_id, key)), r => { state.work = r; state.practicePreview = null })
  }
  return { state, open, loadEvidence, loadCandidates, chooseQuestion, setAnswer, submitAnswer, generatePractice, recoverWork, setDecisions, reviewPractice, confirmPractice, setPathOptions, previewPath, confirmPath, previewLinks, confirmLinks, previewRelated, confirmRelated, cancel, dirty, resetIdentity, dispose() { resetIdentity(); disposed = true } }
}
