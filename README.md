# MaterialAI Workbench QA

这是 MaterialAI Workbench 的独立黑盒测试仓库。它不导入产品源码，只通过发布 ZIP、EXE、HTTP 页面、Socket 协议、JSON Schema 和生成工件判断产品是否可发布。产品白盒单元测试不能替代这里的用户视角门禁。

## 测试边界

- `portable-offline`：无 Python、无 Abaqus、无网络的 Windows 便携包核心能力。
- `source-mock`：产品 CLI 与 Fake MCP 的协议和故障恢复。
- `portable-abaqus`：Windows 便携包连接 Abaqus 2023 的真实闭环。
- `source-llm`：外部 LLM 适配器合同，不允许绕过任务 Schema 直接执行任意命令。

## 本地开始

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test,ui]"
$env:MATERIALAI_QA_PRODUCT_ROOT = "D:\githubproject\pyLabFEA"
.\.venv\Scripts\python.exe -m pytest -m "not ui and not abaqus_real"
```

执行完整发布包门禁：

```powershell
.\.venv\Scripts\materialai-qa.exe gate `
  --product-root D:\githubproject\pyLabFEA `
  --expected-version 0.3.0.dev0
```

报告写入 `reports/`，可归档证据写入 `evidence/`。任何 P0 失败都不得发布正式版本。

## Abaqus 实机门禁

只有明确设置以下变量时，测试才会提交真实 Job：

```powershell
$env:MATERIALAI_QA_RUN_ABAQUS_REAL = "1"
$env:MATERIALAI_QA_PRODUCT_PYTHON = "conda run -n pylabfea"
```

大型 ODB 不提交 Git。测试保留输入、版本、哈希、`.sta`、结果 JSON 和精简报告。

## 一键执行

```powershell
.\scripts\run_local_release_gate.ps1 `
  -ProductRoot D:\githubproject\pyLabFEA `
  -Version 0.3.0.dev0 `
  -RunAbaqus
```

脚本依次执行测试系统自检、Fake MCP、ZIP/EXE、中文路径与离线边界、源码/冻结包 UI、真实 Abaqus 闭环，并生成发布判定。`reports/release_decision.md` 是人读结论，`reports/release_decision.json` 是机器可读结果，`reports/release_decision_evidence.zip` 只收录精简证据，不打包大型 ODB。

## 发布规则

- 任一自动化套件失败或缺失，状态为 `blocked`。
- 实时 Abaqus MCP 只能心跳、不能读取模型与 Job 时，状态仍为 `blocked`。
- Abaqus 无许可证、Job aborted、无 ODB 或工程容差失败，都不能记为通过。
- 发布 ZIP 不得包含 `.env`、API Key、workspace、ODB/CAE、缓存或测试目录。
- 真实客户模型和未经授权的数据不得进入 fixture、报告或 Git 历史。

详细测试编号与验收标准见 `docs/TEST_MATRIX_CN.md`，本地/CI 操作见 `docs/RUNBOOK_CN.md`。
