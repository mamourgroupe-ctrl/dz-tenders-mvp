# Phase 1 Security & Data Safety — Implementation Plan

**Created:** 2026-11-08  
**Status:** Stage B — IMPLEMENTATION COMPLETE (with corrections)  
**Branch:** `fix/phase1-security` (to be created in Stage B)

---

## Scope

Phase 1 addresses five security and data safety areas identified in the comprehensive audit:

| Area | Audit ID | Severity | Status |
|------|----------|----------|--------|
| TLS certificate verification in crawlers | SEC-01 | HIGH | **Needs fix** |
| SQLite foreign-key enforcement (legacy) | DM-01 | MEDIUM | **Needs fix** |
| Secure environment variables/secrets handling | OPS-04, SEC-04 | HIGH | **Partially compliant** |
| Database backup/restore procedures | OPS-03 | HIGH | **Missing** |
| Dependency vulnerability auditing in CI | OPS-05 | MEDIUM | **Missing** |

---

## Verified Root Causes & Locations

### 1. TLS Certificate Verification — SEC-01

**File:** `crawlers/marches_publics_auth_crawler.py:63`  
**Code:**
```python
self._context = self._browser.new_context(
    storage_state=str(self.state_path),
    ignore_https_errors=True,  # <-- SECURITY ISSUE
    viewport={"width": 1400, "height": 900},
)
```

**Root Cause:** Playwright browser context created with `ignore_https_errors=True` disables TLS certificate validation for the Marches Publics portal (`marches-publics.gov.dz`). This exposes crawler traffic to MITM attacks and certificate spoofing.

**Business Impact:** Compromised tender data integrity when scraping the official government procurement portal.

**Proposed Minimal Change:**
```python
# Option A: Remove the flag entirely (recommended - default is False)
self._context = self._browser.new_context(
    storage_state=str(self.state_path),
    viewport={"width": 1400, "height": 900},
)

# Option B: If certificate issues persist, use a CA bundle instead
# import certifi
# self._context = self._browser.new_context(
#     storage_state=str(self.state_path),
#     viewport={"width": 1400, "height": 900},
#     # certifi.where() provides Mozilla's CA bundle
# )
```

**Regression Test:**
- Unit test: Verify `ignore_https_errors` is not in browser context creation
- Integration test: Run crawler against `https://marches-publics.gov.dz` with valid TLS (manual verification)
- Existing tests in `tests/test_marches_crawler.py` should continue passing

**Rollback:** Revert the single line change in `marches_publics_auth_crawler.py`

---

### 2. SQLite Foreign Key Enforcement (Legacy) — DM-01

**File:** `storage/database.py:54-57`  
**Code:**
```python
def _connect(self):
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    return conn
```

**Root Cause:** Legacy database connections do not enable `PRAGMA foreign_keys = ON`. While the current schema has no explicit `FOREIGN KEY` constraints, future migrations or the `sent_tenders`/`failed_deliveries`/`blocked_tenders` tables (which reference `tenders.id`) would benefit from referential integrity.

**Note:** Platform database (`webapp/db.py:54`) already enforces FK:
```python
@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA busy_timeout = 5000")
    cursor.close()
```

**Business Impact:** Risk of orphaned records in delivery/notification tracking tables; data integrity gaps if schema evolves.

**Proposed Minimal Change:**
```python
def _connect(self):
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # <-- ADD THIS LINE
    conn.execute("PRAGMA busy_timeout = 5000")  # Match platform setting
    return conn
```

**Regression Test:**
- Unit test: Create connection, execute `PRAGMA foreign_keys`, verify returns `1`
- Integration test: Run full legacy pipeline (`python main.py --dry-run`) — verify no regressions
- Existing tests in `tests/test_storage.py` should pass

**Rollback:** Remove the two `conn.execute()` lines

---

### 3. Secure Environment Variables/Secrets Handling — OPS-04, SEC-04

**Current State (Verified):**

