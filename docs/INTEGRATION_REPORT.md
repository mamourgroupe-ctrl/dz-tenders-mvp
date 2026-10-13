# Branch Integration Report — TENDRA DZ / DZ-TENDERS-MVP

Date: 2026-10-13
Author: Arena agent session `arena/1375cfc9-dz-tenders-mvp`

## 1. Scope

Integrate all valid, relevant, non-conflicting work from the outstanding
branches into `main`, keep the existing (newer) implementations, repair
regressions found during integration, and verify the pipeline with tests,
linters and a production build.

## 2. Baseline and recovery references

| Ref | Value | Note |
| --- | --- | --- |
| Original `main` commit | `dac2aee9f976e07758539000625b36c1d5eb4486` | merge of `0e11c4e` (feature/web-dashboard) + `00b39b7` (web-dashboard) |
| Local backup ref | `backup/main-pre-integration-20261013` | lightweight tag pointing at `dac2aee`; nothing on `main` is rewritten |
| Integration branch | `arena/1375cfc9-dz-tenders-mvp` | based on `dac2aee`; source of the PR to `main` |

The repository was a shallow clone; `git fetch --unshallow origin` was run
first so ancestry and merges could be evaluated correctly.

## 3. Branch inventory

| Branch | Tip | Unique commits vs `main` | Verdict |
| --- | --- | --- | --- |
| `origin/main` | `dac2aee` | — | baseline |
| `origin/feature/web-dashboard` | `0e11c4e` | 0 (ancestor of `main`) | already integrated |
| `origin/web-dashboard` | `00b39b7` | 0 (ancestor of `main`) | already integrated |
| `origin/arena/4592683f-dz-tenders-mvp` | `4a60ceb` | `755406f`, `4a60ceb` | **partially integrated** (additive classifier work only) |
| `origin/feature/dry-run-mode` | `f51e85b` | `66cd099`, `94d3e99`, `62dea7a`, `f51e85b` | **excluded — already present in main in a newer form** |

`dac2aee` is a real merge commit (parents `0e11c4e` + `00b39b7`); its tree is
byte-identical to the tip of `web-dashboard`, so no dashboard work was lost.

### 3.1 Integrated commit

`755406f` *"fix: harden bilingual tender classification"* (author:
`mamourgroupe-ctrl`, co-authored by arena-agent) is the only commit that
contains work not already present on `main`. Its parent is `0e11c4e`, i.e. it
was written **before** the Marches Publics auth crawler (`00b39b7`) existed, so
the branch is missing files that already live on `main`.

## 4. Files integrated (content-level, not a branch merge)

| File | Change vs `dac2aee` | Source |
| --- | --- | --- |
| `tender_filter.py` | +322 / −67 | `755406f` verbatim |
| `docs/TENDER_FILTER_DIAGNOSTIC.md` | +113 (new) | `755406f` verbatim |
| `tests/test_tender_filter_classification.py` | +91 (new, 6 tests) | `755406f` verbatim |
| `README.md` | +15 | diagnosis section (from `755406f`) + note that the FastAPI service is not implemented |
| `tests/test_main.py` | +5 | integration repair (see §6) |

What the integrated classifier adds over the previous implementation:

- `unicodedata.normalize("NFKC")`, Arabic diacritics/tatweel removal, hamza and
  `ى`/`ة` unification, `casefold()` for Latin text, punctuation → boundary.
- Whole-phrase matching with word boundaries (`(?<!\w)…(?!\w)`) instead of raw
  substring tests, so `pvc` no longer matches inside larger identifiers.
- Robust reading of the real crawler schemas: `title_ar`, `title_fr`, `titre`,
  `objet`, `products` as list **or** mapping, `product_codes`, nested values.
- `matched_product_evidence` per product category.
- `last_filter_diagnostics` + explicit rejection reasons
  (`product_required`, `no_product_or_family_match`) and a warning that names
  the dominant reason when a run classifies nothing — this is the fix for the
  "0 من 138" symptom described in `docs/TENDER_FILTER_DIAGNOSTIC.md`.

Preserved contracts (must not regress): `WEIGHT_ENTITY=4`, `WEIGHT_KEYWORD=2`,
`WEIGHT_PRODUCT=3`, `MIN_SCORE_THRESHOLD=3`, the freshness filter
(`FRESHNESS_*`, `REASON_*`), `REQUIRE_PRODUCTS` strict mode, the
`news_aggregator` exemption for Google News, `group_by_family`, `summary`.

## 5. Excluded changes and why

