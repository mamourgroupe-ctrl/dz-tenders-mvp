# Audit Report 03: Security

**Date:** 2026-11-08  
**Repository:** dz-tenders-mvp  
**Auditor:** Claude Opus 5.5

---

## Executive Summary

The codebase demonstrates **strong security fundamentals** for a read-heavy public platform: parameterized queries everywhere, Argon2id password hashing, CSRF double-submit cookies, rate limiting, secure headers, and input validation. The legacy pipeline has fewer protections (no auth, file-based lock) but operates in a controlled scheduled environment. **No critical vulnerabilities found**; several defense-in-depth improvements identified.

---

## Authentication & Authorization

### Platform (webapp/)

| Mechanism | Implementation | Location | Assessment |
|-----------|----------------|----------|------------|
| **Password Hashing** | Argon2id (via `argon2-cffi`) | `webapp/security.py:hash_password()` | ✅ Best practice; `verify_password()` constant-time |
| **Session Management** | Server-side sessions in `user_sessions` table; token = 32-byte URL-safe random | `webapp/security.py:create_session()` | ✅ Secure; `HttpOnly`, `SameSite=Lax`, `Secure` in prod |
| **CSRF Protection** | Double-submit cookie (`dz_csrf`) + form field validation | `webapp/security.py:validate_csrf()`, `webapp/web/routes_auth.py` | ✅ Proper; cookie `HttpOnly`, rotated on login |
| **Rate Limiting** | Fixed-window (DB-backed `rate_limit_events`); 5/login/15min per phone, 10/IP/15min | `webapp/security.py:RateLimiter`, `webapp/web/routes_auth.py` | ✅ Effective; per-phone + per-IP |
| **Phone Normalization** | E.164 format (`+213XXXXXXXXX`); rejects invalid Algerian numbers | `webapp/security.py:normalize_phone()` | ✅ Strict; prevents enumeration via format variance |
| **Open Redirect Prevention** | `safe_next_url()` allows only relative paths | `webapp/web/deps.py:safe_next_url()` | ✅ Blocks `//evil.com`, `https://evil.com` |
| **Role-Based Access** | `UserRole` enum (user/editor/support/admin); `current_user` dependency | `webapp/enums.py`, `webapp/web/deps.py` | ✅ Clear; admin routes not yet implemented |

### Legacy Pipeline
- **No authentication** — runs as scheduled CLI with env vars for secrets
- **Secrets**: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `SMTP_*`, `MOUN_PHONE`, `MOUN_PASSWORD` via `.env`
- **Playwright state file**: `storage/marches_state.json` (authenticated session) — **sensitive, gitignored**

---

## Input Validation & Injection Prevention

### SQL Injection

| Component | Protection | Evidence |
|-----------|------------|----------|
| **Platform API** (`api/repository.py`) | SQLAlchemy ORM + `text()` with bound params only | `ReadOnlyTenderRepository.list_tenders()` uses `stmt.where()`, `params()` |
| **Platform Web** (`webapp/search.py`, `webapp/repositories.py`) | SQLAlchemy ORM + `text()` with `:param` binding | `_join_fts()` uses `text(f"{FTS_TABLE} MATCH :fts_query").params(fts_query=...)` |
| **Legacy** (`storage/database.py`) | Parameterized `?` placeholders in all `execute()` calls | `save_many()`, `mark_sent()`, `register_failed_attempt()` all use `?` |
| **FTS5 MATCH** | User input → `build_fts_query()` → sanitized FTS syntax | `webapp/text.py:build_fts_query()` escapes quotes, prefixes terms |

**Test Coverage**: `tests/test_api.py:test_sql_injection_attempts()` — attempts `'; DROP TABLE tenders; --` return 422/empty, no execution.

### XSS Prevention

| Layer | Protection |
|-------|------------|
| **API** | Returns JSON; `Content-Type: application/json`; no HTML rendering |
| **Web (Jinja2)** | Auto-escaping enabled by default; `|safe` used only for trusted admin content |
| **Frontend (React)** | JSX auto-escapes; `dangerouslySetInnerHTML` **not used** |
| **Email Digest** | `html.escape()` on all user-derived fields (`notifications/digest.py:_render_row()`) |
| **Test** | `tests/test_phase1_routes.py:test_query_is_escaped()` — `<script>` → `<script>` |

