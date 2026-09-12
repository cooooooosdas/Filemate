export type CompanionMood =
  | 'happy'
  | 'thinking'
  | 'focused'
  | 'surprised'
  | 'shy'
  | 'frustrated'
  | 'encouraging'
  | 'wink'

export interface CompanionEvent {
  mood: CompanionMood
  title: string
  message: string
  evidence: string
  route?: string
  actionLabel?: string
  occurredAt: string
}

export interface CompanionGrowth {
  points: number
  stage: string
  progress: number
  nextStage: string | null
  pointsToNext: number
  evidence: string
}

interface CompanionEvidenceTotals {
  source_count: number
  artifact_count: number
  completed_study_days: number
  mastered_wrong_count: number
  interview_count: number
}

// 学习事件可能包含任务标题或评分反馈，不能放进未绑定服务端身份的
// localStorage。模块内缓存足以支持单次工作台会话中的页面跳转，也会在
// 刷新或关闭页面后自动清除，避免匿名身份变化后显示上一位用户的内容。
let recentEvent: CompanionEvent | null = null

export function calculateCompanionGrowth(
  totals: CompanionEvidenceTotals
): CompanionGrowth {
  const points =
    Math.min(totals.source_count, 5) * 4 +
    Math.min(totals.artifact_count, 10) * 3 +
    Math.min(totals.completed_study_days, 10) * 8 +
    Math.min(totals.mastered_wrong_count, 10) * 6 +
    Math.min(totals.interview_count, 5) * 10
  const stages = [
    { name: '初识同行', start: 0, end: 40 },
    { name: '整理学徒', start: 40, end: 100 },
    { name: '复习搭档', start: 100, end: 180 },
    { name: '答辩伙伴', start: 180, end: 240 }
  ]
  const index = stages.findIndex(stage => points < stage.end)
  const currentIndex = index === -1 ? stages.length - 1 : index
  const current = stages[currentIndex]
  const next = stages[currentIndex + 1]
  const progress = next
    ? Math.round((points - current.start) / (current.end - current.start) * 100)
    : 100
  return {
    points,
    stage: current.name,
    progress: Math.max(0, Math.min(progress, 100)),
    nextStage: next?.name || null,
    pointsToNext: next ? Math.max(0, current.end - points) : 0,
    evidence: `由 ${totals.source_count} 份资料、${totals.completed_study_days} 个学习日、${totals.mastered_wrong_count} 道已掌握错题和 ${totals.interview_count} 场面试计算`
  }
}

export function publishCompanionEvent(
  event: Omit<CompanionEvent, 'occurredAt'>
): CompanionEvent {
  const value = { ...event, occurredAt: new Date().toISOString() }
  recentEvent = value
  return value
}

export function getRecentCompanionEvent(maxAgeHours = 12): CompanionEvent | null {
  if (!recentEvent) return null
  const occurredAt = new Date(recentEvent.occurredAt).getTime()
  const maxAge = maxAgeHours * 60 * 60 * 1000
  if (!Number.isFinite(occurredAt) || Date.now() - occurredAt > maxAge) {
    recentEvent = null
    return null
  }
  return recentEvent
}
