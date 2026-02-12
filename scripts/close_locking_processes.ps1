$ErrorActionPreference = "SilentlyContinue"

$repo = "g:\My Drive\Official DRIVE\0001 TURBO\0005 CLAUDE AUTOMATIONS\worktrees\contact-enrichment"

Write-Host "Stopping Excel (common CSV lock source)..."
Get-Process EXCEL | Stop-Process -Force

Write-Host "Stopping Python processes tied to this repo..."
Get-CimInstance Win32_Process |
  Where-Object {
    $_.Name -match "^python(\.exe)?$" -and
    $_.CommandLine -like "*$repo*"
  } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Write-Host "Stopping uv/uvicorn launched from this repo..."
Get-CimInstance Win32_Process |
  Where-Object {
    ($_.Name -match "^(uv|uvicorn|powershell)(\.exe)?$") -and
    $_.CommandLine -like "*$repo*"
  } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Write-Host "Done."
