import type { ReviewFilter, ReviewSessionPreview, ReviewSessionReady, ReviewSessionRef } from '../types/wrongbook.ts'

type SessionApi = {
  getReviewSessionPreview(params: ReviewFilter & { available_minutes: number; minutes_per_question?: number }): Promise<ReviewSessionPreview>
  checkReviewSession(body: { refs: ReviewSessionRef[]; filters?: ReviewFilter }): Promise<ReviewSessionReady>
}
const refFields = ['wrong_id', 'artifact_id', 'question_index', 'question_digest', 'source_id', 'revision', 'next_review_at'] as const
export function createReviewSessionController(api: SessionApi, observe: <T extends object>(s: T) => T = s => s) {
  const state = observe({ preview: null as ReviewSessionPreview | null, loading: false, checking: false, error: '' })
  let epoch = 0, disposed = false
  const fresh = (e: number) => !disposed && epoch === e
  function invalidate() { ++epoch; state.preview = null; state.loading = false; state.checking = false; state.error = '' }
  async function load(filters: ReviewFilter, minutes: number, perQuestion = 4) {
    if (disposed) return false
    invalidate()
    if (!Number.isInteger(minutes) || minutes < 0 || minutes > 1440 || !Number.isInteger(perQuestion) || perQuestion < 1 || perQuestion > 60) {
      state.error = '请输入有效的整数分钟：可用时间0–1440，每题预估1–60。'; return false
    }
    const e = epoch; state.loading = true
    try {
      const result = await api.getReviewSessionPreview({ ...filters, available_minutes: minutes, minutes_per_question: perQuestion })
      if (!fresh(e)) return false
      state.preview = result; return true
    } catch { if (fresh(e)) state.error = '复习预览暂不可用，请重试。'; return false }
    finally { if (fresh(e)) state.loading = false }
  }
  async function check(): Promise<ReviewSessionReady | null> {
    if (disposed || state.loading || state.checking || !state.preview?.items.length) return null
    const refs = state.preview.items.map(item => ({ ...item.ref })), filters = { ...state.preview.filters }, e = ++epoch
    state.checking = true; state.error = ''
    try {
      const result = await api.checkReviewSession({ refs, filters })
      if (!fresh(e)) return null
      if (result.status !== 'ready' || !Array.isArray(result.refs) || result.refs.length !== refs.length || !result.refs.every((r, i) => r && refFields.every(k => r[k] === refs[i]![k]))) {
        state.preview = null; state.error = '题目核验结果已变化，请重新生成预览。'; return null
      }
      return result
    } catch (error) {
      if (!fresh(e)) return null
      if ((error as { response?: { status?: number } })?.response?.status === 409) {
        state.preview = null; state.error = '题目或复习状态已变化，请重新生成预览。'
      } else state.error = '暂时无法核验题目；预览已保留，请重试核验。'
      return null
    } finally { if (fresh(e)) state.checking = false }
  }
  return { state, load, check, invalidate, dispose() { invalidate(); disposed = true } }
}
