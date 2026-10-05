# scripts/run_daily.ps1
# Runs DZ-TENDERS-MVP daily (production mode).
# Called by Windows Task Scheduler.

$ErrorActionPreference = "Stop"

# Force UTF-8 (fixes emoji/Arabic in logs)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

# Production mode: real notifications (overrides .env)
$env:DRY_RUN = "false"

$ProjectRoot = "D:\07_Programming\Githup_project\dz-tenders-mvp-main"
$VenvActivate = Join-Path $ProjectRoot "venv\Scripts\Activate.ps1"
$MainPy = Join-Path $ProjectRoot "main.py"
$LogDir = Join-Path $ProjectRoot "logs"
$RunnerLog = Join-Path $LogDir "scheduler_runs.log"
$StdoutLog = Join-Path $LogDir "scheduler_stdout.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

function Write-RunnerLog($msg) {
    "$timestamp | $msg" | Out-File -FilePath $RunnerLog -Append -Encoding utf8
}

try {
    Set-Location $ProjectRoot
    & $VenvActivate
    Write-RunnerLog "START (DRY_RUN=$env:DRY_RUN)"
    python $MainPy *> $StdoutLog
    $exitCode = $LASTEXITCODE
    Write-RunnerLog "END (exit $exitCode)"
    exit $exitCode
} catch {
    Write-RunnerLog "FATAL: $_"
    exit 2
}
