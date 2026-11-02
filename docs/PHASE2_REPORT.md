# Phase 2 — Accounts, phone OTP, subscriptions and manual payments

**Status:** complete · **Branch:** `arena/4912d33a-dz-tenders-mvp` (Arena session branch; the name is fixed by the environment) · **Date:** 2026-11-02

Phase 2 adds the self-service half of the platform on the same stack used in
Phase 1 (FastAPI, SQLAlchemy 2.0, Jinja2, SQLite by default, PostgreSQL in
production). Every new flow is covered by tests; everything that depends on a
credential, a real bank account or a commercial price stays an explicitly
marked placeholder.

---

## 1. What changed

### 1.1 Security fixes first

The security items required at the start of the phase were done before the
account flows, so the new features build on them:

| Issue | Fix | Test |
| --- | --- | --- |
| Crawlers disabled TLS verification (`verify=False`) | New `crawlers/http.py` client performs verified TLS by default; verification can only be relaxed per source (`verify_tls`) or through an explicit `CRAWLER_VERIFY_TLS=false` global, and a CA bundle can be supplied. Both crawlers now use it. | `test_no_crawler_disables_tls_verification`, `test_verification_is_enabled_by_default`, `test_ca_bundle_is_honoured`, `test_per_source_opt_out`, `test_global_switch` |
| SELECT-then-INSERT race in `storage/database.py:add_tender` | Unique index on the tender identity plus an atomic upsert; concurrent inserts keep one row and refresh `last_seen`. | `test_parallel_inserts_keep_one_row`, `test_duplicate_insert_refreshes_last_seen` |
| Missing security headers | `X-Content-Type-Options`, `X-Frame-Options: DENY`, CSP, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy` on web and API responses. | `test_web_responses_carry_security_headers`, `test_api_security_headers` |
| Open auth/search/contact endpoints | Database-backed rate limiter (hashed IP, fixed window) on registration, login, password reset, OTP resend, proof upload, keyword search, archive browsing and the contact form. | `test_search_rate_limit`, `test_archive_browsing_is_rate_limited`, `test_contact_rate_limit`, plus the OTP cooldown tests |

`crawlers/http.py` is the only place that builds a `requests` session for
crawlers, which makes a future regression easy to spot in review.

### 1.2 Accounts

New module `webapp/accounts.py` (no FastAPI imports, so it is reusable by the
CLI and the future worker):

* **Registration** — company name, phone, email, password (argon2id, minimum
  8 characters), at least one sector, explicit terms acceptance. The account is
  created **inactive** (`is_active=False`) until the phone is verified.
* **Phone OTP** — six-digit code, TTL 10 minutes, 5 wrong attempts allowed,
  60-second resend cooldown. Delivery goes through a pluggable provider:
  `console` (logs and in-memory outbox, the default) or `webhook`
  (Bearer-authenticated POST). No SMS account is invented.
* **Email verification** — single-use token, 48-hour lifetime, sent after phone
  verification; `GET /verifier-email?token=…` marks the address verified and a
  second use reports «استُعمل هذا الرابط».
* **Login** — phone + password. Correct credentials on an inactive account are
  redirected to `/inscription/verifier` instead of being rejected, so the user
  resumes verification. Sessions are opaque random tokens hashed in
  `user_sessions`, with expiry and revocation.
* **Password reset** — phone + OTP only (`/mot-de-passe-oublie` →
  `/reinitialiser`); an unknown phone returns the same neutral page
  («إن كان الرقم مسجلاً…»). A successful reset revokes **every** session of the
  account.
* **Pending-phone cookie** — HttpOnly, `SameSite=Lax`, 30-minute lifetime,
  scoped to the whole site (`/`) so the same cookie drives both phone
  verification and password reset.

Routes live in `webapp/web/routes_accounts.py` and are mounted by
`webapp/web/main.py`:

| Route | Purpose |
| --- | --- |
| `GET/POST /inscription` | Registration form and submission |
| `GET/POST /inscription/verifier` | OTP entry, verifies phone, logs the user in |
| `POST /inscription/renvoyer` | Resend OTP (cooldown + rate limit) |
| `GET /verifier-email` | Email confirmation link |
| `GET/POST /mot-de-passe-oublie` | Request a reset code |
| `GET/POST /reinitialiser` | Set a new password with the OTP |
| `GET /tableau-de-bord` | Subscriber dashboard |
| `POST /tableau-de-bord/alertes` | Alert preferences (frequency, wilayas) |
| `POST /tableau-de-bord/secteurs` | Replace sectors of interest |
| `POST /tableau-de-bord/sauvegardes/{id}` | Save/unsave an announcement |
| `GET /desabonnement?token=…` | One-click alert unsubscribe (no login) |

The inactive flows are excluded from indexing with `X-Robots-Tag`/meta noindex
and a dedicated `noindex` path list in `webapp/web/main.py`.

### 1.3 Plans, quotes and manual payments

`webapp/billing.py` owns every money rule; templates only display computed
values.

* Prices come from the seeded `plans` table — **placeholders** flagged by
  `is_price_placeholder`. No amount is hardcoded in the code.
* `quote()` = plan price for the period + `extra_sector` add-on for every sector
  above the plan's included limit (800 DZD/month, 9,600 DZD/year per extra
  sector with the seeded placeholder add-on).
* Plans: Free, Bronze (1 sector), Silver (4), Gold (6), Premium (10),
  Platinum (all), auctions-only, plus the extra-sector add-on. Annual prices are
  the seeded annual amounts (the brief's discount is reflected there).
* Methods: bank transfer, postal account, cash. Transfers require a reference
  (3–120 characters) so staff can match the receipt.
* Checkout (`GET/POST /abonnement`) creates a **pending subscription** and a
  **pending payment together**, redirecting to `/paiement/{id}` with private
  payment instructions.
* Proof upload (`POST /paiement/{id}/preuve`) validates, in order: non-empty,
  ≤ 5 MiB (`APP_MAX_UPLOAD_BYTES`), magic bytes must be PDF/JPEG/PNG, declared
  MIME type must agree with the bytes. Files are stored under
  `APP_UPLOAD_DIR/payments/` with a random name, mode `0640`, and a SHA-256
  digest; the client filename is kept only as sanitised metadata.
  `GET /paiement/{id}/preuve` serves a proof only to its owner or to
  admin/support staff, and resolves the path with a traversal guard.
* Staff queue (`GET /admin/paiements`, `POST /admin/paiements/{id}/verifier`),
  restricted to `admin` and `support`. Approving sets the payment verified,
  activates the subscription, **cancels any other active subscription of the
  same user**, starts the clock (one calendar month or twelve) and writes an
  `audit_logs` entry. Rejection cancels the pending subscription. A payment can
  only be processed once, and approval requires an attached proof.
* Free-plan checkout and unknown/duplicate sector selections are rejected with
  Arabic messages.

### 1.4 Maintenance job — expiry and renewal reminders

`billing.run_maintenance()` is idempotent:

1. active subscriptions whose `ends_at` has passed become `expired`;
2. active subscriptions ending within `APP_RENEWAL_REMINDER_DAYS` (7 by
   default) receive **one** renewal email, recorded in `reminder_sent_at`;
3. a transport failure does not set the marker, so the next tick retries.

Exposed as `python -m webapp.cli maintenance [--days N]`, which builds the
configured email provider, renders the Arabic `renewal_email`, and prints
`{'expired': …, 'reminders_sent': …, 'reminders_failed': …}`. It is the job a
cron entry or the Phase 3 scheduler will call daily.

### 1.5 Dashboard

`/tableau-de-bord` shows the active plan and end date (or the free-plan
callout), sectors of interest, saved announcements, alert frequency/wilayas and
payment history with statuses. All POST actions are CSRF-protected and
rate-limited where relevant.

### 1.6 PostgreSQL search path

Phase 2 also lands the required PostgreSQL branch of the search interface:

* `webapp/search.py` selects `postgres` → `fts5` → `like` at runtime, with the
  same Arabic normalisation and the same article/hamza variants.
* Migration `879e89a1df33` adds `ix_announcements_search_tsv` (GIN on
  `to_tsvector('simple', search_text)`) and, **only when `pg_trgm` is
  installed**, `ix_announcements_search_trgm` (GIN trigram) for typo-tolerant
  recall. The trigram branch is guarded, never assumed.
* `tests/test_phase2_postgres_search.py` migrates and searches a real
  PostgreSQL 16 cluster; CI now runs a `postgres:16` service container and sets
  `TEST_POSTGRES_URL`, so the `pg_trgm` test is exercised there too
  (`psycopg[binary]` added to `requirements.txt`).

### 1.7 Data model and migration

Alembic revision `879e89a1df33_phase_2_accounts_billing_and_contact.py`
(replaces the earlier draft `9b2be8498795`) adds:

| Table / column | Notes |
| --- | --- |
| `contact_messages` | Contact-form inbox with status, hashed IP, index on `created_at` |
| `user_sectors` | Many-to-many interests, unique `(user_id, sector_id)` |
| `one_time_tokens.destination`, `attempts`, `sent_at` | OTP/email tokens now carry the destination, attempt counter (`server_default='0'`) and delivery timestamp, with a purpose index |
| `payments.proof_filename`, `proof_original_name`, `proof_sha256`, `proof_content_type`, `proof_size_bytes` | Proof metadata; the file itself is never in the database |
| `subscriptions.reminder_sent_at` | Idempotent renewal reminders |

Postgres-specific parts of the migration (expression index, optional trigram
index, `pg_trgm` creation attempt) are hand-written; `migrations/env.py` keeps
them out of autogenerate. `alembic upgrade head` + `alembic check` are clean on
fresh SQLite **and** fresh PostgreSQL 16.

``storage/platform.db`` was re-seeded: **69 wilayas** (codes 1–69). The 11 new
wilayas follow Law 26-06 (Journal Officiel no. 25, 5 April 2026) and Presidential
Decree 26-206 (JO no. 40, 3 June 2026); the transition period for the mother
wilayas runs until 31 December 2026. `APP_WILAYAS_FILE` remains the override.

### 1.8 Templates and styling

Nine new Arabic RTL templates extending `base.html`: `register.html`,
`verify_phone.html`, `forgot_password.html`, `reset_password.html`,
`dashboard.html`, `subscribe.html`, `payment.html`, `admin_payments.html`,
`message.html`. Existing pages were adjusted: `pricing.html` CTAs now point to
`/abonnement?plan=<code>`, `login.html` links to registration and reset (and
shows the `?reset=1` confirmation), `header.html` shows the account name and a
«تسجيل» entry, and `detail.html` gained the save/unsave button. Roughly 230
lines were appended to `webapp/static/css/app.css` for forms, tables, badges and
the payment timeline, keeping the navy/gold/teal identity.

### 1.9 Configuration

`.env.example` gained the Phase 2 block: search/contact limits, OTP TTL,
attempts and resend floor, email-token TTL, renewal window, email backend
(`console`/`smtp`) with SMTP settings, and SMS backend
(`console`/`webhook`) with API settings. All providers default to `console`,
which keeps local flows testable without any credential. **No secret and no
real bank/CCP number is in the repository.**

---

## 2. How to run and test

### Run locally

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt

.venv/bin/python -m webapp.cli init-db --demo     # migrate + seed 69 wilayas, plans, demo content
.venv/bin/python -m webapp.cli serve --reload     # http://localhost:8000

# Staff account for the payment queue
.venv/bin/python -m webapp.cli create-user \
    --phone 0555123456 --company "فريق الإدارة" --role admin

# Daily job (cron): expiry + renewal reminders
.venv/bin/python -m webapp.cli maintenance
```

