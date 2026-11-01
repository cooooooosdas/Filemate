import type { TodayPreferences, TodayStorage } from '../types/today.ts'

const PREFERENCES = 'filemate-today-preferences-v1:'
const PENDING = 'filemate-today-pending-v1:'
export const todayPendingKey = (identity: string): string => `${PENDING}${encodeURIComponent(identity)}`

function clean(value: unknown): TodayPreferences {
  const item = value !== null && typeof value === 'object' ? value as Record<string, unknown> : {}
  return { mode: item.mode === 'exam' || item.mode === 'project' ? item.mode : 'daily',
    last_goal_id: typeof item.last_goal_id === 'string' && item.last_goal_id.length > 0 && item.last_goal_id.length <= 128 &&
      !/[\x00-\x1f]/.test(item.last_goal_id) ? item.last_goal_id : null }
}

/** Keep display preferences separate from per-tab unresolved writes. */
export function createTodayStorage(local: TodayStorage, session: TodayStorage): TodayStorage {
  function area(key: string): TodayStorage {
    if (key.length <= 512 && key.startsWith(PENDING)) return session
    if (key.length <= 512 && key.startsWith(PREFERENCES)) return local
    throw new Error('不支持的今日行动存储项')
  }
  return { getItem: key => area(key).getItem(key), setItem: (key, value) => area(key).setItem(key, value),
    removeItem: key => area(key).removeItem(key) }
}

export function createTodayPreferences(storage: TodayStorage, identity: string) {
  const key = `${PREFERENCES}${encodeURIComponent(identity)}`
  let memory = clean(null)
  return {
    read(): TodayPreferences {
      try {
        const raw = storage.getItem(key)
        if (raw !== null) memory = raw.length <= 4096 ? clean(JSON.parse(raw)) : clean(null)
      } catch { /* Display settings remain usable when browser storage is unavailable. */ }
      return { ...memory }
    },
    write(value: TodayPreferences): void {
      memory = clean(value)
      try { storage.setItem(key, JSON.stringify(memory)) } catch { /* No write permission is needed for an in-memory theme preference. */ }
    },
    clearMemory(): void { memory = clean(null) },
  }
}
