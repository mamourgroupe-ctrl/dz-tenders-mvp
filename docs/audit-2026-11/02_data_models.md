# Audit Report 02: Data Models & Schema

**Date:** 2026-11-08  
**Repository:** dz-tenders-mvp  
**Auditor:** Claude Opus 5.5

---

## Executive Summary

Two **independent SQLite databases** with no shared models or migrations:

1. **`storage/tenders.db`** (Legacy) — 7 tables, implicit schema via `TenderDatabase` class
2. **`storage/platform.db`** (Platform) — 28 SQLAlchemy models, Alembic-managed (1 migration: `e416d5834430`)

---

## Legacy Schema (`storage/tenders.db`)

Defined imperatively in `storage/database.py:TenderDatabase.__init__()`:

```sql
-- Core tender storage
CREATE TABLE tenders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    link TEXT NOT NULL UNIQUE,           -- deduplication key
    reference TEXT,
    organisation TEXT,
    wilaya TEXT,
    product TEXT,
    deadline TEXT,
    status TEXT,
    published_date TEXT,
    source TEXT NOT NULL,                -- 'ade', 'mounakassat', 'marches_publics', etc.
    source_uuid TEXT,                    -- external ID for idempotency
    mode TEXT,
    nature TEXT,
    ministere TEXT,
    commune TEXT,
    relevance_score INTEGER DEFAULT 0,
    matched_families TEXT,               -- JSON array
    matched_products TEXT,               -- JSON array
    wilaya_priority TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Fingerprint deduplication (SHA256 of normalized title+org+date)
CREATE TABLE tender_fingerprints (
    fingerprint TEXT PRIMARY KEY,        -- SHA256 hex
    tender_id INTEGER NOT NULL,
    FOREIGN KEY(tender_id) REFERENCES tenders(id)
);

-- Sent notification tracking (prevents re-delivery)
CREATE TABLE sent_tenders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tender_id INTEGER NOT NULL UNIQUE,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    channel TEXT NOT NULL,               -- 'telegram', 'email', 'excel'
    FOREIGN KEY(tender_id) REFERENCES tenders(id)
);

-- Failed delivery attempts (blocks after 3 failures)
CREATE TABLE failed_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tender_id INTEGER NOT NULL,
    attempt_count INTEGER DEFAULT 1,
    last_attempt_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_error TEXT,
    FOREIGN KEY(tender_id) REFERENCES tenders(id)
);

-- Blocked tenders (permanently excluded after 3 failed deliveries)
CREATE TABLE blocked_tenders (
    tender_id INTEGER PRIMARY KEY,
    reason TEXT,
    blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(tender_id) REFERENCES tenders(id)
);

-- Noise patterns (titles to auto-reject)
CREATE TABLE noise_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Schema version tracking
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY
);
```

**Indexes** (created in `TenderDatabase._ensure_schema()`):
- `idx_tenders_link` ON `tenders(link)`
- `idx_tenders_source_uuid` ON `tenders(source_uuid)`
- `idx_tenders_published_date` ON `tenders(published_date)`
- `idx_tenders_relevance` ON `tenders(relevance_score DESC)`
- `idx_tenders_source` ON `tenders(source)`

---

## Platform Schema (`storage/platform.db`)

Managed by Alembic (migration `e416d5834430_phase_1_platform_schema.py`). **28 tables** across 6 domains:

### 1. Taxonomy (Reference Data)

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `wilayas` | 69 Algerian wilayas | `code` (2-char, UNIQUE), `slug`, `name_ar`, `name_fr`, `is_active` |
| `sectors` | Business sectors | `slug` (UNIQUE), `name_ar`, `name_fr`, `sort_order`, `is_active` |
| `issuers` | Tender-issuing entities | `slug` (UNIQUE), `name_ar`, `name_fr`, `kind`, `wilaya_id` (FK), `website`, `is_active` |

### 2. Users & Auth

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `users` | Subscribers + staff | `phone` (UNIQUE, E.164), `email` (UNIQUE), `company_name`, `password_hash` (argon2id), `role` (user/editor/support/admin), `is_active`, `locale`, `last_login_at` |
| `user_sessions` | Server-side sessions | `token_hash` (UNIQUE), `user_id` (FK), `expires_at`, `ip_hash`, `user_agent` |
| `one_time_tokens` | Email verification, password reset | `token_hash` (UNIQUE), `user_id` (FK), `purpose` (verify_email/reset_password), `expires_at`, `used_at` |

