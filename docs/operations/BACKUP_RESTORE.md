# Backup & Restore Procedures

**Version:** 2.0
**Date:** 2026-11-08
**Status:** MVP — Local backups only; encrypted off-site storage planned for Phase 3

---

## Overview

This document describes the backup and restore procedures for the DZ-TENDERS-MVP databases and sensitive assets.

**Key Principle:** All backups are **local only** — stored outside the Git repository on the local filesystem. No cloud uploads, no GitHub Actions artifacts, no third-party storage in MVP.

### Assets Covered

| Asset | Path | Description | Backup Method |
|-------|------|-------------|---------------|
| Legacy tenders DB | `storage/tenders.db` | Scraped tender data, delivery tracking | SQLite `.backup()` API |
| Platform DB | `storage/platform.db` | Public portal data (announcements, users, subscriptions) | SQLite `.backup()` API |
| Marches session | `storage/marches_state.json` | Playwright authenticated session | File copy (via backup script) |
| Uploads | `storage/uploads/` | Payment proofs, attachments | `tar.gz` archive |

### Assets NOT Covered (Git-tracked)

| Asset | Path | Reason |
|-------|------|--------|
| Taxonomy | `data/targets.json` | Versioned in Git |
| Source code | All `.py`, `.ts`, `.tsx` | Versioned in Git |
| Configuration templates | `.env.example` | Versioned in Git |

---

## Backup Procedure

### Automated (Daily via Windows Task Scheduler)

**Schedule:** Daily at 02:00 local time (configurable)
**Retention:** Configurable (default: 30 days manual cleanup)
**Location:** `~/dz-tenders-backups/` (outside repository, configurable via `DZ_TENDERS_BACKUP_DIR`)

#### Setup Windows Task Scheduler (One-time)

1. **Open Task Scheduler** (`taskschd.msc`)
2. **Create Basic Task** → Name: "DZ-TENDERS Daily Backup"
3. **Trigger:** Daily, 02:00 AM (or your preferred time)
4. **Action:** Start a Program
   - Program: `powershell.exe`
   - Arguments: 
     ```
     -ExecutionPolicy Bypass -Command "& 'D:\07_Programming\vccode\dz-tenders-mvp\scripts\backup_db.py'"
     ```
   - Start in: `D:\07_Programming\vccode\dz-tenders-mvp`
5. **Finish** → Open Properties → **Run whether user is logged on or not** → Check "Run with highest privileges"
6. **Conditions/Power:** Uncheck "Start only if on AC power" (optional, for laptops)

#### PowerShell Equivalent (for automation)

```powershell
# Register scheduled task (run as Administrator)
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument '-ExecutionPolicy Bypass -Command "& ''D:\07_Programming\vccode\dz-tenders-mvp\scripts\backup_db.py''"'
$trigger = New-ScheduledTaskTrigger -Daily -At 02:00
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId (whoami) -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName "DZ-TENDERS Daily Backup" -Action $action -Trigger $trigger -Settings $settings -Principal $principal
```

### Manual (Local Development)

```powershell
# Back up all databases (uses default ~/dz-tenders-backups/)
python scripts/backup_db.py

# Back up to custom directory
$env:DZ_TENDERS_BACKUP_DIR = "D:\Backups\dz-tenders"
python scripts/backup_db.py
```

**Output location:** `~/dz-tenders-backups/` (or custom directory)
**Format:** `{database}_{YYYYMMDD_HHMMSS}.bak`
**Manifest:** `{database}_{YYYYMMDD_HHMMSS}.manifest.json` (contains SHA256)
**Uploads:** `uploads_{YYYYMMDD_HHMMSS}.tar.gz` + `.manifest.json`

### Backup Verification

Each backup includes a **manifest file** with:
- SHA256 checksum of the backup file
- Table list and row counts
- Creation timestamp (UTC)
- File size

```
[OK] Backup created: ~/dz-tenders-backups/tenders_20261108_020000.bak (2048576 bytes)
[OK] Manifest written: ~/dz-tenders-backups/tenders_20261108_020000.manifest.json
```

**Manifest content example:**
```json
{
  "backup_file": "tenders_20261108_020000.bak",
  "created_utc": "2026-11-08T02:00:00.123456+00:00",
  "tables": ["tenders", "sent_tenders", "failed_deliveries", "blocked_tenders"],
  "row_counts": {"tenders": 1234, "sent_tenders": 567},
  "sha256": "a1b2c3d4e5f6...",
  "size_bytes": 2048576
}
```

---

## Restore Procedure

