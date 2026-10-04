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
