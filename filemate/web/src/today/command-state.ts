import { readHttpStatus } from './http-status.ts'
import type { OperationReceipt, OrchestratorClient, PreviewRequest, ScopeRequest, UndoPreview } from '../types/orchestrator.ts'
import type { PendingLocator, TodayState, TodayStorage } from '../types/today.ts'
import { todayPendingKey } from './preferences.ts'
import { TODAY_EPOCH_KEY } from '../services/today-session.ts'
const clockDay = () => new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString().slice(0, 10)

const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T
const id = (value: unknown, max = 128): value is string => typeof value === 'string' && value.length > 0 && value.length <= max && !/[\x00-\x1f]/.test(value)
const keyValid = (value: unknown): value is string => typeof value === 'string' && /^[a-zA-Z0-9_-]{16,80}$/.test(value)
const tokenValid = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
const httpStatus = (error: unknown): number | undefined => readHttpStatus(error)
function dateValid(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const instant = Date.parse(`${value}T00:00:00Z`)
  return Number.isFinite(instant) && new Date(instant).toISOString().slice(0, 10) === value
}
function scopeKey(value: ScopeRequest | null): string | null {
  if (!value || !id(value.goal_id) || value.course_id != null && !id(value.course_id) ||
    !Array.isArray(value.source_ids) || value.source_ids.length > 20 || value.source_ids.some(source => !id(source))) return null
  return JSON.stringify([value.goal_id, value.course_id ?? null, [...value.source_ids].sort()])
}
class PendingStorageError extends Error {}
type Flight = { kind: 'preview' | 'confirm' | 'recover' | 'undo_preview' | 'undo'; identity: string; generation: number; epoch: string | null }
type Reviewed = { body: PreviewRequest; token: string; until: number; identity: string; generation: number; study_date: string; epoch: string | null }
type ReviewedUndo = { value: UndoPreview; until: number; identity: string; generation: number; read_date: string; read_revision: number; epoch: string | null }

