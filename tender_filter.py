"""
tender_filter.py
وحدة فلترة وتصنيف المناقصات - v3.0
معالجة خاصة للغة العربية (البادئات، اللواحق، حدود الكلمة)
"""

import json
import os
import re
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

TARGETS_FILE = os.path.join(os.path.dirname(__file__), "data", "targets.json")


class TenderFilter:
    """
    فلترة المناقصات بإستراتيجية النقاط المرجحة مع معالجة عربية دقيقة
    """

    WEIGHT_ENTITY = 4
    WEIGHT_KEYWORD = 2
    WEIGHT_PRODUCT = 3
    MIN_SCORE_THRESHOLD = 3

    # كلمات عربية شائعة جدًا ولا تفيد في التصنيف (Stop Words)
    STOP_WORDS = {
        "من", "في", "على", "الى", "إلى", "عن", "مع", "هذا", "هذه",
        "ذلك", "التي", "الذي", "ما", "لا", "هو", "هي", "أو", "و",
        "ثم", "قد", "كل", "بعض", "بين", "عند", "لدى", "نحو", "حول",
        "the", "and", "or", "of", "for", "to", "in", "on", "at", "by"
    }

    def __init__(self, targets_file: str = TARGETS_FILE):
        self.targets_file = targets_file
        self.targets = self._load_targets()
        self._compile_patterns()

    def _load_targets(self) -> Dict:
        try:
            with open(self.targets_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"❌ ملف {self.targets_file} غير موجود!")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"❌ خطأ في تنسيق JSON: {e}")
            raise

    def _normalize(self, text: str) -> str:
        """
        تطبيع النص العربي:
        - إزالة التشكيل
        - توحيد الألف والياء والتاء المربوطة
        - إزالة علامات الترقيم
        - تحويل لحروف صغيرة للإنجليزية
        """
        if not text:
            return ""
        # إزالة التشكيل
        text = re.sub(r"[\u064B-\u0652\u0670\u0640]", "", text)
        # توحيد الحروف
        text = re.sub(r"[إأآٱا]", "ا", text)
        text = re.sub(r"ى", "ي", text)
        text = re.sub(r"ة", "ه", text)
        text = re.sub(r"ؤ", "و", text)
        text = re.sub(r"ئ", "ي", text)
        # إزالة علامات الترقيم
        text = re.sub(r"[،,.:;؛\-\(\)\[\]/\|!?؟\"'«»]", " ", text)
        # توحيد المسافات
        text = re.sub(r"\s+", " ", text).strip().lower()
        return text

    def _strip_arabic_prefix(self, word: str) -> str:
        """
        إزالة البادئات العربية الشائعة من الكلمة:
        ال، وال، بال، فال، كال، لل، وال
        """
        if len(word) <= 3:
            return word
        # إزالة "ال" التعريف إذا كانت الكلمة أطول من 4 أحرف
        if word.startswith("ال") and len(word) > 4:
            return word[2:]
        return word

    def _tokenize(self, text: str) -> List[str]:
        """تقسيم النص إلى كلمات مفتاحية (بدون كلمات التوقف)"""
        tokens = text.split()
        result = []
        for token in tokens:
            if token in self.STOP_WORDS:
                continue
            if len(token) < 3:  # تجاهل الكلمات القصيرة جدًا
                continue
            # إضافة الكلمة الأصلية
            result.append(token)
            # إضافة الكلمة بدون بادئة "ال"
            stripped = self._strip_arabic_prefix(token)
            if stripped != token and len(stripped) >= 3:
                result.append(stripped)
        return result

    def _compile_patterns(self):
        self.family_patterns = []
        for family in self.targets.get("families", []):
            keywords = []
            for k in family.get("keywords", []):
                if k:
                    keywords.append(self._normalize(k))
            
            # تقسيم أسماء المؤسسات إلى كلمات مفتاحية
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

    def _has_keyword(self, text: str, keyword: str) -> bool:
        """
        البحث عن كلمة مفتاحية مع مراعاة البادئات العربية
        """
        if not keyword:
            return False
        # بحث مباشر
        if keyword in text:
            return True
        # بحث بدون "ال"
        stripped = self._strip_arabic_prefix(keyword)
        if stripped != keyword and stripped in text:
            return True
        return False

    def _count_keyword_matches(self, text: str, keywords: List[str]) -> Tuple[int, List[str]]:
        """عدد الكلمات المفتاحية المطابقة"""
        matched = []
        for kw in keywords:
            if self._has_keyword(text, kw):
                matched.append(kw)
        return len(matched), matched

    def _count_token_matches(self, text_tokens: set, tokens: List[str]) -> Tuple[int, List[str]]:
        """عدد الكلمات (من أسماء المؤسسات) المطابقة"""
        matched = []
        for token in tokens:
            if token in text_tokens:
                matched.append(token)
        return len(matched), matched

    def classify_tender(self, tender: Dict) -> Optional[Dict]:
        """تصنيف مناقصة واحدة"""
        combined_text = " ".join([
            str(tender.get("title", "")),
            str(tender.get("organisation", "")),
            str(tender.get("product", "")),
            str(tender.get("description", "")),
        ])
        combined_text = self._normalize(combined_text)
        text_tokens = set(self._tokenize(combined_text))

        matched_families = []
        for family in self.family_patterns:
            # مطابقة الكلمات المفتاحية
            kw_count, kw_matches = self._count_keyword_matches(combined_text, family["keywords"])
            # مطابقة كلمات أسماء المؤسسات
            tok_count, tok_matches = self._count_token_matches(text_tokens, family["entity_tokens"])

            # حساب النقاط
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

        # ترتيب حسب النقاط
        matched_families.sort(key=lambda x: x["score"], reverse=True)

        # مطابقة المنتجات
        matched_products = []
        for product_key, patterns in self.product_patterns.items():
            for p in patterns:
                if self._has_keyword(combined_text, p):
                    matched_products.append(product_key)
                    break

        if not matched_families and not matched_products:
            return None

        total_score = sum(f["score"] for f in matched_families) + (self.WEIGHT_PRODUCT * len(matched_products))

        return {
            **tender,
            "matched_families": matched_families,
            "matched_products": matched_products,
            "relevance_score": total_score,
        }

    def filter_tenders(self, tenders: List[Dict]) -> List[Dict]:
        results = []
        for tender in tenders:
            classified = self.classify_tender(tender)
            if classified:
                results.append(classified)
        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        logger.info(f"✅ تم تصنيف {len(results)} من أصل {len(tenders)} مناقصة")
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


