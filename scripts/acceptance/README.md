# FileMate 自动化验收脚本

本目录存放由产品/评测侧维护的可复现验收脚本，不修改 `server.py`、`storage.py`、`api.ts` 等高冲突文件。

## 目录

- `flow2_api.py`：流程 2 端到端验收（导入 → 摘要/知识卡/笔记 → 知识库 → 重启可查）。
- `flow4_api.py`：流程 4 API 闭环验收（出题→作答→错题→今日复习→掌握）。
- `a3_lifecycle.py`：A3 数据生命周期验收（创建→重启可读→删除预览→删除→外部文件不删→重复删除 404）。
- `browser_smoke.mjs`：Playwright 浏览器路由冒烟（需先启动 FastAPI 与 Vue）；任一路由/API/控制台检查失败时返回非零退出码。

## 运行方式

```powershell
# 流程 4 / A3：使用临时 SQLite，不污染真实数据
.venv\Scripts\python.exe scripts\acceptance\flow4_api.py
.venv\Scripts\python.exe scripts\acceptance\a3_lifecycle.py

# 浏览器冒烟：先启动 FastAPI 和 Vue，再安装 Playwright 后运行
cd _working\playwright-runner
npm install playwright
node <repo>\scripts\acceptance\browser_smoke.mjs
```

输出写入 `_working/`，属于临时证据，不入库。

三个脚本都以退出码作为验收结论，不能只检查是否生成 JSON 文件。
