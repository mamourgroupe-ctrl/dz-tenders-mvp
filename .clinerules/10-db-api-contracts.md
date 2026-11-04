---
paths:
  - "api/**"
  - "storage/**"
  - "src/**"
---
# DB & API Contracts

## Database
- Path comes from `DB_PATH` env var; default `storage/tenders.db`.
- Schema changes must be reversible migrations.
- Never commit `storage/*.db` files.
- SQLite; use versioned scripts/migrations.

## API
- Base prefix: `/api` (also exposed at root for health).
- Endpoints:
  - `GET /health` -> `HealthResponse`
  - `GET /api/health` -> `HealthResponse`
  - `GET /api/tenders` -> `TenderPage` (filters: search, wilaya, product, priority, date_from, date_to; pagination)
  - `GET /api/tenders/{id}` -> `TenderOut`
  - `GET /api/stats/summary` -> `SummaryStats`
  - `GET /api/stats/by-wilaya` -> `WilayaPoint[]`
  - `GET /api/stats/by-product` -> `ProductPoint[]`
  - `GET /api/stats/timeline` -> `TimelinePoint[]`
- All responses JSON; errors use HTTP status + `{"error": {"code", "message", "details"}}` envelope (no stack traces/SQL/paths).
- Validation via Pydantic models; return 422 for validation errors.
- Public read-only; no unauthenticated writes.

## Frontend
- Fetch via relative `/api/*`; Vite proxy handles routing.
- Types shared between backend and frontend should stay in sync (`src/types.ts`, API models).
