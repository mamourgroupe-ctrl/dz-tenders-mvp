# Audit Report 04: Performance & Scalability

**Date:** 2026-11-08  
**Repository:** dz-tenders-mvp  
**Auditor:** Claude Opus 5.5

---

## Executive Summary

The system is **designed for low-to-moderate scale** (hundreds of tenders/day, thousands of users). Current architecture has **hard scalability ceilings**: SQLite + file lock (legacy), single-process FastAPI (platform), no caching, no horizontal scaling. For the current MVP scope (dry-run scraper + read-only platform), performance is adequate. Production growth requires PostgreSQL, Redis, and stateless services.

---

## Legacy Pipeline Performance

### Scraping Throughput

| Crawler | Pages/Run | Tendrs/Page | Est. Tendrs/Run | Duration |
|---------|-----------|-------------|-----------------|----------|
| ADE | 1 (listing) | ~20 | ~20 | ~10s |
| Mounakassat | 3 (configurable) | ~12 | ~36 | ~60s (6s delay/page) |
| Marches Publics | 3 (configurable) | ~12 | ~36 | ~60s (6s delay/page) |
| Safqatic | 1 | ~15 | ~15 | ~5s |
| Google News | 1 (RSS) | ~10 | ~10 | ~3s |

**Total**: ~120 tenders/run, ~2-3 minutes wall time.

### Bottlenecks

1. **Sequential crawling** — `main.py:scrape_all_sources()` awaits each crawler serially
2. **Fixed delays** — `MARCHES_DELAY_SEC=6`, Mounakassat similar; polite but slow
3. **File lock contention** — `LOCK_TIMEOUT_SECONDS=900` (15 min); blocks parallel runs
4. **No incremental scraping** — Full re-fetch each run (except Mounakassat progress tracking)
4. **Synchronous HTTP** — `requests` (blocking); no connection pooling across crawlers

### Database (tenders.db)

| Operation | Complexity | Index | Notes |
|-----------|------------|-------|-------|
| `save_many()` (upsert) | O(n) per tender | `link` UNIQUE, `source_uuid` | `INSERT OR IGNORE` + `UPDATE`; fingerprint check adds SHA256 |
| `mark_sent()` | O(1) | `sent_tenders.tender_id` UNIQUE | Single-row insert |
| `register_failed_attempt()` | O(1) | `failed_deliveries.tender_id` | Upsert with attempt counter |
| `is_blocked()` | O(1) | `blocked_tenders.tender_id` PK | Fast lookup |

**No slow queries observed** — dataset small (<10k rows expected).

---

## Platform Performance

### API Endpoints (`api/main.py`)

| Endpoint | Query Pattern | Pagination | Typical Latency (est.) |
|----------|---------------|------------|------------------------|
| `GET /api/tenders` | FTS5 MATCH or LIKE + filters | `limit`/`offset` (max 100) | 10-50ms (FTS), 50-200ms (LIKE) |
| `GET /api/tenders/{id}` | PK lookup + eager load | N/A | 5-15ms |
| `GET /api/stats` | 5 COUNT queries | N/A | 10-30ms |
| `GET /api/health` | `count_public()` | N/A | <5ms |

### Web Routes (`webapp/web/routes_public.py`)

| Route | Queries | Rendering | Notes |
|-------|---------|-----------|-------|
| `GET /` (home) | `home_stats()` (5 COUNTs), `latest_announcements()` (1) | Jinja2 | ~50ms |
| `GET /annonces` | `search_announcements()` (FTS/LIKE + COUNT) | Jinja2 + partial | ~50-200ms |
| `GET /annonces/{id}` | `published_announcement()` (PK + joins), `similar_announcements()` | Jinja2 | ~30ms |
| `GET /archives/{year}` | `search_announcements()` filtered by year | Jinja2 | ~50ms |

### Database (platform.db)

**Indexes** (from migration):
- `announcements`: 12 indexes including composite `(status, publish_date)`, `(type, status)`, `(wilaya_id)`, `(publish_year)`
- `announcement_fts`: FTS5 internal (BM25 ranking)
- `search_logs`: `term_normalized`, `created_at`
- `rate_limit_events`: `(bucket, key_hash, created_at)`
- `user_sessions`: `token_hash` (UNIQUE), `expires_at`, `user_id`

