import type { VisualSample } from './observations'

export interface LiveFaceSample extends VisualSample { brow?: number; jaw?: number }
export function liveFaceIndicators(sample: LiveFaceSample) {
  const reliable = sample.face && Number.isFinite(sample.luminance) && sample.luminance >= 45
  const strength = (value: number | undefined) => reliable && Number.isFinite(value)
    ? Math.round(Math.max(0, Math.min(1, value!)) * 100) : null
  return {
    status: !sample.face ? '未检测到人脸' : !reliable ? '光线不足，暂停动作读数' : '已检测到人脸',
    smile: strength(sample.smile), brow: strength(sample.brow), jaw: strength(sample.jaw),
    yaw: reliable && Number.isFinite(sample.yaw) ? Math.round(sample.yaw!) : null,
    pitch: reliable && Number.isFinite(sample.pitch) ? Math.round(sample.pitch!) : null,
  }
}
