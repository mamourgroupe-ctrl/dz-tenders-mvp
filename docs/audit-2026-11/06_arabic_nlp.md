# Audit Report 06: Arabic NLP & Classification Pipeline

**Date:** 2026-11-08  
**Repository:** dz-tenders-mvp  
**Auditor:** Claude Opus 5.5

---

## Executive Summary

The Arabic text processing pipeline is a **core differentiator** — it handles normalization, tokenization, entity/keyword matching, weighted scoring, and product classification for 4 product categories across 8 marketing families. Implementation is in `tender_filter.py` (legacy) with platform search using `webapp/text.py`. **Quality is high** for a rule-based system: comprehensive normalization (NFKC, hamza folding, ta marbuta, tatweel, diacritics), bilingual (AR/FR/EN) keyword dictionaries, and tunable weights. **Not ML-based** — deterministic, explainable, no training data needed.

---

## Pipeline Architecture

```
Raw Tender Title/Description
         │
         ▼
┌─────────────────────────────────────┐
│ _normalize(text)                    │
│ 1. NFKC normalization               │
│ 2. Hamza folding: إ أ آ → ا          │
│ 3. Ta marbuta: ة → ه                │
│ 4. Tatweel removal: ـ → ""          │
│ 5. Diacritic stripping (harakat)    │
│ 6. Latin digit → Arabic-Indic       │
│ 7. Lowercase + whitespace collapse  │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ _tokenize(normalized)               │
│ - Split on non-word (Unicode)       │
│ - Filter stopwords (AR/FR/EN)       │
│ - Return set of tokens              │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ classify_tender(title, desc, org)   │
│ 1. Entity matching (exact substring)│
│ 2. Keyword matching (token overlap) │
│ 3. Product matching (markers)       │
│ 4. Wilaya priority (target/priority)│
│ 5. Weighted scoring                 │
│ 6. Family assignment (max score)    │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ filter_tenders(tenders)             │
│ - Apply MIN_SCORE threshold         │
│ - Require product match (config)    │
│ - Allow news as tenders (config)    │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ filter_fresh(tenders, window_days)  │
│ - Parse published_date              │
│ - Keep if within FRESHNESS_WINDOW   │
└─────────────────────────────────────┘
```

---

## Normalization Details (`tender_filter.py:_normalize`)

```python
def _normalize(text: str) -> str:
    # 1. Unicode NFKC (compatibility composition)
    text = unicodedata.normalize("NFKC", text)
    
    # 2. Hamza folding: all alif variants → bare alif
    text = re.sub(r"[إأآ]", "ا", text)
    
    # 3. Ta marbuta → ha
    text = text.replace("ة", "ه")
    
    # 4. Tatweel (kashida) removal
    text = text.replace("ـ", "")
    
    # 5. Diacritic stripping (harakat, tanwin, sukun, shadda)
    text = re.sub(r"[ً-ٰٟ]", "", text)
    
    # 6. Latin digits → Arabic-Indic (٠-٩)
    text = text.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))
    
    # 7. Lowercase + collapse whitespace
    text = " ".join(text.lower().split())
    
    return text
```

**Test Coverage**: `tests/test_tender_filter_classification.py` — 6 tests for normalization edge cases.

**Platform Equivalent**: `webapp/text.py:normalize_search()` — identical logic + `build_fts_query()` for FTS5 syntax.

---

## Taxonomy Source: `data/targets.json`

### Products (4 categories, 168 terms)

| Category | Terms | Languages | Examples |
|----------|-------|-----------|----------|
| `PE_TANKS` | 81 | AR/FR/EN | "خزان PE", "réservoir PE", "water tank", "citerne d'eau" |
| `PEHD_PIPES` | 50 | AR/FR/EN | "أنبوب PEHD", "tuyau PEHD", "HDPE pipe", "PE100" |
| `PVC_PIPES` | 44 | AR/FR/EN | "أنبوب PVC", "tuyau PVC", "PVC-U", "UPVC" |
| `FITTINGS` | 14 | AR/FR/EN | "وصلات PEHD", "raccords PVC", "fittings", "صمامات" |