| Protection | Status | Evidence |
|------------|--------|----------|
| `.gitignore` excludes `.env`, `.env.*` | ✅ | `.gitignore:2-4` |
| `.gitignore` excludes `storage/*.db` | ✅ | `.gitignore:24-30` |
| `.gitignore` excludes `storage/auth/`, `storage/marches_state.json` | ✅ | `.gitignore:68-78` |
| Secret redaction in logs | ✅ | `notifications/base.py:14-31` |
| Platform `Settings` uses Pydantic-style validation | ✅ | `webapp/config.py:47-155` |
| No hardcoded secrets in source | ✅ | Verified via grep |

**Gaps Identified:**
1. **No startup validation** — Platform `Settings.from_env()` doesn't fail fast on missing required secrets in production
2. **No secret rotation mechanism** — Telegram bot token, SMTP credentials, crawler credentials stored long-term
3. **Single `.env` for all environments** — No separation between dev/staging/prod (OPS-06)

**Proposed Minimal Changes:**

**A. Add required secret validation at startup (webapp/config.py):**
```python
# In Settings.from_env(), after loading:
REQUIRED_IN_PRODUCTION = (
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID", 
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
    "MOUN_PHONE", "MOUN_PASSWORD",
)
if self.is_production:
    missing = [k for k in REQUIRED_IN_PRODUCTION if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"Missing required production secrets: {missing}")
```

**B. Document secret rotation procedure in `SECURITY.md`** (to be created)

**C. Add `.env.example` entries for all required secrets** (already largely present)

**Regression Test:**
- Unit test: `Settings.from_env()` raises `RuntimeError` in production mode with missing secrets
- Integration test: Start platform in `APP_ENV=production` without secrets — should fail fast

**Rollback:** Remove validation block; revert to current permissive behavior

---

### 4. Database Backup/Restore Procedures — OPS-03

**Current State:** No automated backups. No restore procedures. No DR testing.

**Assets Needing Backup:**
| Asset | Current State | RPO Target |
|-------|---------------|------------|
| `storage/tenders.db` (legacy) | GitHub Actions artifact (7-day) | 24h |
| `storage/platform.db` (platform) | **None** | 24h |
| `storage/marches_state.json` | **None** (gitignored) | Manual re-login |
| `storage/uploads/` | **None** | 24h |
| `data/targets.json` | Git (versioned) | 0 |

**Implemented Solution (Corrected — Local-Only, No Cloud Uploads):**

**A. Backup script (`scripts/backup_db.py`):**
- Uses SQLite `.backup()` API for consistent online snapshots
- Creates SHA256 manifest (`.manifest.json`) alongside each backup
- Stores backups in configurable local directory outside repository (default: `~/dz-tenders-backups/`)
- Configurable via `DZ_TENDERS_BACKUP_DIR` environment variable
- Covers: `tenders.db`, `platform.db`, `marches_state.json`, `uploads/`
- **No GitHub Actions artifact uploads** — removed per security corrections

**B. Restore script (`scripts/restore_db.py`):**
- Verifies SHA256 from manifest before any restoration
- SQLite integrity check + logical consistency (tables + row counts)
- Interactive confirmation required by default (`--force` to skip)
- Dry-run mode (`--dry-run`) for safe verification
- Safety copy of existing database before replacement
- Automatic rollback to safety copy on failure
- Rejects restoration if manifest missing or SHA256 mismatched

**C. Windows Task Scheduler (replaces GitHub Actions workflow):**
- Daily scheduled task at 02:00 local time (configurable)
- Runs `scripts/backup_db.py` via PowerShell
- See `docs/operations/BACKUP_RESTORE.md` for setup instructions
- **No GitHub Actions backup workflow** — `.github/workflows/backup.yml` removed

**D. Document restore procedure in `docs/operations/BACKUP_RESTORE.md`** — Updated with local-only procedures

**Regression Test:**
- Unit test: `backup_database()` produces valid SQLite file + manifest
- Integration test: `restore_db.py` restores backup; verify SHA256, row counts match
- Manual test: Quarterly restore drill (documented in runbook)

**Rollback:** Delete backup scripts; remove Task Scheduler task; local backups remain on disk

---

### 5. Dependency Vulnerability Auditing — OPS-05

