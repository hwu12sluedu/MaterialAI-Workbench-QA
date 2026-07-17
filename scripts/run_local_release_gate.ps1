param(
    [Parameter(Mandatory = $true)][string]$ProductRoot,
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$AppUrl = "http://127.0.0.1:8501",
    [string]$BrowserChannel = "msedge",
    [string]$McpDiagnostics = "",
    [switch]$RunAbaqus
)

$ErrorActionPreference = "Stop"
$QaRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ProductRoot = (Resolve-Path -LiteralPath $ProductRoot).Path
$Python = Join-Path $QaRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "QA virtual environment is missing. Follow README.md to install it."
}

$env:MATERIALAI_QA_PRODUCT_ROOT = $ProductRoot
$env:MATERIALAI_QA_EXPECTED_VERSION = $Version
$env:MATERIALAI_QA_RUN_UI = "1"
$env:MATERIALAI_QA_RUN_FROZEN_UI = "1"
$env:MATERIALAI_QA_APP_URL = $AppUrl
Set-Location $QaRoot
$RunStartedAt = Get-Date

# Archive fixed-name outputs so stale suites cannot be counted in this run.
$ReportsRoot = Join-Path $QaRoot "reports"
$ArchiveRoot = Join-Path $ReportsRoot ("archive\" + $RunStartedAt.ToUniversalTime().ToString("yyyyMMddTHHmmssZ"))
$GeneratedReports = @(
    "unit-junit.xml", "unit.html",
    "source-mock-junit.xml", "source-mock.html",
    "release-audit-junit.xml", "release-audit.html",
    "portable-lifecycle-junit.xml", "portable-lifecycle.html",
    "portable-boundaries-junit.xml", "portable-boundaries.html",
    "ui-junit.xml", "ui.html",
    "abaqus-real-junit.xml", "abaqus-real.html",
    "release_decision.json", "release_decision.md",
    "release_decision_evidence.zip"
)
foreach ($Name in $GeneratedReports) {
    $Source = Join-Path $ReportsRoot $Name
    if (Test-Path -LiteralPath $Source) {
        New-Item -ItemType Directory -Force -Path $ArchiveRoot | Out-Null
        Move-Item -LiteralPath $Source -Destination (Join-Path $ArchiveRoot $Name) -Force
    }
}

function Invoke-Gate {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    & $Python -m pytest @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "QA gate failed: pytest $($Arguments -join ' ')"
    }
}

Invoke-Gate @(
    "-m", "not portable and not source_mock and not ui and not abaqus_real",
    "--junitxml=reports\unit-junit.xml",
    "--html=reports\unit.html", "--self-contained-html"
)
Invoke-Gate @(
    "-m", "source_mock",
    "--junitxml=reports\source-mock-junit.xml",
    "--html=reports\source-mock.html", "--self-contained-html"
)
Invoke-Gate @(
    "tests\test_release_asset.py",
    "--junitxml=reports\release-audit-junit.xml",
    "--html=reports\release-audit.html", "--self-contained-html"
)
Invoke-Gate @(
    "tests\test_process_control.py",
    "--junitxml=reports\portable-lifecycle-junit.xml",
    "--html=reports\portable-lifecycle.html", "--self-contained-html"
)
Invoke-Gate @(
    "tests\test_portable_boundaries.py",
    "--junitxml=reports\portable-boundaries-junit.xml",
    "--html=reports\portable-boundaries.html", "--self-contained-html"
)
Invoke-Gate @(
    "tests\test_ui.py", "--browser-channel=$BrowserChannel",
    "--screenshot=only-on-failure", "--full-page-screenshot",
    "--output=test-results", "--junitxml=reports\ui-junit.xml",
    "--html=reports\ui.html", "--self-contained-html"
)

if ($RunAbaqus) {
    $env:MATERIALAI_QA_RUN_ABAQUS_REAL = "1"
    Invoke-Gate @(
        "tests\test_abaqus_real.py",
        "--junitxml=reports\abaqus-real-junit.xml",
        "--html=reports\abaqus-real.html", "--self-contained-html"
    )
}

$diagnostics = $null
if (-not [string]::IsNullOrWhiteSpace($McpDiagnostics)) {
    $diagnostics = Get-Item -LiteralPath (Resolve-Path -LiteralPath $McpDiagnostics).Path
}
elseif ($RunAbaqus) {
    $McpOutputRoot = Join-Path $QaRoot ("evidence\mcp_live\" + $RunStartedAt.ToUniversalTime().ToString("yyyyMMddTHHmmssZ"))
    & conda run -n pylabfea materialai-diagnostics --output-root $McpOutputRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Fresh live MCP diagnostics failed with exit code $LASTEXITCODE"
    }
    $diagnostics = Get-ChildItem -LiteralPath $McpOutputRoot `
        -Recurse -Filter diagnostics.json -ErrorAction Stop |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
}
$summaryArgs = @("summarize", "--reports", "reports", "--evidence", "evidence")
if ($diagnostics) {
    $summaryArgs += @("--mcp-diagnostics", $diagnostics.FullName)
}
& (Join-Path $QaRoot ".venv\Scripts\materialai-qa.exe") @summaryArgs
exit $LASTEXITCODE
