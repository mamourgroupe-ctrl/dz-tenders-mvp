# Audit Report 09: DevOps, CI/CD & Operations

**Date:** 2026-11-08  
**Repository:** dz-tenders-mvp  
**Auditor:** Claude Opus 5.5

---

## Executive Summary

**CI/CD is minimal** — only a GitHub Actions daily dry-run for the legacy scraper. **No deployment automation** for the platform (API, Web, Frontend). **No infrastructure as code** beyond Railway configs (removed). **Observability is absent** — no metrics, tracing, structured logging, or alerting. Operations rely on manual processes. For an MVP this is acceptable; for production it's a blocker.

---

## CI/CD Pipeline

### Current: `.github/workflows/scraper.yml`

```yaml
name: Daily Scraper Dry-Run
on:
  schedule:
    - cron: '0 6 * * *'  # Daily 06:00 UTC
  workflow_dispatch:     # Manual trigger

jobs:
  dry-run:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-${{ runner.os }}-${{ hashFiles('requirements.txt') }}
      - name: Install deps
        run: pip install -r requirements.txt
      - name: Install Playwright
        run: playwright install --with-deps chromium
      - name: Run scraper (DRY_RUN=true)
        env:
          DRY_RUN: "true"
          # No secrets — dry run only
        run: python main.py
      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: scraper-output
          path: |
            storage/tenders.db
            *.xlsx
          retention-days: 7
```

**What it does**: Runs legacy pipeline in `DRY_RUN=true` mode → scrapes, filters, generates Excel → uploads `tenders.db` + Excel as artifacts. **No secrets used**.

**What it lacks**: 
- Platform tests (API, Web, Frontend)
- Linting (ruff, black, tsc)
- Security scanning (pip-audit, npm audit)
- Deployment steps
- Notification on failure

### Missing Pipelines

| Pipeline | Needed For | Status |
|----------|------------|--------|
| **Platform API Tests** | `api/`, `webapp/` | ❌ |
| **Frontend Lint/Build** | `src/` | ❌ (local only) |
| **Security Scan** | Dependencies | ❌ |
| **Staging Deploy** | Platform (API + Web) | ❌ |
| **Production Deploy** | Platform + Frontend | ❌ |
| **Dependency Updates** | Renovate/Dependabot | ❌ |

---

## Infrastructure

### Current State

