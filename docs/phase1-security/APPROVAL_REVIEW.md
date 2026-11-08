# Phase 1 Security & Data Safety — Approval Review

**Review Date:** 2026-11-08  
**Status:** Pre-Stage B Gate Review  
**Reviewer:** Automated review per user request  
**Action Required:** Resolve findings below before Stage B approval

---

## 1. Backup Destination, Encryption, GitHub Actions Permissions, Artifact Retention, Database Protection

### Findings

| Aspect | Current Plan | Risk |
|--------|--------------|------|
| **Backup destination** | Local `storage/backups/` → uploaded as GitHub Actions artifact | ✅ Simple, but artifacts are **not encrypted at rest** in GitHub |
| **Encryption** | None specified | ❌ **HIGH** — SQLite backups contain full tender data (titles, organizations, wilayas, links, scores). If GitHub account compromised, data exposed. |
| **GitHub Actions permissions** | Default `GITHUB_TOKEN` (read/write) | ⚠️ Artifacts accessible to anyone with repo read access |
| **Artifact retention** | 30 days (`retention-days: 30`) | ✅ Reasonable for MVP; not compliant with long-term retention policies |
| **Database protection** | Both `tenders.db` and `platform.db` backed up | ✅ Both covered, but `marches_state.json` and `storage/uploads/` not included |

### Unresolved Risks

1. **No encryption at rest** — Backup artifacts stored in GitHub infrastructure unencrypted. For government procurement data (Algerian public tenders), this may violate data sovereignty requirements.
2. **No access control on artifacts** — Any collaborator with read access can download tender database backups.
3. **Missing assets** — `marches_state.json` (crawler session, effectively credentials) and `storage/uploads/` (payment proofs, attachments) not backed up.
4. **No off-site replication** — Single copy in GitHub; if GitHub unavailable, no recovery.

### Recommended Corrections

**Option A (Minimal - MVP acceptable):**
- Add `storage/marches_state.json` and `storage/uploads/` to backup script
- Document in `BACKUP_RESTORE.md` that artifacts are unencrypted; restrict repo access to minimal team
- Add note: "For production, migrate to encrypted object storage (S3/GCS/Azure Blob) with KMS"

**Option B (Production-ready - add to Phase 1):**
- Encrypt backups before upload using age/GPG with key from GitHub Secrets
- Upload to external encrypted bucket instead of (or in addition to) GitHub artifacts
- Add IAM policy restricting artifact download to specific roles

**Decision Required:** Which option for Stage B? Recommendation: **Option A for MVP**, document limitation, plan Option B for Phase 3.

---

## 2. Restore Script Safety

### Findings

| Safety Feature | Current Plan | Status |
|----------------|--------------|--------|
| **Default refusal to overwrite** | No — `temp_path.replace(dest_path)` overwrites silently | ❌ **HIGH** |
| **Explicit confirmation** | No — CLI runs without prompt | ❌ **HIGH** |
| **Integrity checks** | None — no checksum, schema validation, row count verification | ❌ **MEDIUM** |
| **Recovery procedure documentation** | Planned in `BACKUP_RESTORE.md` | ✅ Planned |

### Unresolved Risks

1. **Accidental overwrite** — Running `restore_db.py` with wrong arguments destroys current database instantly.
2. **No validation** — Corrupted/incomplete backup restores silently; application fails later with cryptic errors.
3. **No dry-run mode** — Cannot preview what would be restored.

### Recommended Corrections

**Update `scripts/restore_db.py` to include:**

```python
#!/usr/bin/env python3
"""Restore SQLite database from backup file — SAFE VERSION."""
import shutil
import sys
import sqlite3
import hashlib
from pathlib import Path

def verify_backup(backup_path: Path) -> dict:
    """Verify backup is valid SQLite and return metadata."""
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")
    conn = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
    try:
        # Check it's a valid SQLite DB
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )]
        # Count rows in key tables
        counts = {}
        for table in ("tenders", "announcements"):
            if table in tables:
                counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        # SHA256 for integrity
        sha256 = hashlib.sha256(backup_path.read_bytes()).hexdigest()
        return {"tables": tables, "counts": counts, "sha256": sha256}
    finally:
        conn.close()

def restore_database(backup_path: Path, dest_path: Path, force: bool = False, dry_run: bool = False) -> None:
    info = verify_backup(backup_path)
    
    print(f"Backup verification:")
    print(f"  Tables: {info['tables']}")
    print(f"  Row counts: {info['counts']}")
    print(f"  SHA256: {info['sha256']}")
    
    if dest_path.exists() and not force:
        print(f"\n⚠️  Destination {dest_path} exists. Use --force to overwrite.")
        sys.exit(1)
    
    if dry_run:
        print("\n[DRY RUN] Would restore. No changes made.")
        return
    
    # Confirm interactively unless --force
    if not force:
        resp = input(f"\nOverwrite {dest_path}? Type 'YES' to confirm: ")
        if resp != "YES":
            print("Aborted.")
            sys.exit(1)
    
    temp_path = dest_path.with_suffix(".tmp")
    shutil.copy2(backup_path, temp_path)
    temp_path.replace(dest_path)
    print(f"✅ Restored {backup_path} → {dest_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Restore SQLite database from backup")
    parser.add_argument("backup_file", type=Path)
    parser.add_argument("destination_db", type=Path)
    parser.add_argument("--force", action="store_true", help="Overwrite without prompt")
    parser.add_argument("--dry-run", action="store_true", help="Verify only, no changes")
    args = parser.parse_args()
    restore_database(args.backup_file, args.destination_db, force=args.force, dry_run=args.dry_run)
```

