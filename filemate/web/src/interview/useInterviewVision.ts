import { onBeforeUnmount, ref } from 'vue'
import type { VisualMetrics } from '../types/interviewReview'
import { ObservationAccumulator } from './observations'
import { liveFaceIndicators, type LiveFaceSample } from './liveFace'

export function useInterviewVision() {
  const state = ref<'off' | 'loading' | 'ready' | 'observing' | 'error'>('off')
  const hint = ref('视觉观察默认关闭，开启后只在本机处理画面。')
  const metrics = ref<VisualMetrics>()
  const live = ref<ReturnType<typeof liveFaceIndicators>>()
  let worker: Worker | undefined
  let timer: number | undefined
  let epoch = 0
  let workerGeneration = 0
  let busy = false
  let startTime = 0
  let origin: 'recording' | 'visual' = 'visual'
  let accumulator = new ObservationAccumulator()
  let initializationTimer: number | undefined
  let pendingInitialization: ((ready: boolean) => void) | undefined
  let captureCanvas: OffscreenCanvas | undefined
  let useCanvasCapture = false
  async function captureFrame(video: HTMLVideoElement): Promise<ImageBitmap> {
    if (!useCanvasCapture) {
      try { return await createImageBitmap(video, { resizeWidth: 640, resizeHeight: 480 }) }
      catch { useCanvasCapture = true }
    }
    // Some video frame formats cannot be copied directly to an ImageBitmap.
    captureCanvas ||= new OffscreenCanvas(640, 480)
    const context = captureCanvas.getContext('2d')
    if (!context) throw new Error('本地画面转换不可用')
    context.drawImage(video, 0, 0, 640, 480)
    return captureCanvas.transferToImageBitmap()
  }
  function reset() { pause(); epoch++; accumulator = new ObservationAccumulator(); metrics.value = undefined; live.value = undefined; startTime = 0; busy = false }
  function pause() { if (timer !== undefined) clearInterval(timer); timer = undefined; live.value = undefined; if (state.value === 'observing') state.value = 'ready' }
  function stop() {
    pause(); epoch++; workerGeneration++; worker?.terminate(); worker = undefined
    if (initializationTimer !== undefined) clearTimeout(initializationTimer)
    initializationTimer = undefined
    pendingInitialization?.(false); pendingInitialization = undefined
    state.value = 'off'
  }
  async function enable(): Promise<boolean> {
    stop()
    state.value = 'loading'
    hint.value = '正在加载本地视觉模型…'
    const current = workerGeneration
    try {
      worker = new Worker(new URL('./vision.worker.ts', import.meta.url), { type: 'module' })
      return await new Promise(resolve => {
        pendingInitialization = resolve
        const fail = (reason: string) => {
          if (current !== workerGeneration) return resolve(false)
          if (initializationTimer !== undefined) clearTimeout(initializationTimer)
          initializationTimer = undefined; pendingInitialization = undefined
          pause(); worker?.terminate(); worker = undefined; state.value = 'error'; hint.value = reason; resolve(false)
        }
        initializationTimer = window.setTimeout(() => fail('本地视觉模型加载超时，请重试；原训练功能仍可使用。'), 30000)
        worker!.onerror = () => fail('本地视觉不可用，请重试或继续文字训练。')
        worker!.onmessage = event => {
          if (current !== workerGeneration) return
          if (event.data.type === 'ready') {
            clearTimeout(initializationTimer); initializationTimer = undefined; pendingInitialization = undefined
            state.value = 'ready'; hint.value = '本地视觉已就绪，开启后实时采集动作；画面不上传。'; resolve(true)
          } else if (event.data.type === 'error') { clearTimeout(initializationTimer); fail(event.data.reason) }
          else if (event.data.type === 'sample') {
            busy = false
            if (event.data.epoch !== epoch) return
            if (state.value !== 'observing') return
            const sample: LiveFaceSample = event.data
            live.value = liveFaceIndicators(sample)
            accumulator.add(sample)
            metrics.value = accumulator.snapshot(sample.second, origin)
            hint.value = sample.luminance < 45 ? '当前视频质量较低，视觉观察可信度可能下降。' : !sample.face ? '当前未检测到稳定人脸，可检查镜头位置。' : '正在记录可观察动作，不推断心理状态。'
          }
        }
        worker!.postMessage({ type: 'init', assets: new URL(import.meta.env.BASE_URL + 'interview-vision', location.origin).href })
      })
    } catch { state.value = 'error'; hint.value = '当前浏览器不支持本地视觉分析，请继续文字或录像训练。'; return false }
  }
  function observe(video: HTMLVideoElement, recordingStart?: number) {
    if (!worker || !['ready', 'observing'].includes(state.value)) return
    pause()
    reset()
    // Worker remains valid when resetting only the collection epoch.
    startTime = recordingStart || performance.now()
    origin = recordingStart ? 'recording' : 'visual'
    const captureEpoch = epoch
    state.value = 'observing'
    timer = window.setInterval(async () => {
      if (!worker || captureEpoch !== epoch || state.value !== 'observing') return
      const second = (performance.now() - startTime) / 1000
      if (second >= 1800) { pause(); hint.value = '本轮视觉观察已达到30分钟上限。'; return }
      if (busy || video.paused || video.readyState < 2) { accumulator.dropped++; return }
      busy = true
      try {
        const bitmap = await captureFrame(video)
        if (!worker || captureEpoch !== epoch) { bitmap.close(); busy = false; return }
        worker.postMessage({ type: 'frame', bitmap, timestamp: performance.now(), second, epoch }, [bitmap])
      } catch { busy = false; pause(); state.value = 'error'; hint.value = '无法读取本地画面，已采集观察保留。' }
    }, 500)
  }
  function finish() { pause(); epoch++; busy = false; if (startTime) { metrics.value = accumulator.snapshot(Math.min(1800, (performance.now() - startTime) / 1000), origin); startTime = 0 }; return metrics.value }
  onBeforeUnmount(stop)
  return { state, hint, metrics, live, enable, observe, finish, pause, stop, reset }
}
