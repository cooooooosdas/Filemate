import type {
  CoachContext,
  CoachInput,
  CoachLocator,
  CoachRunView,
  CoachState,
  LearningCoachClient,
} from '../types/learning-coach'
import { readHttpStatus } from './http-status.ts'

const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T
function stable(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(stable).join(',') + ']'
  if (value && typeof value === 'object')
    return (
      '{' +
      Object.keys(value)
        .sort()
        .map((key) => JSON.stringify(key) + ':' + stable((value as Record<string, unknown>)[key]))
        .join(',') +
      '}'
    )
  return JSON.stringify(value) ?? 'null'
}
function empty(): CoachState {
  return {
    phase: 'closed',
    identity: null,
    generation: 0,
    capabilities: null,
    input: null,
    context: null,
    run: null,
    draft: null,
    preview: null,
    undo_preview: null,
    receipt: null,
    pending: null,
    dirty: false,
    error: '',
  }
}
export function coachError(error: unknown): string {
  const code = readHttpStatus(error)
  return code === 401
    ? '登录已过期，请重新登录后读取原结果。'
    : code === 403
      ? '当前账号无权执行此操作，请重新登录后读取。'
      : code === 404
        ? '原记录已移除或无法访问，请关闭教练并重新选择目标与依据。'
        : code === 409
          ? '依据或安排已更新，请重新读取并预览。'
          : code === 429
            ? '当前请求受限，请稍后查询；滚动24小时额度不会在午夜清零。'
            : code === 503
              ? '学习服务暂不可用，原记录保留，请稍后重新读取。'
              : code === 413
                ? '本次内容过多，请减少所选内容后重新核对。'
                : code === 422 || code === 400
                  ? '输入未通过校验，请核对范围、日期和时长。'
                  : '连接未完成，原记录保留；请查询原结果，避免重复生成。'
}
export function acceptCoachRun(state: CoachState, view: CoachRunView) {
  if (
    !view ||
    !['ready', 'running', 'failed', 'cancelled', 'interrupted', 'stale'].includes(view.status) ||
    typeof view.work_id !== 'string'
  )
    throw new Error('invalid_response')
  state.run = copy(view)
  state.phase = view.status === 'running' ? 'running' : 'ready'
  if (view.status !== 'running') state.pending = null
  state.draft =
    view.proposal && view.status === 'ready'
      ? {
          work_id: view.work_id,
          expected_context_revision: view.context_revision,
          days: view.proposal.days.map(({ study_date, options }) => ({
            study_date,
            options: copy(options),
          })),
          new_actions: copy(view.proposal.new_actions),
          overlap_choices: [],
        }
      : null
}
export function createCoachWorkspace(
  client: LearningCoachClient,
  options: {
    identity: () => string | null
    wrap?: (state: CoachState) => CoachState
    beforeRequest?: (locator: CoachLocator) => void
    afterRequest?: (run: CoachRunView) => void
    requestFailed?: (error: unknown, locator: CoachLocator) => void
  },
) {
  const state = (options.wrap ?? ((value) => value))(empty())
  let authority: { input: string; payload: string; revision: string; digest: string } | null = null
  function reset(phase: CoachState['phase']) {
    const generation = state.generation + 1
    Object.assign(state, empty(), { phase, generation })
    authority = null
  }
  function invalidate() {
    reset('expired')
    state.error = '账号或学习范围已变化，请重新打开教练。'
  }
  function live(generation: number, identity: string | null): boolean {
    if (options.identity() !== identity) {
      invalidate()
      return false
    }
    return generation === state.generation
  }
  function fail(error: unknown) {
    if (readHttpStatus(error) === 401) invalidate()
    else state.phase = 'error'
    state.error =
      !readHttpStatus(error) && !state.pending
        ? '连接未完成，原记录保留，请恢复网络后重新读取。'
        : coachError(error)
  }
  function accept(view: CoachRunView) {
    options.afterRequest?.(view)
    acceptCoachRun(state, view)
  }
  async function readContext(input: CoachInput) {
    if (state.pending) {
      state.error = '原请求尚待核验，请先查询原结果。'
      return
    }
    const identity = options.identity()
    if (!identity) {
      invalidate()
      return
    }
    if (state.identity && state.identity !== identity) {
      invalidate()
      return
    }
    const previousRun =
      state.run && state.context && stable(state.context.input) === stable(input)
        ? copy(state.run)
        : null
    const previousDraft = previousRun && state.draft ? copy(state.draft) : null
    const generation = ++state.generation
    state.identity = identity
    state.phase = 'loading'
    state.error = ''
    state.input = copy(input)
    state.context = null
    state.run = null
    state.draft = null
    state.receipt = null
    authority = null
    state.preview = null
    state.undo_preview = null
    try {
      const context = await client.context(copy(input))
      if (!live(generation, identity)) return
      if (
        context?.input?.scope?.goal_id !== input.scope.goal_id ||
        !/^[a-f0-9]{64}$/.test(context.context_revision) ||
        !/^[a-f0-9]{64}$/.test(context.external_digest) ||
        !context.external_payload
      )
        throw new Error('invalid_response')
      state.context = copy(context)
      state.input = copy(context.input)
      state.phase = 'ready'
      if (previousRun?.context_revision === context.context_revision) {
        state.run = previousRun
        state.draft = previousDraft
      }
      authority = {
        input: stable(context.input),
        payload: stable(context.external_payload),
        revision: context.context_revision,
        digest: context.external_digest,
      }
    } catch (error) {
      if (live(generation, identity)) {
        fail(error)
      }
    }
  }
  async function open(input: CoachInput) {
    reset('loading')
    const identity = options.identity()
    const generation = state.generation
    if (!identity) {
      invalidate()
      return
    }
    state.identity = identity
    try {
      const capability = await client.capabilities()
      if (!live(generation, identity)) return
      if (
        capability?.contract_version !== 'learning-coach-v1' ||
        typeof capability.enabled !== 'boolean'
      )
        throw new Error('invalid_response')
      state.capabilities = copy(capability)
      if (!capability.enabled) {
        state.phase = 'error'
        state.error = '学习教练当前未开启，原今日安排可以继续使用。'
        return
      }
      await readContext(input)
    } catch (error) {
      if (live(generation, identity)) {
        fail(error)
      }
    }
  }
  async function submit(mode: 'rule' | 'llm') {
    if (state.phase === 'running' || state.pending) return
    const context: CoachContext | null = state.context
    if (
      !context ||
      !state.input ||
      !authority ||
      stable(state.input) !== authority.input ||
      stable(context.external_payload) !== authority.payload ||
      context.external_digest !== authority.digest ||
      context.context_revision !== authority.revision
    ) {
      state.error = '内容已调整，请先重新核对依据，再授权本次生成。'
      return
    }
    const identity = state.identity,
      generation = ++state.generation
    if (!live(generation, identity)) return
    const key = 'coach_request_' + crypto.randomUUID().replaceAll('-', '')
    const locator: CoachLocator = {
      kind: 'request',
      request_key: key,
      issued_study_date: context.snapshot.study_date,
    }
    try {
      try {
        options.beforeRequest?.(locator)
      } catch {
        state.error = '浏览器存储无法保存请求记录，尚未发送生成请求。'
        return
      }
      state.pending = locator
      state.phase = 'running'
      state.error = ''
      state.preview = null
      state.undo_preview = null
      const result = await client.request({
        input: copy(state.input),
        expected_context_revision: authority.revision,
        request_key: key,
        mode,
        allow_external_model: mode === 'llm',
        consent_digest: mode === 'llm' ? authority.digest : null,
      })
      if (live(generation, identity)) accept(result)
    } catch (error) {
      if (live(generation, identity)) {
        try {
          options.requestFailed?.(error, locator)
        } catch {
          /* The original locator is kept for explicit recovery. */
        }
        fail(error)
      }
    }
  }
  async function cancel() {
    const key = state.pending?.request_key ?? state.run?.request_key
    if (!key) return
    const identity = state.identity,
      generation = ++state.generation
    if (!live(generation, identity)) return
    try {
      const result = await client.cancel(key)
      if (live(generation, identity)) accept(result)
    } catch (error) {
      if (live(generation, identity)) {
        fail(error)
      }
    }
  }
  return { state, open, readContext, submit, cancel, close: () => reset('closed'), invalidate }
}
