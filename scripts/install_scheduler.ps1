# scripts/install_scheduler.ps1
# Registers a Windows Task Scheduler task to run main.py daily at 08:00.
# Must be run as Administrator.

$ErrorActionPreference = "Stop"

$TaskName = "DZ-Tenders-Daily"
$ProjectRoot = "D:\07_Programming\Githup_project\dz-tenders-mvp-main"
$RunnerScript = Join-Path $ProjectRoot "scripts\run_daily.ps1"
$RunTime = "08:00"

# Verify script exists
if (-not (Test-Path $RunnerScript)) {
    Write-Host "ERROR: runner script not found at $RunnerScript" -ForegroundColor Red
    exit 1
}

# Remove existing task (idempotent)
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "Removing existing task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Build action: powershell.exe -NoProfile -ExecutionPolicy Bypass -File run_daily.ps1
$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$RunnerScript`""

# Trigger: daily at 08:00
$Trigger = New-ScheduledTaskTrigger -Daily -At $RunTime

# Settings: run whether logged in or not; hidden window
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

# Principal: current user, run whether logged in or not
$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType S4U `
    -RunLevel Limited

# Register
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Runs DZ-Tenders-MVP main.py daily at $RunTime" | Out-Null

Write-Host "OK: Task '$TaskName' registered (daily at $RunTime)" -ForegroundColor Green
Write-Host ""
Write-Host "Verify with: Get-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Cyan
Write-Host "Test now with: Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Cyan
