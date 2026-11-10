# Phase 1 Security & Data Safety — Remaining Risks

**Date:** 2026-11-08
**Status:** Post-implementation risk assessment
**Scope:** Risks acknowledged but not addressed in Phase 1 (deferred to Phase 2/3)

---

## Risk Classification

| Priority | Description |
|----------|-------------|
| **Critical** | Active vulnerability, immediate exploitation possible |
| **High** | Significant exposure, likely exploitation path |
| **Medium** | Moderate exposure, requires specific conditions |
| **Low** | Minor exposure, defense-in-depth improvement |

---

## Remaining Risks After Phase 1

### 1. Local-Only Backup — No Off-Site Recovery (Medium)

**Description:** Backups stored only on local filesystem (`~/dz-tenders-backups/`). If the machine is lost/destroyed (theft, hardware failure, ransomware), all backups are lost.

**Impact:** Complete data loss in disaster scenario (RPO = forever)

**Phase 1 Mitigation:** Documented in `BACKUP_RESTORE.md` as MVP limitation

**Planned Resolution (Phase 3):**
- Encrypted upload to S3/GCS/Azure Blob with KMS
- Cross-region replication
- Automated lifecycle policies

**Residual Risk:** Accepted for MVP — manual off-site copy recommended for critical deployments

---

### 2. No Encryption at Rest for Local Backups (Medium)

**Description:** Backup files (`.bak`, `.tar.gz`, `.manifest.json`) stored unencrypted on local disk. Any user/process with filesystem read access can extract tender data, user data, crawler sessions.

**Impact:** Data exposure if host compromised or backup directory permissions misconfigured

**Phase 1 Mitigation:** 
- Backup directory permissions restricted to current user only (documented)
- SHA256 manifests detect tampering
- No cloud upload reduces attack surface

**Planned Resolution (Phase 3):**
- Age/GPG encryption before write
- Key management via OS keyring or HSM

**Residual Risk:** Accepted for MVP with documented permission hardening

---

### 3. No Automated Retention/Cleanup (Low)

**Description:** Backups accumulate indefinitely in `~/dz-tenders-backups/`. No automated rotation.

**Impact:** Disk space exhaustion over time

**Phase 1 Mitigation:** Manual cleanup commands documented in `BACKUP_RESTORE.md`

**Planned Resolution (Phase 3):** Configurable lifecycle policies in object storage

**Residual Risk:** Low — disk space monitoring recommended

---

### 4. Staging Environment Secret Validation Gap (Medium)

**Description:** `Settings.is_staging_or_production` validates secrets for both staging and production, but staging may use real credentials without full production hardening.

**Impact:** Staging deployment with missing/invalid secrets fails fast (good), but staging may not have same network/security controls as production

**Phase 1 Mitigation:** Validation extended to staging; format checks added

**Planned Resolution (Phase 2):** Separate staging infrastructure with production-parity security controls

**Residual Risk:** Medium — staging treated as production for secret validation

---

### 5. Legacy Pipeline (`main.py`) Secret Validation Missing (Medium)

**Description:** Secret validation implemented in `webapp/config.py` (platform) but not in legacy scraper entry point (`main.py`). Legacy pipeline uses `MOUN_PHONE`, `MOUN_PASSWORD`, `MARCHES_STATE_PATH` without startup validation.

**Impact:** Legacy scraper may fail at runtime with cryptic errors instead of fast fail

**Phase 1 Mitigation:** Platform (primary API) validated; legacy is secondary

**Planned Resolution (Phase 2):** Add validation to `main.py` or shared config module

**Residual Risk:** Medium — legacy pipeline less robust than platform

---

### 6. TLS Certificate Failure Not Handled Gracefully (Low)

**Description:** If `marches-publics.gov.dz` TLS certificate expires or changes CA, crawler fails hard with `net::ERR_CERT_*` instead of graceful degradation or alerting.

**Impact:** Scraper stops collecting tenders until cert issue resolved

**Phase 1 Mitigation:** Comment documents `certifi.where()` fallback option

**Planned Resolution (Phase 2):** Certificate monitoring + alerting + automatic CA bundle update