With the default `console` backends the OTP and the emails are printed to the
server log; the test suite reads the same in-memory outbox.

### Test

```bash
.venv/bin/python -m pytest -o addopts="" -q                     # full suite
.venv/bin/python -m pytest -o addopts="" -q tests/test_phase2_*.py
.venv/bin/python -m pytest -o addopts="" -q tests/test_phase2_postgres_search.py

# PostgreSQL branch against a local server (CI uses the service container)
TEST_POSTGRES_URL=postgresql+psycopg://postgres:postgres@localhost:5432/dz_tenders_test \
    .venv/bin/python -m pytest -o addopts="" -q tests/test_phase2_postgres_search.py

.venv/bin/ruff check .
.venv/bin/black --check webapp migrations tests/conftest.py tests/test_phase*.py
.venv/bin/mypy webapp --ignore-missing-imports
```

### Results (2026-11-02)

| Gate | Result |
| --- | --- |
| Full pytest suite | **484 passed, 1 skipped** (skip: `pg_trgm` absent on the local `pgserver` build) |
| New Phase 2 tests | 22 accounts + 36 billing + 23 security (1 new archive throttle) + 2 CLI + 10 PostgreSQL (9 pass, 1 skip locally) |
| `ruff check .` | clean |
| `black --check` (webapp, migrations, conftest, `test_phase*`) | clean |
| `mypy webapp` | clean (30 files) |
| `alembic upgrade head` + `alembic check`, fresh PostgreSQL 16 | clean |
| Dev server smoke | `/`, `/annonces`, `/inscription`, `/connexion`, `/tarifs`, `/abonnement`, `/archives`, `/contact` all 200 with `dir="rtl"` |

