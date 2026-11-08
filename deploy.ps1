<#
.SYNOPSIS
    Local DB init -> tests -> live API smoke test -> Railway deploy -> remote verification.

.EXAMPLE
    .\deploy.ps1
    .\deploy.ps1 -Endpoints "/api/docs","/api/tenders" -SkipTests
    .\deploy.ps1 -SkipDeploy                       # local checks only
    .\deploy.ps1 -RemoteUrl "https://xxx.up.railway.app" -Force
#>
[CmdletBinding()]
param(
  [string]$AppModule = "api.main:app",
  [string]$DbPath = ".\data\tenders.db",
  [int]   $Port = 8000,
  # Python statement(s) that create the DB schema. Adjust to your project.
  [string]$InitCommand = "from api.repository import TenderDatabase; TenderDatabase()",
  # Paths that must return HTTP 200 (add a DB-backed endpoint to catch 503s).
  [string[]]$Endpoints = @("/api/docs"),
  [string]$RemoteUrl,
  [switch]$SkipTests,
  [switch]$SkipDeploy,
  [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# ---------- helpers ----------
function Write-Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Write-Ok($m) { Write-Host "  [OK]   $m" -ForegroundColor Green }
function Write-Warn2($m) { Write-Host "  [WARN] $m" -ForegroundColor Yellow }
function Stop-Script($m) { Write-Host "  [FAIL] $m" -ForegroundColor Red; exit 1 }

function Invoke-Native {
  param([string]$File, [string[]]$Arguments)
  & $File @Arguments
  if ($LASTEXITCODE -ne 0) { Stop-Script "'$File $($Arguments -join ' ')' exited with code $LASTEXITCODE" }
}

function Get-HttpStatus([string]$Url) {
  try {
    return [int](Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10).StatusCode
  }
  catch {
    if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
    return 0   # connection refused / timeout
  }
}

function Wait-Http([string]$Url, [int]$TimeoutSec = 40) {
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    if ((Get-HttpStatus $Url) -ne 0) { return $true }
    Start-Sleep -Milliseconds 800
  }
  return $false
}

# ---------- 1. preflight ----------
Write-Step "Preflight checks"
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Stop-Script "Virtual env not found at .venv. Create it: python -m venv .venv" }
Write-Ok "Python: $(& $py --version)"

if (-not $SkipDeploy) {
  if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    Stop-Script "Railway CLI missing. Install: npm i -g @railway/cli"
  }
  Write-Ok "Railway CLI found"
}

# ---------- 2. local database ----------
Write-Step "Initializing local database"
$DbFull = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $DbPath))
New-Item -ItemType Directory -Force -Path (Split-Path $DbFull) | Out-Null
$env:DB_PATH = $DbFull
Write-Ok "DB_PATH = $DbFull"

Invoke-Native $py @("-c", $InitCommand)
if (-not (Test-Path $DbFull)) { Stop-Script "DB file was not created. Check -InitCommand." }
Write-Ok "Database file ready ($([math]::Round((Get-Item $DbFull).Length / 1KB, 1)) KB)"
Write-Warn2 "Schema only: if the API needs rows or required columns, load your data before relying on a 200."

# ---------- 3. tests ----------
if (-not $SkipTests) {
  Write-Step "Running tests"
  $hasTests = (Test-Path ".\tests") -or (Get-ChildItem -Filter "test_*.py" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1)
  if ($hasTests) {
    Invoke-Native $py @("-m", "pytest", "-x", "-q")
    Write-Ok "Tests passed"
  }
  else {
    Write-Warn2 "No tests found, skipping"
  }
}

# ---------- 4. live smoke test ----------
Write-Step "Starting local server on port $Port"
New-Item -ItemType Directory -Force -Path ".\logs" | Out-Null
$proc = Start-Process -FilePath $py `
  -ArgumentList @("-m", "uvicorn", $AppModule, "--port", $Port) `
  -RedirectStandardOutput ".\logs\uvicorn.out.log" `
  -RedirectStandardError  ".\logs\uvicorn.err.log" `
  -WindowStyle Hidden -PassThru

try {
  $base = "http://127.0.0.1:$Port"
  if (-not (Wait-Http "$base$($Endpoints[0])")) {
    Get-Content ".\logs\uvicorn.err.log" -Tail 20 -ErrorAction SilentlyContinue
    Stop-Script "Server did not start. See logs\uvicorn.err.log"
  }
  Write-Ok "Server is up (PID $($proc.Id))"

  $failed = @()
  foreach ($ep in $Endpoints) {
    $code = Get-HttpStatus "$base$ep"
    if ($code -eq 200) { Write-Ok "$ep -> $code" }
    else { Write-Host "  [FAIL] $ep -> $code" -ForegroundColor Red; $failed += $ep }
  }
  if ($failed.Count) { Stop-Script "Endpoints failed: $($failed -join ', ')" }
}
finally {
  if ($proc -and -not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force
    Write-Ok "Local server stopped"
  }
}

# ---------- 5. deploy ----------
if ($SkipDeploy) { Write-Step "Done (local checks only)"; exit 0 }

Write-Step "Railway deployment"
Invoke-Native "railway" @("whoami")
Invoke-Native "railway" @("status")

if (-not $Force) {
  $answer = Read-Host "Deploy to the Railway project shown above? (y/N)"
  if ($answer -notmatch '^[yY]') { Stop-Script "Deployment cancelled by user." }
}

Invoke-Native "railway" @("up", "--detach")
Write-Ok "Deployment submitted"

# ---------- 6. remote verification ----------
if (-not $RemoteUrl) {
  Write-Warn2 "No -RemoteUrl given, skipping remote check. Tail logs with: railway logs"
  exit 0
}

Write-Step "Verifying remote deployment ($RemoteUrl)"
$ready = Wait-Http "$RemoteUrl$($Endpoints[0])" -TimeoutSec 180
if (-not $ready) { Stop-Script "Remote did not respond in time. Run: railway logs" }

$remoteFailed = @()
foreach ($ep in $Endpoints) {
  $code = Get-HttpStatus "$RemoteUrl$ep"
  if ($code -eq 200) { Write-Ok "$ep -> $code" }
  else { Write-Host "  [FAIL] $ep -> $code" -ForegroundColor Red; $remoteFailed += $ep }
}
if ($remoteFailed.Count) {
  Write-Warn2 "A 503 usually means the DB file is missing on the Volume. Check DB_PATH and the Mount Path."
  Stop-Script "Remote endpoints failed: $($remoteFailed -join ', ')"
}

Write-Step "All done: local and remote checks passed"