**Residual Risk:** Low — gov.dz uses standard Let's Encrypt with auto-renewal

---

### 7. No Secret Rotation Automation (Medium)

**Description:** Secrets (Telegram bot token, SMTP credentials, crawler credentials) rotated manually. No automated rotation or expiry tracking.

**Impact:** Long-lived credentials increase blast radius if compromised

**Phase 1 Mitigation:** Documented rotation procedure needed (not yet created)

**Planned Resolution (Phase 2):** Secret rotation runbook + automation (HashiCorp Vault / AWS Secrets Manager / Azure Key Vault)

**Residual Risk:** Medium — manual process dependent on team discipline

---

### 8. Single `.env` File for All Environments (Low)

**Description:** No `.env.staging`, `.env.production` separation. Environment determined by `APP_ENV` variable only.

**Impact:** Accidental production secret use in development (or vice versa)

**Phase 1 Mitigation:** Validation only runs in staging/production; development uses defaults

**Planned Resolution (Phase 2):** Environment-specific `.env` files with gitignore patterns

**Residual Risk:** Low — current pattern works with discipline

---

### 9. GitHub Actions Runner Trust (Low)

**Description:** CI runs on GitHub-hosted runners (`ubuntu-latest`). Supply chain risk if runner image compromised.

**Impact:** Build environment compromise could inject malicious code

**Phase 1 Mitigation:** Dependency scanning (pip-audit, npm audit), pinned action versions (@v4), no secrets in CI

**Planned Resolution (Phase 3):** Self-hosted runners or GitHub Actions Runner Controller for isolation

**Residual Risk:** Low — industry standard practice, low likelihood

---

### 10. No Application-Level Audit Logging (Medium)

**Description:** Security events (login attempts, secret access, backup/restore operations, admin actions) not logged to tamper-evident store.

**Impact:** Forensic investigation limited; insider threat detection absent

**Phase 1 Mitigation:** None — out of scope for Phase 1

**Planned Resolution (Phase 2):** Structured audit logging to append-only store (CloudWatch, Elastic, Splunk)

**Residual Risk:** Medium — compliance gap for audit requirements

---

## Risk Acceptance Summary

| Risk | Priority | Accepted for MVP? | Phase Target |
|------|----------|-------------------|--------------|
| No off-site backup | Medium | ✅ Yes (documented) | Phase 3 |
| No backup encryption at rest | Medium | ✅ Yes (permissions hardened) | Phase 3 |
| No automated retention | Low | ✅ Yes (manual documented) | Phase 3 |
| Staging secret validation gap | Medium | ⚠️ Partial (validated but infra parity missing) | Phase 2 |
| Legacy pipeline validation | Medium | ✅ Yes (platform primary) | Phase 2 |
| TLS cert failure handling | Low | ✅ Yes (fallback documented) | Phase 2 |
| Secret rotation automation | Medium | ❌ No (manual process) | Phase 2 |
| Single `.env` file | Low | ✅ Yes (works with discipline) | Phase 2 |
| GitHub runner trust | Low | ✅ Yes (industry standard) | Phase 3 |
| No audit logging | Medium | ❌ No (compliance gap) | Phase 2 |

---

## Recommendations for Phase 2

1. **Priority 1:** Implement secret rotation runbook + automation
2. **Priority 2:** Add audit logging for security events
3. **Priority 3:** Extend validation to legacy pipeline (`main.py`)
4. **Priority 4:** Environment-specific `.env` files
5. **Priority 5:** Certificate monitoring/alerting

---

## Recommendations for Phase 3

1. **Priority 1:** Encrypted off-site backup storage (S3/GCS + KMS)
2. **Priority 2:** Backup encryption at rest (local + remote)
3. **Priority 3:** Automated retention/lifecycle policies
4. **Priority 4:** Self-hosted CI runners
5. **Priority 5:** Cross-region backup replication

---

## Sign-Off

**Phase 1 Implementation:** Complete with documented remaining risks
**Risk Acceptance:** Acknowledged by team for MVP scope
**Next Review:** Phase 2 planning session

*This document should be reviewed and updated at each phase gate.*