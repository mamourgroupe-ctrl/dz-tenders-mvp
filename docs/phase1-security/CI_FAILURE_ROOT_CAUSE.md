# CI Failure Root Cause Report — PR #22

**Branch:** `security/phase1-data-safety`
**Commit:** `fc627bebafbe7893d9a967e8bf1808e363e0db21`
**PR:** https://github.com/mamourgroupe-ctrl/dz-tenders-mvp/pull/22
**CI Run:** https://github.com/mamourgroupe-ctrl/dz-tenders-mvp/actions/runs/42488225689
**Run Attempt:** 5
**Date:** 2026-11-09
**Mode:** READ ONLY — no project files modified

---

## 1. Executive Summary

CI run #42488225689 **failed** with all three jobs concluding in `failure`:

| Job | Duration | Result | Failing Step |
|-----|----------|--------|--------------|
| `python` | 34s | ❌ Failure | Black (format check) |
| `frontend` | 12s | ❌ Failure | Install dependencies (`npm ci`) |
| `CI Summary` | 4s | ❌ Failure | Upstream jobs failed |

Two **independent root causes** were confirmed:
1. **Black format check fails** — 36 Python files do not conform to Black formatting.
2. **`npm ci` fails with ERESOLVE** — peer dependency conflict between `vite@8.3.6` and `@vitejs/plugin-react@4.7.0`.

A third potential issue (starlette vulnerabilities) was identified but could not be confirmed in CI because the Python job failed before reaching `pip-audit`.

---

## 2. Python Job — Black Format Check (CONFIRMED)

### 2.1 Actual Error Message

CI step `Black (format check)` at `.github/workflows/ci.yml:48-49`:

```
run: black --check .
```

Exit code: 1. Steps after it (MyPy, Pytest, Pip-audit) were **skipped**.

### 2.2 Local Verification (CONFIRMED)

Running `python -m black --check .` locally with Black 26.10.1:

```
36 files would be reformatted, 79 files would be left unchanged.
```

### 2.3 Affected Files (36)

| File |
|------|
| `crawlers/safqatic_crawler.py` |
| `crawlers/mounakassat_crawler.py` |
| `crawlers/public_tender_crawler.py` |
| `tests/__init__.py` |
| `api/repository.py` |
| `storage/tender_quality.py` |
| `telegram_notifier.py` |
| `main.py` |
| `storage/delivery.py` |
| `storage/tools.py` |
| `tests/test_base_crawler.py` |
| `scripts/backup_db.py` |
| `scripts/restore_db.py` |
| `tests/test_notifications.py` |
| `tests/test_public_tender_crawlers.py` |
| `tests/test_ade_crawler.py` |
| `test_run.py` |
| `tools/ai_router.py` |
| `whatsapp_notifier.py` |
| `storage/database.py` |
| `tests/test_mounakassat_crawler.py` |
| `tests/test_w7_acceptance.py` |
| `tests/test_tender_filter_freshness.py` |
| `tests/test_main.py` |
| `tests/test_api.py` |
| `tests/test_storage.py` |
| `tender_filter.py` |

**Note:** `webapp/config.py` is NOT among the files flagged by Black. It is not the sole cause.

### 2.4 Root Cause (Confirmed)

Code changes in commit `fc627be` were not formatted according to Black's style (line-length=88, target=py311 as defined in `pyproject.toml:14-16`). The CI runs `black --check .` which fails when any file deviates from the configured format.

### 2.5 Proposed Fix

Run `black .` to auto-format all 36 files, then commit. Do NOT change `pyproject.toml` Black settings.

---

## 3. Frontend Job — `npm ci` ERESOLVE (CONFIRMED)

### 3.1 Actual Error Message

CI step `Install dependencies` at `.github/workflows/ci.yml:104-105`:

```
run: npm ci
```

Exit code: 1. Steps after it (TypeScript lint, Production build, NPM audit) were **skipped**.

Local reproduction of `npm ci` produced:

