# DZ-TENDERS-MVP

> Automated Algerian public tenders scraper with intelligent filtering and Telegram notifications.

## Overview

DZ-TENDERS-MVP is a Python project that:
- Scrapes tenders from multiple government websites (ADE, ONA, AlgeriaTenders).
- Filters tenders based on marketing targets (8 business families).
- Classifies tenders with a weighted scoring system and Arabic NLP support.
- Sends automatic reports to Telegram (text + Excel file).

## Features

- Multi-source crawling (ADE, ONA, AlgeriaTenders)
- Intelligent Arabic filtering (prefix and word-boundary handling)
- Weighted scoring classification
- Support for 8 marketing families
- Telegram notifications with Excel attachment
- Secure secrets storage with `.env` + `.gitignore`

## Tech Stack

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)
![Git](https://img.shields.io/badge/Git-F05032?style=for-the-badge&logo=git&logoColor=white)

## Frontend Dashboard

The repository includes a React 18 + TypeScript dashboard for exploring Algerian tenders. It runs with a local mock API by default and can be switched to the FastAPI service when it is available.

### Run the dashboard

```bash
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). The dashboard includes the overview, tender search, tender detail drawer with Leaflet map, favorites, dark mode, and statistics pages.

### Connect the FastAPI service

The read-only FastAPI backend lives in `api/` (`api/main.py`, factory
`create_app`). It serves the existing SQLite `tenders` table — it never
creates, migrates, or writes to the database.

#### Backend setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
# The database must already exist (created by the collection pipeline,
# e.g. `python main.py` / `TenderDatabase`). The API will not create it:
# a missing database yields HTTP 503 `database_unavailable`.
.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/health          # {"status":"ok","database":"available","tenders":N}
curl "http://localhost:8000/api/tenders?page=1&page_size=20"
```

Environment variables (see `.env.example`, empty placeholders only):

| Variable | Default | Purpose |
| --- | --- | --- |
| `DB_PATH` | `storage/tenders.db` (repo-root relative) | SQLite file opened read-only (`mode=ro`) |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated allowed origins; credentials are never enabled |
| `PORT` | `8000` locally | Hosting port used by the `Procfile` command |

Endpoints (all `GET`, public-read, unauthenticated — only tender
listings collected for publication are exposed):

| Endpoint | Response |
| --- | --- |
| `GET /health`, `GET /api/health` | `{"status", "database", "tenders"}`; 503 when the DB is unavailable |
| `GET /api/tenders?search=&wilaya=&product=PVC_PIPES\|PEHD_PIPES\|PE_TANKS&priority=1..3&date_from=&date_to=&page=&page_size=` | `{"items": [Tender], "total", "page", "pageSize", "pages"}` (`page_size` max 100) |
| `GET /api/tenders/{id}` | One `Tender`, or 404 |
| `GET /api/stats/summary` | `{"total", "active", "priority1", "priority2", "priority3", "change"}` |
| `GET /api/stats/by-wilaya` | `[{"wilaya", "count", "percentage"}]` |
| `GET /api/stats/by-product` | `[{"product", "label", "count", "color"}]` |
| `GET /api/stats/timeline` | Last 30 days `[{"date", "label", "tenders"}]`, zeros included, no invented baseline |

Errors always use `{"error": {"code", "message", "details": [...]}}`
(422 `validation_error`, 404 `not_found`, 503 `database_unavailable`,
500 `internal_error`) without stack traces, SQL, or filesystem paths.

Schema mapping (`api/mapping.py`): the single stored `title` becomes
`titleAr` (Arabic) or `titleFr` (Latin, mirrored into `titleAr` for the
heading); `publicationDate` is the stored `first_seen` date;
`score = relevance_score`; `priority` reuses the project thresholds
(>=85 → 1, >=70 → 2, else 3); `status` derives from the real `deadline`;
`products` are recognized from the crawler free-text `product` column.
Coordinates, estimated value, official reference, description and
source name are **not stored**, so the API returns `null` for them and
the dashboard renders explicit "not available" states — they are never
fabricated.

#### Frontend setup

```bash
npm install
VITE_API_URL=http://localhost:8000/api npm run dev   # real API mode
# or, equivalently, proxy mode:
VITE_API_URL=/api npm run dev                       # Vite proxies /api → :8000
npm run dev                                          # explicit mock mode (no API URL)
```

Known limitations: the monthly comparison on the Statistics page is
limited to the API's 30-day timeline in real mode (no previous-period
series is stored), `organisationShort` repeats the stored organisation
name (no acronym is stored), and product recognition depends on the
crawler free-text `product` column, so unrecognized text yields an
empty `products` list rather than a guess.

