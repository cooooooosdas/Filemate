import type { AudioBinding } from '../types/interviewAudio'
import type { LocalVideoTake } from '../types/interviewVideo'

export const VIDEO_LIMITS = { seconds: 1800, bytes: 100 * 1024 * 1024, pageBytes: 200 * 1024 * 1024, takes: 20 }
export interface VideoCaptureState { phase: 'idle' | 'requesting' | 'recording' | 'stopping'; error: string | null; take: LocalVideoTake | null; started: number }
interface Dependencies {
  getMedia: (input: MediaStreamConstraints) => Promise<MediaStream>
  makeStream: (tracks: MediaStreamTrack[]) => MediaStream
  makeRecorder: (stream: MediaStream) => MediaRecorder
  now: () => number
}
interface Run {
  binding: AudioBinding; tracks: MediaStreamTrack[]; recorder?: MediaRecorder
  chunks: Blob[]; bytes: number; maxBytes: number; started: number; stopped?: number
  issue: string | null; partial: boolean; hasAudio: boolean
  permission?: ReturnType<typeof setTimeout>; limit?: ReturnType<typeof setTimeout>; stopTimer?: ReturnType<typeof setTimeout>
  resolves: ((take: LocalVideoTake | null) => void)[]
}
function defaultRecorder(stream: MediaStream) {
  const mimeType = ['video/webm;codecs=vp8,opus', 'video/webm', 'video/mp4'].find(type => MediaRecorder.isTypeSupported(type))
  return new MediaRecorder(stream, { ...(mimeType ? { mimeType } : {}), videoBitsPerSecond: 1000000, audioBitsPerSecond: 64000 })
}
export class VideoCapture {
  state: VideoCaptureState = { phase: 'idle', error: null, take: null, started: 0 }
  private run: Run | null = null
  private deps: Dependencies
  private changed: (state: VideoCaptureState) => void
  constructor(deps: Partial<Dependencies> = {}, changed: (state: VideoCaptureState) => void = () => {}) {
    this.changed = changed
    this.deps = { getMedia: input => navigator.mediaDevices.getUserMedia(input), makeStream: tracks => new MediaStream(tracks), makeRecorder: defaultRecorder, now: () => performance.now(), ...deps }
  }
  private publish(patch: Partial<VideoCaptureState>) { this.state = { ...this.state, ...patch }; this.changed(this.state) }
  private release(run: Run) {
    clearTimeout(run.permission); clearTimeout(run.limit); clearTimeout(run.stopTimer)
    if (run.recorder) run.recorder.ondataavailable = run.recorder.onstop = run.recorder.onerror = null
    for (const track of run.tracks) { track.onended = track.onmute = null; track.stop() }
    run.tracks = []
  }
  async start(binding: AudioBinding, preview: MediaStream, microphoneId: string | null, maxBytes = VIDEO_LIMITS.bytes): Promise<void> {
    if (this.run) return
    if (!preview.getVideoTracks().some(t => t.readyState === 'live') || maxBytes <= 0) { this.publish({ error: 'device_unavailable' }); return }
    const run: Run = { binding: { ...binding }, tracks: [], chunks: [], bytes: 0, maxBytes: Math.min(maxBytes, VIDEO_LIMITS.bytes), started: 0, issue: null, partial: false, hasAudio: false, resolves: [] }
    this.run = run; this.publish({ phase: 'requesting', error: null, take: null })
    run.permission = setTimeout(() => { if (this.run === run) { this.dispose(); this.publish({ error: 'permission_timeout' }) } }, 15000)
    try {
      if (microphoneId !== null) {
        const mic = await this.deps.getMedia({ video: false, audio: microphoneId ? { deviceId: { exact: microphoneId }, channelCount: 1 } : { channelCount: 1 } })
        if (this.run !== run) { mic.getTracks().forEach(t => t.stop()); return }
        run.tracks.push(...mic.getTracks())
        if (!mic.getAudioTracks().some(t => t.readyState === 'live')) throw new Error('microphone_unavailable')
        run.hasAudio = true
      }
      if (!preview.getVideoTracks().some(t => t.readyState === 'live')) throw new Error('camera_unavailable')
      run.tracks.push(...preview.getVideoTracks().map(t => t.clone()))
      clearTimeout(run.permission)
      const recorder = this.deps.makeRecorder(this.deps.makeStream(run.tracks)); run.recorder = recorder
      recorder.ondataavailable = event => {
        if (this.run !== run || !event.data.size) return
        if (run.bytes + event.data.size > run.maxBytes) { run.partial = true; run.issue = 'size_limit'; void this.stop(); return }
        run.chunks.push(event.data); run.bytes += event.data.size
      }
      recorder.onstop = () => this.finish(run)
      recorder.onerror = () => { if (this.run === run) void this.stop('recording_error') }
      for (const track of run.tracks) {
        track.onended = () => { if (this.run === run) void this.stop('device_disconnected') }
        track.onmute = () => { if (this.run === run) void this.stop('device_muted') }
      }
      run.started = this.deps.now(); recorder.start(500)
      this.publish({ phase: 'recording', started: run.started })
      run.limit = setTimeout(() => { if (this.run === run) { run.issue = 'duration_limit'; void this.stop() } }, VIDEO_LIMITS.seconds * 1000)
    } catch (error) {
      if (this.run !== run) return
      this.release(run); this.run = null
      this.publish({ phase: 'idle', error: (error as { name?: string }).name === 'NotAllowedError' ? 'microphone_denied' : 'capture_unavailable' })
    }
  }
  async stop(issue?: string): Promise<LocalVideoTake | null> {
    const run = this.run
    if (!run) return this.state.take
    if (this.state.phase === 'requesting') { this.dispose(); return null }
    if (issue) { run.partial = true; run.issue = issue }
    const result = new Promise<LocalVideoTake | null>(resolve => run.resolves.push(resolve))
    if (this.state.phase === 'stopping') return result
    run.stopped = this.deps.now(); this.publish({ phase: 'stopping' })
    run.stopTimer = setTimeout(() => { run.partial = true; run.issue = 'stop_timeout'; this.finish(run) }, 5000)
    try { if (run.recorder?.state === 'recording') run.recorder.stop(); else this.finish(run) }
    catch { run.partial = true; run.issue = 'recording_error'; this.finish(run) }
    return result
  }
  private finish(run: Run) {
    if (this.run !== run) return
    const blob = new Blob(run.chunks, { type: run.recorder?.mimeType || 'video/webm' })
    run.chunks = []; this.release(run); this.run = null
    const take: LocalVideoTake | null = blob.size ? { id: crypto.randomUUID(), binding: run.binding, blob, duration: Math.min(VIDEO_LIMITS.seconds, Math.max(0, ((run.stopped ?? this.deps.now()) - run.started) / 1000)), hasAudio: run.hasAudio, partial: run.partial, issue: run.issue } : null
    this.publish({ phase: 'idle', take, error: take ? run.issue : 'no_samples' })
    run.resolves.splice(0).forEach(resolve => resolve(take))
  }
  dispose() {
    const run = this.run; this.run = null
    if (run) { try { if (run.recorder?.state === 'recording') run.recorder.stop() } catch { /* 取消后不发布旧片段。 */ }; this.release(run); run.chunks = []; run.resolves.splice(0).forEach(resolve => resolve(null)) }
    this.publish({ phase: 'idle', error: null, take: null, started: 0 })
  }
}
