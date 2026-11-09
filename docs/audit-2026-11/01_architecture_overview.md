# Audit Report 01: Architecture Overview

**Date:** 2026-11-08  
**Repository:** dz-tenders-mvp  
**Branch:** fix/remove-railway-configs  
**Auditor:** Claude Opus 5.5

---

## Executive Summary

DZ-TENDERS-MVP is a **dual-pipeline system** comprising:

1. **Legacy Scraper Pipeline** (root/`main.py`, `crawlers/`, `storage/`, `tender_filter.py`) — Scheduled CLI that scrapes Algerian public procurement portals, filters/classifies tenders for PE/PVC pipe products, and delivers results via Telegram/Excel/Email.
2. **Public Arabic Platform** (`webapp/`) — Read-only FastAPI + React 18 dashboard serving a bilingual (Arabic/French) tender portal with plan-gated access control, FTS5 search, and subscription billing.

Both pipelines share **no runtime code** but overlap in domain concepts (wilayas, sectors, product taxonomy). The legacy pipeline writes to `storage/tenders.db`; the platform reads from `storage/platform.db`.

---

## Component Map

```
├── main.py                          # Legacy entry point (scrape → filter → deliver)
├── api/
│   ├── main.py                      # FastAPI factory (read-only API)
│   ├── repository.py                # ReadOnlyTenderRepository (SQL injection safe)
│   └── mapping.py                   # row_to_tender, PRODUCT_MARKERS, scoring
├── crawlers/
│   ├── base_crawler.py              # BaseCrawler with retry/timeout logic
│   ├── ade_crawler.py               # ADE (Algerian Water) portal scraper
│   ├── mounakassat_crawler.py       # Authenticated MounakassatDZ crawler
│   ├── marches_publics_auth_crawler.py  # Playwright-based marches-publics.gov.dz
│   ├── safqatic_crawler.py          # Safqatic portal scraper
│   └── google_news_crawler.py       # Google News RSS fallback
├── storage/
│   ├── database.py                  # TenderDatabase (fingerprint dedup, migrations)
│   ├── delivery.py                  # Critical section: lock → save_many → send
│   └── lock.py                      # Cross-platform file lock (msvcrt/fcntl)
├── tender_filter.py                 # Arabic normalization, classification, scoring
├── notifications/                   # Telegram, Email (SMTP), Excel report builders
├── webapp/
│   ├── models.py                    # 28 SQLAlchemy models (User, Plan, Announcement, etc.)
│   ├── search.py                    # FTS5 + LIKE fallback search engine
│   ├── repositories.py              # Read-side queries for public pages
│   ├── access.py                    # Plan-gated field visibility (free vs paid)
│   ├── entitlements.py              # Subscription → effective rights resolution
│   ├── security.py                  # Argon2id, CSRF, RateLimiter, session mgmt
│   ├── cli.py                       # init-db, seed, reindex, create-user, serve
│   ├── web/
│   │   ├── routes_public.py         # Public pages: home, listings, detail, archive
│   │   ├── routes_auth.py           # Login/logout, CSRF, rate limiting
│   │   └── deps.py                  # DB session, current_user, safe_next_url
│   └── db.py                        # Engine, session_scope, FTS5 ensure_fts
├── src/                             # React 18 + TypeScript + Vite dashboard
│   ├── lib/api.ts                   # TanStack Query client (mock/real modes)
│   ├── pages/TendersPage.tsx        # Main table with filters, favorites, drawer
│   └── pages/DashboardPage.tsx      # Metrics cards, Recharts, recent tenders
└── data/targets.json                # 8 families, 4 products, 69 wilayas, entities
```

---

## Data Flow

### Legacy Pipeline (Daily Dry-Run via GitHub Actions)

```
main.py:scrape_all_sources()
    → crawlers/*.run() → List[dict] (raw tenders)
    → drop_reference_data() → filter using data/targets.json
    → tender_filter.classify_tender() → relevance_score + family + products
    → filter_fresh(FRESHNESS_WINDOW_DAYS=90)
    → storage.delivery.deliver():
         db_lock(LOCK_TIMEOUT_SECONDS=900)
         → TenderDatabase.save_many()  (fingerprint dedup)
         → TelegramNotifier.send_excel_report()
         → SMTP digest email
         → mark_sent / register_failed_attempt (block after 3 failures)
```

### Public Platform (Request-Response)

```
HTTPS Request → FastAPI (api/main.py or webapp.web.main)
    → CORS + Security Headers + RateLimiter
    → webapp.search.search_announcements()
         → FTS5 (if available) or LIKE on Announcement.search_text
         → Filters: type, wilaya, sector, issuer, date range
         → Sort: relevance (BM25), recent, deadline, oldest
         → Pagination (page/per_page clamped to 12/48)
    → webapp.access.build_announcement_view()
         → Plan entitlements → REASON_* gating
    → JSON (API) or Jinja2 HTML (web routes)
```

---