**Current State:** `.github/workflows/scraper.yml` runs daily dry-run only. No `pip-audit`, no `npm audit`, no Dependabot.

**Proposed Minimal Changes:**

**A. Add security scan job to new CI workflow (`.github/workflows/ci.yml`):**
```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  lint-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - name: Install deps
        run: pip install -r requirements.txt -r requirements-dev.txt
      - name: Ruff
        run: ruff check .
      - name: Black
        run: black --check .
      - name: MyPy
        run: mypy .
      - name: Pytest
        run: pytest -q
      - name: Pip-audit
        run: pip-audit -r requirements.txt -r requirements-dev.txt
  
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm' }
      - run: npm ci
      - run: npm run lint
      - run: npm run build
      - name: NPM audit
        run: npm audit --audit-level=high
```

**B. Enable Dependabot (`.github/dependabot.yml`):**
```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 10
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 10
```

**C. Add `pip-audit` to `requirements-dev.txt`** (already has pytest, ruff, mypy, etc.)

**Regression Test:**
- CI pipeline runs `pip-audit` and `npm audit --audit-level=high` on every PR
- Dependabot creates weekly PRs for vulnerable dependencies
- Build fails on HIGH/CRITICAL vulnerabilities

**Rollback:** Remove `pip-audit` step; remove Dependabot config; remove from requirements-dev.txt

---

## Dependencies & Execution Order

```
Phase 1 Implementation Sequence:
├── 1. TLS Fix (SEC-01)                    ← Independent, do first
├── 2. Legacy FK Enforcement (DM-01)       ← Independent, do second
├── 3. Secret Validation (OPS-04/SEC-04)   ← Independent, do third
├── 4. Backup/Restore Scripts (OPS-03)     ← Depends on #3 (secrets for storage)
├── 5. CI Security Scanning (OPS-05)       ← Independent, can run in parallel
```

**Critical Path:** Items 1-3 are code changes; Items 4-5 are new files + CI config.

---

## Security Impact Summary

| Change | Attack Surface Reduced | Data Integrity Improved |
|--------|------------------------|-------------------------|
| TLS verification | MITM on gov portal scraping | ✅ Tender data authenticity |
| FK enforcement | Orphaned delivery records | ✅ Referential integrity |
| Secret validation | Accidental production deploy without secrets | ✅ Fail-fast safety |
| Automated backups | Data loss (RPO 24h → 0) | ✅ Disaster recovery |
| Dependency scanning | Supply chain exploits | ✅ Proactive patching |

---

## Files to Modify (Stage B)

| File | Change Type | Lines |
|------|-------------|-------|
| `crawlers/marches_publics_auth_crawler.py` | Modify | 63 |
| `storage/database.py` | Modify | 54-57 |
| `webapp/config.py` | Modify | ~120-155 (add validation) |
| `scripts/backup_db.py` | **New** | ~40 |
| `scripts/restore_db.py` | **New** | ~30 |
| `docs/operations/BACKUP_RESTORE.md` | **New** | ~100 |
| `.github/workflows/ci.yml` | **New** | ~60 |
| `.github/dependabot.yml` | **New** | ~25 |
| `requirements-dev.txt` | Modify | Add `pip-audit` |

---

## Acceptance Criteria (Stage B Completion)

- [ ] `ruff check .` passes
- [ ] `python -m pytest -q` passes (334 tests)
- [ ] `npm run lint` passes (tsc --noEmit)
- [ ] `npm run build` succeeds
- [ ] `pip-audit -r requirements.txt -r requirements-dev.txt` returns 0 HIGH/CRITICAL
- [ ] `npm audit --audit-level=high` returns 0 HIGH/CRITICAL
- [ ] Legacy crawler runs against `marches-publics.gov.dz` with valid TLS
- [ ] Legacy pipeline `PRAGMA foreign_keys` returns `1`
- [ ] Platform startup fails fast in production mode with missing secrets
- [ ] Backup script creates valid `.bak` files; restore script recovers them
- [ ] CI workflow runs on PR; security scans gate merge

---

**Next Step:** Await explicit user approval to proceed to **Stage B — Implementation**.