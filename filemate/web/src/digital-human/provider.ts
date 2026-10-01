export interface SpeechOptions {
  voiceId: string
  rate: number
  volume: number
}

export interface SpeechEvents {
  onStart: () => void
  onBoundary: (characterIndex: number) => void
  onEnd: () => void
  onError: (reason: string) => void
}

export interface DigitalHumanProvider {
  readonly id: string
  available(): boolean
  voices(): SpeechSynthesisVoice[]
  speak(text: string, options: SpeechOptions, events: SpeechEvents): void
  pause(): void
  resume(): void
  stop(): void
}

export function splitSpeechText(text: string, maxLength = 140): string[] {
  if (!Number.isSafeInteger(maxLength) || maxLength < 2) {
    throw new RangeError('语音分段长度必须是至少为 2 的整数。')
  }
  const chunks: string[] = []
  let remaining = text.trim()
  while (remaining.length > maxLength) {
    const excerpt = remaining.slice(0, maxLength)
    const cuts = [...excerpt.matchAll(/[。！？；，,.!?;\s]/g)]
    const cut = cuts.at(-1)?.index
    let length = cut !== undefined && cut > maxLength / 3 ? cut + 1 : maxLength
    // 保留完整的 Unicode 字符，避免分段把生僻字拆成无效代理项。
    if (/[\uD800-\uDBFF]/.test(remaining[length - 1]) && /[\uDC00-\uDFFF]/.test(remaining[length])) length--
    chunks.push(remaining.slice(0, length))
    remaining = remaining.slice(length)
  }
  if (remaining) chunks.push(remaining)
  return chunks
}

interface SpeechTask {
  events: SpeechEvents
  utterance: SpeechSynthesisUtterance | null
  timer?: number
  deadline: number
  remaining: number
  paused: boolean
  timeoutMessage: string
}

export class BrowserSpeechProvider implements DigitalHumanProvider {
  readonly id = 'web_speech'
  private task: SpeechTask | null = null

  private clearTimer(task: SpeechTask): void {
    if (task.timer !== undefined) window.clearTimeout(task.timer)
    task.timer = undefined
  }

  private armTimer(task: SpeechTask, duration: number, reason: string): void {
    this.clearTimer(task)
    task.remaining = duration
    task.timeoutMessage = reason
    if (task.paused) return
    task.deadline = Date.now() + duration
    task.timer = window.setTimeout(() => this.fail(task, reason), duration)
  }

  private fail(task: SpeechTask, reason: string): void {
    if (this.task !== task) return
    this.stop()
    task.events.onError(reason)
  }

  available(): boolean {
    return typeof window !== 'undefined' &&
      'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window
  }

  voices(): SpeechSynthesisVoice[] {
    try { return this.available() ? window.speechSynthesis.getVoices() : [] }
    catch { return [] }
  }

  speak(text: string, options: SpeechOptions, events: SpeechEvents): void {
    this.stop()
    if (!this.available()) {
      events.onError('当前浏览器不支持语音合成，请使用最新版 Chrome 或 Edge。')
      return
    }
    const chunks = splitSpeechText(text)
    if (!chunks.length) {
      events.onError('请先输入讲解文字。')
      return
    }
    if (!Number.isFinite(options.rate) || options.rate < 0.7 || options.rate > 1.5 ||
        !Number.isFinite(options.volume) || options.volume < 0 || options.volume > 1) {
      events.onError('语速或音量无效，请调整后重试。')
      return
    }
    const task: SpeechTask = {
      events, utterance: null, deadline: 0, remaining: 0, paused: false, timeoutMessage: '',
    }
    this.task = task
    const voice = this.voices().find(item => item.voiceURI === options.voiceId)
    let chunkIndex = 0
    let offset = 0
    let started = false
    const next = (): void => {
      if (this.task !== task) return
      if (chunkIndex >= chunks.length) {
        this.clearTimer(task)
        this.task = null
        task.utterance = null
        events.onEnd()
        return
      }
      const chunk = chunks[chunkIndex]
      let utterance: SpeechSynthesisUtterance
      try { utterance = new window.SpeechSynthesisUtterance(chunk) }
      catch { this.fail(task, '语音服务启动失败，请检查浏览器语音设置后重试。'); return }
      task.utterance = utterance
      utterance.lang = voice?.lang || 'zh-CN'
      utterance.voice = voice || null
      utterance.rate = options.rate
      utterance.volume = options.volume
      utterance.onstart = () => {
        if (this.task !== task || task.utterance !== utterance) return
        this.armTimer(task, Math.max(30000, chunk.length * 600 / options.rate + 15000), '语音播放超时，请检查设备声线后重试。')
        if (!started) { started = true; events.onStart() }
        events.onBoundary(offset)
      }
      utterance.onboundary = event => {
        if (this.task === task && task.utterance === utterance && !task.paused) events.onBoundary(offset + event.charIndex)
      }
      utterance.onend = () => {
        if (this.task !== task || task.utterance !== utterance) return
        offset += chunk.length
        chunkIndex++
        next()
      }
      utterance.onerror = event => {
        if (task.utterance === utterance) {
          this.fail(task, `语音播放失败（${event.error || '未知错误'}），可以重试。`)
        }
      }
      this.armTimer(task, 15000, '语音服务未响应，请检查设备声线后重试。')
      try {
        // cancel 不会复位全局暂停状态，重播前先恢复语音队列。
        if (window.speechSynthesis.paused && !task.paused) window.speechSynthesis.resume()
        window.speechSynthesis.speak(utterance)
      } catch { this.fail(task, '语音服务启动失败，请检查浏览器语音设置后重试。') }
    }
    next()
  }

  pause(): void {
    const task = this.task
    if (!task || task.paused) return
    task.remaining = Math.max(1, task.deadline - Date.now())
    task.paused = true
    this.clearTimer(task)
    try { window.speechSynthesis.pause() }
    catch { this.fail(task, '语音暂停失败，请重试。') }
  }

  resume(): void {
    const task = this.task
    if (!task || !task.paused) return
    task.paused = false
    this.armTimer(task, task.remaining, task.timeoutMessage)
    try { window.speechSynthesis.resume() }
    catch { this.fail(task, '语音继续失败，请重试。') }
  }

  stop(): void {
    const task = this.task
    this.task = null
    if (task) { this.clearTimer(task); task.utterance = null }
    try { if (this.available()) window.speechSynthesis.cancel() }
    catch { /* 页面卸载仍须释放本地状态和定时器。 */ }
  }
}
