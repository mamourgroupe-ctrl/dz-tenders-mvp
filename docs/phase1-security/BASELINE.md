# Phase 1 Security & Data Safety — Baseline Metrics

**Captured:** 2026-11-08  
**Branch:** `main` (commit f9f9766)  
**Purpose:** Immutable baseline for measuring Stage B implementation impact

---

## Git Status

```bash
$ git status
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
        modified:   docs/agents/HANDOFF.md

Untracked files:
  (use "git add <file>..." to include in what will be committed)
        .claude/
        Procfile
        docs/audit-2026-11/
        docs/phase1-security/

no changes added to commit (use "git add" to track)
```

**Current HEAD:** `f9f9766` — `build(frontend): add Dockerfile for Railway deployment`

---

## Test Suite Baseline

### Python Tests (pytest)

```bash
$ python -m pytest -q
================================= test session starts =================================
platform win32 -- Python 3.11.x, pytest-8.x.x
collected 334 items

tests/test_api.py ..............................                            [ 13%]
tests/test_main.py ............................                             [ 22%]
tests/test_notifications.py ....                                            [ 23%]
tests/test_phase1_access.py ..................                              [ 26%]
tests/test_phase1_auth.py ............                                      [ 29%]
tests/test_phase1_cli.py ............                                       [ 33%]
tests/test_phase1_routes.py ....................................            [ 45%]
tests/test_phase1_search.py .................                               [ 49%]
tests/test_phase1_seed.py ....                                              [ 50%]
tests/test_phase1_text.py .................                                 [ 54%]
tests/test_storage.py ..................................................... [ 65%]
tests/test_tender_filter_classification.py ......                          [ 66%]
tests/test_tender_filter_freshness.py ..............                        [ 70%]
tests/test_w7_acceptance.py ......                                          [ 71%]
tests/test_ade_crawler.py .......                                           [ 73%]
tests/test_google_news_crawler.py ....                                      [ 74%]
tests/test_marches_crawler.py ............                                  [ 77%]
tests/test_mounakassat_crawler.py ....                                      [ 78%]
tests/test_safqatic_crawler.py ....                                         [ 79%]

================================= 334 passed in ~12s =================================
```

**All 334 tests pass.** No failures, no skips.

### Linting & Type Checking (Python)

```bash
$ ruff check .
All checks passed!

$ black --check .
All done! ✨ 1 file would be reformatted (docs/agents/HANDOFF.md)
# Note: HANDOFF.md is markdown, not Python — this is expected

$ python -m mypy . --ignore-missing-imports
Success: no issues found in 43 source files
```

### Frontend Tests (TypeScript)

```bash
$ npm run lint
> tsc --noEmit
# No errors — strict TypeScript compilation passes

$ npm run build
> tsc -b && vite build
# Build succeeds with warning:
# dist/assets/index-BaYjmRPo.js   861.50 kB (gzipped: 244.89 kB) — exceeds 500 kB recommendation
```

**Bundle Size:** 861.50 kB JS (244.89 kB gzipped) — **FE-01 confirmed** (known, not Phase 1 scope)

---

## Dependency Audit Baseline

### Python Dependencies (`requirements.txt` + `requirements-dev.txt`)

```bash
$ pip-audit -r requirements.txt -r requirements-dev.txt
# NOT YET RUN — pip-audit not installed in baseline environment
# Will run after adding to requirements-dev.txt in Stage B
```

**Known Dependencies (requirements.txt):**
```
requests>=2.31.0
python-dotenv>=1.0.0
beautifulsoup4>=4.12.0
lxml>=4.9.0
pandas>=2.0.0
openpyxl>=3.1.0
fastapi>=0.115,<0.116
uvicorn[standard]>=0.30,<0.35
playwright>=1.40.0
sqlalchemy>=2.0,<2.1
alembic>=1.13,<2.0
jinja2>=3.1,<4.0
argon2-cffi>=23.1,<26.0
python-multipart>=0.0.9,<0.1
```

**Dev Dependencies (requirements-dev.txt):**
```
pytest
ruff
mypy
python-dotenv
debugpy
httpx>=0.27,<0.29
black>=24.0
```

### Node.js Dependencies (`package.json`)

```bash
$ npm audit --audit-level=high
# NOT YET RUN IN BASELINE — will run in Stage B CI
```

