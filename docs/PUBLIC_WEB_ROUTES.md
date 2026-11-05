# 公开网页与 API 路由

前端静态路径以 `filemate/web/src/router/index.ts` 为源。增加或删除路径后执行：

```powershell
node scripts/sync-public-routes.mjs
node scripts/sync-public-routes.mjs --check
```

工具更新 Nginx 与 Caddy 中标记的白名单，不包含前端 catch-all。动态路由需要单独审核网关匹配规则。已知网页返回 SPA 或对应预渲染 HTML；未知网页保留原地址并返回 HTTP 404，由前端呈现“页面不存在”。缺失静态文件亦为 404，不返回成功状态的脚本内容。

`/api/` 始终代理 API，包括 Accept 为 text/html 的请求。`/knowledge`、`/wrongbook`、`/interview`、`/goals`、`/trust` 等重名路径沿用 Accept 分流；JSON 请求保留后端合同。`/knowledge-graph` 是网页，不匹配 `/knowledge` API 前缀。API 的 JSON 404 不经过网页错误模板。两种网关的错误页均保留安全响应头。

爬虫文件仅列出首页、登录、注册和可信与隐私页，不公开学习资料地址。`robots.txt` 是 text/plain，`sitemap.xml` 是 application/xml。部署仍须验证域名、证书、上游和文件路径。

真实回环网关回归（传入自有合成 API；输出目录必须不存在）：

```powershell
.venv/Scripts/python.exe scripts/acceptance/public_routes.py --caddy PATH_TO_CADDY --dist filemate/web/dist --api http://127.0.0.1:7729 --out _working/NEW_ROUTE_CHECK
```

2026-11-05：15项 HTTP 合同通过；真实 Edge 验证404标题、原地址及返回首页。生产 openresty/1.19.9.1 仅在新 `/tmp` 配置执行 nginx -t 通过，未重载线上服务。完整发布与回滚见最终交付回执。

## 2026-11-05 公开页面构建与压缩

`npm run build` 生成 `/`、`/login`、`/register`、`/trust` 的匿名初始界面、H1和首段，以及每页OG/Twitter/canonical和Organization/WebSite信息。构建使用全新浏览器上下文和仅监听回环的临时静态服务，阻断全部API及第三方请求，不连接任何用户数据库。缺少浏览器时明确告警并保留SPA；正式发布须检查 `dist/prerender-report.json` 四页均为true。

Windows使用本机Edge；Linux/容器构建先执行 `npx playwright-core install --with-deps chromium`。浏览器仅为开发依赖，不进入后端运行时。预渲染样式链接统一为站内路径；运行时等当前路由加载完再接管，不把临时端口写入HTML。首帧主题脚本由主题目录生成，跟随系统和四种手动主题同步theme-color。

构建为文本资源生成 `.br` 和 `.gz`。Caddy使用原生 `file_server precompressed br gzip`。现役OpenResty没有Brotli模块，但已有headers-more模块：示例Nginx配置按Accept-Encoding读取静态Brotli，保留原MIME、安全头和Vary，不重新压缩Brotli；br;q=0回退gzip。其他Nginx发行版先确认headers-more能力，禁止未经nginx -t直接使用此配置。隔离临时监听的15组真实HTTP验证已通过，未替换生产监听。

分享图由现有品牌素材合成，1200×630、63050字节，不使用虚构统计。实际微信/QQ客户端卡片展示仍待客户端验证，meta及HTTP验证不能代替该项。