### Path Traversal
- **Uploads**: `webapp/cli.py` uses `APP_UPLOAD_DIR` (config); `stored_name` = UUID + extension; no user-controlled path
- **Static Files**: Served via FastAPI `StaticFiles` from `webapp/static/` — no directory traversal

---

## Secrets Management

| Secret | Storage | Rotation | Audit |
|--------|---------|----------|-------|
| Telegram Bot Token | `.env` (local), Railway env (prod) | Rotated after 2024 leak (commit 61fd2d7) | ✅ Old token verified 401 |
| SMTP Password | `.env` / Railway | Not documented | ⚠️ No rotation policy |
| Mounakassat Credentials | `.env` / Railway | Not documented | ⚠️ No rotation policy |
| Playwright Session | `storage/marches_state.json` (file) | Manual re-login via `scripts/marches_login.py` | ⚠️ File gitignored but persists locally |
| Platform DB | SQLite file (`platform.db`) | N/A (read-only API) | ✅ No secrets in DB |
| Argon2 Hash | `users.password_hash` | Rehash on params change (`needs_rehash()`) | ✅ Handled |

**Finding**: `notifications/base.py:redact_secrets()` redacts `BOT_TOKEN_PATTERN` and env vars with `TOKEN`/`SECRET`/`KEY`/`PASSWORD` in name — **good defensive logging**.

---

## Transport & Headers

### Security Headers (Platform Web)
```python
# webapp/web/main.py (in create_app)
response.headers["X-Content-Type-Options"] = "nosniff"
response.headers["X-Frame-Options"] = "DENY"
response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; connect-src 'self'"
response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
```
**Test**: `tests/test_phase1_routes.py:test_security_headers()` — all present.

### API CORS
```python
# api/main.py:232
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True, ...)
```
**Test**: `tests/test_api.py:test_cors_headers()` — reflects origin, allows credentials.

### HTTPS Enforcement
- **Development**: `APP_COOKIE_SECURE=false` (`.env.example:57`)
- **Production**: `Settings(app_env="production").secure_cookies == True` (tested)
- **Proxy**: `APP_TRUST_PROXY=false` by default; enable behind known reverse proxy only

---

## Access Control (Plan-Gated Fields)

Implemented in `webapp/access.py:build_announcement_view()`:

| Field | Free Tier | Paid Tier (covered sector) | Paid Tier (uncovered sector) |
|-------|-----------|---------------------------|------------------------------|
| `title_ar`, `type`, `sector`, `wilaya`, `publish_date` | ✅ Visible | ✅ Visible | ✅ Visible |
| `issuer_name`, `deadline_at`, `description_ar`, `reference`, `attachments`, `source_url` | ❌ Hidden (`REASON_SUBSCRIPTION_REQUIRED`) | ✅ Visible | ❌ Hidden (`REASON_SECTOR_NOT_COVERED`) |

**Constants**: `REASON_SUBSCRIPTION_REQUIRED`, `REASON_SECTOR_NOT_COVERED`, `REASON_EXPIRED_SUBSCRIPTION`, `REASON_NOT_PUBLISHED`.

**Test Coverage**: `tests/test_phase1_routes.py` — `test_detail_free_hides_paid_fields`, `test_detail_paid_unlocks_fields_for_covered_sector`, `test_detail_paid_stays_locked_for_uncovered_sector`, `test_detail_expired_subscription_is_locked`.

---

## Crawler Security (Legacy)

| Crawler | Auth Method | Risks | Mitigations |
|---------|-------------|-------|-------------|
| `ade_crawler.py` | None (public) | None | Public site |
| `mounakassat_crawler.py` | Form login (phone/password from `.env`) | Credentials in env; session reused | `MOUN_PHONE`/`MOUN_PASSWORD` not in repo; progress tracking for resume |
| `marches_publics_auth_crawler.py` | Playwright + saved session (`storage/marches_state.json`) | Session file = bearer token; Playwright launches Edge (headless=False) | File gitignored; `ignore_https_errors=True` (⚠️ cert validation disabled); single page reuse |