**Also update `BACKUP_RESTORE.md` with:**
- Step-by-step restore procedure with screenshots/commands
- Quarterly drill schedule and checklist
- Rollback to previous backup if restore fails

---

## 3. Existing GitHub Actions Workflows — Duplication/Conflict Analysis

### Current Workflows

| Workflow | Trigger | Purpose | Secrets Used |
|----------|---------|---------|--------------|
| `scraper.yml` | Schedule (05:00 UTC) + manual | Daily dry-run scraper | **None** (explicitly no secrets) |

### Proposed New Workflows

| Workflow | Trigger | Purpose | Potential Conflicts |
|----------|---------|---------|---------------------|
| `ci.yml` | Push, PR | Lint, test, security scan | None — different triggers |
| `backup.yml` | Schedule (03:00 UTC) | Daily DB backup | **Schedule overlap risk** with scraper (05:00 UTC) — both use `ubuntu-latest`, could contend for runner resources |

### Conflict Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Runner contention (backup 03:00 + scraper 05:00) | Low (2hr gap, each ~3-5 min) | Medium (delayed runs) | Stagger: backup at 02:00, scraper at 06:00 |
| Artifact storage quota | Low (7-day + 30-day retention) | Low | Monitor; add cleanup workflow if needed |
| `pip install` duplication | Medium (3 workflows install deps) | Low (time/cost) | Add dependency caching to all workflows |

### Recommended Corrections

1. **Stagger schedules:**
   - `backup.yml`: `cron: '0 2 * * *'` (02:00 UTC)
   - `scraper.yml`: Keep `0 5 * * *` (05:00 UTC) — or move to `0 6 * * *`
   - `ci.yml`: Event-driven (no schedule conflict)

2. **Add dependency caching to all workflows** (copy from scraper.yml):
   ```yaml
   - name: Cache pip
     uses: actions/cache@v4
     with:
       path: ~/.cache/pip
       key: pip-${{ runner.os }}-${{ hashFiles('requirements.txt', 'requirements-dev.txt') }}
   ```

3. **Consider merging backup into scraper workflow** as a post-step (same runner, sequential) — reduces workflow count, but couples concerns. **Recommendation: Keep separate for clarity**, just stagger times.

---

## 4. Production Secret Validation

### Current Plan (from IMPLEMENTATION_PLAN.md)

```python
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

### Required Environment Variables (Exact List)

| Variable | Purpose | Source |
|----------|---------|--------|
| `TELEGRAM_BOT_TOKEN` | Bot API token for notifications | Telegram @BotFather |
| `TELEGRAM_CHAT_ID` | Target chat/channel ID for messages | Telegram |
| `SMTP_HOST` | SMTP server hostname | Email provider |
| `SMTP_PORT` | SMTP server port (typically 587/465) | Email provider |
| `SMTP_USER` | SMTP authentication username | Email provider |
| `SMTP_PASSWORD` | SMTP authentication password | Email provider |
| `MOUN_PHONE` | MounakassatDZ portal login phone | Credentials |
| `MOUN_PASSWORD` | MounakassatDZ portal login password | Credentials |

**Also likely needed (not in list but used in codebase):**
- `MARCHES_STATE_PATH` — Path to Playwright session file (default `storage/marches_state.json`)
- `APP_DATABASE_URL` — Platform database URL (has default)
- `APP_BASE_URL` — Public base URL for canonical links
- `APP_ADMIN_PHONE/EMAIL/PASSWORD` — Bootstrap admin (optional)

### Safe Local Development Behavior

| Environment | `APP_ENV` | Validation Behavior |
|-------------|-----------|---------------------|
| Local dev | `development` (default) | **No validation** — all secrets optional, defaults used |
| Test | `test` | **No validation** — uses test fixtures/mocks |
| Staging | `staging` | **No validation** (per current plan) — ⚠️ **Gap** |
| Production | `production` | **Fail-fast** — all `REQUIRED_IN_PRODUCTION` must be set |

### Unresolved Risks

1. **Staging gap** — `APP_ENV=staging` bypasses validation but may use real credentials. Should staging also validate?
2. **No secret format validation** — Only presence checked; invalid token format fails later at runtime.
3. **Error message leaks secret names** — `RuntimeError` lists missing secret names (acceptable, but note for audit).
4. **Legacy pipeline secrets not validated** — `main.py` uses `MOUN_PHONE`, `MOUN_PASSWORD`, `MARCHES_STATE_PATH` but has no production mode concept.

### Recommended Corrections

**A. Extend validation to staging:**
```python
@property
def is_production_or_staging(self) -> bool:
    return self.app_env.lower() in ("production", "staging")