### 3. Plans & Subscriptions

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `plans` | Subscription tiers | `code` (UNIQUE), `name_ar/fr`, `kind` (subscription/addon), `sector_limit`, `auctions_only`, `price_monthly_dzd`, `price_annual_dzd`, `is_price_placeholder`, `is_active`, `sort_order` |
| `subscriptions` | User-plan bindings | `user_id` (FK), `plan_id` (FK), `status` (pending/active/expired/cancelled), `starts_at`, `ends_at`, `billing_period` (monthly/annual) |
| `subscription_sectors` | Sector entitlements per subscription | `subscription_id` (FK), `sector_id` (FK) — PK(subscription_id, sector_id) |

### 4. Announcements (Core Content)

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `announcements` | Tenders/consultations/awards | `ref` (UNIQUE), `slug` (UNIQUE), `type` (9 enum values), `status` (5 enum values), `title_ar/fr`, `description_ar/fr`, `issuer_id` (FK), `issuer_name` (denormalized), `wilaya_id` (FK), `reference`, `publish_date`, `publish_year`, `deadline_at`, `estimated_value_dzd`, `source_url`, `source_name`, `search_text` (normalized for LIKE), `is_sample`, `confidence`, `view_count`, `duplicate_of_id` (FK self), `source_key`, `external_id` (UNIQUE with source_key), `created_by_id`, `reviewed_by_id`, `published_at` |
| `announcement_sectors` | Many-to-many | `announcement_id`, `sector_id`, `is_primary` |
| `attachments` | Files (PDF, images) | `announcement_id` (FK), `original_name`, `stored_name` (UNIQUE), `content_type`, `size_bytes`, `sha256`, `is_public` |

### 5. Subcontracting

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `subcontracting_offers` | Subcontracting notices | `slug` (UNIQUE), `title`, `description`, `sector_id`, `wilaya_id`, `issuer_name`, `contact_name`, `contact_phone`, `contact_email`, `deadline`, `status` (pending/published/rejected/closed), `submitted_by_id`, `moderated_by_id`, `published_at` |

### 6. Operational / Audit

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `alerts` | Saved searches | `user_id` (FK), `name`, `frequency` (daily/weekly), `is_active`, `last_sent_at`, `unsubscribe_token` (UNIQUE) |
| `alert_sectors` / `alert_wilayas` | Alert filters | M2M tables |
| `alert_deliveries` | Delivery log | `alert_id`, `announcement_id`, `status`, `sent_at`, `error` |
| `audit_logs` | Admin actions | `actor_user_id`, `action`, `entity_type`, `entity_id`, `meta` (JSON), `ip_hash` |
| `search_logs` | Search analytics | `term`, `term_normalized`, `result_count` |
| `rate_limit_events` | Login/IP throttling | `bucket`, `key_hash`, `created_at` (indexed) |
| `banners` | Promotional banners | `placement` (home_top/home_middle/list_sidebar), `target_url`, `starts_at`, `ends_at`, `impressions`, `clicks` |
| `payments` | Subscription payments | `user_id`, `subscription_id`, `plan_id`, `method` (bank_transfer/postal_account/cash), `amount_dzd`, `reference`, `proof_filename`, `proof_sha256`, `status` (pending/verified/rejected), `verified_by_id` |
| `saved_announcements` | User bookmarks | `user_id`, `announcement_id` — PK(user_id, announcement_id) |

---

## FTS5 Virtual Table (SQLite-only)

Created in migration `upgrade()` for SQLite dialect:

```sql
CREATE VIRTUAL TABLE announcement_fts USING fts5(
    title, body, issuer,
    tokenize = 'unicode61 remove_diacritics 2'
);
```

- **Tokenization**: Unicode 6.1, diacritic removal, 2-gram (bigram) for partial matching
- **Population**: `webapp.search_index.rebuild_index()` syncs from `announcements.search_text`
- **Fallback**: `webapp.search._like_condition()` uses `Announcement.search_text LIKE %term%` with escape

---

## Data Dictionary: Key Enums

### AnnouncementType (9 values)
```python
TENDER = "tender"
CONSULTATION = "consultation"
PROVISIONAL_AWARD = "provisional_award"
AUCTION = "auction"
CANCELLATION = "cancellation"
DEADLINE_EXTENSION = "deadline_extension"
NOTICE_OF_DEFAULT = "notice_of_default"
CONTRACT_TERMINATION = "contract_termination"
```

### AnnouncementStatus (5 values)
```python
DRAFT = "draft"
PENDING_REVIEW = "pending_review"
PUBLISHED = "published"
ARCHIVED = "archived"
REJECTED = "rejected"
```

### UserRole (4 values)
```python
USER = "user"
EDITOR = "editor"
SUPPORT = "support"
ADMIN = "admin"
```

