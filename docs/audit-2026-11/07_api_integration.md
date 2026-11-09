# Audit Report 07: API & Integration Layer

**Date:** 2026-11-08  
**Repository:** dz-tenders-mvp  
**Auditor:** Claude Opus 5.5

---

## Executive Summary

Two **distinct API layers** serve different consumers:

1. **`api/`** — Read-only FastAPI for the React dashboard (`src/`). JSON-only, SQLite `mode=ro`, Pydantic models, consistent error envelopes.
2. **`webapp/web/`** — Server-rendered Jinja2 routes for public Arabic portal. Same business logic (`webapp/search.py`, `webapp/repositories.py`), HTML responses, plan-gated field visibility.

**No external integrations** (webhooks, webhooks, third-party APIs) except outbound notifications (Telegram, SMTP). **No API versioning** — single `v1` implied.

---

## API Layer 1: `api/` (Dashboard Backend)

### Entry Point: `api/main.py:create_app()`

```python
app = FastAPI(
    title="DZ Tenders API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
```

### Middleware Stack
1. **CORS** — `CORS_ORIGINS` from env (default `localhost:5173,127.0.0.1:5173`), `allow_credentials=True`
2. **Custom Error Handler** — `api/main.py:180` `http_exception_handler` → consistent envelope
3. **Request Logging** — `api/main.py:190` logs method, path, status, latency

### Endpoints

| Method | Path | Description | Response Model |
|--------|------|-------------|----------------|
| `GET` | `/health` | Liveness + announcement count | `HealthResponse` |
| `GET` | `/api/tenders` | Paginated, filtered, sorted listing | `TenderListResponse` |
| `GET` | `/api/tenders/{id}` | Single tender detail | `TenderResponse` |
| `GET` | `/api/stats` | Dashboard aggregates | `StatsResponse` |

### Request/Response Models (`api/models.py`)

```python
# Query parameters (validated by Pydantic)
class TenderQueryParams(BaseModel):
    q: str = ""                    # Search query
    type: TenderType | None = None # Enum: tender, consultation, ...
    wilaya: str = ""               # Wilaya code (2-char)
    sector: str = ""               # Sector slug
    date_from: date | None = None
    date_to: date | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    sort: SortOrder = SortOrder.RELEVANCE  # relevance, recent, deadline, oldest

# Response envelope
class TenderListResponse(BaseModel):
    items: list[TenderResponse]
    total: int
    page: int
    page_size: int
    pages: int
    used_fts: bool
    normalized_query: str

class TenderResponse(BaseModel):
    id: int
    title: str
    type: TenderType
    status: TenderStatus
    organisation: str
    wilaya: str
    product: str
    deadline: str | None
    published_date: str | None
    relevance_score: int
    matched_families: list[str]
    matched_products: list[str]
    source_url: str | None
    # ... (all fields from mapping.py)
```

### Repository: `api/repository.py:ReadOnlyTenderRepository`

```python
class ReadOnlyTenderRepository:
    def __init__(self, db_path: str):
        # SQLite read-only URI
        self.engine = create_engine(f"sqlite:///{db_path}?mode=ro", 
                                     connect_args={"check_same_thread": False})
        # Enforce read-only at session level
        @event.listens_for(self.engine, "connect")
        def set_readonly(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA query_only=ON")
    
    def list_tenders(self, params: TenderQueryParams) -> TenderListResponse:
        # Build WHERE clause dynamically
        # Use parameterized queries only
        # FTS5 if available, else LIKE fallback
    
    def get_tender(self, tender_id: int) -> TenderResponse | None:
        # PK lookup
    
    def get_stats(self) -> StatsResponse:
        # 5 COUNT queries (total, by type, by wilaya, by status, recent)
```

### Mapping: `api/mapping.py`

```python
PRODUCT_MARKERS = {  # Subset of targets.json for API relevance
    "PVC_PIPES": [...],
    "PEHD_PIPES": [...],
    "PE_TANKS": [...],
    "FITTINGS": [...],
}

def row_to_tender(row: sqlite3.Row) -> TenderResponse:
    # Compute relevance_score from matched families/products
    # priority_for_score() → P1/P2/P3/P4
    # derive_status() → OPEN/CLOSED/EXPIRED
```

### Error Handling

```python
# Consistent envelope for all errors
{
    "error": {
        "code": "VALIDATION_ERROR" | "NOT_FOUND" | "INTERNAL_ERROR",
        "message": "Human-readable message",
        "details": {}  # Optional (e.g., validation errors)
    }
}

# HTTP status mapping
400 → VALIDATION_ERROR (Pydantic validation)
404 → NOT_FOUND
422 → VALIDATION_ERROR (query params)
500 → INTERNAL_ERROR (logged, not exposed)
```

**Test Coverage**: `tests/test_api.py` — 44 tests (health, mapping, pagination, validation, injection, CORS, noise exclusion).

---

## API Layer 2: `webapp/web/` (Public Portal)

