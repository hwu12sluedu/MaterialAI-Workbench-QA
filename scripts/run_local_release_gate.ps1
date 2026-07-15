param(
    [Parameter(Mandatory = $true)][string]$ProductRoot,
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$AppUrl = "http://127.0.0.1:8501",
    [string]$BrowserChannel = "msedge",
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

$diagnostics = Get-ChildItem (Join-Path $ProductRoot "workspace\diagnostics") `
    -Recurse -Filter diagnostics.json -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
$summaryArgs = @("summarize", "--reports", "reports", "--evidence", "evidence")
if ($diagnostics) {
    $summaryArgs += @("--mcp-diagnostics", $diagnostics.FullName)
}
& (Join-Path $QaRoot ".venv\Scripts\materialai-qa.exe") @summaryArgs
exit $LASTEXITCODE