```
npm error code ERESOLVE
npm error While resolving: @vitejs/plugin-react@4.7.0
npm error Found: vite@8.3.6
npm error Could not resolve dependency:
npm error peer vite@"^4.2.0 || ^5.0.0 || ^6.0.0 || ^7.0.0" from @vitejs/plugin-react@4.7.0
npm error Conflicting peer dependency: vite@7.3.7
```

### 3.2 Root Cause (Confirmed)

Peer dependency mismatch between two packages declared in `package.json`:

| Package | Declared Version | Required Peer Range |
|---------|-----------------|---------------------|
| `vite` | `^8.3.6` | — |
| `@vitejs/plugin-react` | `^4.3.1` (resolves to 4.7.0) | `vite@"^4.2.0 \|\| ^5.0.0 \|\| ^6.0.0 \|\| ^7.0.0"` |

`@vitejs/plugin-react@4.7.0` does **not** support `vite@8.x`. It only supports vite 4, 5, 6, or 7. Vite 8.3.6 is outside the accepted peer range, causing `npm ci` to fail with ERESOLVE.

### 3.3 Affected Files

- `package.json` — declares incompatible versions of `vite` and `@vitejs/plugin-react`
- `package-lock.json` — locks `vite@8.3.6` and `@vitejs/plugin-react@4.7.0`, which are mutually incompatible

### 3.4 Additional Observations

| Observation | Detail |
|-------------|--------|
| Vite engine constraint | `vite@8.3.6` requires `node: ^20.19.0 || >=22.12.0` (`package-lock.json`) |
| Node.js 20 deprecation | `ubuntu-latest` runners now default to Node 24; `actions/checkout@v4`, `actions/setup-node@v4`, `actions/upload-artifact@v4` run on Node 24. Workflow specifies `node-version: '20'` which `setup-node` installs for workflow steps — this is a **warning**, not the cause of failure. |
| `npm-audit-report.json` missing | Not created because `npm ci` failed before reaching the audit step. |

### 3.5 Proposed Fix

Either:
- **Option A:** Downgrade `vite` to `^7.3.x` (compatible with `@vitejs/plugin-react@4.7.0`), or
- **Option B:** Upgrade `@vitejs/plugin-react` to a version that supports `vite@8.x` (e.g., `@vitejs/plugin-react@^8.x` if available), and update `package-lock.json` accordingly.

Do NOT use `--legacy-peer-deps` or `--force` as a permanent fix.

---

## 4. Vulnerability Review (pip-audit & npm audit)

### 4.1 pip-audit (Python) — NOT CONFIRMED IN CI

The Python job failed at Black before reaching `pip-audit`, so the vulnerability scan did not execute.

Local `pip-audit-report.json` shows **starlette 0.46.2** with multiple vulnerabilities:

| Vuln ID | Aliases | Fix Version |
|---------|---------|-------------|
| PYSEC-2026-1941 | CVE-2025-54121, GHSA-2c2j-9gv5-cj73 | 0.47.2 |
| PYSEC-2026-1942 | CVE-2025-62727, GHSA-7f5h-v6xp-fcq8 | 0.49.1 |
| PYSEC-2026-161 | CVE-2026-48710, GHSA-86qp-5c8j-p5mr | 1.0.1 |
| PYSEC-2026-2281 | CVE-2026-48818, GHSA-wqp7-x3pw-xc5r | 1.1.0 |
| PYSEC-2026-2280 | CVE-2026-48817, GHSA-x746-7m8f-x49c | 1.1.0 |
| PYSEC-2026-249 | CVE-2026-54283, GHSA-82w8-qh3p-5jfq | 1.3.1 |
| PYSEC-2026-248 | CVE-2026-54282, GHSA-jp82-jpqv-5vv3 | 1.3.0 |