### Entry Point: `webapp/web/main.py:create_app()`

Same FastAPI instance serves both API (`/api/*`) and web routes (`/*`).

### Web Routes (`webapp/web/routes_public.py`)

| Route | Template | Purpose |
|-------|----------|---------|
| `GET /` | `home.html` | Hero, stats, latest 6 announcements |
| `GET /annonces` | `list.html` | Filterable, paginated listing |
| `GET /annonces/{id}/{slug?}` | `detail.html` | Announcement detail (plan-gated) |
| `GET /archives` | `archive_index.html` | Year list with counts |
| `GET /archives/{year}` | `archive_year.html` | Year-filtered listing |
| `GET /sous-traitance` | `subcontracting_list.html` | Subcontracting offers (gated) |
| `GET /sous-traitance/{id}` | `subcontracting_detail.html` | Offer detail (contact gated) |
| `GET /tarifs` | `pricing.html` | Plans with placeholder prices |
| `GET /mentions-legales` | `legal.html` | Legal notices |
| `GET /contact` | `contact.html` | Contact form (not wired) |
| `GET /sitemap.xml` | XML response | SEO sitemap |
| `GET /robots.txt` | Plain text | Crawler directives |
| `GET /health` | JSON | Platform health + announcement count |

### Auth Routes (`webapp/web/routes_auth.py`)

| Route | Method | Purpose |
|-------|--------|---------|
| `/connexion` | GET | Login form (CSRF token in cookie) |
| `/connexion` | POST | Validate phone/password/CSRF → set session cookie |
| `/deconnexion` | POST | Destroy session (CSRF required) |

### Dependencies (`webapp/web/deps.py`)

```python
# Database session (request-scoped)
def get_db() -> Generator[Session, None, None]:
    with session_scope(session_factory) as db:
        yield db

# Current user (optional)
def get_current_user(
    request: Request, 
    db: Session = Depends(get_db)
) -> User | None:
    session_token = request.cookies.get("dz_session")
    if not session_token:
        return None
    return find_session(db, session_token)

# Plan-gated view builder
def build_announcement_view(
    announcement: Announcement,
    user: User | None,
    db: Session
) -> AnnouncementView:
    # Returns view with REASON_* for hidden fields
```

### Plan-Gated Field Visibility (`webapp/access.py`)

| Field | Free | Paid (Covered Sector) | Paid (Uncovered) | Expired |
|-------|------|----------------------|------------------|---------|
| Basic (title, type, sector, wilaya, date) | ✅ | ✅ | ✅ | ✅ |
| Issuer name | ❌ | ✅ | ❌ | ❌ |
| Deadline | ❌ | ✅ | ❌ | ❌ |
| Description | ❌ | ✅ | ❌ | ❌ |
| Reference | ❌ | ✅ | ❌ | ❌ |
| Attachments | ❌ | ✅ | ❌ | ❌ |
| Source URL | ❌ | ✅ | ❌ | ❌ |

**Reason Codes**: `REASON_SUBSCRIPTION_REQUIRED`, `REASON_SECTOR_NOT_COVERED`, `REASON_EXPIRED_SUBSCRIPTION`, `REASON_NOT_PUBLISHED`.

---

## Frontend Integration (`src/lib/api.ts`)

### Dual Mode Client

```typescript
// Mock mode for development (no backend needed)
const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";

export const api = {
  async fetchTenders(params: TenderQueryParams): Promise<TenderListResponse> {
    if (USE_MOCK) return mockTenders(params);
    const res = await fetch(`/api/tenders?${new URLSearchParams(params)}`);
    return res.json();
  },
  // ... fetchDashboardStats, fetchStatistics
};
```

### TanStack Query Hooks

```typescript
// Automatic caching, deduping, background refetch
export function useTenders(params: TenderQueryParams) {
  return useQuery({
    queryKey: ["tenders", params],
    queryFn: () => api.fetchTenders(params),
    staleTime: 30_000,
  });
}
```

### TypeScript Contracts (Shared with API)

```typescript
// src/lib/types.ts (mirrors api/models.py)
interface TenderResponse {
  id: number;
  title: string;
  type: TenderType;
  // ...
}
interface TenderListResponse {
  items: TenderResponse[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  used_fts: boolean;
  normalized_query: string;
}
```

---

## Integration Points

### 1. Legacy → Platform (One-Way Data Flow)

| Mechanism | Description |
|-----------|-------------|
| **Shared Taxonomy** | `data/targets.json` used by `tender_filter.py` and `webapp/seed.py` |
| **Manual Sync** | No automated pipeline; platform seeded via CLI `init-db --demo` |
| **Future** | Legacy could write to `platform.db` via `Announcement` model |

### 2. Notifications (Outbound Only)

| Channel | Trigger | Payload |
|---------|---------|---------|
| **Telegram** | `delivery.py:deliver()` after save | Excel file + caption (Markdown) |
| **SMTP Digest** | `delivery.py:deliver()` after save | HTML digest (grouped by priority) |
| **Excel Report** | Generated in-memory | `notifications/excel_report.py` → DataFrame → BytesIO |

