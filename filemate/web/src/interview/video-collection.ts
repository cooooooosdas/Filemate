import { VIDEO_LIMITS } from './video-capture.ts'
import type { AudioBinding } from '../types/interviewAudio'
import type { LocalVideoTake, VideoItem } from '../types/interviewVideo'
import type { VisualMetrics } from '../types/interviewReview'

export interface FrozenVideo { text: string; sessionId: string; questionIndex: number; takeId: string | null; metrics: VisualMetrics | undefined }
const same = (a: AudioBinding | null, b: AudioBinding) => JSON.stringify(a) === JSON.stringify(b)
export class VideoCollection {
  items: VideoItem[] = []
  private binding: AudioBinding | null = null
  private frozen: FrozenVideo | null = null
  private urls: { create: (blob: Blob) => string; revoke: (url: string) => void }
  constructor(urls = { create: (blob: Blob) => URL.createObjectURL(blob), revoke: (url: string) => URL.revokeObjectURL(url) }) { this.urls = urls }
  get remainingBytes() { return Math.max(0, VIDEO_LIMITS.pageBytes - this.items.reduce((n, t) => n + t.blob.size, 0)) }
  get canRecord() { return this.items.length < VIDEO_LIMITS.takes && this.remainingBytes > 0 }
  context(binding: AudioBinding | null) {
    if (this.binding?.sessionId !== binding?.sessionId) this.clear()
    else if (this.binding?.questionIndex !== binding?.questionIndex) this.invalidate()
    this.binding = binding ? { ...binding } : null
  }
  add(take: LocalVideoTake) {
    if (this.items.some(t => t.id === take.id)) return true
    if (!take.blob.size || take.blob.size > VIDEO_LIMITS.bytes || take.binding.sessionId !== this.binding?.sessionId || !this.canRecord || take.blob.size > this.remainingBytes) return false
    this.items = [...this.items, { ...take, url: this.urls.create(take.blob), attemptId: null }]; return true
  }
  invalidate() { this.frozen = null }
  freeze(text: string, metrics: VisualMetrics | undefined): FrozenVideo {
    if (this.frozen?.text === text && this.frozen.sessionId === this.binding?.sessionId && this.frozen.questionIndex === this.binding.questionIndex) return this.frozen
    const take = [...this.items].reverse().find(t => !t.attemptId && same(this.binding, t.binding))
    this.frozen = { text, sessionId: this.binding?.sessionId ?? '', questionIndex: this.binding?.questionIndex ?? -1, takeId: take?.id ?? null, metrics: metrics ? { ...metrics, events: metrics.events.map(event => ({ ...event })) } : undefined }; return this.frozen
  }
  receipt(frozen: FrozenVideo, attemptId: string, sessionId: string) {
    if (this.frozen !== frozen || frozen.sessionId !== sessionId || sessionId !== this.binding?.sessionId || frozen.questionIndex !== this.binding.questionIndex) return false
    this.items = this.items.map(t => t.id === frozen.takeId ? { ...t, attemptId } : t); this.invalidate(); return true
  }
  remove(id: string) { this.items = this.items.filter(t => { if (t.id !== id) return true; this.urls.revoke(t.url); return false }) }
  clear() { for (const take of this.items) this.urls.revoke(take.url); this.items = []; this.invalidate() }
}