---

## 3. What remains

* **Phase 3** — daily sector/wilaya digest over the alert tables, delivery logs,
  idempotency, unsubscribe links (the `alerts`/`alert_deliveries` schema already
  exists), plus the worker/scheduler process that will also call
  `webapp.cli maintenance`.
* **Phase 4** — editorial admin panel: announcement CRUD, CSV/Excel import,
  attachments, duplicate detection, review/publish, user and subscription
  management, banners, subcontracting moderation, audit-log UI, KPI dashboard.
  The current staff surface is limited to the payment queue.
* **Phase 5** — source ingestion behind a feature flag (fetch, parse, classify,
  dedupe → DRAFT).
* **Phase 6** — PWA, light/dark polish, WCAG AA audit, optional French i18n,
  SEO/performance.
* **Deployment** — `Dockerfile` and `docker-compose` (app, db, worker,
  scheduler) with migrations/seed on boot; the scheduler's first real job is
  the digest + maintenance tick, so it is scheduled with Phase 3.
* **Production credentials** — a real SMS gateway, SMTP relay, bank/CCP
  accounts and final prices (see risks).

---

## 4. Risks and open questions

| # | Risk / open question | Mitigation in this phase |
| --- | --- | --- |
| R1 | No SMS gateway account exists | `console` provider for development; `webhook` provider with Bearer token ready for any vendor. Exact vendor/payload must be confirmed before launch. |
| R2 | No SMTP relay/domain exists | `console` default; `smtp` provider needs `APP_SMTP_HOST` + `APP_SMTP_FROM`. Deliverability (SPF/DKIM) is an ops task. |
| R3 | Bank/CCP details and final prices are unknown | Payment page says «تفاصيل الحساب البنكي والبريدي تُضاف عند تأكيدها»; plan prices are seeded with `is_price_placeholder`. **No invented values.** |
| R4 | Proof files are stored on the local filesystem | `APP_UPLOAD_DIR` must be a persistent volume in production; object storage can replace `webapp/uploads.py` behind the same interface. Proofs are private (no `/static`). |
| R5 | Renewal reminders depend on a scheduler | The command is ready and idempotent, but no cron/compose scheduler is deployed yet. |
| R6 | `pg_trgm` may be unavailable | Trigram index is created only behind a `pg_extension` guard; search still works with `tsvector` + prefix variants. |
| R7 | Staff accounts are created by CLI only | Acceptable for Phase 2; Phase 4 adds user management with role assignment and audit trail. |
| R8 | Email-verification is not a hard gate for paid access | Phone verification is the identity gate; email verification is recorded and reminded. Confirm with the client whether an unverified email must block checkout. |
| R9 | 69-wilaya transition (until 31 Dec 2026) | Seed follows Law 26-06/Decree 26-206 and keeps `APP_WILAYAS_FILE` as override; mother-wilaya administration is a data concern, not a code one. |

