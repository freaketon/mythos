$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host "Clearing run artifacts and caches..."
Get-ChildItem -Path $repoRoot -Filter "run*.log" -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $repoRoot -Filter "run*.jsonl" -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $repoRoot -Filter "run.state.json" -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $repoRoot -Filter "*.hydrated*.csv" -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $repoRoot -Filter "*.low-confidence*.csv" -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $repoRoot -Directory -Filter "__pycache__" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $repoRoot -Directory -Filter ".pytest_cache" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Running tests..."
uv run pytest -q

Write-Host "Starting fresh web session on http://127.0.0.1:8000 ..."
uv run python -m src.web_main
