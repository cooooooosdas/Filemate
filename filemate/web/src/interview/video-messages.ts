const messages: Record<string, string> = {
  permission_denied: '摄像头权限未获准；可在浏览器设置中允许后重试，文字训练仍可继续。',
  microphone_denied: '麦克风权限未获准，未开始录像。可关闭“同时录制声音”后录制静音画面。',
  permission_timeout: '设备授权等待超时，已取消本次开启；请确认浏览器权限后重试。',
  device_unavailable: '所选摄像头不可用或被占用，请刷新设备列表并重新选择。',
  device_list_unavailable: '无法读取设备列表；可检查浏览器权限，或使用系统默认设备。',
  device_disconnected: '设备连接已中断；已有片段保留，请重新选择设备并主动开启。',
  device_muted: '设备暂时无法提供画面或声音，已停止本段录制。',
  capture_unavailable: '当前设备或浏览器无法开始录像，已有文字与片段保留。',
  recording_error: '录制出现异常，已保留此前收到的片段；可导出后重试。',
  size_limit: '本段达到容量上限，已停止；仅保留限额内收到的片段。',
  duration_limit: '本段达到30分钟上限，已自动停止。',
  stop_timeout: '浏览器未及时完成录像收尾，已释放设备并保留已收到的片段。',
  no_samples: '未收到可回放画面；请检查预览后重新录制。',
  page_hidden: '页面进入后台，已停止录制并关闭摄像头；返回后需主动开启。',
  context_changed: '题目或回答版本已切换，已停止旧片段；可在整场汇总中导出。',
}
export const videoIssue = (code: string | null) => code ? messages[code] || '设备暂时不可用，请重试；已有内容保留。' : ''
