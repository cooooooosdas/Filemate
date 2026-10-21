export class FrameWatchdog {
  private key: number | null = null
  private timer?: ReturnType<typeof setTimeout>
  get pending() { return this.key !== null }
  begin(epoch: number, timeout: () => void) {
    if (this.pending) return false
    this.key = epoch
    this.timer = setTimeout(() => { this.clear(); timeout() }, 4000)
    return true
  }
  release(epoch: number) { if (this.key !== epoch) return false; this.clear(); return true }
  clear() { clearTimeout(this.timer); this.key = null }
}
export function watchMediaEnvironment(
  doc: EventTarget & { readonly visibilityState: string }, devices: EventTarget | undefined,
  actions: { hidden: () => void; devicesChanged: () => void },
) {
  const hidden = () => { if (doc.visibilityState === 'hidden') actions.hidden() }
  doc.addEventListener('visibilitychange', hidden)
  devices?.addEventListener('devicechange', actions.devicesChanged)
  return () => { doc.removeEventListener('visibilitychange', hidden); devices?.removeEventListener('devicechange', actions.devicesChanged) }
}