| Component | Current | Target (Prod) |
|-----------|---------|---------------|
| **Legacy Scraper** | GitHub Actions (scheduled) | Kubernetes CronJob / Cloud Scheduler |
| **Platform API** | Manual `uvicorn` | Kubernetes Deployment + Service |
| **Platform Web** | Manual `python -m webapp.cli serve` | Same as API (single process) |
| **Frontend** | `npm run build` → static files | CDN (Cloudflare Pages, Vercel, Netlify) |
| **Database (Legacy)** | SQLite file (`tenders.db`) | PostgreSQL (managed) |
| **Database (Platform)** | SQLite file (`platform.db`) | PostgreSQL (managed, read replica) |
| **Secrets** | `.env` local, Railway env | Secret Manager (AWS/GCP/Azure) / Vault |
| **File Storage** | Local `storage/uploads/` | S3-compatible (MinIO, Cloud Storage) |
| **Cache** | None | Redis (ElastiCache, Cloud Memorystore) |
| **Load Balancer** | None | Ingress Controller / Cloud LB |
| **DNS/SSL** | None | Managed certs (Let's Encrypt / Cloud) |

### Railway (Removed)

- Commit `c9678dc`: "remove railway config files in favor of dashboard settings"
- `Procfile` exists but untracked (`.gitignore`?)
- No active Railway deployment

---

## Configuration Management

### Environment Variables

| Scope | File | Count | Validation |
|-------|------|-------|------------|
| **Legacy** | `.env` (root) | ~25 | None (raw `os.getenv`) |
| **Platform** | `.env` (root) | ~30 | Pydantic `Settings` (`webapp/config.py`) |
| **Frontend** | `.env` (Vite) | 1 (`VITE_API_URL`) | Build-time only |

### `.env.example` (Committed)

Covers all known variables with defaults. **No sensitive values**.

### Configuration Gaps

1. **No environment separation** — single `.env` for dev/staging/prod
2. **No secret validation at startup** — platform `Settings` validates types but not presence of required secrets
3. **No feature flags** — all toggles via env vars (e.g., `FRESHNESS_ENABLED`)
4. **Frontend config at build time** — `VITE_API_URL` baked into bundle; cannot change without rebuild

---

## Observability

### Logging

| Component | Format | Level | Output |
|-----------|--------|-------|--------|
| Legacy (`main.py`, crawlers, storage) | `logging` (text) | INFO | Stdout |
| Platform API/Web | `logging` (text) | INFO | Stdout |
| Frontend | `console.*` | — | Browser |

**No structured logging (JSON)**. **No correlation IDs**. **No log aggregation**.

### Metrics

| Metric | Collected? | Tool |
|--------|------------|------|
| Request latency (p50/p95/p99) | ❌ | — |
| Request rate (RPS) | ❌ | — |
| Error rate (5xx, 4xx) | ❌ | — |
| DB query latency | ❌ | — |
| Cache hit rate | ❌ (no cache) | — |
| Scraper success/failure | ❌ | — |
| Notification delivery rate | ❌ | — |
| Business metrics (tenders/day, users) | ❌ | — |

### Tracing

- **None** — no OpenTelemetry, no distributed tracing

### Health Checks

| Endpoint | Checks | Depth |
|----------|--------|-------|
| `GET /health` (API) | DB connectivity + count | Shallow |
| `GET /health` (Web) | DB connectivity + count | Shallow |
| **Readiness** | None | — |
| **Liveness** | None (same as health) | — |

### Alerting

- **None** — no PagerDuty, OpsGenie, Slack webhooks, email alerts

---

## Backup & Disaster Recovery

| Asset | Backup Strategy | RPO | RTO |
|-------|-----------------|-----|-----|
| `tenders.db` (Legacy) | GitHub Actions artifact (7-day retention) | 24h | Manual |
| `platform.db` | None | ∞ | ∞ |
| `marches_state.json` | None (gitignored) | ∞ | Manual re-login |
| `storage/uploads/` | None | ∞ | ∞ |
| `data/targets.json` | Git (versioned) | 0 | Git restore |

**No automated DB backups**. **No restore procedures documented**. **No DR testing**.

---

## Security Operations

| Practice | Status |
|----------|--------|
| **Dependency Scanning** | ❌ Not in CI |
| **Secret Scanning** | ❌ Not in CI (GitHub secret scanning not enabled) |
| **SAST** | ❌ Not in CI |
| **Container Scanning** | N/A (no containers) |
| **Penetration Testing** | ❌ Never |
| **Incident Response Plan** | ❌ Not documented |
| **Vulnerability Disclosure** | ❌ No `SECURITY.md` |

---

## Development Workflow

### Local Development

```bash
# Legacy
python main.py                    # DRY_RUN=true by default
DRY_RUN=false python main.py      # Live (needs secrets)

# Platform API
uvicorn api.main:create_app --factory --reload --port 8000

# Platform Web
python -m webapp.cli serve --reload --port 8000

# Frontend
npm run dev                       # Vite dev server (port 5173)

# Database (Platform)
python -m webapp.cli init-db --demo
python -m webapp.cli reindex
```

### Code Quality Gates (Local Only)

```bash
ruff check .          # Lint
black --check .       # Format check
mypy .                # Type check (ignore_missing_imports)
pytest                # Tests
npm run lint          # tsc --noEmit
npm run build         # Production build
```

**Not enforced in CI** — only local/pre-commit (not configured).

---

## Audit Findings

| ID | Severity | Finding | Impact | Recommendation |
|----|----------|---------|--------|----------------|
| OPS-01 | CRITICAL | **No production deployment pipeline** | Cannot deploy platform reliably | Build CI/CD: test → build → deploy to staging → promote |
| OPS-02 | HIGH | **No observability (metrics, logs, traces)** | Cannot detect/debug production issues | Add OpenTelemetry → Prometheus → Grafana; structured JSON logs |
| OPS-03 | HIGH | **No automated DB backups** | Data loss risk | Scheduled `pg_dump` / SQLite `.backup` to object storage |
| OPS-04 | HIGH | **Secrets in `.env` / manual management** | Leak risk, rotation hard | Secret Manager (AWS Secrets Manager, GCP Secret Manager, Vault) |
| OPS-05 | MEDIUM | **No dependency vulnerability scanning** | Supply chain risk | Add `pip-audit` + `npm audit` to CI; enable Dependabot |
| OPS-06 | MEDIUM | **Single `.env` for all environments** | Config drift, accidents | Per-environment configs (`.env.dev`, `.env.staging`, `.env.prod`) |
| OPS-07 | MEDIUM | **Frontend config at build time** | Cannot change API URL without rebuild | Runtime config: `/config.json` fetched at startup |
| OPS-08 | LOW | **No health/readiness separation** | K8s cannot distinguish crash vs overload | Add `/ready` (DB + deps) vs `/live` (process alive) |
| OPS-09 | LOW | **No log aggregation** | Debugging across services hard | Ship logs to Loki/Elastic/Datadog; add correlation IDs |
| OPS-10 | LOW | **No DR plan / backup test** | Unknown recovery capability | Document RPO/RTO; quarterly restore drills |
| OPS-11 | INFO | **No feature flag system** | Deploy = release | Add simple flags (LaunchDarkly, Unleash, or DB-based) |
| OPS-12 | INFO | **No capacity planning** | Scaling reactive | Document current capacity; set scaling triggers |

---

## Recommended CI/CD Pipeline (GitHub Actions)

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  lint-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - name: Install deps
        run: pip install -r requirements.txt
      - name: Ruff
        run: ruff check .
      - name: Black
        run: black --check .
      - name: MyPy
        run: mypy .
      - name: Pytest
        run: pytest -q
      - name: Pip-audit
        run: pip-audit -r requirements.txt
  
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm' }
      - run: npm ci
      - run: npm run lint
      - run: npm run build
      - name: NPM audit
        run: npm audit --audit-level=high

# .github/workflows/cd-staging.yml
name: Deploy Staging
on:
  push:
    branches: [main]
jobs:
  deploy-api:
    # Build Docker image → push to registry → deploy to K8s staging
  deploy-frontend:
    # npm run build → upload to CDN (Cloudflare Pages, etc.)

# .github/workflows/cd-production.yml
name: Deploy Production
on:
  workflow_dispatch:
    inputs:
      version:
        description: 'Git tag or commit SHA'
        required: true
jobs:
  # Same as staging but with approval gate
```

---

## Infrastructure as Code (Missing)

| Tool | Status | Recommendation |
|------|--------|----------------|
| **Terraform/OpenTofu** | ❌ | Define cloud resources (DB, Redis, K8s, DNS, Certs) |
| **Helm/Kustomize** | ❌ | Package K8s manifests for API, Web, Frontend |
| **Ansible** | ❌ | VM provisioning (if not K8s) |
| **GitOps (ArgoCD/Flux)** | ❌ | Automated sync from Git to cluster |

---

## Runbook Outline (To Create)

| Scenario | Runbook | Status |
|----------|---------|--------|
| Scraper fails (GH Actions red) | Check logs → re-run → check artifacts | ❌ |
| Platform API 5xx | Check logs → DB connectivity → restart | ❌ |
| Platform Web 5xx | Same as API | ❌ |
| DB corruption | Restore from backup → reindex FTS | ❌ |
| Secret leaked | Rotate secret → update secret manager → redeploy | ❌ |
| Capacity exhaustion | Scale K8s deployment → check HPA | ❌ |
| Security incident | Isolate → investigate → patch → rotate | ❌ |

---

## DevOps Maturity Scorecard

| Capability | Level (1-5) | Description |
|------------|-------------|-------------|
| **Source Control** | 4 | Git, branching, PRs, conventional commits |
| **CI** | 2 | Scraper only; no lint/test for platform/frontend |
| **CD** | 1 | Manual only; no automation |
| **Testing** | 3 | Good unit/integration; no contract, E2E, chaos |
| **Observability** | 1 | Logs only; no metrics, traces, alerts |
| **Configuration** | 2 | Env files; no secret manager, no per-env |
| **Security** | 2 | Good code practices; no scanning, no IR plan |
| **Reliability** | 1 | No backups, no DR, no SLOs, no runbooks |
| **Overall** | **1.9** | **Early MVP — significant investment needed for production** |

---

## Prioritized Roadmap

### Sprint 1-2 (Foundation)
1. **CI for all components** — lint, type-check, test, security scan
2. **Structured JSON logging** — correlation IDs, log levels
3. **Health/Readiness endpoints** — `/live`, `/ready` with DB checks
4. **Secret Manager integration** — migrate `.env` secrets

### Sprint 3-4 (Deploy & Observe)
5. **Containerize** — `Dockerfile` for API, Web, Frontend (nginx)
6. **Staging environment** — K8s namespace / VM with full stack
7. **CD to staging** — Auto-deploy `main` branch
8. **Prometheus + Grafana** — Metrics (latency, errors, RPS, DB, cache)
9. **Log aggregation** — Loki or Cloud Logging

### Sprint 5-6 (Hardening)
10. **Production deployment** — Blue/green or rolling with approval
11. **Automated backups** — Daily DB snapshots, weekly restore test
12. **Alerting** — PagerDuty/Slack for 5xx rate, latency, scraper failure
13. **Runbooks** — Top 5 scenarios documented
14. **Load testing** — k6/Locust for API/Web endpoints

### Ongoing
- Dependabot PRs weekly
- Quarterly DR drill
- Annual pen test