### PlanKind (2 values)
```python
SUBSCRIPTION = "subscription"
ADDON = "addon"
```

### SubcontractingStatus (4 values)
```python
PENDING = "pending"
PUBLISHED = "published"
REJECTED = "rejected"
CLOSED = "closed"
```

---

## Schema Evolution & Migration Strategy

| Aspect | Legacy | Platform |
|--------|--------|----------|
| **Migration Tool** | None (imperative `CREATE TABLE IF NOT EXISTS`) | Alembic (versioned, reversible) |
| **Current Version** | Implicit (schema_version table = 1) | `e416d5834430` (head) |
| **Rollback** | Manual SQL | `alembic downgrade -1` |
| **Seed Data** | `data/targets.json` → `tender_filter.py` | `webapp.seed.seed_all()` via CLI |
| **FTS Rebuild** | N/A | `python -m webapp.cli reindex` |

---

## Audit Findings

| ID | Severity | Finding | Evidence | Impact | Recommendation |
|----|----------|---------|----------|--------|----------------|
| DM-01 | HIGH | **No foreign keys in legacy schema** — referential integrity enforced only in application code | `storage/database.py` creates tables without FK constraints | Orphaned rows, data corruption risk | Add FK constraints; enable `PRAGMA foreign_keys=ON` |
| DM-02 | MEDIUM | **Denormalized `issuer_name` on announcements** — duplicates `issuers.name_ar` | `migrations/...:454` `issuer_name` NOT NULL alongside `issuer_id` FK | Inconsistency if issuer renamed | Remove `issuer_name`; join at query time (index exists) |
| DM-03 | MEDIUM | **`search_text` column duplicates FTS content** — 2x storage for searchable text | `migrations/...:463` `search_text` TEXT NOT NULL | Storage bloat; sync drift risk | Drop `search_text`; use FTS `snippet()` for highlights |
| DM-04 | LOW | **`wilayas.code` is `VARCHAR(3)` but Algerian codes are 2 digits** | `migrations/...:163` `code` length 3 | Wasted space; allows invalid data | Change to `CHAR(2)`; add CHECK constraint |
| DM-05 | LOW | **No `CHECK` constraints on enum-like columns** (status, type, role) | All enum columns use `native_enum=False` → VARCHAR | Invalid values possible via raw SQL | Add `CHECK (col IN (...))` or use native enums in Postgres |
| DM-06 | MEDIUM | **`tender_fingerprints` uses SHA256 but no collision handling** | `storage/database.py:147` `fingerprint` = SHA256(title+org+date) | Theoretical collision → silent dedup failure | Use `source_key + external_id` composite (platform pattern) |
| DM-07 | HIGH | **Legacy `blocked_tenders` has no TTL/auto-expiry** | `storage/database.py:418` `block_tender()` inserts forever | False positives persist indefinitely | Add `expires_at`; periodic review job |
| DM-08 | LOW | **Platform `payments.proof_sha256` nullable but should be required for verified** | `migrations/...:568` `proof_sha256` NULL allowed | Integrity verification gap | Add partial unique index or application-level validation |

---

## Cross-Pipeline Data Mapping

| Legacy Field | Platform Equivalent | Notes |
|--------------|---------------------|-------|
| `tenders.title` | `announcements.title_ar` | Platform has `title_fr` too |
| `tenders.link` | `announcements.source_url` | Platform adds `source_key` + `external_id` for idempotency |
| `tenders.organisation` | `announcements.issuer_name` + `issuers.name_ar` | Platform normalizes to `issuers` table |
| `tenders.wilaya` | `announcements.wilaya_id` → `wilayas.code` | Platform uses FK to taxonomy |
| `tenders.product` | `announcement_sectors` → `sectors.slug` | Many-to-many vs single string |
| `tenders.relevance_score` | Not stored (computed at search) | Platform uses FTS BM25 ranking |
| `tenders.matched_families` | Not stored | Platform uses sector subscriptions for gating |

---

## Recommendations

1. **Enable SQLite FK enforcement** in legacy: `PRAGMA foreign_keys=ON` at connection open.
2. **Unify idempotency keys**: Adopt platform's `(source_key, external_id)` composite in legacy.
3. **Remove denormalized columns** (`issuer_name`, `search_text`) in next platform migration.
4. **Add CHECK constraints** for all enum-backed VARCHAR columns.
5. **Implement blocked tender TTL** (e.g., 90 days) with admin review workflow.
6. **Plan Postgres migration** for platform: native enums, partial indexes, `pg_trgm` for Arabic search.