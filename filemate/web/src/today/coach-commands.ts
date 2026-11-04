import type {
  CoachDraft,
  CoachLocator,
  CoachReceipt,
  CoachRunView,
  CoachState,
  LearningCoachClient,
} from '../types/learning-coach'
import type { TodayStorage } from '../types/today'
import { acceptCoachRun, coachError } from './coach-state'
import { readHttpStatus } from './http-status'

const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T
const encoded = (value: unknown) => JSON.stringify(value)
const dateValid = (value: unknown): value is string =>
  typeof value === 'string' &&
  /^\d{4}-\d{2}-\d{2}$/.test(value) &&
  new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value
const keyValid = (value: unknown): value is string =>
  typeof value === 'string' && /^[a-zA-Z0-9_-]{16,80}$/.test(value)
const idValid = (value: unknown): value is string =>
  typeof value === 'string' && /^[a-zA-Z0-9_-]{1,128}$/.test(value)
const tokenValid = (value: unknown): value is string =>
  typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
export const coachPendingKey = (identity: string) =>
  'filemate-coach-pending-v1:' + encodeURIComponent(identity)

export function appendCoachDay(draft: CoachDraft, today: string): CoachDraft {
  const value = copy(draft),
    latest = value.days.at(-1)?.study_date ?? today
  const candidates = Array.from({ length: 7 }, (_, i) =>
    new Date(Date.parse(`${today}T00:00:00Z`) + i * 86400000).toISOString().slice(0, 10),
  )
  const next = candidates.find((date) => date > latest)
  if (next && value.days.length < 7)
    value.days.push({
      study_date: next,
      options: {
        available_minutes: value.days[0]?.options.available_minutes ?? 0,
        item_order: [],
        pinned_ids: [],
        excluded_ids: [],
        minute_overrides: {},
      },
    })
  return value
}

