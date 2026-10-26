import type { ReviewAnswer, ReviewAnswerResult, ReviewRef } from '../types/wrongbook.ts'

export type ReviewStorage = { getItem(key: string): string | null; setItem(key: string, value: string): void; removeItem(key: string): void }
export const memoryReviewStorage = (): ReviewStorage => { const values = new Map<string, string>(); return { getItem: k => values.get(k) ?? null, setItem: (k, v) => { values.set(k, v) }, removeItem: k => { values.delete(k) } } }
export const browserReviewStorage = (): ReviewStorage => { try { return window.localStorage } catch { return memoryReviewStorage() } }
export const validScope = (scope: unknown): scope is string => typeof scope === 'string' && /^[a-f0-9]{64}$/.test(scope)
export const stableReviewJSON = (value: unknown): string => {
  if (Array.isArray(value)) return '[' + value.map(stableReviewJSON).join(',') + ']'
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + stableReviewJSON((value as Record<string, unknown>)[k])).join(',') + '}'
  return JSON.stringify(value) ?? 'null'
}
export async function reviewHash(value: unknown) {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(stableReviewJSON(value))))].map(n => n.toString(16).padStart(2, '0')).join('')
}
type InputRef = Pick<ReviewRef, 'artifact_id' | 'question_index'> & Partial<ReviewRef>
type Pending = { request_key: string; signature_hash: string; revealed: boolean }
type SubmissionApi = { submitReviewAnswer(body: ReviewAnswer): Promise<ReviewAnswerResult>; getReviewReceipt(key: string): Promise<unknown> }
export type ReviewSubmissionState = { answer: string; answerRevealed: boolean; busy: boolean; receipt: ReviewAnswerResult | null; error: string; uncertain: boolean; stale: boolean }