**Severity:** The pip-audit JSON report uses `dependencies[].vulns[]` structure. The CI step at `.github/workflows/ci.yml:64` queries `.vulnerabilities[] | select(.severity == "HIGH" or .severity == "CRITICAL")` — this jq path **does not match** the actual report structure (which uses `.dependencies[].vulns[]`). As a result, `HIGH_CRITICAL` would evaluate to 0 or null, potentially allowing the step to pass despite vulnerabilities.

**Note:** `uvicorn[standard]>=0.30,<0.35` in `requirements.txt:8` pulls in `starlette`. The installed `starlette@0.46.2` is vulnerable. Fix requires upgrading starlette (which may require upgrading uvicorn beyond `<0.35` or finding a compatible patched version).

### 4.2 npm audit — NOT CONFIRMED IN CI

The frontend job failed at `npm ci` before reaching `npm audit`. No `npm-audit-report.json` was generated.

Local `npm audit` cannot be run against the official registry because the local machine uses `registry.npmmirror.com` (which does not implement the security advisories endpoint). CI uses `registry.npmjs.org` (full support).

### 4.3 Risk Statement

Build success does **not** imply dependency vulnerability freedom. Both `pip-audit` and `npm audit` must run and pass (zero HIGH/CRITICAL) before considering the dependency tree safe.

---

## 5. Local Environment Versions (for parity reference)

| Tool | Local Version | CI Version |
|------|--------------|------------|
| Python | 3.14.7 | 3.11 |
| Node.js | v24.21.0 | 20 |
| npm | 11.19.0 | (npm default for Node 20) |
| Black | 26.10.1 | >=24.0 (from requirements-dev.txt) |

**Important:** Local Python is 3.14.7 while CI uses 3.11. Local Node is 24 while CI uses 20. These differences may affect behavior but were not the cause of the observed failures.

---

## 6. Proposed Fixes Summary

| Issue | Priority | Fix |
|-------|----------|-----|
| Black format check | High | Run `black .` to format 36 files; commit |
| `npm ci` ERESOLVE | High | Resolve `vite` / `@vitejs/plugin-react` peer dep conflict (downgrade vite to ^7 or upgrade plugin) |
| pip-audit structure mismatch | Medium | Fix jq query in CI to match `.dependencies[].vulns[]` severity field |
| Starlette vulnerabilities | Medium | Upgrade starlette to patched version (0.47.2+ for PYSEC-2026-1941) |
| Node.js 20 deprecation | Low | Warning only; consider `node-version: '22'` or `'20.19.0'` |

---

## 7. Verification Commands After Fix

```bash
# Python formatting
python -m black --check .

# Python lint
ruff check .

# Python type check
mypy . --ignore-missing-imports

# Python tests
pytest -q

# Python audit
pip-audit -r requirements.txt -r requirements-dev.txt

# Frontend install (after fixing package.json/package-lock.json)
npm ci

# Frontend type check
npm run lint

# Frontend build
npm run build

# Frontend audit (against official registry)
npm audit --audit-level=high --registry=https://registry.npmjs.org
```

---

## 8. Tests That Must Pass Before Re-pushing

1. `black --check .` — zero files to reformat
2. `ruff check .` — no lint errors
3. `mypy . --ignore-missing-imports` — no type errors
4. `pytest -q` — all tests pass (334 locally on Python 3.14)
5. `pip-audit -r requirements.txt -r requirements-dev.txt` — zero HIGH/CRITICAL
6. `npm ci` — clean install, no ERESOLVE
7. `npm run lint` (tsc) — no TypeScript errors
8. `npm run build` — successful Vite build
9. `npm audit --audit-level=high` — zero HIGH/CRITICAL (official registry)

---

## 9. Conclusion

CI failure is caused by **two independent issues**:
1. **Black format check** — 36 unformatted Python files
2. **`npm ci` ERESOLVE** — `vite@8.3.6` incompatible with `@vitejs/plugin-react@4.7.0` peer requirements

Both must be fixed before the CI pipeline can pass. A third issue (starlette vulnerabilities and pip-audit jq path mismatch) requires attention but did not manifest in this run because earlier steps failed first.

**Do not merge or push fixes without review approval.**
