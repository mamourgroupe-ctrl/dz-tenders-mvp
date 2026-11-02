# Step 0 — Audit, feature matrix and phased plan

- **Repository:** `mamourgroupe-ctrl/dz-tenders-mvp`
- **Baseline commit:** `bfd09594e3826b229a10093830b028dad5101bc6` (`main`, merge of PR #3)
- **Audit date:** 2026-11-02
- **Method:** full read of the 127 tracked files (`git ls-files`), dependency and
  configuration inspection, `pytest` baseline run, `ruff` run, static review of
  every crawler, storage, notification, API and frontend module.
- **Baseline health:** `263 tests collected`, `263 passed` (8.0 s), `ruff check .`
  clean on the tracked Python tree. The legacy pipeline is green; the gap is
  product scope, not broken tests.

---

## 1. Existing stack (kept)

| Layer | What exists | Decision |
| --- | --- | --- |
| Language | Python 3.11 (`pyproject.toml` targets 3.11), TypeScript 5.6 strict | Keep |
| Web framework | FastAPI 0.115 (read-only JSON API in `api/`), Starlette, Uvicorn | Keep. Jinja2 (ships with Starlette/FastAPI stacks) is added for server-rendered Arabic pages — no framework rewrite |
| Data | SQLite (`storage/tenders.db`, raw `sqlite3`), one `tenders` table, home-grown `ALTER TABLE` migration | Keep SQLite as the default; add **SQLAlchemy 2 + Alembic** for the product schema and **FTS5** for Arabic search. PostgreSQL stays a documented deployment option (SQLAlchemy URL); FTS has a LIKE fallback |
| Frontend | React 18 + Vite + Tailwind + TanStack Query + Leaflet/Recharts (statistics dashboard, mock/real API switch) | Keep untouched. The public product site is server-rendered for SEO, RTL and mobile-first performance; the React dashboard remains the internal analytics view |
| Crawling | `requests`/BeautifulSoup/lxml + Playwright (Safqatic), 8 crawler modules, saved HTML fixtures | Keep, reuse in Phase 5 behind adapters + feature flag |
| Notifications | Telegram channel, SMTP digest to a fixed `DIGEST_TO`, Excel report | Keep for the internal ops digest; Phase 3 adds per-user alerts |
| Scheduling | GitHub Actions cron (`scraper.yml`), Windows PowerShell scripts | Keep for the scraper; Phase 3 adds a scheduler in Docker |
| Config | `config.AppConfig` (frozen dataclass) + `python-dotenv`, `.env.example` | Keep convention; new settings dataclass mirrors it |
| Tests / quality | pytest (263 tests, fixtures for every crawler), Ruff, mypy config, 100-char lines, double quotes | Keep and extend; Black is added for the new package (legacy tree is not reformatted to avoid a 8.5k-line noise diff) |
| CI | One workflow: daily scraper dry-run | Add `ci.yml` (lint, type-check, tests, frontend build). Keep `scraper.yml` |

**Stack change proposal: none.** The only additions are libraries inside the
existing FastAPI/SQLite stack (SQLAlchemy, Alembic, Jinja2, argon2-cffi). A
Django or Next.js rewrite would discard a tested ingestion layer and the React
dashboard for no functional gain.

---

## 2. What already works

1. **Ingestion** — 8 crawler modules (ADE, ONA, AlgeriaTenders, Safqatic,
   Google News, Marchés Publics, authenticated Marchés Publics, smart crawler)
   with sanitised URLs, relative-link handling and **saved fixtures** for ADE,
   Safqatic, Marchés Publics and Google News.
2. **Arabic/French text matching** — `tender_filter.py` normalises hamza forms,
   diacritics, tatweel, Arabic-Indic digits and French case; weighted scoring
   with entity/keyword/product weights; explainable rejection reasons
   (`deadline_passed`, `published_stale`, `undated_dated_source`).
3. **Durable delivery** — `storage/delivery.py` holds one locked
   select→persist→send→mark transaction; a second concurrent run exits with
   code 75 instead of duplicating notifications; blocked rows after 3 failures
   (`storage/tools.py` exposes list/unblock).
4. **Persistence** — `tenders` table with a SHA-256 fingerprint unique index,
   retry/blocked columns and an idempotent `ALTER TABLE` upgrade path.
5. **Read-only API** — FastAPI factory with a consistent error envelope, bounded
   pagination, parameterised SQL, `mode=ro` + `query_only`, no stack traces or
   filesystem paths, CORS disabled credentials, tests on synthetic databases.
6. **Operations** — Telegram summary + Excel report + SMTP digest, dry-run
   default, logging setup, source registry (`data/sources_master.json`,
   `SourcesLoader`), GitHub Actions dry-run cron with artifacts.
7. **React dashboard** — overview, search, detail drawer, favourites, dark
   mode, statistics; explicit "not available" states instead of fabricated
   values; mock mode only when no API URL is configured.
8. **Docs** — comprehensive README, `DEVELOPMENT_ROADMAP.md`,
   `TENDER_FILTER_DIAGNOSTIC.md`, `INTEGRATION_REPORT.md`.

---

## 3. What is missing, broken or risky

### 3.1 Product gaps (the actual scope of this engagement)

- **No public product site.** There is an operator dashboard, not an Arabic
  RTL public platform: no home, announcement list/detail, archive, static or
  legal pages, no SEO surface (sitemap, robots, canonical, OG), no PWA.
- **No product data model.** Only the single `tenders` table. There are no
  announcement types (8), sectors, wilayas (58/69), issuers, users,
  subscriptions, payments, alerts, saved announcements, subcontracting offers,
  banners, attachments, sessions, audit log or search log.
- **No migrations.** Schema evolution is ad-hoc `ALTER TABLE` in application
  startup; there is no versioned migration tool, no reversible change.
- **No Arabic-aware search index.** Normalisation exists only inside the
  marketing filter; there is no full-text index, ranking, highlighting or
  search query parser.
- **No accounts, plans, subscriptions, payments or renewal/expiry logic.**
- **No per-user alerts.** A single fixed `DIGEST_TO` recipient; no unsubscribe,
  no delivery log, no idempotency per (alert, announcement).
- **No admin panel.** No roles (admin/editor/support), no CRUD, import,
  moderation, payment verification, KPI dashboard or audit log.
- **No OCR/PDF attachment intake, duplicate detection UI or review workflow.**
- **No i18n framework** (Arabic strings are inline; French site does not exist)
  and no Arabic slug strategy in the public URL space.

### 3.2 Bugs and reliability issues found (legacy code, not fixed in Phase 1)

| ID | Severity | Location | Issue |
| --- | --- | --- | --- |
| B1 | High | `crawlers/algeria_tenders_crawler.py:57`, `crawlers/smart_crawler.py:79` | `verify=False` plus `urllib3.disable_warnings` disables TLS verification globally for those sources (MITM risk on collected data) |
| B2 | High | `storage/database.py:add_tender` | SELECT-then-INSERT race: two concurrent writers can raise `IntegrityError` on the fingerprint unique index instead of upserting |
| B3 | Medium | `storage/database.py:_migrate_schema` | First upgrade blocks **all** unnotified rows (`UPDATE tenders SET blocked = 1 WHERE notified = 0`), a destructive default for existing data |
| B4 | Medium | `api/repository.py:summary`, `by_product` | Loads the whole table into Python per request (O(n) memory/CPU); acceptable at MVP size, not at 10⁵ rows |
| B5 | Medium | `api/main.py` | No rate limiting, no security headers, no request ID; only mitigations are CORS and read-only access |
| B6 | Medium | `main.py`, `run_smart_scraper.py`, `test_run.py` | Three entry points on the same database; the lock protects delivery, but the pipelines still duplicate filtering and reporting logic |
| B7 | Low | `telegram_notifier.py:send_message` | Uses `parse_mode="HTML"`; callers escape titles in `main.py` but the notifier itself accepts raw text (a future caller can break delivery) |
| B8 | Low | repo root | 160 KB generated `sources_dashboard.html`, legacy `templates/dashboard.html`, `index.html`, committed `package-lock.json` candidate artifacts |
| B9 | Low | `requirements.txt` / `requirements-dev.txt` | No version pins for test/quality tools, no lock file; dev deps include `debugpy`; `mypy` config exists but is not enforced in CI |
| B10 | Low | `storage/paths.py` + `deploy` | SQLite file is not backed up or WAL-tuned; `journal_mode` left default, no online backup task |
| B11 | Medium | `data/sources_master.json` sources | Some sources return reference/fabricated data (marked `is_sample` and dropped by `drop_reference_data`), but the risk of re-enabling them accidentally remains |

### 3.3 Security review — current state

**Good:** no secrets tracked (`.env` ignored, `.env.example` empty placeholders);
parameterised SQL; read-only DB URI + `PRAGMA query_only`; HTML escaping in the
digest and Telegram summary; URL scheme allow-list in `sanitize_url`; CORS with
credentials disabled; no `eval`/`exec`; upload surface absent.

**To fix / add:** TLS verification (B1); rate limiting on auth and public
forms; CSRF (none needed today — no state-changing web endpoints — but the new
site has them); password/OTP hashing and session rotation; security headers;
upload validation; audit log; `file://`/SSRF surface for the future ingestion
admin; log redaction of tokens in URLs (Telegram token is in the URL; current
logging avoids it, keep it that way).

---

## 4. Feature matrix — DONE / PARTIAL / MISSING

Legend: **DONE** = works end to end today; **PARTIAL** = reusable pieces exist
but the requirement is not met; **MISSING** = no implementation.

| # | Feature | Status | Evidence / gap |
| --- | --- | --- | --- |
| 1.1 | Schema + migrations: announcements, 8 types, sectors, wilayas, issuers, users, subscriptions, payments, alerts, subcontracting, banners | **MISSING** | Only `tenders`; no Alembic |
| 1.1b | 8 announcement types | **MISSING** | Free-text `status` only |
| 1.1c | Sectors / 58–69 wilayas / issuers entities | **MISSING** | Wilaya is a free-text column; sectors are marketing families in `data/targets.json` |
| 1.2 | Public Arabic RTL pages: home, advanced list, detail, archive by year, subcontracting, contact, terms, privacy, cookies | **MISSING** | Dashboard SPA only |
| 1.3 | Advanced search/filters + pagination + sorting | **PARTIAL** | API has search/wilaya/product/priority/date + page; no type/sector/issuer, no sorting choice, no SSR UI |
| 1.4 | Arabic-aware search (normalisation + FTS) | **PARTIAL** | Normaliser exists in `tender_filter.py`; no FTS/index |
| 1.5 | Plan-based access control | **MISSING** | No plans, no users |
| 2.1 | Registration, phone OTP (pluggable), email verification, phone+password login, password reset, rate limiting | **MISSING** | No auth layer; rate limiting absent |
| 2.2 | Plans (Free, Bronze, Silver, Gold, Premium, Platinum, auctions-only, extra-sector) with annual discount | **MISSING** | — |
| 2.3 | Manual payment flow + proof upload + admin verification + expiry + reminders | **MISSING** | — |
| 2.4 | User dashboard (subscription, sectors, saved, alerts, payments) | **MISSING** | — |
| 3.1 | Per-user daily email digest by sectors/wilayas, job queue, idempotent, unsubscribe, delivery logs | **PARTIAL** | Fixed-recipient SMTP digest + `NotificationManager`; no queue, no per-user prefs, no logs |
| 4.1 | Admin roles + announcement CRUD + CSV/Excel import + PDF/image upload + duplicate detection + review/publish workflow | **MISSING** | No admin surface |
| 4.2 | User/subscription management, payment queue, taxonomy admin, banners, moderation, audit log, KPIs | **MISSING** | — |
| 5.1 | Ingestion pipeline behind flag: fetch/parse/classify/dedupe/DRAFT, source adapters, robots + rate limits, attribution | **PARTIAL** | Crawlers + fixtures + filter exist; no adapters contract, no flag, no draft review, no robots enforcement, no classifier confidence |
| 6.1 | PWA, light/dark, WCAG AA, i18n (ar default + fr) | **PARTIAL** | Dashboard has dark mode; no PWA, no i18n, public site absent |
| 6.2 | SEO: meta/OG/sitemap/robots/JSON-LD/canonical/Arabic slugs | **MISSING** | — |
| 6.3 | Performance: indexes, caching, query optimisation, pagination | **PARTIAL** | `tenders` indexes + bounded API pagination; new schema needs its own indexes/budgets |

---

## 5. Phased plan (file-level)

Each phase is a reviewable commit series on the session branch with
`feat:`/`fix:`/`chore:`/`docs:`/`test:` messages and its own report.

### Phase 1 — Data model, public site, search, access control (this delivery)

**New**
- `webapp/__init__.py`, `config.py`, `db.py`, `enums.py`, `models.py`,
  `text.py` (Arabic normalisation + slugs), `search.py`, `search_index.py`,
  `security.py`, `access.py`, `auth.py`, `repositories.py`, `entitlements.py`,
  `viewmodels.py`, `seed.py`, `seed_data.py`, `cli.py`
- `webapp/web/main.py`, `webapp/web/deps.py`, `webapp/web/routes_public.py`,
  `webapp/web/routes_auth.py`, `webapp/web/routes_seo.py`
- `webapp/templates/` (base, home, list, detail, archive, subcontracting,
  static pages, login, error) + partials
- `webapp/static/css/app.css`, `webapp/static/js/theme.js`, `app.js`,
  `webapp/static/img/logo.svg`, `favicon.svg`
- `migrations/` (Alembic env + `0001_phase1_schema` with FTS5 + indexes)
- `tests/test_phase1_*.py` (text, search, access, routes, seed, migrations)
- `docs/AUDIT.md` (this file), `docs/PHASE1.md`
- `Dockerfile`, `docker-compose.yml`, `.env.example` additions (Phase 1 app only;
  worker/scheduler join in Phase 3)

**Modified**
- `requirements.txt` / new `requirements-web.txt`, `pyproject.toml` (black,
  pytest paths, coverage), `.github/workflows/ci.yml` (new), `README.md`,
  `.gitignore` (platform DB, uploads), `Procfile` (new web target documented).

### Phase 2 — Accounts, plans, manual payments

**New:** `webapp/otp.py` (provider interface + console/file placeholder),
`webapp/services/accounts.py`, `webapp/services/payments.py`,
`webapp/web/routes_auth.py` (register/OTP/verify/reset), `routes_account.py`
(dashboard, sectors, saved, payments), templates for register/OTP/dashboard/
billing, `webapp/uploads.py` (type/size checks, EXIF strip), tests
(`test_phase2_*`).
**Modified:** `models.py` (finalise payment/session fields), migrations
`0002`, seed, README.

### Phase 3 — Alerts and jobs

**New:** `webapp/jobs/` (`queue.py`, `digest.py`, `runner.py`,
`unsubscribe.py`), `webapp/tasks.py` CLI (`send-digest`, `expire-subscriptions`,
`renewal-reminders`), email templates, `tests/test_phase3_*`.
**Modified:** `docker-compose.yml` (worker, scheduler), `models.py` delivery
logs, README.

### Phase 4 — Admin panel

**New:** `webapp/web/routes_admin.py`, `webapp/services/importers.py`
(CSV/XLSX), `webapp/services/duplicates.py`, `webapp/services/moderation.py`,
`webapp/web/routes_admin_payments.py`, `webapp/web/routes_admin_taxonomy.py`,
`templates/admin/*`, `tests/test_phase4_*`.
**Modified:** models (audit fields finalised), migrations `0003`, seed
(roles), README.

### Phase 5 — Ingestion pipeline (feature flag)

**New:** `webapp/ingest/` (`base.py` adapter protocol, `registry.py`,
`sources/*.py` wrappers over existing crawlers, `classifier.py`,
`dedupe.py`, `robots.py`, `http.py`, `pipeline.py`), fixtures reused from
`tests/fixtures/`, `tests/test_phase5_*`.
**Modified:** `webapp/config.py` (`INGESTION_ENABLED`), admin review routes,
README, source attribution fields.

### Phase 6 — UX, SEO, performance

**New:** `webapp/static/manifest.webmanifest`, service worker,
`webapp/i18n.py` + `webapp/locales/{ar,fr}.json`, `webapp/web/routes_seo.py`
extensions (JSON-LD, hreflang), cache headers, query budgets, `docs/SEO.md`.
**Modified:** every template (externalised strings), models/migrations for
Arabic-slug uniqueness `0004`, CI Lighthouse budget.

---

## 6. Phase 1 design decisions

1. **Separate SQLite file** `storage/platform.db` (env `APP_DATABASE_URL`).
   The existing `tenders.db` stays owned by the crawler/API; the product schema
   is migrated independently, so nothing in the legacy pipeline changes.
2. **SQLAlchemy 2 + Alembic** with portable DDL (works on SQLite and
   PostgreSQL). Search is SQLite FTS5 with a `LIKE` fallback; the search
   interface is isolated in `webapp/search.py` so a PostgreSQL backend can be
   added without touching templates.
3. **Server-rendered Jinja2 pages** for the public site: RTL-first, no JS
   required to read content, SEO-friendly, mobile-first CSS (no Tailwind build
   step on the public site). The React dashboard is untouched.
4. **Free vs paid gating is enforced server-side** (`webapp/access.py` returns
   a view model containing only permitted fields); templates cannot leak hidden
   fields because they never receive them.
5. **Money is stored as integer DZD**, never floats. All seeded prices are
   **explicit placeholders** pending client confirmation.
6. **58 official wilayas are seeded** (Algeria has 58 since 2019). The brief
   says 69; the 11 extra entries are not invented. The seeder reads an optional
   `APP_WILAYAS_FILE` so the client's 69-entry list can be loaded without a code
   change. See open questions.
7. **Passwords:** argon2id. **Sessions:** opaque 256-bit tokens stored hashed,
   HttpOnly/SameSite=Lax cookies, rotated on login. **CSRF:** double-submit
   cookie + origin check, constant-time compare. **Rate limiting:** DB-backed
   fixed window (works with multiple workers) on login and public POSTs.

---

## 7. Open questions (blocking facts, never invented)

| # | Question | Current placeholder |
| --- | --- | --- |
| O1 | **69 wilayas**: Algeria has 58 official wilayas (since 2019). What are the 11 additional entries — the client's commercial segmentation, new delegations, or a typo? | 58 official seeded; optional import file; seed accepts `APP_WILAYAS_FILE` |
| O2 | DZD pricing per plan, and the exact annual discount | Clearly marked placeholder prices, 10 × monthly for annual |
| O3 | Bank/CCP/cash payment details (account numbers, receipt process) | Payment instructions page text is a placeholder; **no real account numbers** |
| O4 | SMS/OTP provider and credentials | `ConsoleOtpProvider` + provider interface; Phase 2 |
| O5 | SMTP/email provider, sender domain, SPF/DKIM | Existing SMTP env vars; console fallback in dev |
| O6 | Production domain name (canonical URLs, sitemap) | `APP_BASE_URL` default `http://localhost:8000` |
| O7 | Legal review of terms/privacy/cookies (Algerian law 18-07, e-commerce rules) | Draft Arabic text marked “مسودة للمراجعة القانونية” |
| O8 | Sector taxonomy sign-off | 16 proposed sectors, editable seed |
| O9 | Exact scope of the auctions-only plan (all auction notices only, or also provisional awards?) | Auctions only, announced in plan features |
| O10 | Licensing of each crawled source (robots.txt / terms / attribution wording) | Phase 5 gate: only sources explicitly allow-listed; sources currently in the repo remain disabled unless verified |
| O11 | Admin seed credentials | `APP_ADMIN_PHONE` / `APP_ADMIN_PASSWORD` env, **no default password** in production; dev default printed only when `APP_ENV=development` |
| O12 | 8 type labels (FR wording for awards/extensions/terminations) | Arabic + French labels proposed in `webapp/enums.py` |

---

## 8. Test and quality baseline

- `pytest`: **263 passed** before changes. Phase 1 adds a separate test module
  tree for the product app; the legacy suite remains green and untouched.
- `ruff check .`: clean before changes.
- `black --check`: applied to new code only (`webapp/`, `migrations/`,
  `tests/test_phase1_*.py`); the legacy tree is intentionally excluded until a
  dedicated formatting PR (see tech-debt item B9).