---

## 5. Manual test checklist

1. `python -m webapp.cli init-db --demo` then `serve`; open `/tarifs`, confirm
   the plans and «اشترك الآن» buttons point at `/abonnement?plan=gold`.
2. `/inscription`: submit with a short password → Arabic validation error;
   submit valid data → redirected to the OTP screen; the server log shows the
   SMS and the email.
3. Enter a wrong OTP five times → «تجاوزت عدد المحاولات»; request a new code
   before 60 s → cooldown message.
4. Enter the correct OTP → logged in, redirected to `/tableau-de-bord`; the
   verification email appears in the log; open its link → «تم تأكيد البريد
   الإلكتروني»; open it again → «استُعمل هذا الرابط».
5. `/connexion` with the new password, then `/mot-de-passe-oublie`, reset the
   password and confirm the old browser session is logged out.
6. Log in, choose Gold + one sector + bank transfer without a reference →
   Arabic error; add a reference → payment page with placeholder instructions.
7. Upload a `.txt` renamed to `.pdf` → rejected; upload a real PDF → «تم رفع
   الوصل» and the proof is visible only to the owner.
8. Log in as the admin (`create-user --role admin`), open `/admin/paiements`,
   approve the payment; the subscriber's detail page for a water announcement
   unlocks issuer/deadline/description.
9. As a non-staff account, open `/admin/paiements` → 403.
10. Run `python -m webapp.cli maintenance` twice → the second run reports
    `{'expired': 0, 'reminders_sent': 0, …}`; no duplicate email.
11. `GET /desabonnement?token=…` from the dashboard alert → alert deactivated.
12. Resize to a phone width: navigation, forms, tables and the payment timeline
    remain usable (RTL, 44 px targets).