Mock data is an explicit development mode used **only** when
`VITE_API_URL` is omitted. When an API URL is configured, failures are
shown as error states instead of silently falling back to mock data,
and win-rate/outcome widgets are hidden because outcomes are not
stored. Tests: `.venv/bin/python -m pytest` (API tests use temporary
synthetic databases only). Deployment: `Procfile` runs
`uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}`; the process
requires a pre-initialized `DB_PATH` file to answer anything but 503.

### Filter diagnosis

The tender classifier normalizes Arabic and French text (hamza forms, diacritics,
tatweel, Latin case), reads nested crawler schemas (`title_ar`, `products` as a
list or mapping, `objet`, …), and reports explicit rejection reasons instead of
silently returning zero results. See
[`docs/TENDER_FILTER_DIAGNOSTIC.md`](docs/TENDER_FILTER_DIAGNOSTIC.md) for the
root-cause analysis, verification commands, and the checklist for zero-result
runs.

For a production build:

```bash
npm run build
npm run preview
```

## Project Structure

## Blocked Notifications · إدارة الإشعارات المحجوبة

A tender is **blocked** after 3 failed delivery attempts, so a permanently broken
channel cannot re-notify the user every day. Inspect and release blocked tenders:

```bash
python -m storage.tools blocked              # list blocked tenders + last error
python -m storage.tools unblock --fp <hash>  # release one tender by fingerprint
python -m storage.tools unblock --all        # release every blocked tender
python -m storage.tools --db <path> blocked  # target a specific database
```

The fingerprint is the SHA-256 of `title|organisation|link`. Use `--db` when
running from another directory; otherwise the path comes from `DB_PATH`
(default `storage/tenders.db`). Note that `--db` is a global flag and must
precede the subcommand.

## Concurrent Runs · تشغيل متزامن آمن

`main.py`, `run_smart_scraper.py` and `test_run.py` share one database. Each run
reads "what is new?" and then writes "already sent", so two overlapping runs
would send the same tender twice. All three now go through one locked
transaction in `storage/delivery.py`:

1. Acquire an exclusive lock on `<db>.lock` — the database is not even opened
   before the lock is held, because opening it creates/migrates tables.
2. Select new tenders, persist them, build the report, send, then mark.

If another run holds the lock, the current run waits, then exits with code
**75** (`EX_TEMPFAIL`) having written nothing — a skipped cycle is
recoverable, a duplicate notification is not.

```bash
LOCK_TIMEOUT_SECONDS=900 python main.py     # default: wait up to 15 minutes
```

The lock uses only the standard library (`msvcrt` on Windows, `fcntl` on
POSIX) and is released automatically if a process is killed. It is reliable on
local filesystems only — do not rely on it over NFS or SMB.

`LOCK_TIMEOUT_SECONDS` is also honoured by `python -m storage.tools`, so
administrative commands never write over a running cycle.

## Database Path · مسار قاعدة البيانات

Relative paths (`DB_PATH`, default `storage/tenders.db`) resolve against the
**repository root**, not the current directory. Running a script from another
directory therefore targets the same file instead of silently creating a
second database. `storage.paths.resolve_db_path()` is the single source of
truth.

## Scheduled CI · المهمة المجدولة

`.github/workflows/scraper.yml` runs daily in **dry-run** and publishes
`tenders_results.json` / `.xlsx` as a workflow artifact instead of sending to
Telegram. The runner is ephemeral and the database is not tracked in git, so a
sending job would re-notify every tender every day. Keep that job free of
secrets.
