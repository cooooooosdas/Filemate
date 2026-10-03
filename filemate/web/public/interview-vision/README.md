# 本地视觉资产

- `face_landmarker.task` 来自 Google 官方 [Face Landmarker 模型](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task)，2026-10-01 下载，固定 float16 / version 1，不在浏览器中访问远端模型地址。
- 文件大小 3,758,596 bytes；SHA256 `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`。
- 模型与使用背景见 [官方指南](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker) 与 [FaceMesh 模型卡](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf)。仅记录表面动作，不识别人、不推断心理状态。
- Web runtime 固定 `@mediapipe/tasks-vision@1.0.1`，Apache-2.0；WASM / JS由Vite插件从npm包复制到同源 `/interview-vision/wasm/`，按需加载。保留原运行时版权头。完整代码许可见 [MediaPipe LICENSE](https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE)。
- 每500ms最多向本地Worker发送一帧，忙时丢弃下一帧；帧处理后释放，仅汇总计数与有限事件。像素、人脸点、变换矩阵、系数均不写入数据库或外发。
- 运行关闭模块或从页面离开会终止Worker；模型加载失败保留原有文字、语音和本地录像流程。
