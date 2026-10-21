interface DeviceDependencies {
  getMedia: (input: MediaStreamConstraints) => Promise<MediaStream>
  enumerate: () => Promise<MediaDeviceInfo[]>
}
export interface CameraState {
  phase: 'off' | 'requesting' | 'ready'
  stream: MediaStream | null
  devices: MediaDeviceInfo[]
  error: string | null
}
export class CameraPreview {
  state: CameraState = { phase: 'off', stream: null, devices: [], error: null }
  private epoch = 0
  private listing = 0
  private timer?: ReturnType<typeof setTimeout>
  private deps: DeviceDependencies
  private changed: (state: CameraState) => void
  constructor(deps: Partial<DeviceDependencies> = {}, changed: (state: CameraState) => void = () => {}) {
    this.changed = changed
    this.deps = { getMedia: input => navigator.mediaDevices.getUserMedia(input), enumerate: () => navigator.mediaDevices.enumerateDevices(), ...deps }
  }
  private publish(patch: Partial<CameraState>) { this.state = { ...this.state, ...patch }; this.changed(this.state) }
  async refresh() {
    const listing = ++this.listing
    try {
      const devices = (await this.deps.enumerate()).filter(d => ['videoinput', 'audioinput'].includes(d.kind))
      if (listing !== this.listing) return
      this.publish({ devices })
      const active = this.state.stream?.getVideoTracks()[0]?.getSettings().deviceId
      if (active && !devices.some(d => d.kind === 'videoinput' && d.deviceId === active)) this.close('device_disconnected')
    } catch { if (listing === this.listing) this.publish({ error: 'device_list_unavailable' }) }
  }
  async open(deviceId = ''): Promise<boolean> {
    if (this.state.phase === 'requesting') return false
    this.close()
    const epoch = this.epoch
    this.publish({ phase: 'requesting', error: null })
    this.timer = setTimeout(() => { if (epoch === this.epoch) this.close('permission_timeout') }, 15000)
    try {
      const acquired = await this.deps.getMedia({ audio: false, video: { ...(deviceId ? { deviceId: { exact: deviceId } } : { facingMode: 'user' }), width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 15, max: 24 } } })
      if (epoch !== this.epoch) { acquired.getTracks().forEach(t => t.stop()); return false }
      clearTimeout(this.timer)
      if (!acquired.getVideoTracks().some(t => t.readyState === 'live')) { acquired.getTracks().forEach(t => t.stop()); this.close('device_unavailable'); return false }
      for (const track of acquired.getTracks()) track.onended = () => { if (epoch === this.epoch) this.close('device_disconnected') }
      this.publish({ phase: 'ready', stream: acquired })
      void this.refresh()
      return true
    } catch (error) {
      if (epoch === this.epoch) this.close((error as { name?: string }).name === 'NotAllowedError' ? 'permission_denied' : 'device_unavailable')
      return false
    }
  }
  close(error: string | null = null) {
    this.epoch++; clearTimeout(this.timer)
    for (const track of this.state.stream?.getTracks() ?? []) { track.onended = null; track.stop() }
    this.publish({ phase: 'off', stream: null, error })
  }
  dispose() { this.listing++; this.close() }
}