# ==================== اختبار ====================
if __name__ == "__main__":
    sample_tenders = [
        {
            "title": "اقتناء أنابيب PEHD لمشروع الري بالولاية",
            "organisation": "مديرية الموارد المائية",
            "wilaya": "الجزائر",
            "product": "أنابيب PEHD",
            "link": "https://example.com/1",
        },
        {
            "title": "بناء مدرسة ابتدائية جديدة",
            "organisation": "مديرية التربية",
            "wilaya": "وهران",
            "product": "مواد بناء",
            "link": "https://example.com/2",
        },
        {
            "title": "توريد خزانات PE لمحطة تحلية المياه",
            "organisation": "Sonatrach",
            "wilaya": "بومرداس",
            "product": "خزانات PE",
            "link": "https://example.com/3",
        },
        {
            "title": "أشغال الصرف الصحي لمدينة جديدة",
            "organisation": "مديرية الموارد المائية",
            "product": "أنابيب PVC",
            "wilaya": "قسنطينة",
            "link": "https://example.com/4",
        },
    ]

    filter_obj = TenderFilter()
    filtered = filter_obj.filter_tenders(sample_tenders)

    print("\n" + "=" * 60)
    print("📊 نتائج الفلترة (v3.0):")
    print("=" * 60)
    for t in filtered:
        print(f"\n🔹 {t['title']}")
        print(f"   المؤسسة: {t['organisation']}")
        print(f"   العائلات المطابقة:")
        for fam in t["matched_families"]:
            print(f"      • {fam['name_ar']} (النقاط: {fam['score']})")
            if fam['matched_keywords']:
                print(f"         كلمات: {fam['matched_keywords'][:5]}")
            if fam['matched_tokens']:
                print(f"         مؤسسات: {fam['matched_tokens'][:5]}")
        print(f"   المنتجات: {t['matched_products']}")
        print(f"   ⭐ درجة الأهمية الكلية: {t['relevance_score']}")

    print("\n" + "=" * 60)
    print("📈 الملخص:")
    print("=" * 60)
    print(json.dumps(filter_obj.summary(filtered), ensure_ascii=False, indent=2))