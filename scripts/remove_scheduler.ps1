# scripts/remove_scheduler.ps1
# Removes the DZ-Tenders-Daily scheduled task.

$TaskName = "DZ-Tenders-Daily"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "OK: Task '$TaskName' removed" -ForegroundColor Green
} else {
    Write-Host "Task '$TaskName' does not exist" -ForegroundColor Yellow
}
