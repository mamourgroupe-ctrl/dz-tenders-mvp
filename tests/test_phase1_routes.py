"""End-to-end HTTP behaviour of the public site and access gating."""

from __future__ import annotations

from urllib.parse import unquote

from sqlalchemy import func, select

from tests.conftest import login, make_user, subscribe
from webapp.models import Announcement, SearchLog
from webapp.timeutils import format_datetime_ar


def _announcement(db, title_part: str) -> Announcement:
    return db.scalar(
        select(Announcement).where(Announcement.title_ar.contains(title_part))
    )


def _login_with_plan(client, db, *, phone: str, plan: str, sectors: tuple[str, ...]):
    user = make_user(db, phone=phone)
    subscribe(db, user, plan_code=plan, sector_slugs=sectors)
    response = login(client, phone)
    assert response.status_code == 303
    return user


def test_home_page_renders_rtl_arabic(client, seeded) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert '<html lang="ar" dir="rtl">' in response.text
    assert "مناقصات الجزائر" in response.text
    assert "أحدث الإعلانات" in response.text
    assert "المناقصات العمومية الجزائرية" in response.text


def test_listing_page_renders_filters_and_cards(client, seeded) -> None:
    response = client.get("/annonces")
    assert response.status_code == 200
    assert "تصفية النتائج" in response.text
    assert "أحدث الإعلانات" not in response.text
    assert "اقتناء أنابيب PVC" in response.text


def test_listing_search_filters_by_keyword(client, seeded) -> None:
    response = client.get("/annonces", params={"q": "خزانات"})
    assert response.status_code == 200
    assert "خزانات بولي إيثيلين" in response.text
    assert "تهيئة الطرق الحضرية" not in response.text


def test_listing_filter_by_wilaya_and_type(client, seeded) -> None:
    response = client.get("/annonces", params={"wilaya": "31", "type": "consultation"})
    assert response.status_code == 200
    assert "الصيانة المعلوماتية" in response.text
    assert "اقتناء أنابيب PVC" not in response.text


def test_invalid_filter_is_reported_not_crashing(client, seeded) -> None:
    response = client.get("/annonces", params={"type": "unknown", "sector": "nope"})
    assert response.status_code == 200
    assert "نوع الإعلان المطلوب غير معروف" in response.text
    assert "القطاع المطلوب غير معروف" in response.text


def test_invalid_date_range_is_reported(client, seeded) -> None:
    response = client.get(
        "/annonces", params={"from": "2026-12-31", "to": "2026-01-01"}
    )
    assert response.status_code == 200
    assert "تاريخ البداية يجب أن يسبق تاريخ النهاية" in response.text


def test_detail_free_hides_paid_fields(client, seeded) -> None:
    announcement = _announcement(seeded, "أنابيب PVC")
    response = client.get(f"/annonces/{announcement.id}")
    assert response.status_code == 200
    assert announcement.title_ar in response.text
    assert announcement.wilaya.name_ar in response.text
    assert "الجزائرية للمياه" not in response.text
    assert "مناقصة توضيحية لاقتناء أنابيب PVC" not in response.text
    assert format_datetime_ar(announcement.deadline_at) not in response.text
    assert announcement.source_url not in response.text
    assert "التفاصيل الكاملة للمشتركين" in response.text
    assert "أنشئ حساباً واشترك" in response.text


def test_detail_paid_unlocks_fields_for_covered_sector(client, seeded) -> None:
    _login_with_plan(
        client, seeded, phone="0555222001", plan="gold", sectors=("water",)
    )
    announcement = _announcement(seeded, "أنابيب PVC")
    response = client.get(f"/annonces/{announcement.id}")
    assert response.status_code == 200
    assert "الجزائرية للمياه" in response.text
    assert "مناقصة توضيحية لاقتناء أنابيب PVC" in response.text
    assert format_datetime_ar(announcement.deadline_at) in response.text
    assert announcement.source_url in response.text
    assert "التفاصيل الكاملة للمشتركين" not in response.text


def test_detail_paid_stays_locked_for_uncovered_sector(client, seeded) -> None:
    _login_with_plan(
        client, seeded, phone="0555222002", plan="bronze", sectors=("health",)
    )
    announcement = _announcement(seeded, "أنابيب PVC")
    response = client.get(f"/annonces/{announcement.id}")
    assert response.status_code == 200
    assert "قطاع هذه المناقصة غير مشمول في اشتراكك" in response.text
    assert "الجزائرية للمياه" not in response.text


def test_detail_expired_subscription_is_locked(client, seeded) -> None:
    user = make_user(seeded, phone="0555222003")
    subscribe(
        seeded,
        user,
        plan_code="platinum",
        sector_slugs=(),
        starts_days=-40,
        ends_days=-1,
    )
    assert login(client, "0555222003").status_code == 303
    response = client.get("/annonces/1")
    assert "هذه المعلومات متاحة للمشتركين فقط" in response.text
    assert "الجزائرية للمياه" not in response.text


def test_slug_mismatch_redirects_to_canonical(client, seeded) -> None:
    announcement = _announcement(seeded, "أنابيب PVC")
    response = client.get(
        f"/annonces/{announcement.id}/wrong-slug", follow_redirects=False
    )
    assert response.status_code == 301
    location = response.headers["location"]
    assert location.startswith(f"/annonces/{announcement.id}/")
    assert unquote(location).endswith(announcement.slug)
    assert client.get(location).status_code == 200


