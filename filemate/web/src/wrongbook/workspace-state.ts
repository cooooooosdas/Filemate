import type { ReviewAnswer, ReviewAnswerResult, ReviewAttempt, ReviewCapabilities, ReviewDetail, ReviewDiagnosis, ReviewEvent, ReviewFilter, ReviewListItem, ReviewPage, ReviewPreview, ReviewSchedule, ReviewScheduleReceipt, ReviewState, ReviewSummary } from '../types/wrongbook.ts'
import { createReviewSubmission, stableReviewJSON, type ReviewStorage } from './submission.ts'

type Diagnosis = Omit<ReviewDiagnosis, 'request_key' | 'expected_revision'>
export type WorkspaceApi = {
  getReviewBrowserScope(): Promise<string | null>; getReviewCapabilities(): Promise<ReviewCapabilities>
  getReviewSummary(): Promise<ReviewSummary>; getReviewPage(p: ReviewFilter & { limit: number; offset: number }): Promise<ReviewPage<ReviewListItem>>
  getReviewDetail(id: string): Promise<ReviewDetail>; getReviewAttempts(id: string, p: { limit: number; offset: number }): Promise<ReviewPage<ReviewAttempt>>
  getReviewEvents(id: string, p: { limit: number; offset: number }): Promise<ReviewPage<ReviewEvent>>
  getLearningSource(id: string): Promise<unknown>
  setReviewDiagnosis(id: string, body: ReviewDiagnosis): Promise<Partial<ReviewState>>
  previewReviewSchedule(id: string, body: ReviewSchedule): Promise<ReviewPreview>
  confirmReviewSchedule(id: string, body: ReviewSchedule & { confirmed: true; confirmation_token: string }): Promise<ReviewScheduleReceipt>
  submitReviewAnswer(body: ReviewAnswer): Promise<ReviewAnswerResult>; getReviewReceipt(key: string): Promise<unknown>
}
export function createReviewWorkspaceController(api: WorkspaceApi, observe: <T extends object>(s: T) => T = s => s, storage?: ReviewStorage) {
  const blankDiagnosis = (): Diagnosis => ({ error_causes: [], primary_cause: null, custom_tags: [], note: '' })
  const state = observe({ scope: null as string | null, capability: null as ReviewCapabilities | null, capabilityError: '', summary: null as ReviewSummary | null,
    items: [] as ReviewListItem[], total: 0, offset: 0, hasMore: false, filters: {} as ReviewFilter, loading: false, listError: '',
    selected: '', detail: null as ReviewDetail | null, detailLoading: false, detailError: '',
    historyKind: 'attempts' as 'attempts' | 'events', historyItems: [] as (ReviewAttempt | ReviewEvent)[], historyTotal: 0, historyOffset: 0, historyLoading: false, historyError: '',
    source: null as unknown, sourceLoading: false, sourceError: '', diagnosis: blankDiagnosis(), preview: null as ReviewPreview | null,
    writing: false, writeError: '', message: '' })
  const submission = createReviewSubmission(api, { storage, observe })
  let epoch = 0, listEpoch = 0, detailEpoch = 0, historyEpoch = 0, sourceEpoch = 0, disposed = false
  let diagnosisBaseline = '', pendingDiagnosis: ReviewDiagnosis | null = null, pendingSchedule: ReviewSchedule | null = null
  const alive = (e: number, d?: number) => !disposed && e === epoch && (d === undefined || d === detailEpoch)
  const errorText = (e: unknown) => e instanceof Error ? e.message : (e as { status?: number })?.status === 404 ? '此题不存在或已不可用。' : '请求失败，请重试。'
  function draft(detail: ReviewDetail) { state.diagnosis = { error_causes: [...detail.error_causes], primary_cause: detail.error_causes.includes(detail.error_cause as never) ? detail.error_cause as Diagnosis['primary_cause'] : null, custom_tags: [...detail.custom_tags], note: detail.error_cause_note || '' }; diagnosisBaseline = stableReviewJSON(state.diagnosis) }
  async function initialize() {
    const e = epoch; state.capabilityError = ''
    const [cap, scope, summary] = await Promise.allSettled([api.getReviewCapabilities(), api.getReviewBrowserScope(), api.getReviewSummary()])
    if (!alive(e)) return false
    if (cap.status === 'fulfilled') state.capability = cap.value
    else { state.capability = null; state.capabilityError = '暂时无法确认复习服务能力，请重新连接。' }
    const nextScope = scope.status === 'fulfilled' ? scope.value : null
    if (state.scope !== nextScope) submission.resetIdentity(nextScope)
    state.scope = nextScope
    if (summary.status === 'fulfilled') state.summary = summary.value
    return true
  }
  async function loadPage(filters: ReviewFilter, offset = 0) {
    const e = epoch, l = ++listEpoch; state.filters = { ...filters }; state.offset = offset; state.loading = true; state.listError = ''
    try {
      let page = await api.getReviewPage({ ...filters, limit: 30, offset })
      if (!alive(e) || l !== listEpoch) return false
      const valid = page.total ? Math.floor((page.total - 1) / 30) * 30 : 0
      if (!page.items.length && offset > valid) { offset = valid; page = await api.getReviewPage({ ...filters, limit: 30, offset }) }
      if (!alive(e) || l !== listEpoch) return false
      state.items = page.items; state.total = page.total; state.offset = offset; state.hasMore = page.has_more; return true
    } catch (error) { if (alive(e) && l === listEpoch) state.listError = errorText(error); return false }
    finally { if (alive(e) && l === listEpoch) state.loading = false }
  }
  async function select(id: string) {
    const e = epoch, d = ++detailEpoch; ++sourceEpoch; ++historyEpoch
    state.selected = id; state.detail = null; state.detailLoading = true; state.detailError = ''; state.source = null; state.sourceError = ''; state.historyItems = []; state.historyError = ''; state.historyLoading = false; state.sourceLoading = false
    state.preview = null; pendingSchedule = null; pendingDiagnosis = null; state.writeError = ''; state.message = ''; state.diagnosis = blankDiagnosis(); diagnosisBaseline = ''; submission.resetIdentity(state.scope)
    try {
      const detail = await api.getReviewDetail(id)
      if (!alive(e, d)) return false
      state.detail = detail; draft(detail); await submission.open(detail, detail.question)
      if (!alive(e, d)) return false
      if (submission.state.uncertain) await submission.recover()
      return true
    } catch (error) { if (alive(e, d)) state.detailError = errorText(error); return false }
    finally { if (alive(e, d)) state.detailLoading = false }
  }
  async function history(kind: 'attempts' | 'events', offset = 0) {
    const e = epoch, d = detailEpoch, h = ++historyEpoch, id = state.selected
    state.historyKind = kind; state.historyLoading = true; state.historyError = ''; state.historyOffset = offset
    try {
      const page = await (kind === 'attempts' ? api.getReviewAttempts(id, { limit: 20, offset }) : api.getReviewEvents(id, { limit: 20, offset }))
      if (!alive(e, d) || h !== historyEpoch) return false
      state.historyItems = page.items; state.historyTotal = page.total; return true
    } catch (error) { if (alive(e, d) && h === historyEpoch) state.historyError = errorText(error); return false }
    finally { if (alive(e, d) && h === historyEpoch) state.historyLoading = false }
  }
  async function loadSource() {
    const id = state.detail?.source_id; if (!id) { state.sourceError = '原资料已删除或未关联。'; return false }
    const e = epoch, d = detailEpoch, s = ++sourceEpoch; state.sourceLoading = true; state.sourceError = ''
    try { const source = await api.getLearningSource(id); if (!alive(e, d) || s !== sourceEpoch) return false; state.source = source; return true }
    catch (error) { if (alive(e, d) && s === sourceEpoch) state.sourceError = errorText(error); return false }
    finally { if (alive(e, d) && s === sourceEpoch) state.sourceLoading = false }
  }
  const writable = () => !!state.detail && state.capability?.write_enabled === true && !state.detail.read_only_snapshot && !state.detail.data_error && !state.writing
  async function refreshSaved(e: number, d: number) {
    try {
      const [detail, summary] = await Promise.all([api.getReviewDetail(state.selected), api.getReviewSummary()])
      if (!alive(e, d)) return
      state.detail = detail; draft(detail); state.summary = summary; state.message = '已保存。'
      await loadPage(state.filters, state.offset)
      if (state.listError) state.message = '已保存，目录刷新失败，可重新加载。'
    } catch { if (alive(e, d)) state.message = '已保存，刷新失败，可重新加载核对。' }
  }
  async function saveDiagnosis() {
    if (!writable()) return false
    const body = state.diagnosis
    if (body.error_causes.length > 3 || (body.custom_tags?.length ?? 0) > 5 || (body.note?.length ?? 0) > 300 || body.primary_cause && !body.error_causes.includes(body.primary_cause)) { state.writeError = '最多选择3项错因、5个标签；主因应来自已选错因，备注不超过300字。'; return false }
    const input = { ...body, expected_revision: state.detail!.revision }
    if (pendingDiagnosis && stableReviewJSON({ ...pendingDiagnosis, request_key: '' }) !== stableReviewJSON({ ...input, request_key: '' })) { state.writeError = '上次保存结果待确认，请保留原稿并原样重试。'; return false }
    pendingDiagnosis ??= { ...JSON.parse(JSON.stringify(input)), request_key: crypto.randomUUID() }
    const e = epoch, d = detailEpoch; state.writing = true; state.writeError = ''; state.message = ''
    try { await api.setReviewDiagnosis(state.selected, pendingDiagnosis!); if (!alive(e, d)) return false; pendingDiagnosis = null; await refreshSaved(e, d); return true }
    catch (error) { if (alive(e, d)) { if ((error as { status?: number }).status === 409) { pendingDiagnosis = null; state.writeError = '题目已变化，请保留原稿并刷新核对。' } else state.writeError = '保存结果待确认，请保留原稿，原样重试。' } return false }
    finally { if (alive(e, d)) state.writing = false }
  }
  async function previewSchedule(body: Omit<ReviewSchedule, 'request_key' | 'expected_revision'>) {
    if (!writable() || pendingSchedule && state.preview) return false
    const e = epoch, d = detailEpoch; state.writing = true; state.writeError = ''; state.message = ''
    const input = { ...body, request_key: crypto.randomUUID(), expected_revision: state.detail!.revision }
    try { const preview = await api.previewReviewSchedule(state.selected, input); if (!alive(e, d)) return false; pendingSchedule = input; state.preview = preview; return true }
    catch (error) { if (alive(e, d)) state.writeError = errorText(error); return false }
    finally { if (alive(e, d)) state.writing = false }
  }
  async function confirmSchedule() {
    if (!writable() || !state.preview || !pendingSchedule) return false
    const e = epoch, d = detailEpoch; state.writing = true; state.writeError = ''; state.message = ''
    const input = { ...pendingSchedule, confirmed: true as const, confirmation_token: state.preview.confirmation_token }
    try { await api.confirmReviewSchedule(state.selected, input); if (!alive(e, d)) return false; pendingSchedule = null; state.preview = null; await refreshSaved(e, d); return true }
    catch (error) { if (alive(e, d)) { const status = (error as { status?: number }).status; if (status === 409 || status === 410 || status === 422) { pendingSchedule = null; state.preview = null; state.writeError = '预览已失效，请刷新题目后重新预览。' } else state.writeError = '确认结果待核验，请原样重试；不会重复调整排期。' } return false }
    finally { if (alive(e, d)) state.writing = false }
  }
  function resetIdentity(scope: string | null) { ++epoch; ++detailEpoch; ++listEpoch; state.scope = scope; state.capability = null; state.items = []; state.detail = null; state.selected = ''; state.historyItems = []; state.source = null; state.diagnosis = blankDiagnosis(); diagnosisBaseline = ''; state.preview = null; state.writing = false; state.loading = false; state.detailLoading = false; pendingSchedule = null; pendingDiagnosis = null; submission.resetIdentity(scope) }
  return { state, submission, initialize, loadPage, select, history, loadSource, saveDiagnosis, previewSchedule, confirmSchedule, resetIdentity, writable,
    cancelPreview() { if (!state.writing && !state.writeError.includes('待核验')) { state.preview = null; pendingSchedule = null } },
    dirty: () => submission.dirty() || state.writing || !!state.preview || !!pendingDiagnosis || !!state.detail && diagnosisBaseline !== stableReviewJSON(state.diagnosis),
    dispose() { resetIdentity(null); disposed = true; submission.dispose() } }
}