### 3. Crawler Authentication (Inbound to External)

| Portal | Auth Method | Credentials |
|--------|-------------|-------------|
| MounakassatDZ | Form login (POST) | `MOUN_PHONE`, `MOUN_PASSWORD` |
| Marches Publics | Playwright session file | `storage/marches_state.json` (pre-authenticated) |
| ADE / Safqatic / Google News | None (public) | N/A |

---

## API Quality Assessment

| Criterion | `api/` | `webapp/web/` | Score |
|-----------|--------|---------------|-------|
| **OpenAPI Spec** | ✅ Auto-generated (`/docs`) | ❌ Not exposed | 7/10 |
| **Versioning** | None (v1 implicit) | None | 5/10 |
| **Validation** | ✅ Pydantic query/body | ✅ Pydantic + manual | 8/10 |
| **Error Envelope** | ✅ Consistent | ✅ HTML + JSON for HTMX | 8/10 |
| **Rate Limiting** | ❌ None | ✅ Login only (5/15min) | 5/10 |
| **Auth** | ❌ None (read-only) | ✅ Session + CSRF | 7/10 |
| **Pagination** | ✅ Cursor-like (page/size) | ✅ Page numbers | 8/10 |
| **Filtering** | ✅ Rich (7 params) | ✅ Same + UI | 9/10 |
| **Sorting** | ✅ 4 options | ✅ Same | 8/10 |
| **Caching Headers** | ❌ None | ❌ None | 4/10 |
| **Compression** | ❌ Not configured | ❌ Not configured | 5/10 |
| **Request ID** | ❌ None | ❌ None | 4/10 |

---

## Audit Findings

| ID | Severity | Finding | Component | Recommendation |
|----|----------|---------|-----------|----------------|
| API-01 | MEDIUM | **No API versioning** — breaking changes risk | Both | Add `/v1/` prefix; deprecation policy |
| API-02 | MEDIUM | **No rate limiting on read API** | `api/` | Add token bucket (Redis) per IP/API key |
| API-03 | LOW | **No caching headers** (ETag, Cache-Control) | Both | Add `Cache-Control: public, max-age=60` for listings |
| API-04 | LOW | **No request correlation ID** | Both | Add middleware generating `X-Request-ID` |
| API-05 | LOW | **No response compression** (gzip/brotli) | Both | Add `GZipMiddleware` (FastAPI) |
| API-06 | MEDIUM | **Mock/real drift risk** | `src/lib/api.ts` | Contract tests: `mockTenders()` vs real API schema |
| API-07 | INFO | **No webhook/event system** | N/A | Consider for future: `announcement.published` events |
| API-08 | LOW | **`webapp` health endpoint duplicates `api`** | Both | Consolidate; single source of truth |
| API-09 | MEDIUM | **CORS allows credentials without origin validation** | `api/main.py` | Restrict to exact origins; no wildcard with credentials |
| API-10 | LOW | **No API key management** (if external consumers added) | N/A | Design for future: hashed keys, scopes, quotas |

---

## Contract Testing Gap

**Current**: No automated verification that `mockTenders()` matches real API schema.

**Recommended**: 
```python
# tests/contract/test_api_contract.py
def test_mock_matches_real_schema():
    mock_response = mock_tenders()
    real_schema = TenderListResponse.model_json_schema()
    assert validate(mock_response, real_schema)
```

---

## Integration Test Coverage

| Flow | Covered? | Test File |
|------|----------|-----------|
| Scraper → DB → API | ❌ | — |
| Scraper → DB → Web | ❌ | — |
| Web Search → FTS → Results | ✅ | `test_phase1_search.py` |
| Web Detail → Access Gate → View | ✅ | `test_phase1_routes.py` |
| Auth Login → Session → Protected | ✅ | `test_phase1_auth.py` |
| Notifications → Telegram/Email | ✅ | `test_notifications.py` (unit) |

---

## Recommendations

### Immediate
1. **Add API versioning** — `/api/v1/` prefix; update frontend `VITE_API_URL`
2. **Enable GZip compression** — `app.add_middleware(GZipMiddleware, minimum_size=500)`
3. **Add `Cache-Control` headers** — 60s for listings, 300s for stats, no-store for auth
4. **Fix CORS** — Exact origin list; no `allow_credentials=True` with wildcard

### Short Term
5. **Add rate limiting to `api/`** — Redis token bucket (100 req/min/IP)
6. **Implement request correlation IDs** — Middleware + logging
7. **Contract tests for mock/real parity** — CI gate
8. **Consolidate health endpoints** — Single implementation

### Medium Term
9. **Design webhook system** — `announcement.published`, `subscription.created`
10. **API key management** — If third-party integrations needed
11. **Automated legacy→platform sync** — Pipeline writing `Announcement` records