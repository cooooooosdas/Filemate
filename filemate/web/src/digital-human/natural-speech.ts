import type { SpeechEvents, SpeechOptions } from './provider'
import { decodeSpeechMotion, motionLevel, type SpeechMotionTrack } from './speech-motion.ts'

export const NATURAL_VOICES = [
  { voiceURI: 'zh-CN-XiaoxiaoNeural', name: '晓晓 · 温暖女声' },
  { voiceURI: 'zh-CN-YunxiaNeural', name: '云夏 · 清朗男声' },
  { voiceURI: 'zh-CN-YunxiNeural', name: '云希 · 沉稳男声' },
  { voiceURI: 'zh-CN-XiaoyiNeural', name: '晓伊 · 轻柔女声' },
] as const

type Synthesize = (text: string, voice: string, signal: AbortSignal) => Promise<Blob>
interface AudioTask {
  abort: AbortController
  audio: HTMLAudioElement | null
  url: string | null
  timer?: number
  paused: boolean
  events: SpeechEvents
  motion?: SpeechMotionTrack | null
  motionAbort: AbortController
  motionFrame?: number
  motionDecoding: boolean
  waiting: boolean
  started: boolean
  options: SpeechOptions
}

export class MicrosoftSpeechProvider {
  readonly id = 'microsoft_edge'
  private task: AudioTask | null = null
  private readonly synthesize: Synthesize
  private motionEnabled = true

  constructor(synthesize: Synthesize) { this.synthesize = synthesize }
  available(): boolean { return typeof window !== 'undefined' && 'Audio' in window }
  voices(): typeof NATURAL_VOICES { return NATURAL_VOICES }

  updatePlayback(rate: number, volume: number): void {
    const task = this.task
    if (!task || !Number.isFinite(rate) || rate < 0.7 || rate > 1.5 ||
        !Number.isFinite(volume) || volume < 0 || volume > 1) return
    task.options.rate = rate
    task.options.volume = volume
    if (task.audio) {
      task.audio.playbackRate = rate
      task.audio.volume = volume
      if (task.started && !task.paused && !task.waiting) {
        const remaining = Number.isFinite(task.audio.duration) ? task.audio.duration - task.audio.currentTime : 600
        this.timeout(task, Math.max(30000, remaining * 1000 / rate + 30000), '音频播放超时，请重试。')
      }
    }
  }

  setMotionEnabled(enabled: boolean): void {
    this.motionEnabled = enabled
    const task = this.task
    if (!task) return
    if (!enabled) this.clearMotion(task)
    else if (task.started) this.animate(task)
  }

  private clearMotion(task: AudioTask): void {
    if (task.motionFrame !== undefined) window.cancelAnimationFrame(task.motionFrame)
    task.motionFrame = undefined
    task.events.onMotionFrame?.(0, task.audio?.currentTime || 0, false)
  }

  private animate(task: AudioTask): void {
    this.clearMotion(task)
    if (!this.motionEnabled || !task.motion || !task.audio || !task.events.onMotionFrame ||
        typeof window.requestAnimationFrame !== 'function' || task.paused || task.waiting) return
    const tick = (): void => {
      task.motionFrame = undefined
      if (this.task !== task || !this.motionEnabled || task.paused || task.waiting || !task.motion || !task.audio) return
      task.events.onMotionFrame?.(motionLevel(task.motion, task.audio.currentTime), task.audio.currentTime, true)
      task.motionFrame = window.requestAnimationFrame(tick)
    }
    task.motionFrame = window.requestAnimationFrame(tick)
  }

  private clearTimer(task: AudioTask): void {
    if (task.timer !== undefined) window.clearTimeout(task.timer)
    task.timer = undefined
  }
  private timeout(task: AudioTask, milliseconds: number, reason: string): void {
    this.clearTimer(task)
    if (!task.paused) task.timer = window.setTimeout(() => this.fail(task, reason), milliseconds)
  }
  private fail(task: AudioTask, reason: string): void {
    if (this.task !== task) return
    this.stop()
    task.events.onError(reason)
  }

