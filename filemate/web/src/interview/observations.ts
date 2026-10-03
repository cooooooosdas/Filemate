import type { VisualEvent, VisualKind, VisualMetrics } from '../types/interviewReview'

export interface VisualSample { second: number; face: boolean; luminance: number; yaw: number | null; pitch: number | null; smile: number; look: number }
export const visualLabels: Record<VisualKind, string> = {
  no_face: '未检测到稳定人脸', low_light: '画面亮度偏低', head_turn: '头部朝向偏离正面',
  head_pose_change: '头部姿态变化', smile_change: '嘴角动作变化', look_direction_change: '眼部方向系数变化'
}
export class ObservationAccumulator {
  private samples = 0
  private faces = 0
  private dim = 0
  private previous?: VisualSample
  private open = new Map<VisualKind, VisualEvent>()
  private events: VisualEvent[] = []
  private lastMotion = new Map<VisualKind, number>()
  truncated = false
  dropped = 0
  add(sample: VisualSample) {
    this.samples++
    if (sample.face) this.faces++
    if (sample.luminance < 45) this.dim++
    this.interval('no_face', !sample.face, sample.second)
    this.interval('low_light', sample.luminance < 45, sample.second)
    this.interval('head_turn', sample.face && sample.luminance >= 45 && sample.yaw != null && Math.abs(sample.yaw) > 25, sample.second)
    const previous = this.previous
    if (previous?.face && previous.luminance >= 45 && sample.face && sample.luminance >= 45 && sample.second - previous.second <= 1.5) {
      if (sample.yaw != null && previous.yaw != null && sample.pitch != null && previous.pitch != null && Math.hypot(sample.yaw - previous.yaw, sample.pitch - previous.pitch) > 12) this.motion('head_pose_change', sample.second)
      if (Math.abs(sample.smile - previous.smile) > .22) this.motion('smile_change', sample.second)
      if (Math.abs(sample.look - previous.look) > .2) this.motion('look_direction_change', sample.second)
    }
    this.previous = sample
  }
  private interval(kind: VisualKind, active: boolean, second: number) {
    const event = this.open.get(kind)
    if (active) {
      if (!event) this.open.set(kind, { kind, start: second, end: second })
      else event.end = second
    } else if (event) { if (event.end - event.start >= 1) this.push(event); this.open.delete(kind) }
  }
  private motion(kind: VisualKind, second: number) {
    if (second - (this.lastMotion.get(kind) ?? -10) < 3) return
    this.lastMotion.set(kind, second)
    this.push({ kind, start: second, end: second })
  }
  private push(event: VisualEvent) { if (this.events.length < 200) this.events.push({ ...event }); else this.truncated = true }
  snapshot(duration: number, origin: 'recording' | 'visual'): VisualMetrics {
    const open = [...this.open.values()].filter(e => e.end - e.start >= 1)
    const events = [...this.events, ...open].slice(0, 200).map(e => ({ ...e, start: Math.min(e.start, duration), end: Math.min(e.end, duration) }))
    return { source: 'mediapipe_local_v1', timeline_origin: origin, duration_seconds: Math.min(1800, Math.max(0, duration)), sample_count: this.samples, face_samples: this.faces, low_light_samples: this.dim, dropped_samples: this.dropped, events, events_truncated: this.truncated || this.events.length + open.length > 200 }
  }
}