**Matching**: Substring search on normalized text (`marker in normalized_text`). **No word boundaries** — "خزان" matches "خزانات".

### Families (8 marketing families)

| ID | Name (AR) | Priority | Keywords | Entities |
|----|-----------|----------|----------|----------|
| `agriculture` | الفلاحية والحيوانية | استراتيجية / قصوى | 27 | 10 (Ministry, ONID, ONTA, cooperatives) |
| `water_services` | خدمات فلاحية ومائية | عالية جداً | 20 | 7 (ADE, ONA, ANBT, well drillers) |
| `construction` | البناء والأشغال | عالية | 20 | 16 (Ministry, ADE, ONA, Sonelgaz, OPGI, AADL) |
| `trade_distribution` | التجارة والتوزيع | متوسطة إلى عالية | 12 | 7 (wholesalers, retailers, CNRC) |
| `industry_mining_energy` | الصناعية والمنجمية والطاقوية | استراتيجية | 28 | 18 (Sonatrach, Cevital, Lafarge, desalination) |
| `tourism_hospitality` | السياحية والفندقية والخدمية | متوسطة | 13 | 8 (hotels, malls, stations) |
| `public_facilities` | مرافق ومنفعة عامة | متوسطة ومستقرة | 12 | 10 (ministries, municipalities, OPGI) |
| `households_individuals` | الأسر والأفراد | منخفضة / حضور محلي | 9 | 4 (households, plumbers) |

**Entity Matching**: Exact substring on normalized text (e.g., "الجزائرية للمياه" in tender org/title).
**Keyword Matching**: Token overlap between normalized tender text and family keywords.

### Wilayas (69 total, 3 tiers)

| Tier | Wilayas | Count | Use |
|------|---------|-------|-----|
| `target` | الوادي, ورقلة, بسكرة, غرداية, أدرار, الجزائر, البليدة, تيبازة | 8 | Highest priority |
| `priority` | وهران, قسنطينة, عنابة, سطيف, ورقلة, بجاية, تلمسان | 7 | High priority |
| `all_69` | All 69 wilayas | 69 | Filtering/display |

**Aliases**: 79 mappings (Latin → Arabic) e.g., "Constantine" → "قسنطينة", "Oued Souf" → "الوادي".

### Government/Private Entities (for entity matching)

- **Ministries**: 17 (Interior, Defense, Finance, Energy, Agriculture, Irrigation, Public Works, Transport, Health, Education, Higher Ed, Housing, Industry, Trade, Labor, Environment)
- **National Agencies**: 10 (ADE, ONA, ANBT, ONID, ONTA, OAIC, AADL, OPGI, LPP, ENPI)
- **Regional Directorates**: 8 (DRE, DSA, Education, Health, Housing, Public Works, Municipalities, Wilayas)
- **Public Enterprises**: 4 sectors × 5-8 entities each (Energy, Water, Construction, Mining, Transport, Telecom)
- **Private Groups**: 14 top groups (Cevital, Tosyali, Hasnaoui, Biopharm, Condor, Ifri, Rouiba, etc.)

---

## Scoring Algorithm

```python
# Weights (tender_filter.py:30-32)
WEIGHT_ENTITY = 4      # Exact entity name match
WEIGHT_KEYWORD = 2     # Keyword token overlap
WEIGHT_PRODUCT = 3     # Product marker match
MIN_SCORE = 3          # Threshold to keep tender

def _score_match(tokens: set[str], normalized_text: str, family: dict) -> int:
    score = 0
    
    # Entity matching (highest weight)
    for entity in family.get("entities", []):
        if entity in normalized_text:
            score += WEIGHT_ENTITY
    
    # Keyword matching (token overlap)
    family_tokens = set()
    for kw in family.get("keywords", []):
        family_tokens.update(_tokenize(kw))
    overlap = tokens & family_tokens
    score += len(overlap) * WEIGHT_KEYWORD
    
    return score

# Product scoring (separate)
def _match_products(normalized_text: str) -> list[str]:
    matched = []
    for category, markers in PRODUCT_MARKERS.items():
        for marker in markers:
            if marker in normalized_text:
                matched.append(category)
    return list(set(matched))  # Dedupe categories
```

