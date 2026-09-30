$ErrorActionPreference = "Stop"

Write-Host "🔄 جاري مزامنة القواعد..." -ForegroundColor Cyan

New-Item -ItemType Directory -Force -Path ".github" | Out-Null
New-Item -ItemType Directory -Force -Path ".clinerules" | Out-Null
New-Item -ItemType Directory -Force -Path ".kilo/rules" | Out-Null

Copy-Item "AGENTS.md" ".github/copilot-instructions.md" -Force
Copy-Item "AGENTS.md" "CLAUDE.md" -Force
Copy-Item "AGENTS.md" ".clinerules/00-team.md" -Force
Copy-Item "AGENTS.md" ".kilo/rules/00-team.md" -Force

Write-Host "✅ تمت مزامنة القواعد لكل الوكلاء (Copilot, Claude, Cline, Kilo)" -ForegroundColor Green