  speak(text: string, options: SpeechOptions, events: SpeechEvents): void {
    this.stop()
    if (!text.trim() || Array.from(text).length > 5000 ||
        !NATURAL_VOICES.some(voice => voice.voiceURI === options.voiceId) ||
        !Number.isFinite(options.rate) || options.rate < 0.7 || options.rate > 1.5 ||
        !Number.isFinite(options.volume) || options.volume < 0 || options.volume > 1) {
      events.onError('讲解文字、声线、语速或音量无效。'); return
    }
    if (!this.available()) { events.onError('当前浏览器不支持音频播放。'); return }
    const task: AudioTask = { abort: new AbortController(), motionAbort: new AbortController(),
      audio: null, url: null, paused: false, motionDecoding: false, waiting: false, started: false,
      options: { ...options }, events }
    this.task = task
    task.events.onMotionReady?.(false)
    this.timeout(task, 65000, '自然语音准备超时，请稍后重试。')
    void this.load(task, text, task.options)
  }

  private async load(task: AudioTask, text: string, options: SpeechOptions): Promise<void> {
    try {
      const blob = await this.synthesize(text, options.voiceId, task.abort.signal)
      if (this.task !== task) return
      if (!blob.size || !blob.type.startsWith('audio/')) throw new Error('语音服务未返回可播放音频。')
      const audio = new window.Audio()
      task.audio = audio
      task.url = URL.createObjectURL(blob)
      audio.src = task.url
      audio.volume = options.volume
      audio.playbackRate = options.rate
      audio.preservesPitch = true
      audio.onloadedmetadata = () => {
        if (this.task !== task || task.motionDecoding || !task.events.onMotionFrame ||
            typeof window.requestAnimationFrame !== 'function') return
        task.motionDecoding = true
        // 后台准备动画，不等待解码，也不影响首个可听音频。
        void decodeSpeechMotion(blob, audio.duration, task.motionAbort.signal).then(track => {
          if (this.task !== task || task.motionAbort.signal.aborted) return
          task.motion = track
          task.events.onMotionReady?.(track !== null)
          if (task.started) this.animate(task)
        })
      }
      audio.onplaying = () => {
        if (this.task !== task || task.paused) return
        task.waiting = false
        task.started = true
        const remaining = Number.isFinite(audio.duration) ? (audio.duration - audio.currentTime) * 1000 : text.length * 650
        this.timeout(task, Math.max(30000, remaining / options.rate + 30000), '音频播放超时，请重试。')
        task.events.onStart()
        this.animate(task)
      }
      audio.ontimeupdate = () => {
        if (this.task === task && !task.paused && Number.isFinite(audio.duration) && audio.duration > 0) {
          task.events.onBoundary(Math.floor(audio.currentTime / audio.duration * text.length))
        }
      }
      audio.onwaiting = () => {
        if (this.task !== task) return
        task.waiting = true
        this.clearMotion(task)
        this.timeout(task, 15000, '音频加载停滞，请重试。')
      }
      audio.onerror = () => this.fail(task, '音频播放失败，请重试。')
      audio.onended = () => {
        if (this.task !== task) return
        this.stop()
        task.events.onEnd()
      }
      this.timeout(task, 15000, '音频未开始播放，请检查浏览器播放权限后重试。')
      if (!task.paused) await audio.play()
    } catch (cause) {
      if (this.task !== task) return
      this.fail(task, cause instanceof Error ? cause.message : '自然语音暂不可用，请重试。')
    }
  }
  pause(): void {
    const task = this.task
    if (!task || task.paused) return
    task.paused = true
    this.clearMotion(task)
    this.clearTimer(task)
    task.audio?.pause()
  }
  resume(): void {
    const task = this.task
    if (!task || !task.paused) return
    task.paused = false
    this.timeout(task, 15000, '音频未恢复播放，请重试。')
    if (task.audio) void task.audio.play().catch(() => this.fail(task, '浏览器未允许播放，请重新开始讲解。'))
  }
  stop(): void {
    const task = this.task
    this.task = null
    if (!task) return
    task.abort.abort()
    task.motionAbort.abort()
    this.clearMotion(task)
    task.events.onMotionReady?.(false)
    task.motion = null
    this.clearTimer(task)
    if (task.audio) {
      task.audio.onplaying = task.audio.ontimeupdate = task.audio.onended = task.audio.onerror = task.audio.onwaiting = task.audio.onloadedmetadata = null
      task.audio.pause()
      task.audio.removeAttribute('src')
      task.audio.load()
    }
    if (task.url) URL.revokeObjectURL(task.url)
  }
}