# In from_env():
if self.is_production_or_staging:
    missing = [k for k in REQUIRED_IN_PRODUCTION if not os.getenv(k)]
    if missing:
        raise RuntimeError(...)
```

**B. Add basic format validation (optional but recommended):**
```python
# Telegram bot token format: 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
if "TELEGRAM_BOT_TOKEN" in os.environ and not re.match(r"^\d+:[A-Za-z0-9_-]{35}$", os.getenv("TELEGRAM_BOT_TOKEN", "")):
    raise RuntimeError("TELEGRAM_BOT_TOKEN format invalid")
```

**C. Document all required vars in `.env.example` and `SECURITY.md`**

**D. Consider adding legacy pipeline validation** (separate PR, not Phase 1 blocker)

---

## 5. TLS Fix — Playwright/Crawler Configuration Verification

### Current Code (`crawlers/marches_publics_auth_crawler.py:59-67`)

```python
self._playwright = sync_playwright().start()
self._browser = self._playwright.chromium.launch(channel="msedge", headless=False)
self._context = self._browser.new_context(
    storage_state=str(self.state_path),
    ignore_https_errors=True,  # <-- REMOVE THIS
    viewport={"width": 1400, "height": 900},
)
```

### Exact Change Required

**Remove line 63 entirely:** `ignore_https_errors=True,`

### Expected Behavior After Fix

| Scenario | Before (with `ignore_https_errors=True`) | After (default `False`) |
|----------|------------------------------------------|-------------------------|
| Valid TLS cert (marches-publics.gov.dz) | ✅ Works | ✅ Works |
| Expired/invalid TLS cert | ✅ Works (insecure) | ❌ **Fails** — `net::ERR_CERT_*` |
| Self-signed cert (dev/staging) | ✅ Works | ❌ **Fails** |
| MITM attack (cert spoofing) | ✅ Succeeds (data compromised) | ❌ **Fails** — connection blocked |

### Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| `marches-publics.gov.dz` has valid cert | **High** (gov.dz uses valid Let's Encrypt/CA) | None | **Expected to work** |
| Cert expires between renewals | Low (Let's Encrypt auto-renews) | Crawler fails | Monitor; alert on crawler failure |
| Gov.dz uses unusual CA not in system trust | Very Low | Crawler fails | Add custom CA via `certifi` if needed |

### Verification Steps (Pre-merge)

1. **Local test:** Run crawler against `https://marches-publics.gov.dz` with `DRY_RUN=true` — verify it fetches pages
2. **Check cert:** `openssl s_client -connect marches-publics.gov.dz:443 -servername marches-publics.gov.dz </dev/null` — verify chain valid
3. **Fallback plan:** If cert issues arise, use Option B from plan (explicit CA bundle via `certifi.where()`) — **not** re-enable `ignore_https_errors`

### Recommended Correction

**Add a comment explaining the security rationale** (for future maintainers):

```python
self._context = self._browser.new_context(
    storage_state=str(self.state_path),
    # ignore_https_errors=False (default) — enforce TLS certificate validation
    # for data integrity when scraping official government portal.
    # If certificate issues arise, use certifi.where() for custom CA bundle
    # instead of disabling verification.
    viewport={"width": 1400, "height": 900},
)
```

---

## Summary: Required Corrections Before Stage B Approval

| # | Area | Correction | Effort |
|---|------|------------|--------|
| 1 | Backup encryption | Document unencrypted artifact limitation; plan encrypted storage for Phase 3 | 30 min docs |
| 2 | Restore safety | Implement `--force`, `--dry-run`, interactive confirm, SHA256 verification | 1 hour code |
| 3 | Workflow schedules | Stagger backup (02:00) and scraper (06:00); add pip cache to all | 15 min YAML |
| 4 | Secret validation | Extend to staging; add basic format checks; document all vars | 30 min code + docs |
| 5 | TLS fix | Remove flag; add explanatory comment; verify cert locally | 15 min code |

---

## Recommendation

**Conditional Approval:** Stage B may proceed **after** corrections 2, 3, 4, 5 are incorporated into the implementation plan. Correction 1 (backup encryption) is a documented limitation acceptable for MVP with Phase 3 remediation plan.

**Updated IMPLEMENTATION_PLAN.md** should reflect these corrections before Stage B begins.

---

**Next Step:** User to confirm approval with corrections incorporated, or request modifications.