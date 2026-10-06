import json
import logging
import os
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

TARGETS_FILE = os.path.join(os.path.dirname(__file__), "data", "targets.json")

#: نافذة الحداثة الافتراضية.
FRESHNESS_WINDOW_DAYS_DEFAULT = 90

#: مفتاح القتل لفلتر الحداثة.
FRESHNESS_ENABLED_DEFAULT = True

#: تاريخ ISO في بداية النص.
DATE_PREFIX_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _env_int(name: str, default: int) -> int:
    """قراءة عدد صحيح موجب."""
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s=%r ليس رقماً — يُتجاهل", name, raw)
        return default
    if value <= 0:
        logger.warning("%s=%r يجب أن يكون موجباً", name, raw)
        return default
    return value


def _env_bool(name: str, default: bool) -> bool:
    """قراءة قيمة منطقية."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class TenderFilter:
    """فلترة المناقصات مع دعم الولايات والمؤسسات"""

    WEIGHT_ENTITY = 4
    WEIGHT_KEYWORD = 2
    WEIGHT_PRODUCT = 3
    MIN_SCORE_THRESHOLD = 3

    #: سبب الاستبعاد: آخر أجل للتسليم مضى.
    REASON_DEADLINE_PASSED = "deadline_passed"
    #: سبب الاستبعاد: تاريخ نشر أقدم من نافذة الحداثة.
    REASON_PUBLISHED_STALE = "published_stale"
    #: سبب الاستبعاد: مصدر ينشر تواريخ لكن الصفقة بلا تاريخ.
    REASON_UNDATED = "undated_dated_source"

    STOP_WORDS = {
        "من",
        "في",
        "على",
        "الى",
        "لى",
        "عن",
        "مع",
        "هذا",
        "هذه",
        "ذلك",
        "التي",
        "الذي",
        "ما",
        "لا",
        "هو",
        "هي",
        "و",
        "ثم",
        "قد",
        "كل",
        "بعض",
        "بين",
        "عند",
        "لدى",
        "نحو",
        "حول",
        "the",
        "and",
        "or",
        "of",
        "for",
        "to",
        "in",
        "on",
        "at",
        "by",
    }

    def __init__(
        self,
        targets_file: str = TARGETS_FILE,
        freshness_window_days: int | None = None,
        freshness_enabled: bool | None = None,
        require_products: bool | None = None,
    ):
        """تهيئة المرشِّح.

        Args:
            targets_file: مسار ملف الأهداف.
            freshness_window_days: نافذة الحداثة بالأيام (None = من البيئة).
            freshness_enabled: تعطيل/تفعيل فلتر الحداثة (None = من البيئة).
        """
        self.targets_file = targets_file
        self.targets = self._load_targets()
        self._compile_patterns()
        self._compile_wilaya_patterns()
        self.freshness_window_days = (
            _env_int("FRESHNESS_WINDOW_DAYS", FRESHNESS_WINDOW_DAYS_DEFAULT)
            if freshness_window_days is None
            else int(freshness_window_days)
        )
        self.freshness_enabled = (
            _env_bool("FRESHNESS_ENABLED", FRESHNESS_ENABLED_DEFAULT)
            if freshness_enabled is None
            else bool(freshness_enabled)
        )
        #: عند True، تُقبل فقط المناقصات التي تذكر منتجاً واحداً على الأقل
        #: (PVC, PEHD, خزانات PE). هذا يحصر النشاط على تخصص الشركة.
        self.require_products = (
            _env_bool("REQUIRE_PRODUCTS", False)
            if require_products is None
            else bool(require_products)
        )
        # A filter run must be explainable.  These values are populated by
        # ``filter_tenders`` and are also useful in a debugger.
        self.last_filter_diagnostics: dict[str, object] = {}
        self._last_classification_reason = "not_run"

    def _load_targets(self) -> dict:
        try:
            with open(self.targets_file, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"ملف {self.targets_file} غير موجود!")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"خط في تنسيق JSON: {e}")
            raise

    def _normalize(self, text: str) -> str:
        """Normalize Arabic and French text before matching.

        The crawlers do not return a single consistent spelling.  In
        particular, Arabic hamza forms, tatweel, diacritics and French
        punctuation can make an apparently identical phrase miss a literal
        search.  Normalising both the targets and the tender text gives the
        matcher one representation without changing the original tender.
        """
        if not text:
            return ""
        normalized = unicodedata.normalize("NFKC", str(text))
        normalized = re.sub(
            r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]",
            "",
            normalized,
        )
        normalized = re.sub(r"[إأآٱا]", "ا", normalized)
        normalized = re.sub(r"ى", "ي", normalized)
        # Keep this project-wide convention in one place.  The targets file
        # is normalized through the same function, so this is symmetric.
        normalized = re.sub(r"ة", "ه", normalized)
        normalized = re.sub(r"ؤ", "و", normalized)
        normalized = re.sub(r"ئ", "ي", normalized)
        # ``\\w`` is Unicode-aware in Python; retaining letters and numbers
        # keeps Arabic and accented French words while replacing punctuation
        # (PVC-U, PE/HD, apostrophes, etc.) with searchable boundaries.
        normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
        return re.sub(r"\s+", " ", normalized, flags=re.UNICODE).strip().casefold()

    def _strip_arabic_prefix(self, word: str) -> str:
        if len(word) <= 3:
            return word
        if word.startswith("ال") and len(word) > 4:
            return word[2:]
        return word

    def _tokenize(self, text: str) -> list[str]:
        tokens = text.split()
        result = []
        for token in tokens:
            if token in self.STOP_WORDS:
                continue
            if len(token) < 3:
                continue
            result.append(token)
            stripped = self._strip_arabic_prefix(token)
            if stripped != token and len(stripped) >= 3:
                result.append(stripped)
        return result

    @staticmethod
    def _unique(values: Iterable[str]) -> list[str]:
        """Return non-empty strings once, preserving target-file order."""
        return list(dict.fromkeys(value for value in values if value))

    def _phrase_variants(self, phrase: str) -> list[str]:
        """Build normalized phrase variants, including an Arabic article-less form."""
        normalized = self._normalize(phrase)
        variants = [normalized]
        words = normalized.split()
        if len(words) == 1:
            stripped = self._strip_arabic_prefix(normalized)
            if stripped != normalized:
                variants.append(stripped)
        return self._unique(variants)

    def _compile_phrase(self, phrase: str):
        """Compile a Unicode-safe whole-phrase matcher.

        Matching uses boundaries rather than raw ``in`` checks so ``pvc`` does
        not accidentally match a larger identifier.  The explicit flags are
        intentional: source titles are Arabic/French and casing differs in
        Latin product names.
        """
        return [
            re.compile(
                rf"(?<!\w){re.escape(variant)}(?!\w)",
                flags=re.IGNORECASE | re.UNICODE,
            )
            for variant in self._phrase_variants(phrase)
            if variant
        ]

    def _register_phrase(self, phrase: str) -> None:
        normalized = self._normalize(phrase)
        if normalized and normalized not in self._compiled_patterns:
            self._compiled_patterns[normalized] = self._compile_phrase(normalized)

    def _compile_patterns(self):
        """Compile family and product targets from the JSON hierarchy.

        ``products`` is a mapping of category -> phrases and ``families`` is
        a list of objects.  Keeping these shapes explicit avoids the common
        bug of iterating product category names (``PEHD_PIPES``) as if they
        were the actual Arabic/French phrases.
        """
        self._compiled_patterns: dict[str, list[re.Pattern[str]]] = {}
        self.family_patterns = []
        families = self.targets.get("families", [])
        if not isinstance(families, list):
            families = []
        for family in families:
            if not isinstance(family, Mapping):
                continue
            raw_keywords = family.get("keywords", [])
            raw_entities = family.get("entities", [])
            if isinstance(raw_keywords, str):
                raw_keywords = [raw_keywords]
            if isinstance(raw_entities, str):
                raw_entities = [raw_entities]
            keywords = self._unique([self._normalize(k) for k in raw_keywords if k])
            entities = self._unique([self._normalize(e) for e in raw_entities if e])
            entity_tokens = self._unique(
                token
                for entity in entities
                for token in self._tokenize(entity)
            )
            for phrase in [*keywords, *entities, *entity_tokens]:
                self._register_phrase(phrase)

            family_id = str(family.get("id", "unknown"))
            self.family_patterns.append(
                {
                    "id": family_id,
                    "name_ar": family.get("name_ar", family_id),
                    "name_fr": family.get("name_fr", ""),
                    "priority": family.get("priority", ""),
                    "channel": family.get("channel", ""),
                    "keywords": keywords,
                    "entities": entities,
                    # Kept for backwards compatibility with existing reports.
                    "entity_tokens": entity_tokens,
                }
            )

        self.product_patterns: dict[str, list[str]] = {}
        raw_products = self.targets.get("products", {})
        if isinstance(raw_products, Mapping):
            for key, raw_values in raw_products.items():
                if isinstance(raw_values, str):
                    raw_values = [raw_values]
                elif not isinstance(raw_values, (list, tuple, set)):
                    raw_values = []
                patterns = self._unique([self._normalize(v) for v in raw_values if v])
                self.product_patterns[str(key)] = patterns
                for phrase in patterns:
                    self._register_phrase(phrase)

        self.product_regexes = {
            key: [self._compiled_patterns[phrase] for phrase in patterns]
            for key, patterns in self.product_patterns.items()
        }

    def _compile_wilaya_patterns(self):
        wilayas = self.targets.get("wilayas", {})
        raw_all = wilayas.get("all_69", [])
        self.wilaya_names = {
            self._normalize(name): name for name in raw_all if name
        }
        self.all_wilayas = list(self.wilaya_names)
        self.target_wilayas = [self._normalize(w) for w in wilayas.get("target", [])]
        self.priority_wilayas = [self._normalize(w) for w in wilayas.get("priority", [])]

        aliases = self.targets.get("wilaya_aliases", {})
        self.wilaya_aliases = {
            self._normalize(key): value for key, value in aliases.items() if key and value
        }

    def _normalize_wilaya_name(self, name: str) -> str:
        if not name:
            return name
        norm = self._normalize(name)
        return self.wilaya_aliases.get(norm, name)

    def get_wilaya_priority(self, wilaya_text: str) -> str | None:
        if not wilaya_text:
            return None
        norm = self._normalize(wilaya_text)
        for w in self.target_wilayas:
            if w in norm or norm in w:
                return "target"
        for w in self.priority_wilayas:
            if w in norm or norm in w:
                return "priority"
        return "other"

    def find_wilaya_in_text(self, text: str) -> str | None:
        if not text:
            return None
        norm = self._normalize(text)

        # البحث في القاموس ولا
        for alias_norm, arabic_name in self.wilaya_aliases.items():
            if alias_norm in norm:
                return arabic_name

        # البحث في القائمة العربية مع إعادة الاسم الأصلي، لا النسخة المطبعّة.
        for normalized, canonical in self.wilaya_names.items():
            if normalized in norm:
                return canonical
        return None

    def _flatten_value(self, value: object, *, include_mapping_keys: bool = False) -> list[str]:
        """Flatten crawler values without losing nested product categories."""
        if value is None or isinstance(value, bool):
            return []
        if isinstance(value, str | int | float):
            return [str(value)]
        if isinstance(value, Mapping):
            flattened: list[str] = []
            for key, child in value.items():
                if include_mapping_keys:
                    flattened.append(str(key))
                flattened.extend(
                    self._flatten_value(child, include_mapping_keys=include_mapping_keys)
                )
            return flattened
        if isinstance(value, (list, tuple, set)):
            return [
                item
                for child in value
                for item in self._flatten_value(child, include_mapping_keys=include_mapping_keys)
            ]
        return [str(value)]

    def _tender_text(self, tender: Mapping) -> str:
        """Extract all searchable bilingual text from known crawler schemas."""
        field_aliases = (
            "title", "title_ar", "title_fr", "titre", "objet", "object", "name",
            "subject", "description", "description_ar", "description_fr", "content",
            "body", "text", "details", "organisation", "organization", "institution",
            "agency", "entity", "company", "product", "products", "product_name",
            "product_names", "product_category", "product_code", "product_codes",
            "product_family", "category", "categories", "keywords", "tags", "wilaya",
            "location",
        )
        values: list[str] = []
        for field in field_aliases:
            if field not in tender:
                continue
            values.extend(
                self._flatten_value(
                    tender.get(field),
                    include_mapping_keys=field in {
                        "products",
                        "categories",
                        "product_category",
                        "product_codes",
                        "product_family",
                    },
                )
            )
        return self._normalize(" ".join(values))

    def _has_keyword(self, text: str, keyword: str) -> bool:
        """Match a normalized phrase with Unicode-aware regular expressions."""
        normalized_keyword = self._normalize(keyword)
        if not normalized_keyword:
            return False
        normalized_text = self._normalize(text)
        patterns = self._compiled_patterns.get(normalized_keyword)
        if patterns is None:
            patterns = self._compile_phrase(normalized_keyword)
        return any(pattern.search(normalized_text) for pattern in patterns)

    def _count_keyword_matches(self, text: str, keywords: list[str]) -> tuple[int, list[str]]:
        matched = [keyword for keyword in keywords if self._has_keyword(text, keyword)]
        return len(matched), matched

    def _count_token_matches(
        self, text_tokens: set[str], tokens: list[str]
    ) -> tuple[int, list[str]]:
        matched = [token for token in tokens if token in text_tokens]
        return len(matched), matched

    def _matched_products(self, text: str) -> tuple[list[str], dict[str, list[str]]]:
        """Return product category ids and the phrases that triggered them."""
        matched: list[str] = []
        evidence: dict[str, list[str]] = {}
        for product_key, patterns in self.product_patterns.items():
            phrases = [pattern for pattern in patterns if self._has_keyword(text, pattern)]
            if phrases:
                matched.append(product_key)
                evidence[product_key] = phrases
        return matched, evidence

    def classify_tender(self, tender: dict) -> dict | None:
        """Classify one tender using family, entity and product evidence.

        The method deliberately returns ``None`` only for a documented
        rejection reason.  ``self._last_classification_reason`` is consumed
        by ``filter_tenders`` to make a zero-result run diagnosable instead of
        looking like a silent exception.
        """
        self._last_classification_reason = "not_matched"
        combined_text = self._tender_text(tender)
        text_tokens = set(self._tokenize(combined_text))

        matched_families = []
        for family in self.family_patterns:
            kw_count, kw_matches = self._count_keyword_matches(combined_text, family["keywords"])
            tok_count, tok_matches = self._count_token_matches(text_tokens, family["entity_tokens"])
            score = (self.WEIGHT_KEYWORD * kw_count) + (self.WEIGHT_ENTITY * tok_count)
            if score >= self.MIN_SCORE_THRESHOLD:
                matched_families.append(
                    {
                        "id": family["id"],
                        "name_ar": family["name_ar"],
                        "name_fr": family["name_fr"],
                        "priority": family["priority"],
                        "channel": family["channel"],
                        "score": score,
                        "matched_keywords": kw_matches,
                        "matched_tokens": tok_matches,
                    }
                )

        matched_families.sort(key=lambda item: item["score"], reverse=True)
        matched_products, product_evidence = self._matched_products(combined_text)

        if self.require_products and not matched_products:
            self._last_classification_reason = "product_required"
            return None
        if not matched_families and not matched_products:
            self._last_classification_reason = "no_product_or_family_match"
            return None

        total_score = sum(family["score"] for family in matched_families) + (
            self.WEIGHT_PRODUCT * len(matched_products)
        )
        current_wilaya = str(tender.get("wilaya") or "").strip()
        if current_wilaya:
            tender["wilaya"] = self._normalize_wilaya_name(current_wilaya)
        else:
            found_wilaya = self.find_wilaya_in_text(combined_text)
            if found_wilaya:
                tender["wilaya"] = found_wilaya

        self._last_classification_reason = "matched"
        return {
            **tender,
            "matched_families": matched_families,
            "matched_products": matched_products,
            "matched_product_evidence": product_evidence,
            "relevance_score": total_score,
            "wilaya_priority": self.get_wilaya_priority(tender.get("wilaya", "")),
        }

    def filter_tenders(self, tenders: list[dict]) -> list[dict]:
        """تصفية المناقصات: الحداثة أولاً، ثم التصنيف."""
        fresh, dropped = self.filter_fresh(tenders)
        if dropped:
            listed = "، ".join(f"{title} ({reason})" for reason, title in dropped[:5])
            more = f" و{len(dropped) - 5} أخرى" if len(dropped) > 5 else ""
            logger.warning(f"تم استبعاد {len(dropped)} مناقصة منتهية أو غير مؤرّخة: {listed}{more}")
        results = []
        rejection_reasons: Counter[str] = Counter()
        for tender in fresh:
            classified = self.classify_tender(tender)
            if classified:
                results.append(classified)
            else:
                rejection_reasons[self._last_classification_reason] += 1
        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        self.last_filter_diagnostics = {
            "input": len(tenders),
            "fresh": len(fresh),
            "dropped": len(dropped),
            "classified": len(results),
            "rejected": dict(rejection_reasons),
            "require_products": self.require_products,
        }
        logger.info("تم تصنيف %d من أصل %d مناقصة", len(results), len(tenders))
        if rejection_reasons:
            reason_text = ", ".join(
                f"{reason}={count}" for reason, count in rejection_reasons.items()
            )
            logger.info("أسباب عدم التصنيف: %s", reason_text)
        if fresh and not results:
            logger.warning(
                "لم تُصنَّف أي مناقصة. تحقق من REQUIRE_PRODUCTS=%s؛ "
                "أكثر سبب: %s",
                str(self.require_products).lower(),
                rejection_reasons.most_common(1)[0][0] if rejection_reasons else "unknown",
            )
        return results

    def group_by_family(self, filtered_tenders: list[dict]) -> dict:
        groups = {}
        for tender in filtered_tenders:
            for family in tender.get("matched_families", []):
                family_id = family["id"]
                if family_id not in groups:
                    groups[family_id] = {
                        "name_ar": family["name_ar"],
                        "name_fr": family["name_fr"],
                        "priority": family["priority"],
                        "tenders": [],
                    }
                groups[family_id]["tenders"].append(tender)
        return groups

    def summary(self, filtered_tenders: list[dict]) -> dict:
        groups = self.group_by_family(filtered_tenders)
        return {
            "total_filtered": len(filtered_tenders),
            "by_family": {
                fid: {
                    "name": info["name_ar"],
                    "count": len(info["tenders"]),
                    "priority": info["priority"],
                }
                for fid, info in groups.items()
            },
        }

    @staticmethod
    def _coerce_date(value: object) -> date | None:
        """تحويل قيمة إلى date، أو None. لا يرفع استثناءً."""
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            return None
        match = DATE_PREFIX_RE.match(value.strip())
        if not match:
            return None
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None

    @staticmethod
    def _parse_deadline(value: object) -> date | None:
        """قراءة deadline كنص أو تاريخ."""
        return TenderFilter._coerce_date(value)

    @staticmethod
    def _parse_published_date(value: object) -> date | None:
        """قراءة published_date كنص أو تاريخ."""
        return TenderFilter._coerce_date(value)

    def filter_fresh(
        self,
        tenders: list[dict],
        *,
        window_days: int | None = None,
        today: date | None = None,
    ) -> tuple[list[dict], list[tuple[str, str]]]:
        """حذف المناقصات المنتهية أو التي لا يمكن الحكم عليها.

        القواعد:
        1. deadline مضى ⇒ حذف.
        2. لا deadline، وpublished_date أقدم من النافذة ⇒ حذف.
        3. لا تاريخان، والمفتاح published_date موجود ⇒ حذف.
        """
        if not self.freshness_enabled:
            return list(tenders), []
        window = self.freshness_window_days if window_days is None else int(window_days)
        reference = today or date.today()
        cutoff = reference - timedelta(days=window)
        kept: list[dict] = []
        dropped: list[tuple[str, str]] = []
        for tender in tenders:
            title = tender.get("title", "")
            if tender.get("is_sample"):
                kept.append(tender)
                continue
            # في وضع الحصر الصارم، لا نُسقط أخبار GoogleNews لأن published_date
            # يعكس تاريخ الخبر لا آخر أجل المناقصة.
            if self.require_products and tender.get("source") == "news_aggregator":
                kept.append(tender)
                continue
            deadline = self._parse_deadline(tender.get("deadline"))
            published = self._parse_published_date(tender.get("published_date"))
            if deadline is not None:
                if deadline < reference:
                    dropped.append((self.REASON_DEADLINE_PASSED, title))
                else:
                    kept.append(tender)
                continue
            if published is None:
                if "published_date" in tender:
                    dropped.append((self.REASON_UNDATED, title))
                else:
                    kept.append(tender)
                continue
            if published < cutoff:
                dropped.append((self.REASON_PUBLISHED_STALE, title))
            else:
                kept.append(tender)
        return kept, dropped