/** Persist recovery coordinates before writes; authorization remains in memory. */
export function createCoachCommands(
  client: LearningCoachClient,
  options: {
    state: CoachState
    storage: TodayStorage
    refresh: () => Promise<void>
    now?: () => number
  },
) {
  const { state, storage } = options,
    now = options.now ?? Date.now
  const day = () => new Date(now() + 8 * 3600000).toISOString().slice(0, 10)
  type Ticket = { identity: string; generation: number }
  let flight: Ticket | null = null
  let review: {
    body: string
    token: string
    until: number
    day: string
    generation: number
    identity: string
  } | null = null
  let undo: {
    body: string
    token: string
    until: number
    day: string
    generation: number
    identity: string
  } | null = null
  function live(ticket: Ticket) {
    return (
      flight === ticket &&
      state.identity === ticket.identity &&
      state.generation === ticket.generation &&
      state.phase !== 'expired' &&
      state.phase !== 'closed'
    )
  }
  function begin(allowRunning = false): Ticket | null {
    if (
      flight ||
      !state.identity ||
      state.phase === 'closed' ||
      state.phase === 'expired' ||
      (state.phase === 'running' && !allowRunning)
    )
      return null
    flight = { identity: state.identity, generation: state.generation }
    return flight
  }
  function load(): CoachLocator | null {
    if (!state.identity) return null
    const raw = storage.getItem(coachPendingKey(state.identity))
    if (raw === null) return null
    if (raw.length > 512) throw new Error('invalid_locator')
    const value = JSON.parse(raw) as CoachLocator
    if (
      !value ||
      Object.keys(value).some(
        (k) => !['kind', 'request_key', 'issued_study_date', 'operation_id'].includes(k),
      ) ||
      !keyValid(value.request_key) ||
      !dateValid(value.issued_study_date) ||
      !['request', 'confirm', 'undo'].includes(value.kind) ||
      (value.kind === 'undo' ? !idValid(value.operation_id) : value.operation_id !== undefined)
    )
      throw new Error('invalid_locator')
    return copy(value)
  }
  function persist(locator: CoachLocator) {
    if (!state.identity) throw new Error('identity_missing')
    const previous = load()
    if (previous && encoded(previous) !== encoded(locator)) throw new Error('pending_request')
    const raw = encoded(locator),
      key = coachPendingKey(state.identity)
    storage.setItem(key, raw)
    if (storage.getItem(key) !== raw) throw new Error('storage_unavailable')
    state.pending = copy(locator)
  }
  function clearPending(key: string) {
    if (state.identity && load()?.request_key === key)
      storage.removeItem(coachPendingKey(state.identity))
    state.pending = null
  }
  function invalidate() {
    review = null
    undo = null
    state.preview = null
    state.undo_preview = null
  }
  function error(value: unknown, fallback?: string) {
    invalidate()
    if (readHttpStatus(value) === 401) {
      const identity = state.identity
      if (identity) {
        try {
          storage.removeItem(coachPendingKey(identity))
        } catch {
          /* The locator contains no authorization. */
        }
      }
      state.generation++
      state.identity = null
      state.input = null
      state.context = null
      state.run = null
      state.draft = null
      state.receipt = null
      state.pending = null
      state.dirty = false
      state.phase = 'expired'
    } else state.phase = 'error'
    state.error = readHttpStatus(value)
      ? coachError(value)
      : (fallback ?? '请求结果待核验，请先查询保存结果。')
  }
  function unresolved() {
    state.pending = load()
    if (state.pending) {
      state.error = '原请求结果尚待核验，请先查询；不会自动重发或覆盖原请求编号。'
      return true
    }
    return false
  }
  function validReceipt(value: CoachReceipt, locator: CoachLocator) {
    return (
      value &&
      idValid(value.operation_id) &&
      value.request_key === locator.request_key &&
      (locator.kind === 'undo'
        ? value.status === 'undone'
        : ['confirmed', 'undone'].includes(value.status)) &&
      Array.isArray(value.study_dates) &&
      value.study_dates.length > 0 &&
      value.study_dates.length <= 7 &&
      value.study_dates.every(dateValid) &&
      value.day_revisions &&
      value.study_dates.every(
        (d) => Number.isSafeInteger(value.day_revisions[d]) && value.day_revisions[d]! > 0,
      ) &&
      value.affected &&
      Object.values(value.affected).every((v) => Number.isSafeInteger(v) && v >= 0)
    )
  }
  async function saved(value: CoachReceipt, locator: CoachLocator, ticket: Ticket) {
    if (!live(ticket)) return
    if (!validReceipt(value, locator)) throw new Error('invalid_receipt')
    state.receipt = copy(value)
    state.phase = 'ready'
    state.dirty = false
    state.error = ''
    invalidate()
    try {
      clearPending(locator.request_key)
    } catch {
      state.error = '已保存，请求记录尚未清理，可再次查询原结果。'
    }
    try {
      await options.refresh()
    } catch {
      if (live(ticket)) state.error = '已保存，刷新暂不可用，请稍后重新读取。'
    }
  }
  async function preview(draft: CoachDraft) {
    const ticket = begin()
    if (!ticket) return
    let requested = false
    try {
      if (unresolved()) return
      invalidate()
      state.phase = 'loading'
      state.error = ''
      state.draft = copy(draft)
      const body = encoded(draft),
        started = now()
      requested = true
      const value = await client.preview(copy(draft))
      if (!live(ticket)) return
      if (
        !value ||
        encoded(value.draft) !== body ||
        !tokenValid(value.confirmation_token) ||
        !dateValid(value.issued_study_date) ||
        !Number.isInteger(value.expires_in_seconds) ||
        value.expires_in_seconds < 1 ||
        value.expires_in_seconds > 900
      )
        throw new Error('invalid_preview')
      review = {
        body,
        token: value.confirmation_token,
        until: started + value.expires_in_seconds * 1000,
        day: value.issued_study_date,
        ...ticket,
      }
      state.preview = copy(value)
      state.phase = 'ready'
    } catch (e) {
      if (live(ticket))
        error(
          e,
          e instanceof Error && e.message === 'invalid_preview'
            ? '返回的预览与本页调整不一致，请重新读取并预览；原安排保留。'
            : requested
              ? '暂时无法核对本次方案，请恢复网络后重新预览。'
              : '无法读取本页请求存储，请允许本页存储后重新预览。',
        )
    } finally {
      if (flight === ticket) flight = null
    }
  }
  async function writeFailure(e: unknown, locator: CoachLocator, ticket: Ticket) {
    if (!live(ticket)) return
    const code = readHttpStatus(e)
    if ([400, 403, 409, 413, 422, 429].includes(code ?? 0)) {
      try {
        clearPending(locator.request_key)
      } catch {
        /* Retain the safe locator when storage is blocked. */
      }
    }
    if (locator.kind === 'undo' && code === 409) {
      // The server rolls the entire transaction back; never apply a partial undo locally.
      try {
        clearPending(locator.request_key)
      } catch {
        /* A later GET still resolves the original request. */
      }
      error(e)
      state.error = '原安排或任务进度已变化，撤销整体拒绝；所有进度保留，请重新读取。'
    } else error(e)
  }
  async function confirm() {
    const ticket = begin()
    if (!ticket) return
    try {
      if (unresolved()) return
      if (
        !review ||
        review.identity !== ticket.identity ||
        review.generation !== ticket.generation ||
        review.until <= now() ||
        review.day !== day() ||
        encoded(state.draft) !== review.body ||
        state.preview?.confirmation_token !== review.token
      ) {
        invalidate()
        state.error = '内容、日期已变化或预览过期，请重新读取并预览。'
        return
      }
      const locator: CoachLocator = {
        kind: 'confirm',
        request_key: crypto.randomUUID(),
        issued_study_date: review.day,
      }
      try {
        persist(locator)
      } catch {
        state.error = '浏览器存储无法保存请求记录，尚未发送保存请求。'
        return
      }
      const body = {
        ...copy(state.draft!),
        confirmation_token: review.token,
        request_key: locator.request_key,
        confirmed: true as const,
      }
      state.phase = 'loading'
      try {
        await saved(await client.confirm(body), locator, ticket)
      } catch (e) {
        await writeFailure(e, locator, ticket)
      }
    } catch (e) {
      if (live(ticket)) error(e, '无法读取请求存储，尚未发送保存请求。')
    } finally {
      if (flight === ticket) flight = null
    }
  }
  function trackRequest(locator: CoachLocator) {
    persist(locator)
  }
  function settleRequest(view: CoachRunView) {
    if (view.status !== 'running') clearPending(view.request_key)
  }
  function rejectRequest(value: unknown, locator: CoachLocator) {
    if ([400, 401, 403, 409, 413, 422, 429].includes(readHttpStatus(value) ?? 0))
      clearPending(locator.request_key)
  }
  async function recover() {
    const ticket = begin(true)
    if (!ticket) return
    try {
      const locator = load()
      state.pending = locator
      if (!locator) return
      invalidate()
      state.phase = 'loading'
      state.error = ''
      if (locator.kind === 'request') {
        const value = await client.get(locator.request_key)
        if (!live(ticket)) return
        if (value?.request_key !== locator.request_key) throw new Error('invalid_request')
        settleRequest(value)
        acceptCoachRun(state, value)
      } else await saved(await client.operation(locator.request_key), locator, ticket)
    } catch (e) {
      if (live(ticket)) {
        error(e)
        if (readHttpStatus(e) === 404)
          state.error = '暂未查到原请求，结果仍待核验；请再次查询，不会自动重发。'
      }
    } finally {
      if (flight === ticket) flight = null
    }
  }
  async function previewUndo(operationId: string) {
    const ticket = begin()
    if (!ticket) return
    try {
      if (unresolved()) return
      invalidate()
      state.phase = 'loading'
      state.error = ''
      const started = now(),
        value = await client.undoPreview(operationId)
      if (!live(ticket)) return
      if (
        value?.operation_id !== operationId ||
        state.receipt?.operation_id !== operationId ||
        state.receipt.status !== 'confirmed' ||
        !tokenValid(value.confirmation_token) ||
        !dateValid(value.issued_study_date) ||
        !Number.isInteger(value.expires_in_seconds) ||
        value.expires_in_seconds < 1 ||
        value.expires_in_seconds > 900
      )
        throw new Error('invalid_undo')
      undo = {
        body: encoded(value),
        token: value.confirmation_token,
        until: started + value.expires_in_seconds * 1000,
        day: value.issued_study_date,
        ...ticket,
      }
      state.undo_preview = copy(value)
      state.phase = 'ready'
    } catch (e) {
      if (live(ticket)) error(e)
    } finally {
      if (flight === ticket) flight = null
    }
  }
  async function confirmUndo() {
    const ticket = begin()
    if (!ticket) return
    try {
      if (unresolved()) return
      if (
        !undo ||
        undo.identity !== ticket.identity ||
        undo.generation !== ticket.generation ||
        undo.until <= now() ||
        undo.day !== day() ||
        encoded(state.undo_preview) !== undo.body
      ) {
        invalidate()
        state.error = '撤销依据、日期已变化或预览过期，请重新读取。'
        return
      }
      const locator: CoachLocator = {
        kind: 'undo',
        request_key: crypto.randomUUID(),
        issued_study_date: undo.day,
        operation_id: state.undo_preview!.operation_id,
      }
      try {
        persist(locator)
      } catch {
        state.error = '浏览器存储无法保存请求记录，尚未发送撤销请求。'
        return
      }
      const token = undo.token
      state.phase = 'loading'
      try {
        await saved(
          await client.undoConfirm(locator.operation_id!, {
            request_key: locator.request_key,
            confirmed: true,
            confirmation_token: token,
          }),
          locator,
          ticket,
        )
      } catch (e) {
        await writeFailure(e, locator, ticket)
      }
    } catch (e) {
      if (live(ticket)) error(e)
    } finally {
      if (flight === ticket) flight = null
    }
  }
  return {
    preview,
    confirm,
    recover,
    previewUndo,
    confirmUndo,
    invalidate,
    trackRequest,
    settleRequest,
    rejectRequest,
  }
}
