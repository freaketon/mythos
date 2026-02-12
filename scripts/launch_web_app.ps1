$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host "Starting Contact Enrichment web app on http://127.0.0.1:8000 ..."
uv run python -m src.web_main
