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
