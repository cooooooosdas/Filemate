export function routeViewKey(path: string, fullPath: string, revision: number): string {
  const stableQuery = ['/ai-tools', '/import', '/interview'].includes(path)
  return `${stableQuery ? path : fullPath}-${revision}`
}

export interface InterviewDraftState {
  answer: string
  recording: boolean
  videoStarting: boolean
  videoRecording: boolean
  videoStopping: boolean
  localRecordings: number
  preparation: boolean
}

export function hasInterviewDraft(state: InterviewDraftState): boolean {
  return !!state.answer.trim() || state.recording || state.videoStarting || state.videoRecording
    || state.videoStopping || state.localRecordings > 0 || state.preparation
}

export function todayItemTarget(item: { kind: string; plan_id?: string; route: string }): string {
  if (item.kind === 'plan_day' && item.plan_id) return `/study-plan?plan=${encodeURIComponent(item.plan_id)}`
  return item.route
}
