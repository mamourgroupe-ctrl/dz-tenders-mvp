# Phase 1 — Platform schema, public site, Arabic search, access control

**Status:** complete · **Branch:** `feat/phase-1-public-platform` · **Date:** 2026-11-02

Phase 1 turns the scraper MVP into an Arabic-first public procurement site on the
same stack (Python 3.11, FastAPI, SQLite, Jinja2) while the legacy pipeline keeps
writing to its own database untouched. Every requirement of the phase is either
implemented here or explicitly listed as an open question at the end of this
report.

---

## 1. What changed

### 1.1 Data model — 28 tables, one Alembic migration

New package `webapp/` with SQLAlchemy 2.0 models, replacing ad-hoc schema code for
the product surface only (the legacy `tenders` table and its API remain as-is).

| Domain | Tables |
| --- | --- |
| Taxonomy | `sectors`, `wilayas`, `issuers` |
| Announcements | `announcements`, `announcement_sectors`, `attachments`, `search_logs` |
| Accounts | `users`, `user_sessions`, `one_time_tokens` (OTP / email verification / password reset) |
| Billing | `plans`, `subscriptions`, `subscription_sectors`, `payments` |
| Alerts | `alerts`, `alert_sectors`, `alert_wilayas`, `alert_deliveries` |
| Engagement | `saved_announcements`, `subcontracting_offers`, `banners` |
| Operations | `audit_logs`, `rate_limit_events` |

`announcements` covers the eight required types (`tender`, `consultation`,
`provisional_award`, `auction`, `cancellation`, `deadline_extension`,
`notice_of_default`, `contract_termination`) through the `type` column, plus
status, bilingual titles/descriptions, issuer (FK or free text), wilaya, sectors,
publish date/year, deadline, reference, estimated value in DZD, source URL/name,
attachments, confidence, duplicate marker and workflow actors.

Decisions worth recording:

* **Integer DZD** — no floating-point money.
* **Naive UTC datetimes** in storage, Africa/Algiers only for display.
* **Enum columns as VARCHAR** for portable migrations (SQLite/Postgres).
* **Opaque session tokens** hashed in `user_sessions`; no signing secret to rotate.
* **`search_text`** stores the normalised Arabic text so the LIKE fallback and the
  FTS index always agree.

The Alembic revision `e416d5834430` creates the full schema and, on SQLite only,
the FTS5 virtual table `announcement_fts(title, body, issuer)` with
`unicode61 remove_diacritics 2`. Its shadow tables are excluded from
autogenerate (`migrations/env.py:include_object`), so `alembic check` stays clean.

### 1.2 Public Arabic site (RTL, mobile-first)

Server-rendered Jinja2 pages, no client framework required, sharing the visual
identity from the brief: navy `#0c1f33`, gold `#e3a21a`, teal `#0f8b8d`, IBM Plex
Sans Arabic, light/dark themes.

| Route | Content |
| --- | --- |
| `/` | Hero, live stats, latest announcements, type and wilaya shortcuts, banners |
| `/annonces` | Keyword search, filters (type, sector, wilaya, issuer, date range), sort, pagination |
| `/annonces/{id}[/{slug}]` | Canonical slug detail page |
| `/archives[/{year}]` | Counts per publication year |
| `/sous-traitance[/{id}[/{slug}]]` | Subcontracting offers, gated contacts |
| `/tarifs` | Six plans + extra-sector add-on, annual discount, placeholder-price notice |
| `/contact`, `/conditions-utilisation`, `/confidentialite`, `/cookies` | Contact and legal pages |
| `/connexion`, `/deconnexion` | Phone + password session login/logout |
| `/sitemap.xml`, `/robots.txt`, `/health` | SEO and operations |

Accessibility and performance basics: semantic landmarks, skip link, visible focus,
`dir="rtl"` document, 44 px touch targets, inline SVG icons, one CSS file and one
small JS file, no external font/CDN requests at runtime.

### 1.3 Arabic-aware search

`webapp/text.py` normalises **symmetrically** at index and query time:

* alef/hamza forms `أ إ آ ٱ` → `ا`, `ى` → `ي`, `ئ` → `ي`, `ؤ` → `و`, `ة` → `ه`;
* Arabic diacritics and tatweel removed (including those produced by NFKD);
* Arabic-Indic digits → ASCII;
* Latin accents folded, case folded, punctuation collapsed.

SQLite FTS5 is used when present. Queries are rebuilt as quoted prefix terms
joined by `AND`, so FTS operators cannot be injected. When FTS5 is missing the
repository executes an escaped `LIKE` query over the same normalised text; both
paths return the same `AnnouncementFilters`/`SearchResult` shape.

### 1.4 Plan-based access control

`webapp/entitlements.py` resolves the effective plan from the database clock
(active subscription only, expiry honoured), and `webapp/access.py` builds an
`AnnouncementView` containing **only** the fields the visitor may see. Templates
cannot leak hidden values because they are never passed.

| Visitor | Sees |
| --- | --- |
| Anonymous / free plan | title, type, sector, wilaya, publication date |
| Paid plan (covered sector) | + issuer, deadline, description (AR/FR), reference, estimated value, attachments, source URL, contact data |
| Paid plan (uncovered sector) | locked with a sector-specific message |
| Auctions-only plan | auctions unlocked, other types locked |
| Staff (admin/editor/support) | everything, no subscription required |
| Expired / pending subscription | falls back to free |