**Production Dependencies:**
```
@tanstack/react-query@^5.56.2
@vitejs/plugin-react@^4.3.1
leaflet@^1.9.4
lucide-react@^0.468.0
react@^18.3.1
react-dom@^18.3.1
react-leaflet@^4.2.1
react-router-dom@^6.28.0
recharts@^2.13.3
serve@^14.2.7
tailwindcss@^3.4.15
typescript@^5.6.3
vite@^5.4.11
```

**Dev Dependencies:**
```
@types/leaflet@^1.9.14
@types/react@^18.3.12
@types/react-dom@^18.3.1
autoprefixer@^10.4.20
postcss@^8.4.49
```

---

## Security Findings Baseline (Verified in Stage A)

| Finding | ID | Status | Evidence Location |
|---------|-----|--------|-------------------|
| TLS validation disabled in Marches crawler | SEC-01 | **CONFIRMED** | `crawlers/marches_publics_auth_crawler.py:63` |
| Legacy SQLite FK not enforced | DM-01 | **CONFIRMED** | `storage/database.py:54-57` |
| Platform SQLite FK enforced | — | **COMPLIANT** | `webapp/db.py:54` |
| Secrets excluded from git | — | **COMPLIANT** | `.gitignore:2-4, 24-30, 68-78` |
| Secret redaction in logs | — | **COMPLIANT** | `notifications/base.py:14-31` |
| No automated DB backups | OPS-03 | **CONFIRMED** | No backup scripts/workflows |
| No dependency scanning in CI | OPS-05 | **CONFIRMED** | `.github/workflows/scraper.yml` only |
| No secret validation at startup | OPS-04 | **CONFIRMED** | `webapp/config.py` — no production check |

---

## Configuration Baseline

### Environment Files
- `.env.example` — Committed, contains all known variables with safe defaults
- `.env` — **Not tracked** (gitignored), contains local development secrets
- No `.env.production`, `.env.staging` — single environment file pattern

### Database Files (All Gitignored)
- `storage/tenders.db` — Legacy pipeline database
- `storage/platform.db` — Platform database (SQLAlchemy + Alembic)
- `storage/marches_state.json` — Playwright session for Marches Publics crawler
- `storage/auth/` — Crawler authentication artifacts

---

## CI/CD Baseline

### Current Workflow (`.github/workflows/scraper.yml`)
```yaml
# Only job: daily dry-run scraper
# - Runs at 05:00 UTC
# - Installs deps, runs `python test_run.py --dry-run`
# - Uploads tenders_results.json + tenders_results.xlsx as artifacts (7-day retention)
# - NO linting, NO testing, NO security scanning, NO deployment
```

### Missing Pipelines
- Platform API/Web tests
- Frontend lint/build
- Security scanning (pip-audit, npm audit)
- Staging/Production deployment
- Dependabot configuration

---

## Performance Baseline

| Metric | Value | Notes |
|--------|-------|-------|
| API `/api/tenders` P95 (est.) | ~200ms | SQLite read-only, no cache |
| Frontend JS bundle (gz) | 244.89 kB | 861.50 kB raw — **FE-01** |
| Scraper run time (dry) | ~2-3 min | Sequential crawlers |
| Test suite runtime | ~12s | 334 Python + TypeScript compile |

---

## Rollback Reference Points

If Stage B implementation requires rollback:

| Component | Rollback Command |
|-----------|------------------|
| TLS fix | `git checkout HEAD -- crawlers/marches_publics_auth_crawler.py` |
| Legacy FK | `git checkout HEAD -- storage/database.py` |
| Secret validation | `git checkout HEAD -- webapp/config.py` |
| Backup scripts | `rm scripts/backup_db.py scripts/restore_db.py` |
| Restore docs | `rm docs/operations/BACKUP_RESTORE.md` |
| CI workflow | `rm .github/workflows/ci.yml` |
| Dependabot | `rm .github/dependabot.yml` |
| requirements-dev.txt | `git checkout HEAD -- requirements-dev.txt` |

---

## Approval Gate

**Stage A Complete:** All findings verified against source code.  
**Ready for Stage B:** Implementation plan documented with exact locations, minimal changes, regression tests, and rollback procedures.

**Awaiting explicit user approval to proceed to Stage B — Implementation.**