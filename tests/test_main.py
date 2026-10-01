from unittest.mock import patch

from crawlers.algeria_tenders_crawler import AlgeriaTendersCrawler
from crawlers.marches_publics_crawler import MarchesPublicsCrawler
from crawlers.ona_crawler import ONACrawler
from main import apply_filter, build_summary_message, drop_reference_data


def test_apply_filter():
    """اختبار دالة apply_filter للتأكد من استدعاء TenderFilter بشكل صحيح وإرجاع النتائج المفلترة."""
    sample_tenders = [{"title": "مناقصة توريد أنابيب PEHD"}]
    expected_filtered = [{"title": "مناقصة توريد أنابيب PEHD", "score": 5}]

    with patch("main.TenderFilter") as mock_tender_filter_cls:
        mock_instance = mock_tender_filter_cls.return_value
        mock_instance.filter_tenders.return_value = expected_filtered

        result = apply_filter(sample_tenders)

        mock_tender_filter_cls.assert_called_once()
        mock_instance.filter_tenders.assert_called_once_with(sample_tenders)
        assert result == expected_filtered


def test_apply_filter_empty_list():
    """اختبار دالة apply_filter عند تمرير قائمة مناقصات فارغة."""
    empty_tenders = []

    with patch("main.TenderFilter") as mock_tender_filter_cls:
        mock_instance = mock_tender_filter_cls.return_value
        mock_instance.filter_tenders.return_value = []

        result = apply_filter(empty_tenders)

        mock_tender_filter_cls.assert_called_once()
        mock_instance.filter_tenders.assert_called_once_with(empty_tenders)
        assert result == []


def test_apply_filter_no_matches():
    """اختبار دالة apply_filter عندما لا تطابق أي مناقصة معايير الفلترة."""
    unmatched_tenders = [{"title": "مناقصة صيانة سيارات غير مستهدفة"}]

    with patch("main.TenderFilter") as mock_tender_filter_cls:
        mock_instance = mock_tender_filter_cls.return_value
        mock_instance.filter_tenders.return_value = []

        result = apply_filter(unmatched_tenders)

        mock_tender_filter_cls.assert_called_once()
        mock_instance.filter_tenders.assert_called_once_with(unmatched_tenders)
        assert result == []


def test_build_summary_message_counts_tenders_and_families():
    """اختبار تعداد المناقصات وتوزيعها على العائلات."""
    tenders = [
        {
            "title": "مناقصة توريد أنابيب PEHD",
            "matched_families": [{"name_ar": "مواد البناء"}],
        },
        {
            "title": "مناقصة صيانة طرق",
            "matched_families": [{"name_ar": "البنية التحتية"}, {"name_ar": "مواد البناء"}],
        },
    ]

    result = build_summary_message(tenders)

    assert "🔔 <b>تقرير DZ-TENDERS</b>" in result
    assert "📋 2 مناقصة جديدة:" in result
    assert "• مواد البناء: 2" in result
    assert "• البنية التحتية: 1" in result


def test_build_summary_message_sorts_families_by_count_desc():
    """اختبار ترتيب العائلات تنازليًا حسب عدد المطابقات."""
    tenders = [
        {"title": "أ", "matched_families": [{"name_ar": "أولى"}, {"name_ar": "ثالثة"}]},
        {"title": "ب", "matched_families": [{"name_ar": "ثالثة"}]},
    ]

    result = build_summary_message(tenders)
    lines = result.splitlines()
    first_family_line = next(i for i, line in enumerate(lines) if line.startswith("• "))
    family_lines = [line for line in lines[first_family_line:] if line.startswith("• ")]

    assert family_lines == ["• ثالثة: 2", "• أولى: 1"]


def test_build_summary_message_uses_fallback_family_name():
    """اختبار اسم العائلة الافتراضي عند غياب name_ar."""
    tenders = [{"title": "مناقصة", "matched_families": [{"code": "X1"}]}]

    result = build_summary_message(tenders)

    assert "• غير مصنّف: 1" in result