Sector coverage is explicit (`subscription_sectors`); Platinum and staff have
`all_sectors`. The same gate protects subcontracting contacts.

### 1.5 Auth foundation (Phase 2 builds on it)

Phone normalisation to `+213…`, argon2id hashing with transparent rehash,
password policy, opaque session cookies (`HttpOnly`, `SameSite=Lax`, `Secure` in
production), CSRF double-submit cookie validated on every POST, same-origin check,
DB-backed rate limiting per phone and per IP, and an open-redirect-safe `next`
parameter. Phase 2 adds registration, OTP, email verification and password reset
on top of this foundation.

### 1.6 Operations

* CLI: `python -m webapp.cli init-db [--demo] | seed [--demo] | reindex | create-user | serve`.
* Seed data is idempotent: 58 official wilayas, 16 sectors, 20 issuers, 8 plans,
  24 sample announcements (all eight types), 5 subcontracting offers.
* All demo content is flagged `is_sample` and attributed to `example.dz`; no
  third-party content, logos or data are copied.
* `.env.example` documents every `APP_*` variable; no secret has a working default.
* `README.md` documents quickstart, routes, access model, search and database.

---

## 2. How to run and test

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt

.venv/bin/python -m webapp.cli init-db --demo
.venv/bin/python -m webapp.cli serve --reload        # http://localhost:8000

.venv/bin/python -m pytest -o addopts="" -q           # full suite
.venv/bin/ruff check .
.venv/bin/black --check webapp migrations tests/conftest.py tests/test_phase1_*.py
.venv/bin/mypy webapp --ignore-missing-imports
```

`-o addopts=""` is required because the legacy `pyproject.toml` pytest options
suppress the summary line.

### Verification evidence

| Check | Result |
| --- | --- |
| Full test suite | **391 passed**, 1 warning (Starlette deprecation), ~30 s |
| Legacy suite | 263 tests unchanged and green |
| New Phase 1 tests | 128 tests in 7 modules |
| `ruff check .` | clean |
| `black --check` (new code) | clean; legacy tests are intentionally excluded |
| `mypy webapp` | success, 24 source files |
| `alembic upgrade head` on a fresh DB | 28 product tables + `alembic_version` + FTS5 set |
| `alembic check` | “No new upgrade operations detected” |
| Live Uvicorn smoke | `/`, search, detail, `/tarifs`, sitemap, robots, health all 200 |

New test modules:

| Module | Covers |
| --- | --- |
| `test_phase1_text.py` | normalisation, tokens, FTS query safety, slugs, dates, DZD |
| `test_phase1_seed.py` | reference counts, official codes, eight types, idempotency, FTS rows, wilaya override |
| `test_phase1_access.py` | free/paid/staff/expired/pending, sector coverage, auctions-only, offer contacts |
| `test_phase1_search.py` | variant matching, filters, sorting, pagination, drafts, LIKE fallback, hostile queries |
| `test_phase1_auth.py` | phone formats, argon2, session expiry/revocation, CSRF, origin check, rate limit, open redirect, cookie flags |
| `test_phase1_routes.py` | RTL rendering, filters, gating in HTML, slug redirects, archives, sitemap/robots, headers, 404, view counters, pagination |
| `test_phase1_cli.py` | parser, init-db/seed idempotency, create-user/admin, reindex, table set, double upgrade |

---

## 3. What remains

Phase 1 is complete; the following items are intentionally deferred to their
phase and are **not** regressions:

* **Phase 2** — self-service registration, OTP, email verification, password
  reset, payment proof upload + admin verification, billing automation,
  reminders, user dashboard.
* **Phase 3** — scheduled digest emails, job queue, unsubscribe links, delivery logs.
* **Phase 4** — admin CRUD, bulk import, review workflow, moderation, KPI dashboard.
* **Phase 5** — ingestion adapters behind a feature flag.
* **Phase 6** — PWA, French translation, structured data, caching, performance budget.

Known limitations in this phase:

* Pricing is displayed with a visible “temporary prices” notice — no validated
  price list was provided.
* Bank/CCP details are absent (open question O3); the payment pages show
  placeholders until confirmed.
* On PostgreSQL the search layer uses the LIKE path; a `tsvector` implementation
  is planned for Phase 6 once the production database is chosen.
* Sorting exposes newest/oldest/deadline only; relevance sorting depends on the
  Phase 5 confidence score.
* FTS5 tokenisation is `unicode61`; Arabic stemming is intentionally avoided so
  prefix matching stays predictable.

## 4. Risks

| Risk | Mitigation |
| --- | --- |
| SQLite write contention under load | WAL mode, short transactions, separate platform DB; Postgres URL supported |
| 58 vs 69 wilayas (O1) | official 58 seeded, `APP_WILAYAS_FILE` override documented and tested |
| Legal review of data retention (O7) absent | privacy/cookies pages marked as pending review; no analytics or third-party trackers |
| Placeholder prices/contacts mistaken for final | visible notices in UI, `is_price_placeholder` flag, open questions list |
| Demo content leaking into production | `--demo` is opt-in; every sample row is flagged and attributed |
| Session fixation / CSRF | new token on login, rotated session, double-submit CSRF, same-origin check |
| Secrets in repo | `.env` ignored, `.env.example` contains empty values only |
