import type { Milestone, ProcessingSession } from '../types'

export function sessionDates(session: ProcessingSession | null): Milestone[] {
  if (!session) return []
  const dates: Milestone[] = []
  const keys = new Set<string>()
  function append(date: string, event: string): void {
    const cleanDate = date.trim(), cleanEvent = event.trim()
    const key = JSON.stringify([cleanDate, cleanEvent])
    if (!cleanDate || !cleanEvent || keys.has(key)) return
    keys.add(key)
    dates.push({ date: cleanDate, event: cleanEvent, order: dates.length })
  }
  for (const milestone of session.milestones || []) append(String(milestone.date || ''), String(milestone.event || ''))
  const filename = session.source_path.split(/[/\\]/).pop() || ''
  if (session.entities.deadline) append(String(session.entities.deadline), String(session.entities.task_description || filename.replace(/\.[^.]*$/, '')))
  return dates
}
