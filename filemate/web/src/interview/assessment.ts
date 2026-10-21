import type { AssessmentCommand, AssessmentContext, AssessmentRecord } from '../types/interviewAssessment'

export function scoreLabel(value: number | null): string {
  return value == null ? '待评测' : Number(value.toFixed(1)).toString()
}

export function radarGeometry(dimensions: { score: number | null }[]) {
  const axes = Array.from({ length: 6 }, (_, i) => {
    const angle = Math.PI * (i / 3 - 0.5)
    return { x: 130 + Math.cos(angle) * 94, y: 130 + Math.sin(angle) * 94 }
  })
  const points = dimensions.flatMap((dim, index) => {
    const axis = axes[index]
    return dim.score == null || !axis ? [] : [{ index, x: 130 + (axis.x - 130) * dim.score / 100, y: 130 + (axis.y - 130) * dim.score / 100 }]
  })
  return { axes, points, polygon: points.length === 6 ? points.map(p => `${p.x},${p.y}`).join(' ') : '' }
}

export function assessmentFailure(code: string | null): string {
  const labels: Record<string, string> = {
    invalid_evidence: '模型结果未通过结构或证据核验；旧报告保留，可主动重试。',
    timeout: '模型分析超时；旧报告保留，可主动重试。',
    configuration: '模型尚未配置，请在设置中测试连接。',
    access_denied: '模型拒绝访问，请检查设置中的密钥和余额。',
    rate_limit: '模型暂时限流，请稍后重试。',
    budget_exceeded: '当前学习空间模型额度已用尽，已有报告仍可使用。',
    superseded: '回答、任务或权限已改变，本次重算未发布，请刷新后重试。',
    restored: '此分析来自备份中的中断任务，恢复后不会自动调用模型。',
    cancelled: '本次分析已取消，既有报告仍保留。',
  }
  return labels[code || ''] || '本次分析未完成；原回答和旧报告保留，请检查模型连接后主动重试。'
}

interface FlowApi {
  context(id: string): Promise<AssessmentContext>
  read(id: string, key: string): Promise<AssessmentRecord>
  create(id: string, command: AssessmentCommand): Promise<AssessmentRecord>
  cancel?(id: string): Promise<unknown>
}
export interface AssessmentFlowState {
  sessionId: string; context: AssessmentContext | null; selected: AssessmentRecord | null
  loading: boolean; busy: boolean; error: string; cancelling?: boolean
}

export function createAssessmentFlow(api: FlowApi, changed: (state: AssessmentFlowState) => void = () => {}, wait: (ms: number) => Promise<void> = ms => new Promise(resolve => setTimeout(resolve, ms))) {
  const state: AssessmentFlowState = { sessionId: '', context: null, selected: null, loading: false, busy: false, error: '' }
  let epoch = 0, disposed = false, pending: AssessmentCommand | null = null
  const publish = () => { if (!disposed) changed({ ...state }) }
  const valid = (version: number) => !disposed && version === epoch
  const message = (error: unknown) => error instanceof Error ? error.message : '连接未完成，请重试。'

  function reset() {
    epoch++; pending = null
    state.context = null; state.selected = null; state.loading = false; state.busy = false; state.cancelling = false; state.error = ''; publish()
  }

  async function load(id: string) {
    if (disposed) return
    const version = ++epoch
    if (id !== state.sessionId) { state.context = null; state.selected = null; pending = null }
    state.sessionId = id; state.loading = true; state.busy = false; state.cancelling = false; state.error = ''; publish()
    try {
      const context = await api.context(id)
      if (!valid(version)) return
      if (context.input_digest !== state.context?.input_digest) pending = null
      state.context = context
      const latest = context.history.find(item => item.status === 'succeeded')
      if (latest) {
        const selected = await api.read(latest.interview_id, latest.assessment_id)
        if (!valid(version)) return
        state.selected = selected
      } else state.selected = null
      const failed = context.history[0]
      if (failed && ['failed', 'interrupted', 'cancelled'].includes(failed.status)) state.error = assessmentFailure(failed.error_code)
    } catch (error) { if (valid(version)) state.error = message(error) }
    finally { if (valid(version)) { state.loading = false; publish() } }
  }

  async function generate(mode: 'local' | 'model', consent: boolean) {
    const context = state.context
    if (disposed || state.busy || state.loading || !context?.enabled || !context.answered) return
    if (mode === 'model' && !consent) { state.error = '请先确认本次问题与回答的外发授权。'; publish(); return }
    const version = ++epoch, id = state.sessionId
    if (!pending || pending.mode !== mode || pending.expected_digest !== context.input_digest) {
      pending = { request_key: crypto.randomUUID().replaceAll('-', ''), expected_digest: context.input_digest, mode, external_consent: mode === 'model' }
    }
    state.busy = true; state.error = ''; publish()
    try {
      const record = await api.create(id, pending)
      if (!valid(version)) return
      pending = null
      if (record.report) state.selected = record
      else state.error = assessmentFailure(record.error_code)
      const refreshed = await api.context(id)
      if (valid(version)) state.context = refreshed
      return record
    } catch (error) { if (valid(version)) state.error = message(error) }
    finally { if (valid(version)) { state.busy = false; publish() } }
  }

  async function select(id: string, assessmentId: string) {
    if (disposed || state.busy) return
    const version = ++epoch
    state.loading = true; state.error = ''; publish()
    try {
      const record = await api.read(id, assessmentId)
      if (valid(version)) {
        if (record.report) state.selected = record
        else state.error = assessmentFailure(record.error_code)
      }
    } catch (error) { if (valid(version)) state.error = message(error) }
    finally { if (valid(version)) { state.loading = false; publish() } }
  }

  async function cancel() {
    if (disposed || state.cancelling || !api.cancel) return
    const version = ++epoch, id = state.sessionId, deadline = Date.now() + 65000
    state.busy = true; state.cancelling = true; state.error = ''; publish()
    try {
      await api.cancel(id)
      if (!valid(version)) return
      pending = null
      for (let poll = 0; poll < 66 && Date.now() < deadline; poll++) {
        const context = await api.context(id)
        if (!valid(version)) return
        state.context = context; publish()
        if (!context.history.some(item => ['running', 'cancelling'].includes(item.status))) {
          state.error = assessmentFailure(context.history[0]?.error_code || 'cancelled')
          return
        }
        await wait(1000)
      }
      if (valid(version)) state.error = '取消仍在处理，请刷新记录确认终态；旧报告保留。'
    } catch (error) { if (valid(version)) state.error = message(error) }
    finally { if (valid(version)) { state.busy = false; state.cancelling = false; publish() } }
  }
  return { state, load, generate, select, reset, cancel, dispose() { disposed = true; epoch++; pending = null } }
}
