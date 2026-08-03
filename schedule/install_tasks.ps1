# Registra Divmetric_Daily_Collect no Agendador (antes do GitHub_Daily_Publish)
param(
    [string]$CollectTime = "05:45"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$GitHubRoot = (Resolve-Path (Join-Path $root "..")).Path
. (Join-Path $GitHubRoot "data\scripts\HiddenScheduledTask.ps1")

$script = Join-Path $root "schedule\run_collect.ps1"
$action = New-HiddenPowerShellFileTaskAction -ScriptPath $script -WorkingDirectory $root
$settings = New-ScheduledTaskSettingsHidden -ExecutionTimeLimit ([TimeSpan]::FromHours(1))

$h, $m = $CollectTime.Split(":")
$trigger = New-ScheduledTaskTrigger -Daily -At (Get-Date -Hour ([int]$h) -Minute ([int]$m) -Second 0)

Register-ScheduledTask -TaskName "Divmetric_Daily_Collect" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Divmetric: exporta meta/benchmarks para docs/data (antes do publish GitHub)" `
    -Force | Out-Null

Write-Host "OK: Divmetric_Daily_Collect @ $CollectTime" -ForegroundColor Green
Write-Host "GitHub_Daily_Publish ja inclui qualquer repo com .git (inclui Divmetric)." -ForegroundColor Cyan