### Safety Features

The restore script (`scripts/restore_db.py`) enforces:

1. **Manifest verification** — SHA256 from manifest must match backup file
2. **SQLite integrity check** — Backup must be valid SQLite database
3. **Logical consistency** — Manifest tables/counts must match actual backup content
4. **No silent overwrite** — Interactive confirmation required by default
5. **Safety copy** — Pre-restore copy of existing database preserved
6. **Dry-run mode** — Preview without changes
7. **Rollback on failure** — Automatic safety copy restoration if restore fails

### Commands

```powershell
# 1. DRY RUN — verify backup, show what would change (SAFE)
python scripts/restore_db.py ~/dz-tenders-backups/tenders_20261108_020000.bak storage/tenders.db --dry-run

# 2. INTERACTIVE — prompts for confirmation before overwrite
python scripts/restore_db.py ~/dz-tenders-backups/tenders_20261108_020000.bak storage/tenders.db

# 3. FORCE — no prompt (CI/automation only, use with caution)
python scripts/restore_db.py ~/dz-tenders-backups/tenders_20261108_020000.bak storage/tenders.db --force
```

### Restore Output Example

```
[INFO] Locating manifest...
  Manifest: ~/dz-tenders-backups/tenders_20261108_020000.manifest.json
  Created:  2026-11-08T02:00:00.123456+00:00
[INFO] Verifying SHA256 checksum...
  [OK] SHA256 verified: a1b2c3d4...
[INFO] Verifying SQLite integrity and structure...
   Tables: ['tenders', 'sent_tenders', 'failed_deliveries', 'blocked_tenders']
   Row counts: {'tenders': 1234, 'sent_tenders': 567}
   Size: 2048576 bytes
  [OK] Manifest matches backup content (logical consistency)

[INFO] Existing destination (storage/tenders.db):
   Tables: ['tenders', 'sent_tenders', 'failed_deliveries', 'blocked_tenders']
   Row counts: {'tenders': 1100, 'sent_tenders': 500}
   Size: 1950000 bytes

[WARN] This will OVERWRITE storage/tenders.db
   A safety copy will be created first.

Type 'YES' to confirm restoration: YES
[SAFETY] Safety copy created: storage/tenders.pre_restore_20261108_120500.bak
[OK] Restored ~/dz-tenders-backups/tenders_20261108_020000.bak -> storage/tenders.db
   Verified: {'tenders': 1234, 'sent_tenders': 567}, tables: ['tenders', 'sent_tenders', 'failed_deliveries', 'blocked_tenders']
```

---

## Restoring Uploads

```powershell
# Extract uploads backup
tar -xzf ~/dz-tenders-backups/uploads_20261108_020000.tar.gz -C storage/

# Verify
ls -la storage/uploads/
```

---

## Quarterly Restore Drill

**Schedule:** First Monday of each quarter
**Owner:** DevOps / Backend Lead
**Procedure:**

1. [ ] Identify latest backup for each database in `~/dz-tenders-backups/`
2. [ ] Run dry-run restore to verify backup integrity
3. [ ] Restore to temporary location (not production)
4. [ ] Verify row counts and spot-check data
5. [ ] Document results in `docs/operations/restore_drill_YYYY_QN.md`
6. [ ] Clean up temporary databases

### Drill Checklist

- [ ] `tenders.db` restored and verified
- [ ] `platform.db` restored and verified
- [ ] `marches_state.json` restored (test crawler login)
- [ ] `uploads/` extracted and accessible
- [ ] Application starts with restored databases
- [ ] API returns expected data
- [ ] No errors in logs

---

## Disaster Recovery Scenarios

### Scenario 1: Database Corruption

**Detection:** Application errors, failed queries, checksum mismatch
**Response:**
1. Stop application
2. Identify last good backup: `ls -lt ~/dz-tenders-backups/`
3. Run restore with dry-run first
4. Execute restore
5. Restart application
6. Verify data integrity

### Scenario 2: Accidental Data Deletion

**Detection:** Missing tenders, users, or subscriptions
**Response:**
1. Identify time of deletion
2. Select backup from before deletion
3. Run restore (consider restoring to temp DB first, then copying specific rows)
4. Verify recovered data

### Scenario 3: Complete Environment Loss

**Detection:** Server/VM destroyed, local backups unavailable
**Response:**
1. Provision new environment
2. Clone repository
3. Install dependencies
4. **Restore databases from external backup copy** (you must maintain off-site copies manually in MVP)
5. Restore uploads
6. Re-create crawler session (`python scripts/marches_login.py`)
7. Deploy application