**Query Plans** (typical):
```sql
-- search_announcements with FTS (ranked)
SELECT ... FROM announcements
JOIN announcement_fts ON announcement_fts.rowid = announcements.id
WHERE announcement_fts MATCH :fts_query
  AND status IN ('published','archived')
  AND wilaya_id = ?
ORDER BY bm25(announcement_fts) ASC
LIMIT 12 OFFSET 0

-- search_announcements with LIKE (fallback)
SELECT ... FROM announcements
WHERE search_text LIKE '%' || ? || '%' ESCAPE '\'
  AND status IN ('published','archived')
ORDER BY publish_date DESC, id DESC
LIMIT 12 OFFSET 0
```

### Frontend Bundle (Production Build)

| Metric | Value | Assessment |
|--------|-------|------------|
| **JS Bundle** | 861.50 kB (244.89 kB gzip) | ⚠️ **>500 kB warning** — code-splitting needed |
| **CSS Bundle** | 46.63 kB (12.44 kB gzip) | ✅ Good |
| **Modules** | 2,478 transformed | Large; tree-shaking partial |
| **Chunks** | Single `index-BaYjmRPo.js` | No dynamic imports; all routes loaded upfront |

**Key Dependencies** (size contributors):
- `recharts` (~200 kB) — charts on Dashboard
- `leaflet` + `react-leaflet` (~150 kB) — map on TenderDrawer
- `@tanstack/react-query` (~50 kB)
- `lucide-react` (~80 kB) — icons

---

## Concurrency & Scaling Limits

| Component | Current Model | Max Concurrency | Scaling Path |
|-----------|---------------|-----------------|--------------|
| **Legacy Scraper** | Single process + file lock | 1 instance | Split into independent jobs; use queue (Redis/RQ) |
| **Platform API** | Uvicorn workers (default 1) | ~100 req/s (read-only SQLite) | Add workers; migrate to Postgres + PgBouncer |
| **Platform Web** | Same process as API | ~50 req/s (Jinja2 render) | Separate static/frontend; CDN for assets |
| **Frontend** | Static files (Vite build) | Unlimited (CDN) | ✅ Already scalable |
| **Database (Legacy)** | SQLite file + WAL | 1 writer, multiple readers | Postgres for concurrent writes |
| **Database (Platform)** | SQLite `mode=ro` + WAL | Multiple readers only | Postgres for scale + FTS (pg_trgm/pgroonga) |

**SQLite Read Scaling**: WAL mode allows concurrent readers, but:
- `PRAGMA query_only=ON` prevents writes
- Connection pool (SQLAlchemy default 5) limits parallel queries
- No read replicas possible

---

## Caching Strategy (Current: None)

| Data | Cacheable? | Current | Recommended |
|------|------------|---------|-------------|
| Taxonomy (wilayas, sectors, issuers) | ✅ High | None (DB every request) | Redis TTL 1h; invalidate on admin change |
| Search results (popular queries) | ✅ Medium | None | Redis TTL 5-15m; key = hash(filters+page) |
| Announcement detail | ✅ Medium | None | Redis TTL 1h; invalidate on publish/update |
| Home stats | ✅ High | None | Redis TTL 5m; recompute async |
| FTS index | ❌ (DB-native) | N/A | N/A |

**Impact**: Every listing page hit executes 2-3 COUNT queries + 1 SELECT — unnecessary for public data.

---

## Resource Utilization (Estimates)

| Resource | Legacy (per run) | Platform (steady) |
|----------|------------------|-------------------|
| **CPU** | Low (I/O bound scraping) | Low (read-only queries) |
| **Memory** | ~100 MB (Playwright ~200 MB) | ~50 MB (FastAPI + SQLAlchemy) |
| **Disk I/O** | Moderate (DB writes, Excel gen) | Low (reads only) |
| **Network** | Outbound to 5 portals | Inbound HTTP only |
| **DB Size** | ~10 MB (10k tenders) | ~50 MB (with FTS, demo data) |

