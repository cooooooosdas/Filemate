# Microsoft 自然语音

默认导师声线为晓晓（`zh-CN-XiaoxiaoNeural`），云夏（`zh-CN-YunxiaNeural`）为首个备选；仅保留云希、晓伊两种其他自然声线。页面不再列出设备的 Huihui/Kangkang/Yaoyao 等传统声线，也不会在服务失败时自动降级到它们。头像不改变声线。

经用户勾选授权后，正文经 FileMate API 转交 Microsoft Edge 在线朗读服务；浏览器播放真实 MP3，实际 playing/ended 事件驱动人物和记录，暂停/继续使用同一段音频，停止/卸载会取消请求、释放 Blob URL。字幕与进度按音频时长估算，连续嘴部是节奏动画，不是音素对齐。正文编辑后需重新授权。服务器与浏览器不持久化音频或讲解请求正文，原 AI 对话仍按学习记录保存；仅保存可删除/导出的播报元数据。第三方留存政策不由 FileMate 控制。

接口 `POST /api/digital-human/speech`：JSON `{text, voice_id, allow_external_voice:true}`，正文1–5000字、四种白名单声线；响应 `audio/mpeg`、`Cache-Control:no-store`。无授权403，非法参数422，每空间6次/分钟或并发繁忙429，供应商失败502，关闭503。每进程并发2次、供应商总超时55秒、音频上限8MiB。独立关闭 `FILEMATE_ENABLE_NATURAL_VOICE=0`，数字人总开关同时生效；不影响资料、面试或编程。`microsoft_edge` 新元数据兼容旧 `web_speech` 记录，无 schema 变动。

适配库为锁定 `edge-tts==7.2.8`，依赖保持单独安装，未复制或改写其源码。[上游](https://github.com/rany2/edge-tts)按 LGPLv3 发布（字幕组件为 MIT）；下载源码及许可见[许可证](https://github.com/rany2/edge-tts/blob/master/LICENSE)。ZIP仅含 FileMate 源码和前端构建，不捆绑该库或虚拟环境。它是 Edge 在线服务客户端，不是具有 SLA 的 Azure 商业语音接口；长期商业保障需转接[Azure Speech 官方服务](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech)并配置凭据。[Microsoft 声线表](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support)供命名核对。

验证记录：本地与生产服务器网络均真实查询到了四种声线；晓晓/云夏各返回26064/27504字节 MP3。授权、非法参数、容量释放、故障隔离、响应不缓存等21项后端回归通过（其中供应商故障与音频使用显式合成夹具）；46项前端回归、Vue类型、构建和体积通过。真实浏览器晓晓50字完整播放、云夏500字完整播放/暂停/继续/重播/停止、连续动画与减少动态、三种屏宽、故障提示和元数据删除恢复共5项通过，页面脚本错误为0；[精简证据](audits/p1-release-2026-10-10/natural-voice-summary.json)明确区分真实语音与故障注入。最终公网验收以发布回执为准。不能据此宣称已完成人类听感、情绪概率或真实学生学习效果研究。