**Final Tender Score** = max family score + product bonus (if any product matched).

**Family Assignment**: Family with highest score (ties broken by order in `targets.json`).

**Wilaya Priority**: Added as metadata (`wilaya_priority`: "target"/"priority"/"normal") — not in score.

---

## Platform Search Integration (`webapp/text.py`)

### `normalize_search(query: str) → str`
Identical to legacy `_normalize()` — ensures query/database alignment.

### `build_fts_query(query: str) → str`
Converts normalized query to FTS5 MATCH syntax:
```python
# Prefix each token with * for prefix matching
# Escape quotes
tokens = normalize_search(query).split()
fts_query = " ".join(f'"{token}"*' for token in tokens)
```

### `escape_like(text: str) → str`
Escapes `%`, `_`, `\` for SQLite LIKE pattern.

---

## Freshness Filter (`filter_fresh`)

```python
FRESHNESS_WINDOW_DAYS = 90  # .env.example:11
FRESHNESS_ENABLED = true    # .env.example:12

def filter_fresh(tenders: list[dict], window_days: int = 90) -> list[dict]:
    cutoff = date.today() - timedelta(days=window_days)
    kept = []
    for t in tenders:
        pub_date = parse_date(t.get("published_date"))
        if pub_date and pub_date >= cutoff:
            kept.append(t)
    return kept
```

**Date Parsing**: Handles `YYYY-MM-DD`, `DD/MM/YYYY`, `DD-MM-YYYY`, French month names.

**Config**: Disable via `FRESHNESS_ENABLED=false`.

---

## Configuration Flags (`.env.example`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `FRESHNESS_WINDOW_DAYS` | 90 | Keep tenders published within N days |
| `FRESHNESS_ENABLED` | true | Enable/disable freshness filter |
| `REQUIRE_PRODUCTS` | true | Only keep tenders with product match |
| `ALLOW_NEWS_AS_TENDERS` | false | Include news-type results |
| `INCLUDE_SAMPLES` | false | Include sample/demo tenders in output |

---

## Audit Findings

| ID | Severity | Finding | Evidence | Impact | Recommendation |
|----|----------|---------|----------|--------|----------------|
| NLP-01 | MEDIUM | **Substring matching causes false positives** | `marker in normalized_text` matches "خزان" in "خزانات" | Over-classification; noise in results | Add word-boundary aware matching (regex `\b`) or token-based |
| NLP-02 | MEDIUM | **No synonym/lemma expansion** | "خزان" ≠ "خزانات" ≠ "بركة" ≠ "citerne" | Misses morphological variants | Add Arabic stemmer (e.g., `camel_tools`) or expand dictionaries |
| NLP-03 | LOW | **Entity matching case-sensitive after normalize** | `entity in normalized_text` — entities in JSON not normalized | "ADE" vs "ade" mismatch | Normalize entities at load time (`data/targets.json` → normalized cache) |
| NLP-04 | LOW | **Keyword tokenization splits compound terms** | `_tokenize` splits on non-word; "ري محوري" → {"ري", "محوري"} | Loses phrase semantics | Add n-gram (bigram) keywords for important phrases |
| NLP-05 | MEDIUM | **Product markers not normalized at load** | `PRODUCT_MARKERS` from `targets.json` used raw | "PEHD" vs "pehd" mismatch | Pre-normalize all markers at startup |
| NLP-06 | LOW | **French/English keywords not normalized** | Keywords include "irrigation", "forage" — no NFKC/diacritic handling | Inconsistent matching | Apply `_normalize` to all keyword lists at load |
| NLP-07 | INFO | **No confidence/confidence intervals** | Binary keep/discard (MIN_SCORE) | Cannot rank near-threshold | Add score breakdown; expose confidence tiers |
| NLP-08 | INFO | **Wilaya priority not in score** | `wilaya_priority` metadata only | Target wilayas not boosted | Add `WEIGHT_WILAYA_TARGET=2`, `WEIGHT_WILAYA_PRIORITY=1` |
| NLP-09 | MEDIUM | **Duplicate logic: legacy vs platform** | `tender_filter.py:_normalize` ≈ `webapp/text.py:normalize_search` | Drift risk | Single source: `shared/text_normalization.py` |
| NLP-10 | LOW | **`sub_activities` placeholder unused** | `targets.json:820` 90 activities, not referenced | Dead code | Remove or implement advanced filtering |

---

## Test Coverage (Classification)

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_tender_filter_classification.py` | 6 | Normalization, classification, product matching |
| `test_tender_filter_freshness.py` | 12 | Date parsing, window filtering, edge cases |
| `test_phase1_text.py` | 19 | Platform `normalize_search`, `build_fts_query`, `escape_like` |

