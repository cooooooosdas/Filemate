import { FaceLandmarker, FilesetResolver } from '@mediapipe/tasks-vision'

let landmarker: FaceLandmarker | undefined
const canvas = new OffscreenCanvas(64, 48)
const context = canvas.getContext('2d', { willReadFrequently: true })!
self.onmessage = async (event: MessageEvent) => {
  const message = event.data
  if (message.type === 'init') {
    try {
      const files = await FilesetResolver.forVisionTasks(message.assets + '/wasm', true)
      landmarker = await FaceLandmarker.createFromOptions(files, {
        baseOptions: { modelAssetPath: message.assets + '/face_landmarker.task', delegate: 'CPU' },
        runningMode: 'VIDEO', numFaces: 1, minFaceDetectionConfidence: .6,
        minFacePresenceConfidence: .6, minTrackingConfidence: .6,
        outputFaceBlendshapes: true, outputFacialTransformationMatrixes: true
      })
      self.postMessage({ type: 'ready' })
    } catch { self.postMessage({ type: 'error', reason: '本地视觉模型加载失败，可重试；文字与录像仍可使用。' }) }
    return
  }
  if (message.type === 'frame' && landmarker) {
    const bitmap: ImageBitmap = message.bitmap
    try {
      context.drawImage(bitmap, 0, 0, 64, 48)
      const pixels = context.getImageData(0, 0, 64, 48).data
      let luminance = 0
      for (let i = 0; i < pixels.length; i += 4) luminance += .2126 * pixels[i]! + .7152 * pixels[i + 1]! + .0722 * pixels[i + 2]!
      const result = landmarker.detectForVideo(bitmap, message.timestamp)
      const landmarks = result.faceLandmarks[0]
      const categories = result.faceBlendshapes[0]?.categories || []
      const coefficient = (name: string) => categories.find(c => c.categoryName === name)?.score || 0
      const matrix = result.facialTransformationMatrixes[0]?.data
      const yaw = matrix ? Math.atan2(matrix[8]!, matrix[10]!) * 180 / Math.PI : null
      const pitch = matrix ? Math.atan2(-matrix[9]!, Math.hypot(matrix[8]!, matrix[10]!)) * 180 / Math.PI : null
      self.postMessage({ type: 'sample', epoch: message.epoch, second: message.second,
        face: Boolean(landmarks), luminance: luminance / (64 * 48), yaw, pitch,
        smile: (coefficient('mouthSmileLeft') + coefficient('mouthSmileRight')) / 2,
        brow: (coefficient('browDownLeft') + coefficient('browDownRight')) / 2,
        jaw: coefficient('jawOpen'),
        look: (coefficient('eyeLookOutLeft') + coefficient('eyeLookInRight') - coefficient('eyeLookInLeft') - coefficient('eyeLookOutRight')) / 2 })
    } catch { self.postMessage({ type: 'error', reason: '视觉采样中断；已采集观察仍保留，可重新开启。' }) }
    finally { bitmap.close() }
  }
}