## Key Architectural Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Dual databases (tenders.db / platform.db) | Isolation: scraper writes, platform reads | Schema drift risk; no shared migrations |
| File-based exclusive lock (msvcrt/fcntl) | Windows + Linux compatible, no external deps | Coarse-grained; blocks entire pipeline |
| SQLite `mode=ro` + `PRAGMA query_only=ON` | Read-only API enforcement at DB level | Requires SQLite; not portable to Postgres |
| FTS5 with `unicode61 remove_diacritics 2` | Arabic diacritic-insensitive search | SQLite-only; falls back to LIKE on other engines |
| Plan-gated fields via `build_announcement_view` | Single source of truth for visibility | All access logic in one function (complexity) |
| Argon2id + CSRF double-submit + RateLimiter | OWASP-aligned auth | Session stored in DB (not JWT) — scales with DB |
| TanStack Query + mock mode in frontend | Offline dev, testable components | Mock data must stay in sync with API contracts |

---

## Technology Stack

| Layer | Technology | Version Constraint |
|-------|------------|-------------------|
| **Python** | 3.11+ | `python_requires=">=3.11"` |
| **Web Framework** | FastAPI | `>=0.115,<0.116` |
| **ORM** | SQLAlchemy | `>=2.0,<2.1` |
| **Migrations** | Alembic | `>=1.13,<2.0` |
| **Auth** | argon2-cffi | `>=23.1,<26.0` |
| **Scheduler** | GitHub Actions (cron) | Daily 06:00 UTC |
| **Frontend** | React 18, TypeScript, Vite | `react^18.3.1`, `typescript^5.6.3` |
| **State/Data** | TanStack Query v5 | `@tanstack/react-query^5.56.2` |
| **Charts** | Recharts | `^2.13.3` |
| **Maps** | Leaflet + React-Leaflet | `^1.9.4`, `^4.2.1` |
| **Styling** | Tailwind CSS | `^3.4.15` |
| **Scraping** | requests, BeautifulSoup4, lxml, Playwright | `playwright>=1.40.0` |
| **Data/Export** | pandas, openpyxl | `pandas>=2.0.0`, `openpyxl>=3.1.0` |
| **Lint/Format** | Ruff (line-length=100), Black (line-length=88) | `ruff`, `black` |
| **Type Check** | mypy (ignore_missing_imports) | `mypy` |
| **Tests** | pytest | `pytest` |

---

## Cross-Cutting Concerns

### Concurrency Safety
- **Legacy**: Single-process lock via `storage/lock.py` (15-min timeout). No multi-instance protection beyond file lock.
- **Platform**: SQLite WAL mode + connection pool (default 5). Read-only → no write contention.

### Observability
- **Logging**: Standard `logging` module, structured in `main.py`, `delivery.py`, crawlers.
- **Metrics**: None (no Prometheus, OpenTelemetry, or custom counters).
- **Tracing**: None.
- **Health**: `/health` endpoint returns `{status: "ok", announcements: N}`.

### Configuration
- **Single `.env`** at repo root (`.env.example` committed). No per-service configs.
- **Environment-driven**: All secrets via `os.getenv()`. No config classes for legacy pipeline.
- **Platform**: `webapp.config.Settings` (Pydantic BaseSettings) with validation.

---

## Audit Findings Summary

| Area | Score (1-10) | Key Concerns |
|------|-------------|--------------|
| Modularity | 6 | Legacy pipeline monolithic in `main.py`; platform well-modularized |
| Separation of Concerns | 7 | Clear pipeline separation; shared `data/targets.json` is a coupling point |
| Scalability | 4 | SQLite + file lock limits horizontal scaling; no caching layer |
| Observability | 3 | No metrics, tracing, structured logging, or alerting |
| Configuration | 6 | `.env` works but no validation for legacy; platform uses Pydantic |
| Deployment | 5 | GitHub Actions dry-run only; no prod deploy automation for platform |

---

## Recommendations (High Priority)

1. **Extract legacy pipeline into a package** (`scraper/`) with clear CLI entry points — enables testing, reuse, and future service extraction.
2. **Add structured logging (JSON) + correlation IDs** across both pipelines.
3. **Introduce Redis cache** for platform search results and taxonomy lookups.
4. **Migrate platform to PostgreSQL** for production (connection pooling, concurrent reads, FTS via pg_trgm or pgroonga).
5. **Add health/readiness probes** with dependency checks (DB, FTS, external APIs).
6. **Implement CI/CD for platform** (build → test → deploy to staging/prod).

---

## Appendix: Entry Points

| Pipeline | Command | Schedule |
|----------|---------|----------|
| Legacy (dry-run) | `python main.py` | GitHub Actions: `0 6 * * *` |
| Legacy (live) | `DRY_RUN=false python main.py` | Manual / Railway (removed) |
| Platform API | `uvicorn api.main:create_app --factory --port 8000` | Manual / systemd |
| Platform Web | `python -m webapp.cli serve --port 8000` | Manual / systemd |
| Platform CLI | `python -m webapp.cli init-db --demo` | One-time setup |
| Frontend Dev | `npm run dev` | Developer |
| Frontend Build | `npm run build` | CI/CD |