/** Keep authorization in memory and persist only a stable per-tab recovery locator. */
export function createTodayCommands(client: OrchestratorClient, state: TodayState, storage: TodayStorage, refresh: () => Promise<void>) {
  let disposed = false, flight: Flight | null = null, reviewed: Reviewed | null = null, undo: ReviewedUndo | null = null
  const epoch = () => { try { return storage.getItem(TODAY_EPOCH_KEY) ?? '' } catch { return null } }
  let observedClockDay = clockDay()
  const currentIdentity = (ticket: Flight): boolean => !disposed && state.identity === ticket.identity && flight === ticket && ticket.epoch === epoch()
  const current = (ticket: Flight): boolean => currentIdentity(ticket) && state.generation === ticket.generation
  function begin(kind: Flight['kind']): Flight | null {
    if (disposed || flight || state.phase !== 'ready' || !state.identity) return null
    flight = { kind, identity: state.identity, generation: state.generation, epoch: epoch() }
    return flight
  }
  function finish(ticket: Flight): void { if (flight === ticket) flight = null }
  function clearAuthority(): void { reviewed = null; undo = null; state.preview = null; state.undo_preview = null }
  function loadPending(identity: string): PendingLocator | null {
    try {
      const raw = storage.getItem(todayPendingKey(identity))
      if (raw === null) return null
      if (raw.length > 1024) throw new Error()
      const value = JSON.parse(raw) as PendingLocator
      if (!value || typeof value !== 'object' || Array.isArray(value) ||
        Object.keys(value).some(key => !['kind', 'request_key', 'study_date', 'operation_id', 'epoch'].includes(key)) ||
        !keyValid(value.request_key) || !dateValid(value.study_date) || value.epoch !== undefined && !id(value.epoch, 80) ||
        !(value.kind === 'confirm' && value.operation_id === undefined || value.kind === 'undo' && id(value.operation_id))) throw new Error()
      if ((value.epoch ?? '') !== epoch()) { storage.removeItem(todayPendingKey(identity)); return null }
      return copy(value)
    } catch { throw new PendingStorageError('无法读取请求存储，请核验已保存安排后重试。') }
  }
  function persist(identity: string, locator: PendingLocator): void {
    const previous = loadPending(identity)
    if (previous && (previous.request_key !== locator.request_key || previous.kind !== locator.kind || previous.operation_id !== locator.operation_id)) throw new PendingStorageError('另一个请求尚待核验，请先查回执。')
    const currentEpoch = epoch()
    if (currentEpoch === null) throw new PendingStorageError('无法读取本机同步状态，尚未发送请求，请允许本页存储后重试。')
    locator = { ...locator, ...(currentEpoch ? { epoch: currentEpoch } : {}) }
    const encoded = JSON.stringify(locator)
    try {
      storage.setItem(todayPendingKey(identity), encoded)
      if (storage.getItem(todayPendingKey(identity)) !== encoded) throw new Error()
    } catch { throw new PendingStorageError('浏览器无法保存请求记录，尚未发出保存请求，请允许本页存储后重试。') }
    state.pending = copy(locator)
  }
  function removePending(identity: string, requestKey: string): boolean {
    try {
      if (loadPending(identity)?.request_key === requestKey) storage.removeItem(todayPendingKey(identity))
      state.pending = null
      return true
    } catch { state.pending = null; return false }
  }
  function expire(identity: string): void {
    try { storage.removeItem(todayPendingKey(identity)) } catch { /* The server still authenticates every replay. */ }
    clearAuthority(); state.generation++; state.phase = 'expired'; state.identity = null; state.snapshot = null
    state.day = null; state.draft = null; state.receipt = null; state.pending = null; state.dirty = false
    state.write_status = 'idle'; state.error = '登录已过期，请重新登录后读取。'
  }
  function problem(error: unknown, ticket: Flight, fallback: string): void {
    if (httpStatus(error) === 401) { expire(ticket.identity); return }
    state.error = error instanceof PendingStorageError ? error.message : httpStatus(error) === 429
      ? '操作次数较多，请稍后再试；不会自动重复请求。' : fallback
  }
  function newKey(): string {
    if (!globalThis.crypto?.randomUUID) throw new PendingStorageError('当前环境无法安全生成保存请求，请使用安全连接重试。')
    return globalThis.crypto.randomUUID()
  }
  function receiptValid(value: OperationReceipt, pending: PendingLocator): boolean {
    return !!value && id(value.operation_id) && value.request_key === pending.request_key && dateValid(value.study_date) &&
      Number.isSafeInteger(value.revision) && value.revision > 0 && (pending.kind === 'undo' ? value.status === 'undone' : value.status === 'confirmed' || value.status === 'undone') &&
      !!value.affected && typeof value.affected === 'object' && !Array.isArray(value.affected) &&
      Object.values(value.affected).every(amount => Number.isSafeInteger(amount) && amount >= 0)
  }
  async function saved(value: OperationReceipt, pending: PendingLocator, ticket: Flight, direct: boolean): Promise<void> {
    if (!current(ticket)) return
    if (!receiptValid(value, pending)) throw new Error('invalid_receipt')
    const receipt = copy(value)
    const wasHistory = receipt.study_date !== (state.snapshot?.snapshot.study_date ?? state.day?.study_date)
    clearAuthority(); state.receipt = receipt; state.write_status = 'saved'; state.error = ''
    if (direct && !wasHistory) state.dirty = false
    const removed = removePending(ticket.identity, pending.request_key)
    let refreshFailed = false
    try { await refresh() } catch { refreshFailed = true }
    if (!currentIdentity(ticket)) return
    state.write_status = 'saved'
    if (wasHistory || receipt.study_date !== (state.snapshot?.snapshot.study_date ?? state.day?.study_date)) state.error = `已查回${receipt.study_date}的历史回执；当前日期与草稿保持独立。`
    else if (refreshFailed) state.error = '已保存，刷新暂不可用，请稍后重新读取。'
    else if (state.error) state.error = `已保存；刷新提示：${state.error}`
    else if (!removed) state.error = '已保存；请求记录尚未清理，可再次查回执。'
    else if (!direct && state.dirty) state.error = '已查回原请求的保存回执；当前草稿保留，请重新预览后再确认。'
  }
  async function lookup(pending: PendingLocator, ticket: Flight): Promise<void> {
    try {
      const receipt = await client.findOrchestratorOperation(pending.request_key)
      if (current(ticket)) await saved(receipt, pending, ticket, false)
    } catch (error) {
      if (!current(ticket)) return
      clearAuthority(); state.write_status = 'unknown'
      problem(error, ticket, httpStatus(error) === 404
        ? '暂未查到回执，结果仍待核验；可再次查询，或重新预览后沿原请求确认。'
        : '暂时无法核验请求结果，请保留本页并再次查回执。')
    }
  }
  async function preview(): Promise<void> {
    const ticket = begin('preview')
    if (!ticket) return
    try {
      state.pending = loadPending(ticket.identity)
      if (state.pending?.kind === 'undo') { state.write_status = 'unknown'; state.error = '有待核验的撤销，请先查回执或重试原撤销。'; return }
      if (!state.draft || !state.snapshot || !scopeKey(state.draft.scope) || scopeKey(state.draft.scope) !== scopeKey(state.snapshot.snapshot.scope)) throw new Error('missing_scope')
      const body: PreviewRequest = { scope: copy(state.snapshot.snapshot.scope), options: copy(state.draft.options), expected_evidence_revision: state.snapshot.snapshot.evidence_revision }
      clearAuthority(); state.error = ''; state.write_status = 'previewing'
      const sentAt = Date.now(), value = await client.previewOrchestratorSchedule(copy(body))
      if (!current(ticket)) return
      if (!value || scopeKey(value.scope) !== scopeKey(body.scope) || value.evidence_revision !== body.expected_evidence_revision ||
        value.study_date !== state.snapshot?.snapshot.study_date || !tokenValid(value.confirmation_token) ||
        !Number.isInteger(value.expires_in_seconds) || value.expires_in_seconds < 1 || value.expires_in_seconds > 900 ||
        !Number.isSafeInteger(value.day_revision) || value.day_revision < 0 || !Array.isArray(value.selected) || value.selected.length > 20 ||
        new Set(value.selected.map(task => task?.task_id)).size !== value.selected.length ||
        value.selected.some(task => !task || !id(task.task_id, 512) || task.goal_id !== body.scope.goal_id || task.status !== 'pending') ||
        !Array.isArray(value.completed) || value.completed.length > 200 || !Array.isArray(value.deferred) || value.deferred.length > 200) throw new Error('invalid_preview')
      state.draft = copy(body); state.preview = copy(value); state.write_status = 'idle'
      reviewed = { body: copy(body), token: value.confirmation_token, until: sentAt + value.expires_in_seconds * 1000,
        identity: ticket.identity, generation: ticket.generation, study_date: value.study_date, epoch: ticket.epoch }
    } catch (error) {
      if (current(ticket)) { clearAuthority(); state.write_status = state.pending ? 'unknown' : 'idle'; problem(error, ticket, '无法预览当前范围，草稿保留，请重新读取后预览。') }
    } finally { finish(ticket) }
  }
  async function writeFailure(error: unknown, pending: PendingLocator, ticket: Flight, hadPending: boolean): Promise<void> {
    if (!current(ticket)) return
    clearAuthority()
    if (httpStatus(error) === 401) { expire(ticket.identity); return }
    if (!hadPending && pending.kind === 'undo' && httpStatus(error) === 409 &&
      (error as { code?: string })?.code === 'schedule_changed_since_operation') {
      removePending(ticket.identity, pending.request_key); state.write_status = 'idle'
      try { await refresh() } catch { /* The definite rejection still ends this new request. */ }
      if (currentIdentity(ticket)) state.error = '原安排已变化，本次撤销未执行；请核对当前安排后继续。'
      return
    }
    if (httpStatus(error) === 409) { state.write_status = 'unknown'; await lookup(pending, ticket); return }
    if (!hadPending && [400, 403, 413, 422, 429].includes(httpStatus(error) ?? 0)) {
      removePending(ticket.identity, pending.request_key); state.write_status = 'idle'
      problem(error, ticket, '范围、任务或预览已变化，请重新读取并预览。')
    } else { state.write_status = 'unknown'; problem(error, ticket, '请求结果待核验，请查回执；不要重复创建保存请求。') }
  }
  async function confirm(): Promise<void> {
    if (observedClockDay !== clockDay()) { await checkDayBoundary(); return }
    const ticket = begin('confirm')
    if (!ticket) return
    try {
      const review = reviewed
      if (!review || review.identity !== ticket.identity || review.generation !== ticket.generation || review.epoch !== ticket.epoch || Date.now() >= review.until ||
        state.preview?.confirmation_token !== review.token || JSON.stringify(state.draft) !== JSON.stringify(review.body) ||
        state.snapshot?.snapshot.evidence_revision !== review.body.expected_evidence_revision || state.snapshot.snapshot.study_date !== review.study_date) {
        clearAuthority(); state.write_status = state.pending ? 'unknown' : state.receipt ? 'saved' : 'idle'
        state.error = '内容已变化或预览已过期，请重新预览。'; return
      }
      const previous = loadPending(ticket.identity)
      if (previous?.kind === 'undo') throw new PendingStorageError('原撤销尚待核验，请先查回执。')
      const pending: PendingLocator = { kind: 'confirm', request_key: previous?.request_key ?? newKey(), study_date: review.study_date }
      persist(ticket.identity, pending)
      state.write_status = 'confirming'; state.error = ''
      try {
        const receipt = await client.confirmOrchestratorSchedule({ ...copy(review.body), confirmation_token: review.token, request_key: pending.request_key, confirmed: true })
        await saved(receipt, pending, ticket, true)
      } catch (error) { await writeFailure(error, pending, ticket, previous !== null) }
    } catch (error) { if (current(ticket)) problem(error, ticket, '无法保存请求记录，尚未发出保存请求。') }
    finally { finish(ticket) }
  }
  async function recover(): Promise<void> {
    const ticket = begin('recover')
    if (!ticket) return
    try {
      const pending = loadPending(ticket.identity)
      state.pending = pending
      if (!pending) return
      clearAuthority(); state.write_status = 'unknown'; state.error = ''
      await lookup(pending, ticket)
    } catch (error) { if (current(ticket)) problem(error, ticket, '请求记录暂不可读，请核验已保存安排。') }
    finally { finish(ticket) }
  }
  async function previewUndo(operationId: string): Promise<void> {
    const ticket = begin('undo_preview')
    if (!ticket) return
    try {
      state.pending = loadPending(ticket.identity)
      const pending = state.pending, latest = state.day?.latest_operation
      clearAuthority()
      if (!id(operationId) || pending && (pending.kind !== 'undo' || pending.operation_id !== operationId) ||
        !pending && (!latest || latest.status !== 'confirmed' || latest.operation_id !== operationId || latest.study_date !== state.day?.study_date || latest.revision !== state.day?.revision)) {
        state.write_status = pending ? 'unknown' : state.receipt ? 'saved' : 'idle'
        state.error = '无法定位当前撤销回执；待决请求请先核验，旧数据不猜测撤销编号。'; return
      }
      state.write_status = 'previewing'; state.error = ''
      const sentAt = Date.now(), value = await client.previewOrchestratorUndo(operationId)
      if (!current(ticket)) return
      if (!value || value.operation_id !== operationId || !dateValid(value.study_date) || !tokenValid(value.confirmation_token) ||
        !Number.isSafeInteger(value.day_revision) || value.day_revision < 0 || !Number.isInteger(value.expires_in_seconds) ||
        value.expires_in_seconds < 1 || value.expires_in_seconds > 900 || !state.day) throw new Error('invalid_undo_preview')
      undo = { value: copy(value), until: sentAt + value.expires_in_seconds * 1000, identity: ticket.identity,
        generation: ticket.generation, read_date: state.day.study_date, read_revision: state.day.revision, epoch: ticket.epoch }
      state.undo_preview = copy(value); state.write_status = 'undo_preview'
    } catch (error) { if (current(ticket)) { clearAuthority(); state.write_status = state.pending ? 'unknown' : 'idle'; problem(error, ticket, '撤销预览暂不可用，请重新读取当前回执。') } }
    finally { finish(ticket) }
  }
  async function confirmUndo(): Promise<void> {
    if (observedClockDay !== clockDay()) { await checkDayBoundary(); return }
    const ticket = begin('undo')
    if (!ticket) return
    try {
      const review = undo
      if (!review || review.identity !== ticket.identity || review.generation !== ticket.generation || review.epoch !== ticket.epoch || Date.now() >= review.until ||
        state.undo_preview?.confirmation_token !== review.value.confirmation_token || state.day?.study_date !== review.read_date || state.day?.revision !== review.read_revision) {
        clearAuthority(); state.write_status = state.pending ? 'unknown' : state.receipt ? 'saved' : 'idle'
        state.error = '撤销依据已变化或预览已过期，请重新预览撤销。'; return
      }
      const previous = loadPending(ticket.identity)
      if (previous && (previous.kind !== 'undo' || previous.operation_id !== review.value.operation_id)) throw new PendingStorageError('另一个请求尚待核验，请先查回执。')
      const pending: PendingLocator = { kind: 'undo', request_key: previous?.request_key ?? newKey(), study_date: review.value.study_date, operation_id: review.value.operation_id }
      persist(ticket.identity, pending); state.write_status = 'undoing'; state.error = ''
      try {
        const receipt = await client.confirmOrchestratorUndo(review.value.operation_id, { confirmation_token: review.value.confirmation_token, request_key: pending.request_key, confirmed: true })
        await saved(receipt, pending, ticket, true)
      } catch (error) { await writeFailure(error, pending, ticket, previous !== null) }
    } catch (error) { if (current(ticket)) problem(error, ticket, '无法保存撤销请求记录，尚未发出撤销请求。') }
    finally { finish(ticket) }
  }
  function invalidate(): void {
    if (disposed) return
    clearAuthority()
    if (flight && flight.kind !== 'confirm' && flight.kind !== 'undo') flight = null
    if (state.write_status !== 'confirming' && state.write_status !== 'undoing' && state.write_status !== 'saved') state.write_status = state.pending ? 'unknown' : 'idle'
  }
  async function checkDayBoundary(): Promise<boolean> {
    if (disposed || observedClockDay === clockDay()) return false
    observedClockDay = clockDay(); invalidate()
    state.error = '日期可能已变化，旧预览已失效，请按服务端日期重新预览。'
    if (!flight && state.identity && state.phase === 'ready') { try { await refresh() } catch { /* Keep authorization revoked if refresh fails. */ } }
    return true
  }
  function dispose(): void {
    if (disposed) return
    clearAuthority(); state.pending = null
    if (state.write_status === 'confirming' || state.write_status === 'undoing') state.write_status = 'unknown'
    disposed = true; flight = null
  }
  return { preview, confirm, recover, previewUndo, confirmUndo, checkDayBoundary, invalidate, dispose }
}
