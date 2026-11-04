export const TODAY_EPOCH_KEY = 'filemate-today-epoch-v1'
const pendingPrefix = 'filemate-today-pending-v1:'

/** Keep recovery invalidation alive across routes and notify other same-origin tabs. */
export function installTodaySessionBoundary(win: Window): () => void {
  function reset(broadcast = true) {
    try {
      for (let index = win.sessionStorage.length - 1; index >= 0; index--) {
        const key = win.sessionStorage.key(index)
        if (key?.startsWith(pendingPrefix) || key?.startsWith('filemate-coach-pending-v1:')) win.sessionStorage.removeItem(key)
      }
    } catch { /* Stored write locators are also checked against the shared epoch. */ }
    if (broadcast) {
      try { win.localStorage.setItem(TODAY_EPOCH_KEY, globalThis.crypto.randomUUID()) } catch { /* Server authorization remains authoritative. */ }
    }
    win.dispatchEvent(new Event('filemate:today-invalidated'))
  }
  const local = () => reset()
  const remote = (event: StorageEvent) => {
    if (event.key === TODAY_EPOCH_KEY && (!event.storageArea || event.storageArea === win.localStorage)) reset(false)
  }
  const events = ['filemate:data-restored', 'filemate:session-expired', 'filemate:session-reset']
  for (const name of events) win.addEventListener(name, local)
  win.addEventListener('storage', remote)
  return () => { for (const name of events) win.removeEventListener(name, local); win.removeEventListener('storage', remote) }
}
