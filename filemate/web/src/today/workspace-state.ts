import type { DayView, OrchestratorCapabilities, OrchestratorSnapshot, ScheduleOptions, ScopeRequest } from '../types/orchestrator.ts'
import type { TodayReadPort, TodayState, TodayStorage } from '../types/today.ts'
import { todayPendingKey } from './preferences.ts'

const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T
const id = (value: unknown, limit = 128): value is string => typeof value === 'string' && value.length > 0 && value.length <= limit && !/[\x00-\x1f]/.test(value)
const status = (error: unknown): number | undefined => (error as { response?: { status?: number } } | null)?.response?.status
const calendar = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' })
const tasks = (value: unknown, limit: number): boolean => Array.isArray(value) && value.length <= limit && value.every(item =>
  item !== null && typeof item === 'object' && id(item.task_id, 512) && typeof item.status === 'string')
function date(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const parsed = Date.parse(`${value}T00:00:00Z`)
  return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === value
}
function scopeValue(value: ScopeRequest): ScopeRequest {
  if (!id(value?.goal_id) || value.course_id != null && !id(value.course_id)) throw new Error('请明确选择有效目标和课程')
  const sources = value.source_ids ?? []
  if (!Array.isArray(sources) || sources.length > 20 || sources.some(source => !id(source)) || new Set(sources).size !== sources.length) throw new Error('请明确选择最多20份不同资料')
  return { goal_id: value.goal_id, course_id: value.course_id ?? null, source_ids: [...sources].sort() }
}
function sameScope(a: ScopeRequest | null, b: ScopeRequest | null): boolean {
  return !!a && !!b && JSON.stringify(scopeValue(a)) === JSON.stringify(scopeValue(b))
}
function validDay(day: DayView): DayView {
  if (!day || !date(day.study_date) || !Number.isInteger(day.revision) || day.revision < 0 ||
    !['confirmed', 'not_confirmed', 'stale'].includes(day.status) || !tasks(day.selected, 20) ||
    !tasks(day.completed, 200) || !Array.isArray(day.stale_refs)) throw new Error('今日安排返回合同不兼容')
  if (day.scope) scopeValue(day.scope)
  return copy(day)
}
function validSnapshot(value: OrchestratorSnapshot, requested: ScopeRequest): OrchestratorSnapshot {
  if (!value?.snapshot || !value.projection || !date(value.snapshot.study_date) || !id(value.snapshot.evidence_revision) ||
    !tasks(value.projection.tasks, 200) || !tasks(value.projection.completed, 200) ||
    !value.snapshot.facts || typeof value.snapshot.facts !== 'object' || Array.isArray(value.snapshot.facts)) throw new Error('学习证据返回合同不兼容')
  const resolved = scopeValue(value.snapshot.scope)
  if (resolved.goal_id !== requested.goal_id || (resolved.course_id ?? null) !== (requested.course_id ?? null) ||
    requested.source_ids?.length && JSON.stringify(resolved.source_ids) !== JSON.stringify(requested.source_ids)) throw new Error('返回范围与所选范围不同')
  return copy(value)
}
function optionsValue(value: ScheduleOptions, snapshot: OrchestratorSnapshot): ScheduleOptions {
  if (!value || !Number.isInteger(value.available_minutes) || value.available_minutes < 0 || value.available_minutes > 1440) throw new Error('可用时长应为0到1440的整数分钟')
  const allowed = new Set(snapshot.projection.tasks.filter(task => task.status === 'pending').map(task => task.task_id))
  function ids(values: string[] | undefined, limit: number): string[] {
    const result = values ?? []
    if (!Array.isArray(result) || result.length > limit || new Set(result).size !== result.length || result.some(item => !id(item, 512) || !allowed.has(item))) throw new Error('只能调整当前候选任务，已完成任务保持只读')
    return [...result]
  }
  const order = ids(value.item_order, 200), pinned = ids(value.pinned_ids, 20), excluded = ids(value.excluded_ids, 200)
  if (pinned.some(item => !order.includes(item) || excluded.includes(item))) throw new Error('固定任务应在顺序中，且不能同时排除')
  if (value.minute_overrides != null && (typeof value.minute_overrides !== 'object' || Array.isArray(value.minute_overrides))) throw new Error('任务时长格式无效')
  const minutes = Object.entries(value.minute_overrides ?? {})
  if (minutes.length > 200 || minutes.some(([key, amount]) => !id(key, 512) || !allowed.has(key) || !Number.isInteger(amount) || amount < 1 || amount > 240)) throw new Error('候选任务时长应为1到240的整数分钟')
  return { available_minutes: value.available_minutes, item_order: order, pinned_ids: pinned, excluded_ids: excluded, minute_overrides: Object.fromEntries(minutes) }
}

