# Divmetric — coleta diária (stub → export docs/data) antes do GitHub_Daily_Publish
$ErrorActionPreference = "Stop"
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

Set-Location $root
Write-Log "=== Divmetric collect start ==="

$req = Join-Path $root "requirements.txt"
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) {
    Write-Log "FAIL: python not found"
    exit 1
}

Write-Log "ensuring Python deps (quiet)…"
& $py.Source -m pip install -q -r $req 2>&1 | ForEach-Object { Write-Log "pip: $_" }

& $py.Source (Join-Path $root "modules\collector.py") 2>&1 | ForEach-Object { Write-Log "$_" }
if ($LASTEXITCODE -ne 0) {
    Write-Log "FAIL: collector exit $LASTEXITCODE"
    exit $LASTEXITCODE
}
Write-Log "=== Divmetric collect done ==="
exit 0
