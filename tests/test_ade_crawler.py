"""اختبارات ``ADECrawler`` على لقطات حقيقية من موقع ADE.

الملفات في ``tests/fixtures/`` لقطات فعلية، وواحدة منها (``ade_real_page.html``)
تحفظ الخلل الأصلي: الصفحة الجذرية لا تحتوي أي مناقصة.
"""

from pathlib import Path

import pytest

from crawlers.ade_crawler import (
    ADE_ORGANISATION,
    CARD_CLASS,
    LISTING_PATH,
    UNKNOWN_VALUE,
    ADECrawler,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    """قراءة لقطة من ملفات الاختبار."""
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def crawler() -> ADECrawler:
    return ADECrawler()


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    """يمنع أي طلب شبكة صامت."""
    import requests as _requests

    def _boom(*args, **kwargs):
        raise AssertionError("network blocked in ADE tests")

    monkeypatch.setattr(_requests, "get", _boom)


def test_listing_url_points_at_the_category_not_the_homepage(crawler):
    """القائمة في مسار التصنيف، لا في الصفحة الجذرية."""
    assert crawler.listing_url == "https://www.ade.dz/categorie/appel-doffres"
    assert crawler.listing_url != crawler.base_url


def test_parses_real_cards_from_capture(crawler):
    """أربع بطاقات حقيقية تُستخرج عناوينها وروابطها."""
    tenders = crawler.parse_tenders(_load("ade_categorie_appel_doffres.html"))

    assert len(tenders) == 4
    assert tenders[0]["title"].startswith("Avis de prorogation de délai de dépôt")
    assert "compteurs d’eau potable froide" in tenders[1]["title"]


def test_relative_links_become_absolute(crawler):
    """``../article/<slug>`` يُحلّ إلى رابط مطلق على www.ade.dz."""
    tenders = crawler.parse_tenders(_load("ade_categorie_appel_doffres.html"))

    for tender in tenders:
        assert tender["link"].startswith("https://www.ade.dz/article/")
        assert " " not in tender["link"]
        assert not tender["link"].startswith("https://www.ade.dz/article/../")


def test_accented_characters_survive(crawler):
    """العلامات الفرنسية (’ é) تبقى سليمة في العنوان والرابط."""
    tenders = crawler.parse_tenders(_load("ade_categorie_appel_doffres.html"))

    joined = " ".join(t["title"] for t in tenders)
    assert "d’offres" in joined
    assert "é" in joined


def test_homepage_capture_yields_nothing(crawler):
    """حارس العلة الأصلية: الصفحة الجذرية لا بطاقات فيها.

    هذه هي الحالة التي كان ``div.tender-item`` يمرّ عليها صامتاً ويعيد ``[]``
    في كل تشغيل حقيقي.
    """
    assert crawler.parse_tenders(_load("ade_real_page.html")) == []


def test_non_category_page_yields_nothing(crawler):
    """صفحة ``/appel-doffres`` تحمل عنواناً فقط؛ القائمتها تُبنى بالـJS."""
    assert crawler.parse_tenders(_load("ade_appel_doffres.html")) == []


def test_selector_is_the_real_card_class(crawler):
    """المحدِّد يطابق الصنف الفعلي لا صنفاً متخيَّلاً."""
    html = f'<div class="{CARD_CLASS}"><h3><a href="../article/x">عنوان</a></h3></div>'

    tenders = crawler.parse_tenders(html)

    assert len(tenders) == 1
    assert tenders[0]["title"] == "عنوان"


def test_title_falls_back_to_image_alt(crawler):
    """بطاقة بلا ``h3 a`` تأخذ العنوان من نص الصورة البديل."""
    html = (
        '<div class="service-block-two">'
        '<figure class="image-box"><a href="../article/x">'
        '<img src="a.jpg" alt="عنوان احتياطي"></a></figure>'
        "</div>"
    )

    tenders = crawler.parse_tenders(html)

    assert tenders[0]["title"] == "عنوان احتياطي"
    assert tenders[0]["link"] == "https://www.ade.dz/article/x"


def test_card_without_any_link_falls_back_to_base_url(crawler):
    """بطاقة بلا رابط تأخذ رابط الجذر بدل رابط فارغ."""
    html = '<div class="service-block-two"><h3>بلا رابط</h3></div>'

    tenders = crawler.parse_tenders(html)

    assert tenders[0]["link"] == crawler.base_url


def test_empty_and_missing_html_return_empty_list(crawler):
    """HTML فارغ أو مفقود ⇒ قائمة فارغة بلا استثناء."""
    assert crawler.parse_tenders("") == []
    assert crawler.parse_tenders(None) == []


def test_run_fetches_the_listing_page(crawler, monkeypatch):
    """``run`` يجلب صفحة القائمة لا الجذر، ويحلّل ما يصل."""
    fetched: list[str] = []

    def _fake_fetch(url):
        fetched.append(url)
        return _load("ade_categorie_appel_doffres.html")

    monkeypatch.setattr(crawler, "fetch_page", _fake_fetch)

    tenders = crawler.run()

    # W16-2 adds detail fetches for undated tenders, so listing is only the first URL.
    assert fetched[0] == "https://www.ade.dz/categorie/appel-doffres"
    assert all(url.startswith("https://www.ade.dz/") for url in fetched)
    assert len(tenders) == 4


def test_listing_path_is_stable():
    """المسار مثبّت كنص ظاهر لا سلسلة مركّبة في الكود."""
    assert LISTING_PATH == "categorie/appel-doffres"


# ── W16-1: الحقول الصادقة ──────────────────────────────────────────────


def test_emits_the_full_field_set(crawler):
    """كل مفتاح يتوقّعه تقرير Excel موجود في كل صفقة."""
    tenders = crawler.parse_tenders(_load("ade_categorie_appel_doffres.html"))

    expected = {
        "title",
        "link",
        "organisation",
        "wilaya",
        "product",
        "deadline",
        "status",
    }
    assert expected <= set(tenders[0])


def test_organisation_is_the_truthful_ade_constant(crawler):
    """الجهة الناشررة ثابتة صادقة، لا قيمة مُختلَقة."""
    tenders = crawler.parse_tenders(_load("ade_categorie_appel_doffres.html"))

    assert all(t["organisation"] == ADE_ORGANISATION for t in tenders)
    assert "ADE" in ADE_ORGANISATION


def test_wilaya_is_left_empty_for_the_filter_to_infer(crawler):
    """الولاية تُترك فارغة؛ ``classify_tender`` يملؤها من العنوان.

    التكرار هنا كان سيجعل منطق الاستنتاج موزّعاً على طبقتين.
    """
    tenders = crawler.parse_tenders(_load("ade_categorie_appel_doffres.html"))

    assert all(t["wilaya"] == "" for t in tenders)


def test_absent_fields_are_marked_not_invented(crawler):
    """الحقول غير المنشورة تُكتب ``UNKNOWN_VALUE`` لا قيمة مُختلَقة."""
    tenders = crawler.parse_tenders(_load("ade_categorie_appel_doffres.html"))

    for tender in tenders:
        assert tender["product"] == UNKNOWN_VALUE
        assert tender["deadline"] == UNKNOWN_VALUE
        assert tender["status"] == UNKNOWN_VALUE


def test_date_key_is_gone(crawler):
    """``date`` لم يكن في الموقع أصلاً، وحذفه يزيل عموداً إنجليزياً شارداً."""
    tenders = crawler.parse_tenders(_load("ade_categorie_appel_doffres.html"))

    assert all("date" not in t for t in tenders)


def test_ade_rows_are_live_not_reference_data(crawler):
    """صفقات ADE حيّة: بلا ``is_sample`` فلا يمسّها وسم T3."""
    tenders = crawler.parse_tenders(_load("ade_categorie_appel_doffres.html"))

    assert all("is_sample" not in t for t in tenders)


def test_wilaya_backfill_mechanism_resolves_known_wilayas():
    """ترك ``wilaya`` فارغاً آمن: المرشِّح يستنتج ولاية معروفة من العنوان.

    هذا هو ما يجعل ``""`` قراراً لا نقصاً — لكن فقط للولايات التي يعرفها
    ``data/targets.json``.
    """
    from tender_filter import TenderFilter

    resolved = TenderFilter().find_wilaya_in_text("Fourniture de tuyaux PVC a Constantine")

    assert resolved == "قسنطينة"


def test_real_ade_corpus_carries_no_resolvable_wilaya():
    """واقعة صفقات ADE الحالية وطنية؛ «ville d'El Eulma» غير معروفة للفلتر.

    الاختبار يثبّت السلوك الفعلي بدل افتراض: العنوان يذكر ولاية، لكنها ليست في
    ``targets.json``، فتبقى ``wilaya`` فارغة. هذا صادق — مناقصة وطنية لا ولاية لها.
    """
    from tender_filter import TenderFilter

    crawler = ADECrawler()
    tenders = crawler.parse_tenders(_load("ade_categorie_appel_doffres.html"))
    el_eulma_tender = next(t for t in tenders if "El Eulma" in t["title"])

    assert el_eulma_tender["wilaya"] == ""
    assert TenderFilter().find_wilaya_in_text(el_eulma_tender["title"]) is None


def test_wilaya_priority_is_translated_in_excel():
    """عمود ``wilaya_priority`` صار له عنوان عربي بدل الاسم الإنجليزي."""
    from notifications.excel_report import COLUMNS_MAPPING

    assert COLUMNS_MAPPING["wilaya_priority"] == "أولوية الولاية"


def test_ade_extracts_publication_year_from_slug():
    """السنة من الرابط."""
    tenders = ADECrawler().parse_tenders(_load("ade_categorie_appel_doffres.html"))
    assert tenders[0]["published_date"] == "2023-01-01"
    assert tenders[2]["published_date"] == "2023-01-01"


def test_ade_falls_back_to_title_for_year():
    """سنة من العنوان عند غيابها في الرابط."""
    html = ('<div class="service-block-two"><h3>'
            '<a href="../article/sans-annee">Appel d\'Offres National N° 09-2024</a>'
            "</h3></div>")
    tenders = ADECrawler().parse_tenders(html)
    assert tenders[0]["published_date"] == "2024-01-01"


def test_ade_fetches_detail_for_undated_tender(monkeypatch):
    """جلب التفاصيل لصفقة بلا تاريخ."""
    crawler = ADECrawler()
    detail = _load("ade_article_detail.html")
    calls = []

    def _fake_fetch(url):
        calls.append(url)
        return detail

    monkeypatch.setattr(crawler, "fetch_page", _fake_fetch)
    html = ('<div class="service-block-two"><h3><a href="../article/'
            'appel-doffres-national-ouvert-pour-lacquisition-de-compteurs-deau-'
            'potable-froide-de-type-multi-jets">Appel d\'offres national ouvert '
            "pour l'acquisition de compteurs</a></h3></div>")
    tenders = crawler.parse_tenders(html)
    assert tenders[0]["published_date"] == "2023-02-01"
    assert calls == ["https://www.ade.dz/article/appel-doffres-national-ouvert-"
                     "pour-lacquisition-de-compteurs-deau-potable-froide-de-type-multi-jets"]


def test_excel_report_includes_published_date():
    """عمود تاريخ النشر معرّب."""
    from notifications.excel_report import COLUMNS_MAPPING
    assert COLUMNS_MAPPING["published_date"] == "تاريخ النشر"
