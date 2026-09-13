# Reorganize project - detects path automatically

$rootPath = $PSScriptRoot
$innerPath = Join-Path $rootPath "dz-tenders-mvp-main"

Write-Host "`n[1/7] Checking structure..." -ForegroundColor Cyan
Write-Host "   Root: $rootPath"

if (-not (Test-Path (Join-Path $rootPath ".git"))) {
    Write-Host "[X] .git not found in root!" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $innerPath)) {
    Write-Host "[!] Inner folder not found." -ForegroundColor Yellow
    exit 0
}

Write-Host "[OK] Structure valid." -ForegroundColor Green

Write-Host "`n[2/7] Backing up .env..." -ForegroundColor Cyan
$envSource = Join-Path $innerPath ".env"
if (Test-Path $envSource) {
    Copy-Item -Path $envSource -Destination (Join-Path $rootPath ".env.backup") -Force
    Write-Host "[OK] .env.backup saved" -ForegroundColor Green
}

Write-Host "`n[3/7] Moving files..." -ForegroundColor Cyan
$items = @(".github", "crawlers", "data", ".gitignore", "telegram_notifier.py", "tender_filter.py", "test_run.py")
foreach ($item in $items) {
    $src = Join-Path $innerPath $item
    $dst = Join-Path $rootPath $item
    if (Test-Path $src) {
        if (Test-Path $dst) {
            Remove-Item -Path $dst -Recurse -Force -ErrorAction SilentlyContinue
        }
        Move-Item -Path $src -Destination $dst -Force
        Write-Host "  [OK] $item" -ForegroundColor Green
    } else {
        Write-Host "  [SKIP] $item" -ForegroundColor Yellow
    }
}

Write-Host "`n[4/7] Deleting inner folder..." -ForegroundColor Cyan
Remove-Item -Path $innerPath -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "[OK] Deleted" -ForegroundColor Green

Write-Host "`n[5/7] New structure:" -ForegroundColor Cyan
Get-ChildItem -Path $rootPath -Force | Where-Object { $_.Name -ne ".git" } | Select-Object Name | Format-Table -AutoSize

Write-Host "`n[6/7] Git staging..." -ForegroundColor Cyan
Set-Location $rootPath
git add -A
$envStaged = git diff --cached --name-only | Select-String "\.env$"
if ($envStaged) {
    git reset .env
    Write-Host "[!] .env removed from staging" -ForegroundColor Yellow
}
git status --short

Write-Host "`n[7/7] Commit and push..." -ForegroundColor Cyan
git commit -m "Fix: reorganize project structure"
git push

Write-Host "`n===== DONE! =====" -ForegroundColor Magenta