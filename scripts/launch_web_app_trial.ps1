$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host "Clearing run artifacts and caches (no tests)..."
Get-ChildItem -Path $repoRoot -Filter "run*.log" -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $repoRoot -Filter "run*.jsonl" -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $repoRoot -Filter "run.state.json" -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $repoRoot -Filter "*.hydrated*.csv" -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $repoRoot -Filter "*.low-confidence*.csv" -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $repoRoot -Directory -Filter "__pycache__" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $repoRoot -Directory -Filter ".pytest_cache" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Initializing empty hydrated outputs..."
$inputName = "MVI - Elite Outreach List & Tracker - Master List - Elite - Intake - 3009 - 11_16_2025.csv"
$outputName = "MVI - Elite Outreach List & Tracker - Master List - Elite - Intake - 3009 - 11_16_2025.hydrated.full.csv"
$lowConfName = "MVI - Elite Outreach List & Tracker - Master List - Elite - Intake - 3009 - 11_16_2025.low-confidence.full.csv"
$inputPath = Join-Path $repoRoot $inputName
$outputPath = Join-Path $repoRoot $outputName
$lowConfPath = Join-Path $repoRoot $lowConfName

if (Test-Path $inputPath) {
    $header = Get-Content -Path $inputPath -TotalCount 1
    $hydratedColumns = @(
        "Youtube handle",
        "Youtube URL",
        "Youtube Subs count",
        "Youtube Publishing cadence",
        "Youtube Channel Age",
        "Instagram handle",
        "Instagram followers",
        "Instagram publishing cadence",
        "Instagram Account Age"
    ) -join ","
    Set-Content -Path $outputPath -Value ($header + "," + $hydratedColumns) -Encoding UTF8
}
Set-Content -Path $lowConfPath -Value "row_number,queries,candidate_url,candidate_handle,confidence,source" -Encoding UTF8

Write-Host "Starting trial web session on http://127.0.0.1:8000 ..."
uv run python -m src.web_main