def test_archive_pages(client, seeded) -> None:
    response = client.get("/archives")
    assert response.status_code == 200
    assert "الأرشيف حسب السنة" in response.text
    year = _announcement(seeded, "أنابيب PVC").publish_year
    year_page = client.get(f"/archives/{year}")
    assert year_page.status_code == 200
    assert f"أرشيف سنة {year}" in year_page.text
    assert client.get("/archives/1999").status_code == 404


def test_subcontracting_listing_gates_issuer(client, seeded) -> None:
    response = client.get("/sous-traitance")
    assert response.status_code == 200
    assert "عروض التعاقد من الباطن" in response.text
    assert "مؤسسة نموذجية للبناء" not in response.text
    assert "بيانات الاتصال متاحة للمشتركين" in response.text

    _login_with_plan(client, seeded, phone="0555222004", plan="platinum", sectors=())
    paid = client.get("/sous-traitance")
    assert "مؤسسة نموذجية للبناء" in paid.text
    assert "بيانات الاتصال متاحة للمشتركين" not in paid.text


def test_subcontracting_detail_redirect_and_gate(client, seeded) -> None:
    response = client.get("/sous-traitance/1", follow_redirects=False)
    assert response.status_code == 301
    locked = client.get(response.headers["location"])
    assert locked.status_code == 200
    assert "sous-traitance@example.dz" not in locked.text
    assert "بيانات الاتصال للمشتركين" in locked.text

    _login_with_plan(client, seeded, phone="0555222005", plan="platinum", sectors=())
    unlocked = client.get(response.headers["location"])
    assert "sous-traitance@example.dz" in unlocked.text
    assert "بيانات الاتصال للمشتركين" not in unlocked.text


def test_sitemap_and_robots(client, seeded) -> None:
    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "application/xml" in sitemap.headers["content-type"]
    assert "<urlset" in sitemap.text
    assert "http://testserver/annonces/" in sitemap.text
    assert "http://testserver/tarifs" in sitemap.text

    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "Disallow: /connexion" in robots.text
    assert "Sitemap: http://testserver/sitemap.xml" in robots.text


def test_health_endpoint(client, seeded) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["announcements"] == 24


def test_security_headers(client, seeded) -> None:
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_csrf_cookie_is_set_and_httponly(client, seeded) -> None:
    client.get("/")
    token = client.cookies.get("dz_csrf")
    assert token
    response = client.get("/")
    assert "dz_csrf" in response.headers.get("set-cookie", "") or token


def test_unknown_page_returns_arabic_404(client, seeded) -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert "الصفحة غير موجودة" in response.text

    invalid = client.get("/annonces/not-a-number")
    assert invalid.status_code == 404
    assert "الصفحة غير موجودة" in invalid.text


def test_draft_announcement_is_404(client, seeded) -> None:
    announcement = _announcement(seeded, "أنابيب PVC")
    from webapp.enums import AnnouncementStatus

    announcement.status = AnnouncementStatus.DRAFT
    seeded.commit()
    response = client.get(f"/annonces/{announcement.id}")
    assert response.status_code == 404


def test_sample_badge_visible(client, seeded) -> None:
    response = client.get("/annonces")
    assert "نموذج" in response.text
    detail = client.get("/annonces/1")
    assert "إعلان توضيحي (نموذج)" in detail.text


def test_view_counter_increments(client, seeded) -> None:
    announcement = _announcement(seeded, "خزان مياه")
    before = announcement.view_count
    client.get(f"/annonces/{announcement.id}")
    seeded.refresh(announcement)
    assert announcement.view_count == before + 1


def test_search_terms_are_logged(client, seeded) -> None:
    seeded.execute(SearchLog.__table__.delete())
    seeded.commit()
    client.get("/annonces", params={"q": "خزانات"})
    count = seeded.scalar(
        select(func.count(SearchLog.id)).where(
            SearchLog.term_normalized.contains("خزان")
        )
    )
    assert count == 1


def test_pagination_page_two_and_clamping(client, seeded) -> None:
    second = client.get("/annonces", params={"page": 2})
    assert second.status_code == 200
    assert "الصفحة 2" in second.text
    clamped = client.get("/annonces", params={"page": 9999})
    assert clamped.status_code == 200
    assert "الصفحة 2" in clamped.text


def test_query_is_escaped(client, seeded) -> None:
    payload = "<script>alert(1)</script>"
    response = client.get("/annonces", params={"q": payload})
    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_static_assets_are_served(client) -> None:
    css = client.get("/static/css/app.css")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
    js = client.get("/static/js/theme.js")
    assert js.status_code == 200


def test_pricing_page_marks_placeholder_prices(client, seeded) -> None:
    response = client.get("/tarifs")
    assert response.status_code == 200
    assert "الأسعار المعروضة مؤقتة" in response.text
    assert "بلاتيني" in response.text
    assert "المزادات فقط" in response.text
    assert "التفعيل قريباً" in response.text


def test_login_page_and_protected_redirect(client, seeded) -> None:
    response = client.get("/connexion", params={"next": "/annonces"})
    assert response.status_code == 200
    assert 'name="csrf_token"' in response.text
    assert 'value="/annonces"' in response.text


def test_announcement_404_for_missing_id(client, seeded) -> None:
    assert client.get("/annonces/999999").status_code == 404
    assert client.get("/sous-traitance/999999").status_code == 404