**Missing Tests**:
- Entity matching with Arabic diacritics in tender text
- Keyword overlap scoring verification
- Wilaya alias resolution in classification
- Cross-pipeline normalization parity (legacy ↔ platform)

---

## Improvement Roadmap

### Phase 1: Accuracy (1-2 weeks)
1. **Fix substring false positives** — token-based matching with `\b` boundaries
2. **Normalize entities/keywords at load** — single `TaxonomyLoader` class
3. **Add wilaya weight to scoring** — boost target/priority wilayas
4. **Unify normalization** — shared module for legacy + platform

### Phase 2: Intelligence (1 month)
5. **Arabic stemming/lemmatization** — integrate `camel_tools` or `farasa` for morphological normalization
6. **Phrase/bigram keywords** — "محطة ضخ" as unit, not "محطة" + "ضخ"
7. **Confidence tiers** — P1 (≥85), P2 (70-84), P3 (50-69), P4 (<50) — align with digest
8. **Learning from feedback** — log accepted/rejected tenders; periodic dictionary expansion

### Phase 3: ML Enhancement (Future)
9. **Embedding-based similarity** — `sentence-transformers` for Arabic (e.g., `CAMeL-Lab/bert-base-arabic-camelbert-mix`) to catch semantic matches
10. **Active learning** — human-in-the-loop for edge cases; retrain lightweight classifier
11. **Multilingual alignment** — map AR/FR/EN terms to shared concept IDs

---

## Configuration Reference

```python
# tender_filter.py (module constants)
WEIGHT_ENTITY = 4
WEIGHT_KEYWORD = 2
WEIGHT_PRODUCT = 3
MIN_SCORE = 3

PRODUCT_MARKERS = {
    "PE_TANKS": [...],      # 81 terms
    "PEHD_PIPES": [...],    # 50 terms
    "PVC_PIPES": [...],     # 44 terms
    "FITTINGS": [...],      # 14 terms
}

# Environment overrides
FRESHNESS_WINDOW_DAYS = int(os.getenv("FRESHNESS_WINDOW_DAYS", "90"))
FRESHNESS_ENABLED = os.getenv("FRESHNESS_ENABLED", "true").lower() == "true"
REQUIRE_PRODUCTS = os.getenv("REQUIRE_PRODUCTS", "true").lower() == "true"
ALLOW_NEWS_AS_TENDERS = os.getenv("ALLOW_NEWS_AS_TENDERS", "false").lower() == "true"
```

---

## Sample Classification Trace

**Input**: 
```json
{
  "title": "اقتناء أنابيب PVC لمشروع الري",
  "organisation": "الجزائرية للمياه",
  "wilaya": "الجزائر",
  "published_date": "2026-10-15"
}
```

**Normalized**: `اقتناء انابيب pvc لمشروع الري` + `الجزائرية للمياه` + `الجزائر`

**Tokenized**: `{اقتناء, انابيب, pvc, لمشروع, الري, الجزائرية, للمياه, الجزائر}`

**Scores**:
- `construction`: entities=1 ("الجزائرية للمياه"=4) + keywords=2 ("ري", "أنابيب"=2×2=4) = **8**
- `water_services`: entities=1 ("الجزائرية للمياه"=4) + keywords=2 ("ري", "نقل المياه"=2×2=4) = **8**
- `trade_distribution`: keywords=1 ("تجارة" not present) = **0**

**Products**: `PVC_PIPES` matched ("pvc" in markers)

**Family**: `construction` (tie, first in JSON)

**Wilaya Priority**: `target` (الجزائر in target list)

**Final**: Kept (score 8 ≥ 3, product matched, fresh, target wilaya)