import json
import os
import re
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

TARGETS_FILE = os.path.join(os.path.dirname(__file__), "data", "targets.json")


class TenderFilter:
    """فلترة المناقصات مع دعم الولايات والمؤسسات"""

    WEIGHT_ENTITY = 4
    WEIGHT_KEYWORD = 2
    WEIGHT_PRODUCT = 3
    MIN_SCORE_THRESHOLD = 3

    STOP_WORDS = {
        "من", "في", "على", "الى", "لى", "عن", "مع", "هذا", "هذه",
        "ذلك", "التي", "الذي", "ما", "لا", "هو", "هي", "و", "و",
        "ثم", "قد", "كل", "بعض", "بين", "عند", "لدى", "نحو", "حول",
        "the", "and", "or", "of", "for", "to", "in", "on", "at", "by"
    }

    def __init__(self, targets_file: str = TARGETS_FILE):
        self.targets_file = targets_file
        self.targets = self._load_targets()
        self._compile_patterns()
        self._compile_wilaya_patterns()

    def _load_targets(self) -> Dict:
        try:
            with open(self.targets_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"ملف {self.targets_file} غير موجود!")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"خط في تنسيق JSON: {e}")
            raise

    def _normalize(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"[\u064B-\u0652\u0670\u0640]", "", text)
        text = re.sub(r"[آٱا]", "ا", text)
        text = re.sub(r"ى", "ي", text)
        text = re.sub(r"ة", "ه", text)
        text = re.sub(r"ؤ", "و", text)
        text = re.sub(r"ئ", "ي", text)
        text = re.sub(r"[,.:;\-\(\)\[\]/\|!?\"'«»]", " ", text)
        text = re.sub(r"\s+", " ", text).strip().lower()
        return text

    def _strip_arabic_prefix(self, word: str) -> str:
        if len(word) <= 3:
            return word
        if word.startswith("ال") and len(word) > 4:
            return word[2:]
        return word

    def _tokenize(self, text: str) -> List[str]:
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

    def _compile_patterns(self):
        self.family_patterns = []
        for family in self.targets.get("families", []):
            keywords = [self._normalize(k) for k in family.get("keywords", []) if k]
            entity_tokens = []
            for e in family.get("entities", []):
                if e:
                    normalized = self._normalize(e)
                    entity_tokens.extend(self._tokenize(normalized))

            self.family_patterns.append({
                "id": family["id"],
                "name_ar": family["name_ar"],
                "name_fr": family.get("name_fr", ""),
                "priority": family.get("priority", ""),
                "channel": family.get("channel", ""),
                "keywords": keywords,
                "entity_tokens": list(set(entity_tokens)),
            })

        self.product_patterns = {}
        for key, values in self.targets.get("products", {}).items():
            self.product_patterns[key] = [self._normalize(v) for v in values if v]

    def _compile_wilaya_patterns(self):
        wilayas = self.targets.get("wilayas", {})
        self.all_wilayas = [self._normalize(w) for w in wilayas.get("all_69", [])]
        self.target_wilayas = [self._normalize(w) for w in wilayas.get("target", [])]
        self.priority_wilayas = [self._normalize(w) for w in wilayas.get("priority", [])]

        aliases = self.targets.get("wilaya_aliases", {})
        self.wilaya_aliases = {self._normalize(k): v for k, v in aliases.items()}

    def _normalize_wilaya_name(self, name: str) -> str:
        if not name:
            return name
        norm = self._normalize(name)
        return self.wilaya_aliases.get(norm, name)

    def get_wilaya_priority(self, wilaya_text: str) -> Optional[str]:
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

    def find_wilaya_in_text(self, text: str) -> Optional[str]:
        if not text:
            return None
        norm = self._normalize(text)

        # البحث في القاموس ولا
        for alias_norm, arabic_name in self.wilaya_aliases.items():
            if alias_norm in norm:
                return arabic_name

        # البحث في القائمة العربية
        for w in self.all_wilayas:
            if w in norm:
                return w
        return None

    def _has_keyword(self, text: str, keyword: str) -> bool:
        if not keyword:
            return False
        if keyword in text:
            return True
        stripped = self._strip_arabic_prefix(keyword)
        if stripped != keyword and stripped in text:
            return True
        return False

    def _count_keyword_matches(self, text: str, keywords: List[str]) -> Tuple[int, List[str]]:
        matched = [kw for kw in keywords if self._has_keyword(text, kw)]
        return len(matched), matched

    def _count_token_matches(self, text_tokens: set, tokens: List[str]) -> Tuple[int, List[str]]:
        matched = [t for t in tokens if t in text_tokens]
        return len(matched), matched

    def classify_tender(self, tender: Dict) -> Optional[Dict]:
        combined_text = " ".join([
            str(tender.get("title", "")),
            str(tender.get("organisation", "")),
            str(tender.get("product", "")),
            str(tender.get("description", "")),
            str(tender.get("wilaya", "")),
        ])
        combined_text = self._normalize(combined_text)
        text_tokens = set(self._tokenize(combined_text))

        matched_families = []
        for family in self.family_patterns:
            kw_count, kw_matches = self._count_keyword_matches(combined_text, family["keywords"])
            tok_count, tok_matches = self._count_token_matches(text_tokens, family["entity_tokens"])

            score = (self.WEIGHT_KEYWORD * kw_count) + (self.WEIGHT_ENTITY * tok_count)

            if score >= self.MIN_SCORE_THRESHOLD:
                matched_families.append({
                    "id": family["id"],
                    "name_ar": family["name_ar"],
                    "name_fr": family["name_fr"],
                    "priority": family["priority"],
                    "channel": family["channel"],
                    "score": score,
                    "matched_keywords": kw_matches,
                    "matched_tokens": tok_matches,
                })

        matched_families.sort(key=lambda x: x["score"], reverse=True)

        matched_products = []
        for product_key, patterns in self.product_patterns.items():
            for p in patterns:
                if self._has_keyword(combined_text, p):
                    matched_products.append(product_key)
                    break

        if not matched_families and not matched_products:
            return None

        total_score = sum(f["score"] for f in matched_families) + (self.WEIGHT_PRODUCT * len(matched_products))

        current_wilaya = tender.get("wilaya", "").strip()
        if current_wilaya:
            tender["wilaya"] = self._normalize_wilaya_name(current_wilaya)
        else:
            found_wilaya = self.find_wilaya_in_text(combined_text)
            if found_wilaya:
                tender["wilaya"] = found_wilaya

        wilaya_priority = self.get_wilaya_priority(tender.get("wilaya", ""))

        return {
            **tender,
            "matched_families": matched_families,
            "matched_products": matched_products,
            "relevance_score": total_score,
            "wilaya_priority": wilaya_priority,
        }

    def filter_tenders(self, tenders: List[Dict]) -> List[Dict]:
        results = []
        for tender in tenders:
            classified = self.classify_tender(tender)
            if classified:
                results.append(classified)
        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        logger.info(f"تم تصنيف {len(results)} من صل {len(tenders)} مناقصة")
        return results

    def group_by_family(self, filtered_tenders: List[Dict]) -> Dict:
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

    def summary(self, filtered_tenders: List[Dict]) -> Dict:
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
