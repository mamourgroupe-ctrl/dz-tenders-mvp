"""اختبارات التصنيف الثنائي اللغة وبنية targets.json الحالية."""

from tender_filter import TenderFilter


def _filter(*, require_products: bool = True) -> TenderFilter:
    """Build a deterministic filter without freshness affecting the test."""
    return TenderFilter(freshness_enabled=False, require_products=require_products)


def test_arabic_product_in_title_is_classified_when_products_are_required():
    """المطابقة لا تعتمد على وجود حقل ``product`` منفصل."""
    tender = {
        "title": "توريد وتركيب أنابيب PEHD وشبكة مياه الشرب",
        "organisation": "الجزائرية للمياه ADE",
        "description": "مشروع ربط وتوزيع المياه",
        "published_date": "2026-10-01",
    }

    result = _filter().classify_tender(tender)

    assert result is not None
    assert "PEHD_PIPES" in result["matched_products"]
    assert result["relevance_score"] >= TenderFilter.WEIGHT_PRODUCT


def test_french_product_in_nested_products_mapping_is_classified():
    """تُقرأ ``products`` سواء كانت قائمة أو mapping للفئات."""
    tender = {
        "title": "Fourniture de conduites PVC pour l'assainissement",
        "products": {"PVC_PIPES": ["tuyaux PVC", "canalisation"]},
        "organisation": "ONA",
    }

    result = _filter().classify_tender(tender)

    assert result is not None
    assert "PVC_PIPES" in result["matched_products"]
    assert result["matched_product_evidence"]["PVC_PIPES"]


def test_arabic_normalization_handles_hamza_diacritics_and_tatweel():
    """أشكال عربية شائعة لا تمنع مطابقة المنتج."""
    tender = {
        "title": "تَوْرِيد خــزّان مِيَاه من البولي إيثيلين",
        "product": "خَزّان مياه PE",
    }

    result = _filter().classify_tender(tender)

    assert result is not None
    assert "PE_TANKS" in result["matched_products"]


def test_require_products_rejection_is_explicit_and_diagnosable():
    """الخبر العام بلا إشارة منتج يُرفض عمداً، لا بسبب استثناء صامت."""
    tender = {
        "title": "مناقصة وطنية لإنجاز أشغال عمومية",
        "organisation": "وزارة الأشغال العمومية",
    }
    filter_obj = _filter(require_products=True)

    assert filter_obj.classify_tender(tender) is None
    assert filter_obj._last_classification_reason == "product_required"


def test_entity_or_family_match_still_works_without_strict_products():
    """وضع REQUIRE_PRODUCTS=false يحافظ على تصنيف المؤسسة/العائلة."""
    tender = {
        "title": "اقتناء تجهيزات لمحطة معالجة المياه",
        "organisation": "الجزائرية للمياه ADE",
    }

    result = _filter(require_products=False).classify_tender(tender)

    assert result is not None
    assert result["matched_families"]
    assert result["matched_products"] == []


def test_filter_diagnostics_explain_zero_result():
    """التشغيل الجماعي يسجل سبب الصفر بدل إخفائه."""
    filter_obj = _filter(require_products=True)
    tenders = [
        {"title": "مناقصة عامة", "organisation": "صحيفة"},
        {"title": "Appel d'offres pour travaux généraux", "organisation": "Source"},
    ]

    assert filter_obj.filter_tenders(tenders) == []
    assert filter_obj.last_filter_diagnostics["fresh"] == 2
    assert filter_obj.last_filter_diagnostics["rejected"] == {"product_required": 2}