---

## Audit Findings

| ID | Severity | Finding | Evidence | Impact | Recommendation |
|----|----------|---------|----------|--------|----------------|
| PERF-01 | HIGH | **No caching layer** — every request hits DB | `webapp/search.py`, `webapp/repositories.py` | Linear latency growth; DB bottleneck at scale | Add Redis; cache taxonomy (1h), search results (5m), stats (5m) |
| PERF-02 | HIGH | **Frontend bundle 861 kB** — no code splitting | `npm run build` output | Slow initial load (2-3s on 3G); poor Core Web Vitals | Dynamic imports for Dashboard/Map; lazy-load Recharts/Leaflet |
| PERF-03 | MEDIUM | **Sequential crawler execution** | `main.py:355` `scrape_all_sources()` | 2-3 min wall time; no parallelism | Run crawlers in parallel (ThreadPoolExecutor/asyncio); respect rate limits |
| PERF-04 | MEDIUM | **Fixed delays between pages** (6s) | `crawlers/marches_publics_auth_crawler.py:44` | 60s+ per crawler; polite but slow | Adaptive delay: exponential backoff on 429/5xx; min 1s |
| PERF-05 | MEDIUM | **SQLite connection pool default (5)** | `webapp/db.py:make_engine()` | Limits concurrent API requests | Increase pool_size; or migrate to Postgres + PgBouncer |
| PERF-06 | LOW | **No DB query monitoring** | No slow query logs | Cannot detect regressions | Log queries >100ms; add `sqlalchemy.engine` logging in dev |
| PERF-07 | LOW | **`home_stats()` runs 5 COUNT queries** | `webapp/repositories.py:113` | 5 round-trips per home page load | Combine into single query with `GROUPING SETS` (Postgres) or cache |
| PERF-08 | LOW | **FTS5 `unicode61 remove_diacritics 2` bigram** | Migration: `tokenize = 'unicode61 remove_diacritics 2'` | Index size ~2-3x text; good for Arabic partial match | Monitor index size; consider `trigram` for Postgres migration |
| PERF-09 | INFO | **No CDN for static assets** | `webapp/web/main.py` serves `/static/` | All asset requests hit app server | Configure CDN (Cloudflare, CloudFront) for `dist/` + `/static/` |
| PERF-10 | INFO | **Excel report generated in delivery critical section** | `storage/delivery.py:213` `deliver()` | Blocks lock during file I/O | Generate report async; or outside lock |

---

## Scaling Roadmap

### Phase 1: MVP → Beta (0-1k users)
- [ ] Add Redis cache for taxonomy + search results
- [ ] Code-split frontend (lazy load Dashboard, Map)
- [ ] Increase SQLite pool_size to 20
- [ ] Parallelize crawlers with semaphore (max 3 concurrent)

### Phase 2: Beta → Production (1k-10k users)
- [ ] Migrate platform to PostgreSQL (primary + read replica)
- [ ] Replace FTS5 with `pg_trgm` + GIN index or `pgroonga`
- [ ] Add PgBouncer (transaction pooling)
- [ ] Separate API and Web services (stateless)
- [ ] CDN for static assets + Vite `manifest.json` for cache-busting

### Phase 3: Production → Scale (10k+ users)
- [ ] Legacy scraper → queue workers (Redis/RQ or Celery)
- [ ] Platform → Kubernetes (HPA on CPU/request latency)
- [ ] Add observability (Prometheus + Grafana + Loki)
- [ ] Implement incremental scraping (if-modified-since / ETags)

---

## Benchmark Targets (Proposed)

| Metric | Current (est.) | Target (Beta) | Target (Prod) |
|--------|----------------|---------------|---------------|
| API P95 `/tenders` | 200ms | <100ms | <50ms |
| Web P95 `/annonces` | 300ms | <150ms | <100ms |
| Home page TTFB | 100ms | <50ms | <30ms |
| Frontend LC P75 | ~3s (3G) | <2s | <1.5s |
| Scraper run time | 3 min | <90s | <60s |
| DB CPU (steady) | <5% | <20% | <50% |