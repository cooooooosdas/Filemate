# 前端生产构建修复记录

> 修复日期：2026-08-16
> 涉及文件：`scripts/verify.ps1`
> 现象：`npm run build` 在 Vite/Rolldown 阶段失败，报 `index.html` 为绝对路径。

## 根因

项目实际位于 `E:\Desktop\Filemate`，但本机环境仍通过 C 盘目录联接 `C:\Users\杨乐\Desktop\Filemate` 访问。Vite/Rolldown 在通过联接路径启动时，会把 `index.html` 解析成真实绝对路径 `E:/Desktop/Filemate/filemate/web/index.html`，Rolldown 拒绝把绝对路径作为 emitted fileName，导致构建失败。

直接从 E 盘真实路径执行 `npm run build` 可以成功，证明不是代码问题。

## 修复

`scripts/verify.ps1` 在前端构建前重新从 `$PSScriptRoot` 解析真实项目路径：

- 如果项目根是 Junction，读取 `Target` 得到真实路径；
- 前端步骤从真实路径 `E:\Desktop\Filemate\filemate\web` 执行 `npm.cmd ci` 和 `npm.cmd run build`；
- 同时将 npm 调用改为 `npm.cmd`，避免 PowerShell `npm.ps1` 在当前环境下的路径歧义。

## 验证

命令：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

结果：

- Ruff：通过
- 后端测试：`314 passed, 17 skipped, 5 deselected`
- `npm ci`：成功
- `npm run build`：成功
- 完整 `scripts/verify.ps1`：退出码 0，全绿

## 遗留说明

- `npm audit` 报告 1 个 high severity 依赖漏洞，未在本轮处理，建议后续评估升级方案。
- 构建仍有大 chunk 警告（`index-Cyv7M31N.js` 约 774 kB），不阻塞构建，属于后续性能优化项。
