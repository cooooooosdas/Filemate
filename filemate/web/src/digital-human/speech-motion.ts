// 音频只在本机解码分析；动画不连接、接管或重新播放声音输出。
export interface SpeechMotionTrack {
  levels: Float32Array
  step: number
}

export async function decodeSpeechMotion(blob: Blob, duration: number, signal: AbortSignal): Promise<SpeechMotionTrack | null> {
  if (signal.aborted || blob.size > 8 * 1024 * 1024 || !Number.isFinite(duration) || duration <= 0 || duration > 900 ||
      typeof window.OfflineAudioContext !== 'function') return null
  try {
    const context = new window.OfflineAudioContext(1, 1, 8000)
    const bytes = await blob.arrayBuffer()
    if (signal.aborted) return null
    const audio = await context.decodeAudioData(bytes)
    if (signal.aborted || audio.duration > 900 || audio.numberOfChannels > 2) return null
    const step = 0.025
    const width = Math.max(1, Math.round(audio.sampleRate * step))
    const levels = new Float32Array(Math.ceil(audio.length / width))
    // 只保留小型包络，不保留整段解码PCM；停顿是真实低能量区间。
    for (let channel = 0; channel < audio.numberOfChannels; channel++) {
      const samples = audio.getChannelData(channel)
      for (let bin = 0; bin < levels.length; bin++) {
        if (bin % 512 === 0) {
          if (signal.aborted) return null
          // 长讲解分批计算并把主线程交还界面，避免准备口型时卡住当前播放。
          await new Promise<void>(resolve => window.setTimeout(resolve, 0))
        }
        let energy = 0
        const end = Math.min(samples.length, (bin + 1) * width)
        for (let sample = bin * width; sample < end; sample++) energy += samples[sample]! ** 2
        levels[bin] = Math.max(levels[bin]!, Math.sqrt(energy / Math.max(1, end - bin * width)))
      }
    }
    return { levels, step }
  } catch {
    // 不支持解码或资源不足时留空动画区域，已有语音播放继续。
    return null
  }
}

export function motionLevel(track: SpeechMotionTrack, time: number): number {
  if (!Number.isFinite(time) || time < 0) return 0
  const position = time / track.step
  const index = Math.floor(position)
  const fraction = position - index
  const level = (track.levels[index] || 0) * (1 - fraction) + (track.levels[index + 1] || 0) * fraction
  return Math.min(1, Math.max(0, (level - 0.007) * 6))
}