/** Own only scoped reads and a local draft; all writes belong to the command controller. */
export function createTodayWorkspace(port: TodayReadPort, storage: TodayStorage, clock: () => number, wrap: (state: TodayState) => TodayState = value => value) {
  const state = wrap({ phase: 'loading', identity: null, snapshot: null, day: null, draft: null, preview: null,
    receipt: null, undo_preview: null, pending: null, write_status: 'idle', error: '', dirty: false, generation: 0 })
  let disposed = false, initialized = false
  let initialization: Promise<void> | null = null, selectedScope: ScopeRequest | null = null, knownIdentity: string | null = null
  const alive = (ticket: number): boolean => !disposed && ticket === state.generation
  const writing = (): boolean => state.write_status === 'confirming' || state.write_status === 'undoing'
  function invalidate(): void {
    state.preview = null
    state.undo_preview = null
    if (state.write_status === 'previewing' || state.write_status === 'undo_preview') state.write_status = 'idle'
  }
  function clear(phase: TodayState['phase'], removePending: boolean): void {
    if (removePending && knownIdentity) { try { storage.removeItem(todayPendingKey(knownIdentity)) } catch { /* Never reuse an in-memory authority after a reset. */ } }
    state.generation++
    state.phase = phase; state.identity = null; state.snapshot = null; state.day = null; state.draft = null
    state.preview = null; state.undo_preview = null; state.pending = null; state.receipt = null; state.write_status = 'idle'; state.error = ''; state.dirty = false
    selectedScope = null; initialized = false; initialization = null
    if (removePending) knownIdentity = null
  }
  function failure(error: unknown): void {
    if (status(error) === 401) { clear('expired', true); state.error = '登录已过期，请重新登录'; return }
    state.error = status(error) === 422 ? '请选择课程并核对资料范围，再重新读取。' : '暂时无法读取今日行动，已保存安排与输入保留，请重试。'
    state.phase = state.identity ? 'ready' : 'error'
  }
  function draftFromSnapshot(): void {
    if (!state.snapshot) return
    const data = state.snapshot, old = sameScope(state.day?.scope ?? null, data.snapshot.scope) ? state.day?.options : null
    const allowed = new Set(data.projection.tasks.filter(task => task.status === 'pending').map(task => task.task_id))
    const filter = (values: string[] | undefined) => (values ?? []).filter(item => allowed.has(item))
    const order = filter(old?.item_order)
    const candidate: ScheduleOptions = { available_minutes: old?.available_minutes ?? 0, item_order: order,
      pinned_ids: filter(old?.pinned_ids).filter(item => order.includes(item)), excluded_ids: filter(old?.excluded_ids),
      minute_overrides: Object.fromEntries(Object.entries(old?.minute_overrides ?? {}).filter(([key]) => allowed.has(key))) }
    state.draft = { scope: copy(data.snapshot.scope), expected_evidence_revision: data.snapshot.evidence_revision, options: optionsValue(candidate, data) }
  }
  function clockNotice(): void {
    const now = clock(), serverDay = state.snapshot?.snapshot.study_date ?? state.day?.study_date
    if (Number.isFinite(now) && serverDay && calendar.format(now) !== serverDay) state.error = '本机与服务器日期不同，请刷新核对；安排日期以服务器为准。'
  }
  async function selectScope(value: ScopeRequest): Promise<void> {
    if (disposed) return
    const scope = scopeValue(value)
    if (!state.identity || !initialized) { state.error = '请先重新确认当前账号'; return }
    if (writing()) { state.error = '正在保存，请等待结果或查回执后再切换'; return }
    const ticket = ++state.generation
    selectedScope = scope; state.snapshot = null; state.draft = null; state.dirty = false; state.error = ''; invalidate()
    try {
      const next = validSnapshot(await port.client.readOrchestratorSnapshot(scope), scope)
      if (!alive(ticket)) return
      state.snapshot = next; selectedScope = scopeValue(next.snapshot.scope); state.phase = 'ready'
      draftFromSnapshot(); clockNotice()
    } catch (error) { if (alive(ticket)) failure(error) }
  }
  function initialize(capabilities?: OrchestratorCapabilities): Promise<void> {
    if (disposed || initialized && (state.identity !== null || state.phase === 'legacy')) return Promise.resolve()
    if (initialization) return initialization
    if (!state.identity) { initialized = false; selectedScope = null }
    const ticket = ++state.generation
    state.phase = 'loading'; state.error = ''
    const task = (async () => {
      try {
        const caps = capabilities ?? await port.client.getOrchestratorCapabilities()
        if (!alive(ticket)) return
        if (caps?.enabled === false) { clear('legacy', false); initialized = true; return }
        if (caps?.enabled !== true || caps.ui_contract !== 'today-workspace-v1') throw new Error('incompatible_contract')
        const identity = await port.getCourseBrowserScope()
        if (!alive(ticket)) return
        if (!id(identity, 256)) { clear('error', false); state.error = '无法确认账号，请重新连接或登录'; return }
        if (knownIdentity && knownIdentity !== identity) { try { storage.removeItem(todayPendingKey(knownIdentity)) } catch { /* Other identities never reuse this locator. */ } }
        state.identity = identity; knownIdentity = identity
        const day = validDay(await port.client.getOrchestratorToday())
        if (!alive(ticket)) return
        state.day = day; state.receipt = day.latest_operation ?? null; state.phase = 'ready'; initialized = true
        if (day.status !== 'not_confirmed' && day.scope) await selectScope(day.scope)
        else clockNotice()
      } catch (error) { if (alive(ticket)) failure(error) }
    })()
    initialization = task
    void task.then(() => { if (initialization === task) initialization = null })
    return task
  }
  async function refresh(): Promise<void> {
    if (disposed) return
    if (!initialized || !state.identity) return initialize()
    if (writing()) { state.error = '正在保存，请等待结果后再刷新'; return }
    let ticket = ++state.generation
    invalidate(); state.error = ''
    try {
      const identity = await port.getCourseBrowserScope()
      if (!alive(ticket)) return
      if (!id(identity, 256)) { clear('error', false); state.error = '无法确认账号，请重新连接或登录'; return }
      if (identity !== state.identity) {
        clear('loading', true); knownIdentity = identity; state.identity = identity; initialized = true
        ticket = state.generation
      }
      const scope = selectedScope ? copy(selectedScope) : null
      const [dayResult, snapshotResult] = await Promise.allSettled([
        port.client.getOrchestratorToday().then(validDay),
        scope ? port.client.readOrchestratorSnapshot(scope).then(value => validSnapshot(value, scope)) : Promise.resolve(null),
      ])
      if (!alive(ticket)) return
      const rejected = [dayResult, snapshotResult].find(result => result.status === 'rejected')
      if ([dayResult, snapshotResult].some(result => result.status === 'rejected' && status(result.reason) === 401)) { clear('expired', true); state.error = '登录已过期，请重新登录'; return }
      if (dayResult.status === 'fulfilled') { state.day = dayResult.value; state.receipt = dayResult.value.latest_operation ?? state.receipt }
      if (snapshotResult.status === 'fulfilled' && snapshotResult.value) {
        const previous = state.snapshot?.snapshot
        state.snapshot = snapshotResult.value; selectedScope = scopeValue(snapshotResult.value.snapshot.scope)
        if (!state.dirty) draftFromSnapshot()
        else if (previous?.evidence_revision !== snapshotResult.value.snapshot.evidence_revision || previous?.study_date !== snapshotResult.value.snapshot.study_date) state.error = '学习证据已变化，草稿保留，请重新预览后确认。'
      }
      state.phase = 'ready'
      if (rejected?.status === 'rejected') failure(rejected.reason)
      if (!scope && dayResult.status === 'fulfilled' && dayResult.value.status !== 'not_confirmed' && dayResult.value.scope) await selectScope(dayResult.value.scope)
      clockNotice()
    } catch (error) { if (alive(ticket)) failure(error) }
  }
  function setOptions(options: ScheduleOptions): void {
    if (disposed || !state.identity || !state.snapshot || !state.draft || writing()) throw new Error('当前无法调整安排，请等待读取或保存完成')
    const normalized = optionsValue(options, state.snapshot)
    state.generation++; invalidate(); state.draft = { ...copy(state.draft), options: normalized }; state.dirty = true; state.error = ''
    clockNotice()
  }
  function resetIdentity(): void { if (!disposed) { clear('expired', true); state.error = '账号或资料已变化，请重新读取' } }
  function dispose(): void { if (!disposed) { clear('expired', false); disposed = true } }
  return { state, initialize, selectScope, setOptions, refresh, resetIdentity, dispose }
}
