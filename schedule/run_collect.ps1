# Divmetric — coleta diária → docs/data (antes do GitHub_Daily_Publish)
# Evita `pip install` diário (travava no Agendador) e preserva exit code do collector.
$ErrorActionPreference = "Continue"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$logDir = Join-Path $root "data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd"
$log = Join-Path $logDir "collect_$stamp.log"

function Write-Log([string]$Message) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $log -Value $line -Encoding UTF8
    Write-Host $line
}

function Resolve-Python {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) { return $c }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notmatch "WindowsApps") { return $cmd.Source }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return $py.Source }
    return $null
}

Set-Location $root
Write-Log "=== Divmetric collect start ==="

$python = Resolve-Python
if (-not $python) {
    Write-Log "FAIL: python not found"
    exit 1
}
Write-Log "python: $python"

# Só instala deps se imports essenciais falharem (pip diário no Task Scheduler travava/abortava).
$probe = & $python -c "import requests, yaml; print('deps-ok')" 2>&1
if ($LASTEXITCODE -ne 0 -or ("$probe" -notmatch "deps-ok")) {
    Write-Log "deps missing — pip install once…"
    Write-Log "probe: $probe"
    $req = Join-Path $root "requirements.txt"
    $pipLog = Join-Path $logDir "pip_$stamp.log"
    $pip = Start-Process -FilePath $python -ArgumentList @("-m", "pip", "install", "-r", $req) `
        -WorkingDirectory $root -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $pipLog -RedirectStandardError $pipLog
    if ($pip.ExitCode -ne 0) {
        Write-Log "FAIL: pip exit $($pip.ExitCode) — see $pipLog"
        exit $pip.ExitCode
    }
    Write-Log "pip OK"
} else {
    Write-Log "deps OK (skip pip)"
}

$outLog = Join-Path $logDir "collector_out_$stamp.log"
$errLog = Join-Path $logDir "collector_err_$stamp.log"
Remove-Item $outLog, $errLog -ErrorAction SilentlyContinue
$proc = Start-Process -FilePath $python -ArgumentList @("-m", "modules.collector") `
    -WorkingDirectory $root -Wait -PassThru -NoNewWindow `
    -RedirectStandardOutput $outLog -RedirectStandardError $errLog

foreach ($f in @($outLog, $errLog)) {
    if (Test-Path -LiteralPath $f) {
        Get-Content -LiteralPath $f -ErrorAction SilentlyContinue | ForEach-Object { Write-Log $_ }
    }
}

if ($proc.ExitCode -ne 0) {
    Write-Log "FAIL: collector exit $($proc.ExitCode)"
    exit $proc.ExitCode
}
Write-Log "=== Divmetric collect done ==="
exit 0