| Source | Change | Reason for exclusion |
| --- | --- | --- |
| `755406f` (implicit) | deletion of `crawlers/marches_publics_auth_crawler.py`, `scripts/marches_login.py`, `tests/test_marches_auth_crawler.py`, `tests/fixtures/marches_sample.json`, the crawler wiring in `main.py` / `crawlers/__init__.py`, and the `storage/marches_state.json` ignore rule | Those files never existed on that lineage, so their "deletion" is an artefact, not a decision. Removing them would delete a working, tested authenticated crawler. Kept. |
| `62dea7a` (feature/dry-run-mode) | rewrite of `crawlers/base_crawler.py` into an async Playwright session manager (`BaseCrawler(site_name)`, `storage/auth/<site>_state.json`, `chromium.launch(headless=False)`), plus a stray empty `storage/auth` file | It replaces the current `BaseCrawler` and drops `sanitize_url()` — a contract used by six crawlers and three test modules (SSRF-scheme filtering, control-char stripping, percent-encoding). Session persistence already exists for the source that needs it (`marches_publics_auth_crawler` + `scripts/marches_login.py`), and `.gitignore` already covers `storage/auth/`. Port it later as a separate additive module instead of replacing the base class. |
| `94d3e99` (feature/dry-run-mode) | `.vscode/settings.json`: `python.testing.pytestEnabled=false`, `unittestEnabled=true`, `-p *test.py` | The suite is pytest (229 tests, `pyproject.toml [tool.pytest.ini_options]`, fixtures/`monkeypatch`). Switching discovery to unittest would disable the real suite in the IDE. The `main.py` import-reordering part of this commit is already on `main`. |
| `66cd099` (feature/dry-run-mode) | `TenderStore.mark_sent/is_sent/count/close` compatibility methods | Already on `main` in a newer form: `storage/db.py` has all four; `mark_sent` there also inserts the tender, and `main.py` already calls `mark_notified`. |
| `f51e85b` (feature/dry-run-mode) | `DRY_RUN` skip in `main.py` + `storage/auth*` ignore rules | Already on `main`: `config.AppConfig.dry_run` → `storage.delivery.deliver(dry_run=…)` skips sending **and** skips `mark_sent`, so dry cycles do not consume notifications. `.gitignore:57-59` already ignores `storage/auth/`. |
| `4a60ceb` | merge commit on the arena branch | Merged `8bf0ff8` (dashboard) which is already in `main` through `dac2aee`. Nothing new. |

## 6. Regression repaired during integration

`tests/test_main.py::test_smart_scraper_skips_blocked_tender` was already
failing on `main` before any integration. Root cause: commit `48e6ec7`
(W7-b, shared delivery pipeline) made `run_smart_scraper.py` gate the Telegram
sender on `TELEGRAM_BOT_TOKEN` (`send if TELEGRAM_BOT_TOKEN else None`) and did
not update the test, which still exercised the send path without a token — the
run therefore logged `تخطّي الإرسال: لا مُرسّل متاح` and asserted
`len(sent) == 1` against an empty list.

The fix is test-only and restores the test's original intent (blocked tender is
skipped, live tender is sent): the test now monkeypatches
`run_smart_scraper.TELEGRAM_BOT_TOKEN` with a dummy value. Production code was
not weakened.

## 7. Verification

Run on the integration branch (`2246ecb` + this report):

| Check | Command | Result |
| --- | --- | --- |
| Python tests | `.venv/bin/python -m pytest` | **229 passed, 0 failed** (exit 0) |
| Lint | `ruff check .` | **All checks passed** |
| Types | `mypy .` | 20 errors in 8 files — **pre-existing on `main`, unchanged by the integration** (`main.py:159-160` `TelegramChannel` `str | None`, etc.) |
| Frontend typecheck | `npm run lint` (`tsc --noEmit`) | clean |
| Frontend build | `npm run build` | success — 2477 modules, `dist/index.html` 0.48 kB, CSS 46.63 kB, JS 857.40 kB (rollup chunk-size warning only) |
| Dashboard runtime | `npm run dev` on `0.0.0.0:5173` | serves `200` for `/` and `/src/main.tsx`, including with a proxy-style `Host:` header |
| Offline pipeline smoke | fixture HTML → classify → SQLite → exports | 4/4 tenders parsed from the ADE fixture, 4/4 classified (scores 8), strict mode rejects with `product_required=1`, insert dedup `4` then `0`, pending-after-save 4 → 0 after `mark_notified`, Excel + HTML digest generated |
| Scheduled workflow | `.github/workflows/scraper.yml` | parses; runs `python test_run.py --dry-run` (CLI verified with `--help`); no secrets; artifacts `tenders_results.*` |

Test groups: crawlers and sanitisation 74; filter/freshness/classification 18;
storage/delivery/lock/paths 61; notifications/digest/email 17;
acceptance/smoke/CI-parity 14; config/logging/main 33 (some tests belong to more
than one group).

Safety: all tests use fixtures and mocks; `requests.get` is monkeypatched to
fail in crawler tests and in the smoke script. No Telegram message was sent, no
production database or external API was touched, and no credential is stored in
the repository (`git ls-files` contains no `.env`, `*.db`, `*.lock`,
`marches_state.json`).

## 8. Remaining risks / follow-ups

1. **No HTTP API exists.** No `api.py`/`app.py`/FastAPI service is present in
   any branch (only `README.md` and `.env.example` mention `/api/*`). The
   dashboard therefore runs on its local mock dataset; `VITE_API_URL` is the
   switch that will point it at a service. `Procfile` (`gunicorn app:app`) is
   likewise unusable until that service exists — either implement it or drop
   the references and the `flask`/`gunicorn` dependencies (roadmap W18/T15).
2. **Pre-existing type errors.** 20 mypy errors remain (not introduced here),
   including `main.py:159-160`.
3. **Two entry points remain.** `main.py` and `run_smart_scraper.py` both exist;
   both now go through the single locked `storage.delivery.deliver()`, but the
   roadmap item T13 (fold the smart scraper into `main.run()`) is still open.
4. **Live sources were not exercised.** Sandbox egress only allows GitHub,
   PyPI and npm, so Safqatic (Playwright), ADE and Google News were verified
   through fixtures/mocks only. The Marches Publics auth crawler needs a local
   `storage/marches_state.json` session and a headed browser.
5. **Blocked notifications require a human.** Tenders blocked after three
   failed attempts are visible/released with `python -m storage.tools
   blocked|unblock`; nothing unblocks them automatically.
6. **Branch protection could not be read** (`gh api …/branches/main/protection`
   returns 403 for this private repository). If protection exists, the merge
   into `main` needs the required review.

## 9. How to roll back

```bash
git checkout main
git reset --hard backup/main-pre-integration-20261013   # back to dac2aee
```

`main` history was never rewritten; the merge is additive.
