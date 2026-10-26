import type { ReviewFilter, ReviewRef } from '../types/wrongbook.ts'
import type { ReviewStorage } from './submission.ts'
import { validScope } from './submission.ts'
import { reviewCauses } from './presentation.ts'

export type ReviewBrowse = { filters: ReviewFilter; focus: string; offset: number; mode: 'browse' | 'focus'; notice: string }
export type ReviewBatch = { created_at: string; position: number; items: (ReviewRef & { attempt_id?: string; request_key?: string })[] }
const statuses = ['all', 'due', 'overdue', 'active', 'pending', 'criterion_met', 'legacy_completed', 'paused', 'history', 'invalid']
const allowed = ['focus', 'q', 'status', 'source_id', 'course_id', 'knowledge_q', 'cause', 'min_errors', 'max_errors', 'due_from', 'due_to', 'created_from', 'created_to', 'sort', 'direction', 'offset', 'mode']
const id = (v: unknown): v is string => typeof v === 'string' && v.length > 0 && v.length <= 128 && !/[\u0000-\u001f]/.test(v)
export function readReviewBrowse(query: Record<string, unknown>): ReviewBrowse {
  let invalid = Object.keys(query).some(k => !allowed.includes(k))
  const scalar = (key: string, max = 128) => { const v = query[key]; if (v == null || v === '') return ''; if (typeof v !== 'string' || v.length > max || /[\u0000-\u001f]/.test(v)) { invalid = true; return '' }; return v }
  const filters: ReviewFilter = { status: 'all', sort: 'due', direction: 'asc' }
  for (const key of ['q', 'source_id', 'course_id', 'knowledge_q'] as const) { const v = scalar(key, key === 'q' ? 160 : key === 'knowledge_q' ? 120 : 128); if (v) filters[key] = v }
  const choices = { status: statuses, sort: ['due', 'updated', 'errors', 'created'], direction: ['asc', 'desc'], cause: ['unconfirmed', ...reviewCauses.map(c => c.value)] }
  for (const [key, values] of Object.entries(choices)) {
    if (query[key] != null) { const v = scalar(key); if (values.includes(v)) Object.assign(filters, { [key]: v }); else invalid = true }
  }
  for (const key of ['min_errors', 'max_errors'] as const) {
    if (query[key] != null) { const v = scalar(key); if (/^\d{1,7}$/.test(v) && Number(v) <= 1000000) filters[key] = Number(v); else invalid = true }
  }
  if (filters.min_errors != null && filters.max_errors != null && filters.min_errors > filters.max_errors) { delete filters.min_errors; delete filters.max_errors; invalid = true }
  for (const prefix of ['due', 'created']) {
    for (const suffix of ['from', 'to']) { const key = `${prefix}_${suffix}` as 'due_from'; if (query[key] == null) continue; const v = scalar(key, 64); if (/T.*(?:Z|[+-]\d\d:\d\d)$/.test(v) && Number.isFinite(Date.parse(v))) filters[key] = v; else invalid = true }
    const low = filters[`${prefix}_from` as 'due_from'], high = filters[`${prefix}_to` as 'due_to']
    if (low && high && Date.parse(low) > Date.parse(high)) { delete filters[`${prefix}_from` as 'due_from']; delete filters[`${prefix}_to` as 'due_to']; invalid = true }
  }
  const focus = scalar('focus'), offsetText = scalar('offset'), mode = scalar('mode')
  let offset = 0
  if (offsetText) { if (/^\d{1,7}$/.test(offsetText) && Number(offsetText) <= 1000000) offset = Number(offsetText); else invalid = true }
  if (mode && !['browse', 'focus'].includes(mode)) invalid = true
  return { filters, focus, offset, mode: mode === 'focus' ? 'focus' : 'browse', notice: invalid ? '部分浏览条件无效，已忽略；回答不会保存在网址中。' : '' }
}
export function reviewBrowseQuery(state: ReviewBrowse): Record<string, string> {
  const query: Record<string, string> = {}
  for (const [key, value] of Object.entries(state.filters)) if (allowed.includes(key) && value != null && value !== '') query[key] = String(value)
  if (id(state.focus)) query.focus = state.focus
  if (state.offset) query.offset = String(state.offset)
  if (state.mode === 'focus') query.mode = 'focus'
  return query
}
export function createReviewPreferences(storage: ReviewStorage, scope: string | null) {
  const key = validScope(scope) ? `filemate-review-workspace-v1:${scope}` : null
  let browse: { browse: ReviewBrowse; scroll: number } | null = null, batch: ReviewBatch | null = null
  const sanitizeBatch = (value: unknown): ReviewBatch | null => {
    if (!value || typeof value !== 'object') return null
    const b = value as ReviewBatch
    if (!Array.isArray(b.items) || b.items.length > 20 || !b.items.length || !Number.isInteger(b.position) || b.position < 0 || b.position >= b.items.length || typeof b.created_at !== 'string' || b.created_at.length > 64 || !Number.isFinite(Date.parse(b.created_at))) return null
    const items: ReviewBatch['items'] = []
    for (const r of b.items) {
      if (!r || !id(r.wrong_id) || !id(r.artifact_id) || !Number.isInteger(r.question_index) || r.question_index < 0 || r.question_index > 100000 || typeof r.question_digest !== 'string' || !/^[a-f0-9]{64}$/.test(r.question_digest)) return null
      const clean: ReviewBatch['items'][number] = { wrong_id: r.wrong_id, artifact_id: r.artifact_id, question_index: r.question_index, question_digest: r.question_digest }
      if (id(r.attempt_id)) clean.attempt_id = r.attempt_id
      if (typeof r.request_key === 'string' && /^[A-Za-z0-9_-]{16,80}$/.test(r.request_key)) clean.request_key = r.request_key
      items.push(clean)
    }
    if (new Set(items.map(i => i.wrong_id)).size !== items.length) return null
    return { created_at: b.created_at, position: b.position, items }
  }
  try {
    const saved = JSON.parse(key ? storage.getItem(key) || '{}' : '{}')
    batch = sanitizeBatch(saved.batch)
    if (saved.browse && typeof saved.browse.query === 'object') browse = { browse: readReviewBrowse(saved.browse.query), scroll: Math.max(0, Math.min(1000000, Number(saved.browse.scroll) || 0)) }
  } catch { /* 使用当前页状态。 */ }
  const persist = () => { try { if (key) storage.setItem(key, JSON.stringify({ browse: browse ? { query: reviewBrowseQuery(browse.browse), scroll: browse.scroll } : null, batch })) } catch { /* 使用当前页状态。 */ } }
  return {
    getBrowse: () => browse ? structuredClone(browse) : null,
    setBrowse(value: ReviewBrowse, scroll = 0) { browse = { browse: readReviewBrowse(reviewBrowseQuery(value)), scroll: Math.max(0, Math.min(1000000, scroll)) }; persist() },
    getBatch: () => batch ? structuredClone(batch) : null,
    saveBatch(value: ReviewBatch) { const safe = sanitizeBatch(value); if (!safe) return false; batch = safe; persist(); return true },
    clearBatch() { batch = null; persist() }, clearMemory() { batch = null; browse = null },
  }
}
