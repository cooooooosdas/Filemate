import type { ReviewAttempt, ReviewDetail, ReviewFilter, ReviewListItem, ReviewPage, ReviewRef } from '../types/wrongbook.ts'
import type { createReviewSubmission } from './submission.ts'
import type { createReviewPreferences, ReviewBatch } from './browse-state.ts'

type FocusApi = { getReviewPage(p: ReviewFilter & { limit: number; offset: number }): Promise<ReviewPage<ReviewListItem>>; getReviewDetail(id: string): Promise<ReviewDetail>; getReviewAttempts(id: string, p: { limit: number; offset: number }): Promise<ReviewPage<ReviewAttempt>> }
export function createFocusReviewController(api: FocusApi, submission: ReturnType<typeof createReviewSubmission>, preferences: ReturnType<typeof createReviewPreferences>, observe: <T extends object>(s: T) => T = s => s) {
  const state = observe({ items: [] as ReviewBatch['items'], position: 0, completed: {} as Record<string, string>, skipped: [] as string[], loading: false, unavailable: false, expired: false, finished: false, message: '', error: '' })
  let current: ReviewDetail | null = null, created = '', epoch = 0, disposed = false, identityValid = true
  const fresh = (e: number) => !disposed && e === epoch
  function persist() { if (state.items.length) preferences.saveBatch({ created_at: created, position: state.position, items: state.items }) }
  async function verify(id: string, attempt: string, ref: ReviewRef) {
    // 不凭本机ID认定完成；超出最近100条的记录保持待核验，不重放旧请求。
    const page = await api.getReviewAttempts(id, { limit: 100, offset: 0 })
    return page.items.some(a => a.attempt_id === attempt && a.artifact_id === ref.artifact_id && a.question_index === ref.question_index)
  }
  async function recordSaved() {
    const e = epoch, item = state.items[state.position], receipt = submission.state.receipt
    if (!item || !receipt) return false
    try {
      if (!await verify(item.wrong_id, receipt.attempt_id, item) || !fresh(e)) { if (fresh(e)) state.error = '回执与本题记录尚未核验，请重试核验。'; return false }
      state.completed = { ...state.completed, [item.wrong_id]: receipt.attempt_id }; item.attempt_id = receipt.attempt_id; persist(); return true
    } catch { if (fresh(e)) state.error = '作答回执已收到，记录核验暂不可用，请重试核验。'; return false }
  }
  async function open(index: number) {
    if (disposed || !Number.isInteger(index) || index < 0 || index >= state.items.length || submission.state.busy) return false
    const e = ++epoch, ref = state.items[index]!; current = null; state.position = index; state.loading = true; state.unavailable = false; state.error = ''
    // submission的命名空间由父层注入；切题只清应用状态，不能切换其身份。
    try {
      const detail = await api.getReviewDetail(ref.wrong_id)
      if (!fresh(e)) return false
      if (detail.artifact_id !== ref.artifact_id || detail.question_index !== ref.question_index || detail.question_digest !== ref.question_digest || detail.read_only_snapshot || detail.data_error || detail.schedule_status === 'paused' || detail.legacy_mastered) throw Error('unavailable')
      current = detail; await submission.open(ref, detail.question)
      if (!fresh(e)) return false
      if (ref.attempt_id) {
        if (await verify(ref.wrong_id, ref.attempt_id, ref) && fresh(e)) state.completed = { ...state.completed, [ref.wrong_id]: ref.attempt_id }
        else { delete ref.attempt_id; state.message = '本机完成标记未通过核验，以服务器记录为准。' }
      }
      if (submission.state.uncertain) { await submission.recover(); if (fresh(e) && submission.state.receipt) await recordSaved() }
      if (!fresh(e)) return false
      persist(); return true
    } catch { if (fresh(e)) { current = null; state.unavailable = true; state.error = '此题已修订、删除、暂停或暂不可用。可重试或跳过，不会替换为其他题。' }; return false }
    finally { if (fresh(e)) state.loading = false }
  }
  async function start(filters: ReviewFilter, size = 10) {
    if (disposed || !identityValid || state.loading || !Number.isInteger(size) || size < 1 || size > 20 || submission.dirty()) return false
    const e = ++epoch; state.loading = true; state.error = ''; state.message = ''; state.expired = false; state.finished = false
    try {
      const page = await api.getReviewPage({ ...filters, reviewable_only: true, limit: size, offset: 0 })
      if (!fresh(e)) return false
      state.items = page.items.slice(0, size).map(r => ({ wrong_id: r.wrong_id, artifact_id: r.artifact_id, question_index: r.question_index, question_digest: r.question_digest })); state.completed = {}; state.skipped = []; state.position = 0; created = new Date().toISOString()
      if (!state.items.length) { current = null; preferences.clearBatch(); state.message = '当前筛选没有可复习题目。'; return false }
      state.loading = false; persist(); return open(0)
    } catch { if (fresh(e)) state.error = '暂时无法建立批次，请重试。'; return false }
    finally { if (fresh(e)) state.loading = false }
  }
  async function resume() {
    const b = preferences.getBatch(); if (!b || disposed || !identityValid) return false
    const age = Date.now() - Date.parse(b.created_at)
    if (age < -60000 || age > 7 * 86400000) { state.expired = true; state.message = '本机批次已过期。已提交作答仍可在历史查看，请重新开始批次。'; return false }
    const e = ++epoch
    created = b.created_at; state.items = b.items; state.completed = {}; state.finished = false
    await Promise.all(b.items.filter(r => r.attempt_id).map(async r => { try { if (await verify(r.wrong_id, r.attempt_id!, r) && fresh(e)) state.completed = { ...state.completed, [r.wrong_id]: r.attempt_id! } } catch { /* 未核验的本机标记不算完成。 */ } }))
    if (!fresh(e)) return false
    return open(b.position)
  }
  async function advance(skip: boolean) {
    const item = state.items[state.position]; if (!item || state.loading || submission.state.busy) return false
    if (!skip && !state.completed[item.wrong_id] && !await recordSaved()) return false
    if (skip) state.skipped = [...new Set([...state.skipped, item.wrong_id])]
    if (state.position + 1 >= state.items.length) { state.finished = true; current = null; ++epoch; persist(); return true }
    return open(state.position + 1)
  }
  function resetIdentity(scope: string | null) { ++epoch; identityValid = false; current = null; state.items = []; state.completed = {}; state.skipped = []; state.loading = false; state.finished = false; state.unavailable = false; state.error = ''; submission.resetIdentity(scope) }
  return { state, start, resume, open, recordSaved, skip: () => advance(true), next: () => advance(false), exit() { ++epoch; current = null; persist() }, resetIdentity,
    question() { if (!current) return null; if (submission.state.answerRevealed || submission.state.receipt) return current.question; const { type, question_type, stem, question, options, code } = current.question; return { type, question_type, stem, question, options, code } },
    dispose() { ++epoch; current = null; disposed = true; submission.dispose() } }
}
