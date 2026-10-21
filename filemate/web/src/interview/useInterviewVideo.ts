import { computed, ref, shallowRef } from 'vue'
import { CameraPreview } from './video-devices'
import { VideoCapture } from './video-capture'
import { VideoCollection, type FrozenVideo } from './video-collection'
import type { AudioBinding } from '../types/interviewAudio'
import type { VisualMetrics } from '../types/interviewReview'
import { saveDownload } from '../services/downloads'

interface Options { blocked: () => boolean; pendingSave: () => boolean; stopOthers: () => Promise<void> | void; finishVision: () => void }
export function useInterviewVideo(options: Options) {
  const collection = new VideoCollection()
  const items = shallowRef(collection.items), error = ref(''), cameraId = ref(''), microphoneId = ref(''), withAudio = ref(false), starting = ref(false)
  let binding: AudioBinding | null = null, disposed = false, recordEpoch = 0
  const publish = () => { items.value = [...collection.items] }
  const capture = new VideoCapture({}, state => {
    if (disposed) return
    captureState.value = state
    if (state.take) { if (!collection.add(state.take)) error.value = '本页录像容量已满；请先导出并删除部分片段。'; publish() }
    if (state.phase === 'idle') options.finishVision()
  })
  const captureState = shallowRef(capture.state)
  const preview = new CameraPreview({}, state => {
    if (disposed) return
    const wasReady = camera.value.phase === 'ready'
    camera.value = state
    if (wasReady && !state.stream) { void capture.stop(state.error || undefined); options.finishVision() }
  })
  const camera = shallowRef(preview.state)
  const busy = computed(() => starting.value || captureState.value.phase !== 'idle')
  function pausePlayback() { document.querySelectorAll<HTMLMediaElement>('.interview-video-library video').forEach(el => el.pause()) }
  async function stop(issue?: string) { recordEpoch++; starting.value = false; const take = await capture.stop(issue); options.finishVision(); return take }
  function context(next: AudioBinding | null) {
    if (JSON.stringify(binding) === JSON.stringify(next)) return
    if (binding?.sessionId !== next?.sessionId) { clear() }
    else { void stop('context_changed'); pausePlayback() }
    collection.context(next); binding = next ? { ...next } : null; publish()
  }
  async function toggleCamera() {
    if (camera.value.phase !== 'off') { await stop(); preview.close(); return }
    if (!binding) return
    await preview.open(cameraId.value)
  }
  async function record() {
    if (!binding || !camera.value.stream || busy.value || options.blocked() || options.pendingSave()) return
    if (!collection.canRecord) { error.value = '本页最多20段、200MiB；请先导出并删除部分录像。'; return }
    const key = JSON.stringify(binding), epoch = ++recordEpoch; starting.value = true; error.value = ''; pausePlayback()
    try {
      await options.stopOthers()
      if (epoch !== recordEpoch || !starting.value || key !== JSON.stringify(binding) || !camera.value.stream || options.pendingSave()) return
      collection.invalidate()
      await capture.start(binding, camera.value.stream, withAudio.value ? microphoneId.value : null, collection.remainingBytes)
    } finally { if (epoch === recordEpoch) starting.value = false }
  }
  async function download(id: string) {
    const take = collection.items.find(t => t.id === id); if (!take) return
    try { await saveDownload(take.blob, `filemate-video-q${take.binding.questionIndex + 1}-${take.id}.${take.blob.type.includes('mp4') ? 'mp4' : 'webm'}`) }
    catch { error.value = '导出未完成，可重试；录像仍保留在当前页面。' }
  }
  function remove(id: string) { collection.remove(id); publish() }
  function receipt(frozen: FrozenVideo, attempt: string, session: string) { collection.receipt(frozen, attempt, session); publish() }
  function interrupted() { void stop('page_hidden'); preview.close('page_hidden'); options.finishVision(); pausePlayback() }
  function clear() { recordEpoch++; starting.value = false; capture.dispose(); preview.close(); options.finishVision(); pausePlayback(); collection.clear(); publish(); binding = null; withAudio.value = false; cameraId.value = microphoneId.value = '' }
  function dispose() { clear(); preview.dispose(); disposed = true }
  return { items, camera, captureState, cameraId, microphoneId, withAudio, busy, error, context, toggleCamera, record, stop, download, remove, receipt, interrupted, clear, dispose, pausePlayback, refresh: () => preview.refresh(), invalidate: () => collection.invalidate(), freeze: (text: string, metrics: VisualMetrics | undefined) => collection.freeze(text, metrics) }
}
