# 本地与 CI 操作手册

## 1. 创建环境

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test,ui,windows]"
```

UI 默认使用 Playwright 固定 Chromium。若下载受限，可使用系统 Edge：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ui.py --browser-channel=msedge
```

## 2. 普通回归

普通回归不提交 Abaqus Job：

```powershell
$env:MATERIALAI_QA_PRODUCT_ROOT = "D:\githubproject\pyLabFEA"
.\.venv\Scripts\python.exe -m pytest -m "not portable and not source_mock and not ui and not abaqus_real"
```

## 3. 真实 Abaqus 门禁

确认许可证可用后再显式开启：

```powershell
$env:MATERIALAI_QA_RUN_ABAQUS_REAL = "1"
.\.venv\Scripts\python.exe -m pytest tests\test_abaqus_real.py -vv
```

运行会生成新的三维带孔板、提交 Job、读取 ODB 并加入案例库。大型工件写入 `evidence/` 且被 Git 忽略；只提交 fixture、代码和精简报告规则。

## 4. 发布判定

```powershell
.\.venv\Scripts\materialai-qa.exe summarize `
  --reports reports `
  --evidence evidence `
  --mcp-diagnostics D:\path\to\diagnostics.json
```

返回码 `0` 表示全部通过，`2` 表示仍有阻塞项，`1` 表示 QA 工具本身执行失败。

`run_local_release_gate.ps1` 会把上一轮固定名称的 JUnit、HTML 和判定文件移入 `reports/archive/<时间戳>`，并且只使用本轮显式提供或本轮新生成的 MCP 诊断。未加 `-RunAbaqus` 时，离线和 UI 套件可以全部通过，但完整发布判定仍会因缺少本轮 Abaqus 实机证据而保持 `blocked`。

已有本轮只读 MCP 诊断时可显式传入：

```powershell
.\scripts\run_local_release_gate.ps1 `
  -ProductRoot D:\githubproject\pyLabFEA `
  -Version 0.4.0a1 `
  -McpDiagnostics D:\path\to\diagnostics.json
```

## 5. CI 分层

- `qa.yml`：托管 Windows Runner 上执行 QA 自检、Schema 与 Fake Bridge 单测。
- `source-mock.yml`：手动选择产品 branch/tag，验证产品 CLI 对 Fake MCP 的行为。
- `abaqus-real.yml`：仅在带 Abaqus 2023 和许可证的自托管 Runner 上执行。
