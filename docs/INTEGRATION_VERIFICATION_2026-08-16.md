# FileMate 跨模块联调验证记录

> 验证日期：2026-08-16
> 基线：`main` = `049d7d6`
> 执行人：杨乐（产品、评测与跨模块联调）

## 已执行

### 1. 后端非 e2e 测试

命令：

```powershell
.venv\Scripts\python.exe -m pytest -q -m "not e2e" --no-header -p no:cacheprovider
```

结果：

- `314 passed`
- `17 skipped`
- `5 deselected`

跳过原因主要是缺少 `.docx/.pdf/.pptx` 真实样本和 PaddleOCR，属于测试资产缺口，不是代码失败。

### 2. 离线可复现评测

命令：

```powershell
$env:PYTHONPATH='.'
.venv\Scripts\python.exe evaluation/run_evaluation.py --output _working/evaluation-report-2026-08-16.json
```

结果（合成工程基线，不代表真实教学效果）：

- 检索：12 个用例，Recall@1 = 1.0，Recall@3 = 1.0，MRR = 1.0
- 面试本地降级：5 个用例，区间通过率 = 1.0

机器可读证据：`_working/evaluation-report-2026-08-16.json`

### 3. `scripts/verify.ps1` 完整门禁

命令：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

结果：

- `uv sync --extra dev`：成功
- `ruff check`：通过
- `pytest -m "not e2e"`：`314 passed, 17 skipped, 5 deselected`
- `npm ci`：成功
- `npm run build`：成功（修复见 `docs/FRONTEND_BUILD_FIX_2026-08-16.md`）
- 完整 `scripts/verify.ps1`：退出码 0，全绿

## 未执行 / 待办

- 六条核心流程的真实浏览器手动验收尚未执行。
- `npm audit` 的 1 个 high severity 依赖漏洞尚未处理。
- A1 题目主链、A2 拒答阈值、A3 数据生命周期、A4 UI 状态、A5 自动验收均未合并到 `main`，属于阻塞项。

## 结论

当前后端测试和离线评测基线可复现且为绿；主要风险不是“代码全红”，而是任务卡 A1–A5 尚未落地、API 文档有缺口、e2e 样本缺失。
