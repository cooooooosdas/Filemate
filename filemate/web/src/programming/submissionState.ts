import type { CodingSubmission } from '../types/programming'

type SubmissionState = Pick<CodingSubmission, 'status' | 'active' | 'data_error' | 'result'>
const assessedVerdicts = new Set(['AC', 'WA', 'TLE', 'MLE', 'RE', 'CE'])

export function codingStateText(state: string): string {
  return ({ queued: '待评测', running: '评测中', completed: '已完成', cancelled: '已取消', failed: '环境异常' } as Record<string, string>)[state] || state
}

export function submissionVerdictText(record: SubmissionState): string {
  if (record.data_error) return '记录不可用'
  return record.status === 'completed' ? record.result.verdict || '数据待核对' : codingStateText(record.status)
}

export function submissionEvidenceText(record: SubmissionState): string {
  if (!record.active) return '已撤销，不计入统计'
  if (record.data_error) return '记录不可用，不计入统计'
  if (record.status === 'completed') {
    return assessedVerdicts.has(record.result.verdict || '') ? '计入练习统计' : '结果待核对，不计入统计'
  }
  return ['queued', 'running'].includes(record.status) ? '尚未计入统计' : '不计入练习统计'
}
