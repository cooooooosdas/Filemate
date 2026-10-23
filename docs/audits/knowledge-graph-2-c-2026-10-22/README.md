# C级工程证据

均为本地合成测试，不含真实用户数据库、密钥或资料。原始SQLite、HTTP日志和门禁日志只留`_working/kg-c-20261022/`。

- `benchmark.json`：独立100／1000／10000库的服务与真实HTTP逐次耗时、响应字节、实际返回规模、FK、DB/WAL体积、请求计数。browser未测字段仍null；实际浏览器记录另存。
- `browser-scale.json`：三次真实页面装载以及选择／缩放／重置采样；开发模式有界画布，不是总体P95。heap未测。
- `viewport-matrix.json`、五尺寸PNG：实际innerWidth、内容宽度、画布位置、横向溢出、按钮触达。1920使用`task8-1920-full.png`原尺寸完整图。
- `theme-contrast.json`：四主题可见文字采样，不能外推全站；`network-recovery.json`、offline PNG：真实停止并重启本次自建进程。
- `boundary-browser.json`：205章节／63来源分页；`mobile-return.json`与PNG：原文返回后的真实焦点。
- `task7-source-invalidated.png`：来源正文改变后拒绝旧引用；`reduced-motion-component.png`：同一组件prop开启后的静态渲染，不声称OS媒体模拟。

集成账户链、租户、故障、来源、布局与控制器行为由仓库测试验证，详见[C级交付](../../KNOWLEDGE_GRAPH_2_0_C_DELIVERY.md)。