def test_build_summary_message_lists_at_most_five_titles():
    """اختبار اقتصار قائمة العناوين على أول 5 مناقصات."""
    tenders = [{"title": f"مناقصة رقم {i}"} for i in range(1, 8)]

    result = build_summary_message(tenders)
    lines = result.splitlines()
    separator_index = next(i for i, line in enumerate(lines) if "━" in line)
    numbered = [line for line in lines[separator_index + 1 :] if line[:2].rstrip(".").isdigit()]

    assert len(numbered) == 5
    assert numbered[0] == "1. مناقصة رقم 1"
    assert numbered[-1] == "5. مناقصة رقم 5"
    assert "مناقصة رقم 6" not in result


def test_build_summary_message_truncates_long_title():
    """اختبار اقتصاص العنوان عند تجاوزه 80 حرفًا."""
    long_title = "ط" * 120
    tenders = [{"title": long_title}]

    result = build_summary_message(tenders)

    assert f"1. {'ط' * 80}" in result
    assert f"1. {'ط' * 81}" not in result


def test_build_summary_message_handles_missing_title_and_key():
    """اختبار التعامل مع مناقصة بلا عنوان أو بلا مفتاح matched_families."""
    tenders = [{}, {"title": "مناقصة صيانة"}]

    result = build_summary_message(tenders)

    assert "📋 2 مناقصة جديدة:" in result
    assert "1. بدون عنوان" in result
    assert "2. مناقصة صيانة" in result
    assert "• " not in result


def test_build_summary_message_empty_list():
    """اختبار توليد التقرير عند عدم وجود مناقصات جديدة."""
    result = build_summary_message([])

    assert "📋 0 مناقصة جديدة:" in result
    assert "\n━━━━━━━━━━━━━━━━━━" in result
    assert result.strip().endswith("━━━━━━━━━━━━━━━━━━")


def test_drop_reference_data_removes_samples_by_default():
    """البيانات المرجعية تُحذف افتراضياً حتى لا تُبلَّغ كصفقات حقيقية."""
    tenders = [
        {"title": "حية", "is_sample": False},
        {"title": "مرجعية", "is_sample": True, "source_status": "reference"},
        {"title": "بلا وسم"},
    ]

    result = drop_reference_data(tenders)

    assert [t["title"] for t in result] == ["حية", "بلا وسم"]


def test_drop_reference_data_keeps_samples_when_explicitly_enabled():
    """تضمين البيانات المرجعية ممكن عبر include_samples صراحةً."""
    tenders = [{"title": "مرجعية", "is_sample": True}]

    assert drop_reference_data(tenders, include_samples=True) == tenders


def test_drop_reference_data_does_not_mutate_input():
    """الدالة لا تعدّل القائمة الأصلية."""
    tenders = [{"title": "مرجعية", "is_sample": True}]

    drop_reference_data(tenders)

    assert tenders == [{"title": "مرجعية", "is_sample": True}]


def test_reference_tenders_are_flagged(monkeypatch):
    """كل البيانات المرجعية في الزواحف موسومة is_sample و source_status."""
    ona = ONACrawler()
    monkeypatch.setattr(ona, "fetch_page", lambda url: "<html></html>")
    algeria = AlgeriaTendersCrawler()
    monkeypatch.setattr(algeria, "fetch_page", lambda url: "<html></html>")

    batches = [
        ona.run(),
        algeria.run(),
        MarchesPublicsCrawler().run(),
    ]

    assert batches[0] and batches[1] and batches[2]
    for tender in [t for batch in batches for t in batch]:
        assert tender["is_sample"] is True, tender["title"]
        assert tender["source_status"] == "reference", tender["title"]


def test_is_sample_flag_survives_filtering():
    """وسم البيانات المرجعية ينجو من مرحلة الفلترة قبل الوصول إلى التنبيه."""
    samples = [
        {
            "title": "Acquisition de tuyaux PVC assainissement CR8 DN 200/315",
            "is_sample": True,
        }
    ]

    filtered = apply_filter(samples)

    assert len(filtered) == 1
    assert filtered[0]["is_sample"] is True
    assert "relevance_score" in filtered[0]