export function createReviewSubmission(api: SubmissionApi, options: { makeKey?: () => string; scope?: string | null; storage?: ReviewStorage; observe?: (state: ReviewSubmissionState) => ReviewSubmissionState } = {}) {
  const initial = (): ReviewSubmissionState => ({ answer: '', answerRevealed: false, busy: false, receipt: null, error: '', uncertain: false, stale: false })
  const state = (options.observe ?? (s => s))(initial())
  const storage = options.storage ?? memoryReviewStorage(), makeKey = options.makeKey ?? (() => crypto.randomUUID())
  let scope = options.scope ?? null, epoch = 0, disposed = false, identity = '', ref: InputRef | null = null
  let raw: Record<string, unknown> | null = null, pendingBody: ReviewAnswer | null = null
  let records: Record<string, Pending> = Object.create(null)
  const storageKey = () => validScope(scope) ? `filemate-review-pending-v1:${scope}` : null
  function load() {
    records = Object.create(null)
    try {
      const key = storageKey(), data = JSON.parse(key ? storage.getItem(key) || '{}' : '{}')
      if (!data || typeof data !== 'object' || Array.isArray(data)) return
      for (const [id, record] of Object.entries(data).slice(-20)) {
        const item = record as Pending
        if (id.length > 300 || !item || typeof item !== 'object' || typeof item.revealed !== 'boolean' || typeof item.request_key !== 'string' || !/^(?:[A-Za-z0-9_-]{16,80})?$/.test(item.request_key) || typeof item.signature_hash !== 'string' || !/^(?:[a-f0-9]{64})?$/.test(item.signature_hash)) continue
        records[id] = { request_key: item.request_key, signature_hash: item.signature_hash, revealed: item.revealed }
      }
    } catch { /* 不可用的本机存储不影响页内作答。 */ }
  }
  function persist() {
    const keys = Object.keys(records)
    // 未确认请求不能被自动淘汰，否则刷新会丢失去重标识。
    while (keys.length > 20) {
      const remove = keys.find(k => !records[k]?.request_key && k !== identity)
      if (!remove) break
      delete records[remove]; keys.splice(keys.indexOf(remove), 1)
    }
    try { const key = storageKey(); if (key) storage.setItem(key, JSON.stringify(records)) } catch { /* 保留内存状态。 */ }
  }
  const fresh = (e: number) => !disposed && e === epoch
  load()
  async function open(target: InputRef, question: Record<string, unknown>) {
    const e = ++epoch; pendingBody = null; ref = null; raw = null; identity = ''
    Object.assign(state, initial())
    const questionHash = await reviewHash(question)
    if (!fresh(e)) return false
    ref = { ...target }; raw = JSON.parse(JSON.stringify(question))
    identity = `${target.artifact_id}:${target.question_index}:${questionHash}`
    const saved = records[identity]
    state.answerRevealed = saved?.revealed ?? false; state.uncertain = !!saved?.request_key
    return true
  }
  function setAnswer(value: string) {
    if (disposed || state.busy || state.receipt || state.uncertain && pendingBody) return false
    state.answer = value.slice(0, 10000); return true
  }
  function revealAnswer() {
    if (disposed || state.busy || state.uncertain) return false
    state.answerRevealed = true
    records[identity] = { request_key: '', signature_hash: '', ...records[identity], revealed: true }; persist(); return true
  }
  async function submit(action: 'answer' | 'dont_know' = 'answer') {
    if (!ref || !raw || state.busy || state.stale || state.receipt || disposed || action === 'answer' && !state.answer.trim()) return false
    const e = epoch; state.busy = true; state.error = ''
    try {
      const input = { artifact_id: ref.artifact_id, question_index: ref.question_index, expected_question: raw,
        user_answer: action === 'dont_know' ? '' : state.answer, action, answer_revealed: state.answerRevealed }
      const signature = await reviewHash(input)
      if (!fresh(e)) return false
      const saved = records[identity]
      if (saved?.request_key && saved.signature_hash !== signature) { state.error = '上次保存结果待确认，请核验回执或重新输入上次回答；也可以先跳过此题。'; return false }
      if (!saved?.request_key && Object.values(records).filter(r => r.request_key).length >= 20) { state.error = '请先核验已有待确认作答，再开始新的提交。'; return false }
      const key = saved?.request_key || makeKey()
      pendingBody ??= { ...input, request_key: key }
      records[identity] = { request_key: key, signature_hash: signature, revealed: state.answerRevealed }; persist()
      const result = await api.submitReviewAnswer(pendingBody)
      if (!fresh(e)) return false
      state.receipt = result; state.uncertain = false; delete records[identity]; persist(); return true
    } catch (cause) {
      if (!fresh(e)) return false
      const status = (cause as { status?: number }).status
      if (status === 409) { state.stale = true; state.error = '题目或复习规则已变化，请先刷新核对；原稿保留。'; delete records[identity]; pendingBody = null; persist() }
      else if (status && status >= 400 && status < 500 && status !== 408 && status !== 429) { state.error = cause instanceof Error ? cause.message : '本次请求未被接受，请检查输入。'; delete records[identity]; pendingBody = null; persist() }
      else { state.uncertain = true; state.error = '保存结果尚未确认。保留原请求，可查询回执或原样重试。' }
      return false
    } finally { if (fresh(e)) state.busy = false }
  }
  async function recover() {
    const saved = records[identity]
    if (disposed || state.busy || !saved?.request_key) return false
    const e = epoch; state.busy = true; state.error = ''
    try {
      const result = await api.getReviewReceipt(saved.request_key)
      if (!fresh(e)) return false
      if (!result || typeof result !== 'object' || !('attempt_id' in result)) throw Error('invalid_receipt')
      state.receipt = result as ReviewAnswerResult; state.uncertain = false; delete records[identity]; persist(); return true
    } catch {
      if (fresh(e)) { state.uncertain = true; state.error = '暂未查到回执，不代表保存失败。请保留原稿后核验或原样重试。' }
      return false
    } finally { if (fresh(e)) state.busy = false }
  }
  function resetIdentity(next: string | null) { ++epoch; scope = next; ref = null; raw = null; pendingBody = null; identity = ''; Object.assign(state, initial()); load() }
  return { state, open, setAnswer, revealAnswer, submit, recover, resetIdentity,
    dirty: () => state.busy || state.uncertain || !!state.answer.trim() && !state.receipt,
    dispose() { ++epoch; disposed = true; ref = null; raw = null; pendingBody = null; Object.assign(state, initial()) } }
}