**Finding SEC-01 (MEDIUM)**: `marches_publics_auth_crawler.py:60` uses `ignore_https_errors=True` — **disables TLS certificate validation** for the official procurement portal. Should use valid certs or pin CA.

**Finding SEC-02 (LOW)**: `marches_publics_auth_crawler.py:60` launches `channel="msedge", headless=False` — requires GUI/Edge installed; not server-friendly. Should use `headless=True` in production.

---

## Dependency Security

| Tool | Status |
|------|--------|
| **Snyk** | Referenced in CLAUDE.md ("Check dependencies with Snyk before adding them") — not automated in CI |
| **pip-audit / safety** | Not in CI |
| **npm audit** | Not in CI (frontend deps in `package.json`) |
| **Dependabot** | Not configured |

**Current Deps** (from `requirements.txt`, `package.json`): All pinned to reasonable ranges; no known CVEs in quick check (but no automated scanning).

---

## Audit Findings

| ID | Severity | Finding | File/Line | Evidence | Recommendation |
|----|----------|---------|-----------|----------|----------------|
| SEC-01 | MEDIUM | TLS cert validation disabled for marches-publics.gov.dz | `crawlers/marches_publics_auth_crawler.py:60` | `ignore_https_errors=True` in `new_context()` | Remove or use custom CA bundle; enable in prod |
| SEC-02 | LOW | Playwright launches headed Edge browser | `crawlers/marches_publics_auth_crawler.py:60` | `headless=False` | Use `headless=True`; add `args=["--no-sandbox"]` for containers |
| SEC-03 | LOW | No automated dependency vulnerability scanning | CI (`.github/workflows/scraper.yml`) | Only runs `pytest`; no `pip-audit`/`npm audit` | Add `pip-audit` and `npm audit` to CI; consider Dependabot |
| SEC-04 | LOW | Session cookies not `Secure` in development | `.env.example:57` | `APP_COOKIE_SECURE=false` | Document: must be `true` in prod; add startup check |
| SEC-05 | LOW | Rate limiter uses fixed window (burst at boundary) | `webapp/security.py:85` | `RateLimiter.hit()` counts per 15-min window | Consider sliding window or token bucket for smoother limiting |
| SEC-06 | INFO | No Content-Security-Policy `report-uri` | `webapp/web/main.py` | CSP lacks reporting endpoint | Add `report-uri /csp-report` endpoint for monitoring |
| SEC-07 | INFO | No HSTS header | `webapp/web/main.py` | Missing `Strict-Transport-Security` | Add `Strict-Transport-Security: max-age=31536000; includeSubDomains` in prod |
| SEC-08 | INFO | Playwright session file unencrypted | `storage/marches_state.json` | Contains authenticated cookies | Encrypt at rest; or use keyring/secret manager |

---

## Compliance Notes

| Standard | Status | Gaps |
|----------|--------|------|
| **OWASP Top 10 (2021)** | ✅ Mostly covered | A01: Broken Access Control — admin routes not implemented; A05: Security Misconfiguration — no HSTS, CSP reporting |
| **GDPR** | ⚠️ Partial | No data export/delete endpoint; no privacy policy page; `audit_logs` stores `ip_hash` (pseudonymous) |
| **Algerian Data Localization** | ✅ SQLite on local disk | If migrating to cloud Postgres, must ensure data stays in DZ |

---

## Recommendations Priority

1. **SEC-01**: Fix TLS validation for marches-publics crawler (production data integrity)
2. **SEC-03**: Add `pip-audit` + `npm audit` to GitHub Actions (supply chain)
3. **SEC-04**: Enforce `Secure` cookies in production via startup validation
4. **SEC-08**: Encrypt Playwright session file or migrate to secret manager
5. **SEC-06/07**: Add CSP reporting + HSTS for defense-in-depth
6. **SEC-05**: Upgrade rate limiter to sliding window (better UX, same security)