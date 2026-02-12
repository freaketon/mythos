param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("app", "fresh-test", "trial")]
    [string]$Mode = "app"
)

$ErrorActionPreference = "Stop"
$scriptsDir = $PSScriptRoot

switch ($Mode) {
    "app" {
        & (Join-Path $scriptsDir "launch_web_app.ps1")
    }
    "fresh-test" {
        & (Join-Path $scriptsDir "launch_web_app_fresh_test.ps1")
    }
    "trial" {
        & (Join-Path $scriptsDir "launch_web_app_trial.ps1")
    }
}