> ⚠️ **MVP Limitation:** Local backups only. If the machine is lost, backups are lost. Phase 3 will add encrypted off-site storage.

---

## Windows Folder Permissions

For the backup directory (`~/dz-tenders-backups/` or custom):

```powershell
# Restrict to current user only (run in PowerShell as Admin)
$backupDir = "$env:USERPROFILE\dz-tenders-backups"
icacls $backupDir /inheritance:r
icacls $backupDir /grant:r "$env:USERNAME:(OI)(CI)F"
icacls $backupDir /remove "Authenticated Users" "Users" "Everyone" 2>$null
```

**Result:** Only the current Windows user (and SYSTEM/Administrators) can read/write backups.

---

## Retention & Cleanup

**MVP:** Manual cleanup — no automated retention policy.

```powershell
# Keep last 30 backups per database (example)
$keep = 30
$backupDir = "$env:USERPROFILE\dz-tenders-backups"
Get-ChildItem $backupDir\*.bak | Sort-Object LastWriteTime -Descending | Select-Object -Skip $keep | Remove-Item -Force
Get-ChildItem $backupDir\*.manifest.json | Sort-Object LastWriteTime -Descending | Select-Object -Skip $keep | Remove-Item -Force
Get-ChildItem $backupDir\uploads_*.tar.gz | Sort-Object LastWriteTime -Descending | Select-Object -Skip $keep | Remove-Item -Force
Get-ChildItem $backupDir\uploads_*.manifest.json | Sort-Object LastWriteTime -Descending | Select-Object -Skip $keep | Remove-Item -Force
```

**Phase 3:** Configurable lifecycle policies in encrypted object storage.

---

## Current Limitations (MVP)

| Limitation | Impact | Planned Resolution |
|------------|--------|-------------------|
| **Local-only backups** | If local disk fails, no recovery | Phase 3: Encrypted S3/GCS/Azure Blob with KMS |
| **No encryption at rest** | Local backups readable by anyone with filesystem access | Phase 3: Age/GPG encryption before write |
| **No cross-region replication** | Regional outage = backup loss | Phase 3: Multi-region bucket replication |
| **Manual retention** | Older backups accumulate | Phase 3: Configurable lifecycle policies |
| **Manual uploads backup** | Large uploads may be missed | Phase 3: Incremental sync to object storage |
| **No automated scheduling** | Requires Task Scheduler setup | Documented above; Phase 3: native scheduler |

---

## Security Notes

- **Never commit backup files to Git** — `storage/backups/` is in `.gitignore`; backups go to `~/dz-tenders-backups/`
- **Never log SHA256 of production data** in shared CI logs (restore script prints only first 16 chars)
- **Restrict backup directory permissions** to current user only (see above)
- **Rotate encryption keys** when Phase 3 encryption is implemented
- **No cloud uploads in MVP** — all backup operations are local filesystem only

---

## Quick Reference

| Task | Command |
|------|---------|
| Create backup (default dir) | `python scripts/backup_db.py` |
| Create backup (custom dir) | `$env:DZ_TENDERS_BACKUP_DIR="D:\Backups"; python scripts/backup_db.py` |
| List backups | `ls -lt ~/dz-tenders-backups/` |
| Verify backup (dry-run) | `python scripts/restore_db.py <backup> <dest> --dry-run` |
| Restore (interactive) | `python scripts/restore_db.py <backup> <dest>` |
| Restore uploads | `tar -xzf ~/dz-tenders-backups/uploads_<timestamp>.tar.gz -C storage/` |
| Emergency safety copy | `cp storage/tenders.db storage/tenders.emergency_$(date +%s).bak` |
| Setup Task Scheduler | See "Automated (Daily via Windows Task Scheduler)" above |

---

## Related Files

- `scripts/backup_db.py` — Backup creation with SHA256 manifest and verification
- `scripts/restore_db.py` — Safe restore with manifest SHA256, dry-run, confirmation, rollback
- `.github/workflows/ci.yml` — CI pipeline with security scanning (no backup)
- `.github/dependabot.yml` — Weekly dependency updates
- `docs/phase1-security/IMPLEMENTATION_PLAN.md` — Phase 1 implementation details
- `docs/phase1-security/FINAL_ACCEPTANCE_REVIEW.md` — Pre-PR acceptance review

---

## Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-11-08 | Initial (GitHub Actions artifact-based) |
| 2.0 | 2026-11-08 | **Local-only backups**, SHA256 manifests, Windows Task Scheduler, removed GitHub artifact uploads |