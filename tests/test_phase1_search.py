"""FTS5 search, filters, sorting, pagination and the LIKE fallback."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, text

from webapp.enums import AnnouncementStatus, AnnouncementType
from webapp.models import Announcement, Issuer, Sector, Wilaya
from webapp.search import AnnouncementFilters, search_announcements
from webapp.search_index import index_announcement
from webapp.text import slugify
from webapp.timeutils import today_algiers

_counter = {"n": 0}


def add_announcement(
    db,
    *,
    title: str,
    description: str = "",
    type: AnnouncementType = AnnouncementType.TENDER,
    wilaya_code: str = "25",
    sectors: tuple[str, ...] = ("water",),
    issuer_slug: str = "ade",
    publish_days_ago: int = 0,
    status: AnnouncementStatus = AnnouncementStatus.PUBLISHED,
    is_sample: bool = False,
) -> Announcement:
    """Insert a minimal published announcement and index it."""
    _counter["n"] += 1
    number = _counter["n"]
    wilaya = db.scalar(select(Wilaya).where(Wilaya.code == wilaya_code))
    issuer = db.scalar(select(Issuer).where(Issuer.slug == issuer_slug))
    sector_objects = [
        db.scalar(select(Sector).where(Sector.slug == slug)) for slug in sectors
    ]
    publish_date = today_algiers() - timedelta(days=publish_days_ago)
    announcement = Announcement(
        ref=f"TEST-{number:04d}",
        slug=slugify(title, fallback=f"test-{number}"),
        type=type,
        status=status,
        title_ar=title,
        description_ar=description,
        issuer_id=issuer.id if issuer else None,
        issuer_name=issuer.name_ar if issuer else "",
        wilaya_id=wilaya.id,
        publish_date=publish_date,
        publish_year=publish_date.year,
        deadline_at=None,
        is_sample=is_sample,
        source_key="test",
        external_id=f"test-{number}",
    )
    announcement.sectors = [sector for sector in sector_objects if sector]
    db.add(announcement)
    db.flush()
    index_announcement(db, announcement)
    db.commit()
    return announcement


def search(db, **kwargs):
    filters = AnnouncementFilters(**kwargs)
    return search_announcements(db, filters, per_page=kwargs.get("per_page", 48))


def test_fts_finds_alef_variants(seeded) -> None:
    result = search(seeded, q="انابيب")
    assert result.used_fts
    assert result.total >= 1
    assert any("أنابيب" in item.title_ar for item in result.items)


def test_fts_finds_ta_marbuta_normalised(seeded) -> None:
    add_announcement(seeded, title="إدارة المشاريع المائية", description="دراسة إدارة")
    result = search(seeded, q="اداره")
    assert any("إدارة" in item.title_ar for item in result.items)


def test_fts_is_prefix_aware(seeded) -> None:
    result = search(seeded, q="خزان")
    assert result.total >= 1
    assert all("خزان" in (item.title_ar + item.description_ar) for item in result.items)


def test_fts_matches_description_and_diacritics(seeded) -> None:
    add_announcement(
        seeded,
        title="مناقصة تجريبية للتوثيق",
        description="أَنَابِيبُ ضغط عالٍ للشبكة",
    )
    result = search(seeded, q="انابيب ضغط")
    assert any("ضغط" in item.description_ar for item in result.items)


def test_filter_by_type(seeded) -> None:
    result = search(seeded, type=AnnouncementType.AUCTION)
    assert result.total >= 1
    assert all(item.type == AnnouncementType.AUCTION for item in result.items)


def test_filter_by_wilaya(seeded) -> None:
    result = search(seeded, wilaya_code="31")
    assert result.total >= 1
    assert all(item.wilaya.code == "31" for item in result.items)


def test_filter_by_sector(seeded) -> None:
    result = search(seeded, sector_slug="health")
    assert result.total >= 1
    assert all(
        any(sector.slug == "health" for sector in item.sectors) for item in result.items
    )


def test_filter_by_issuer(seeded) -> None:
    result = search(seeded, issuer_slug="sonelgaz")
    assert result.total >= 1
    assert all(item.issuer and item.issuer.slug == "sonelgaz" for item in result.items)


def test_filter_by_date_range(seeded) -> None:
    today = today_algiers()
    result = search(
        seeded,
        date_from=today - timedelta(days=5),
        date_to=today,
        per_page=48,
    )
    assert result.total >= 1
    assert all(
        today - timedelta(days=5) <= item.publish_date <= today for item in result.items
    )


def test_date_range_does_not_leak_outside_bounds(seeded) -> None:
    today = today_algiers()
    result = search(seeded, date_to=today - timedelta(days=300))
    assert all(
        item.publish_date <= today - timedelta(days=300) for item in result.items
    )


def test_sort_order_recent_and_oldest(seeded) -> None:
    recent = search(seeded, sort="recent")
    dates = [item.publish_date for item in recent.items]
    assert dates == sorted(dates, reverse=True)

    oldest = search(seeded, sort="oldest", q="مناقصة")
    oldest_dates = [item.publish_date for item in oldest.items]
    assert oldest_dates == sorted(oldest_dates)


def test_pagination_metadata(seeded) -> None:
    for index in range(14):
        add_announcement(seeded, title=f"مناقصة ترقيم الصفحات {index}", is_sample=False)
    result = search_announcements(
        seeded, AnnouncementFilters(type=AnnouncementType.TENDER), per_page=5
    )
    assert result.total >= 14
    assert result.pages == (result.total + 4) // 5
    assert len(result.items) == 5
    assert result.page_numbers[0] == 1
    second = search_announcements(
        seeded,
        AnnouncementFilters(type=AnnouncementType.TENDER, page=2),
        per_page=5,
    )
    assert second.page == 2
    assert {item.id for item in second.items}.isdisjoint(
        {item.id for item in result.items}
    )


def test_page_is_clamped_to_last_page(seeded) -> None:
    result = search_announcements(seeded, AnnouncementFilters(page=9999), per_page=12)
    assert result.page == result.pages


def test_drafts_are_not_public(seeded) -> None:
    draft = add_announcement(
        seeded,
        title="مسودة سرية لا يجب نشرها",
        status=AnnouncementStatus.DRAFT,
    )
    assert search(seeded, q="مسودة سرية").total == 0
    archived = add_announcement(
        seeded,
        title="إعلان مؤرشف قديم",
        status=AnnouncementStatus.ARCHIVED,
    )
    titles = [item.title_ar for item in search(seeded, per_page=48).items]
    assert "إعلان مؤرشف قديم" in titles
    assert draft.title_ar not in titles
    assert archived.id


def test_samples_can_be_excluded(seeded) -> None:
    result = search(seeded, include_samples=False)
    assert result.total == 0


def test_like_fallback_without_fts(engine, session_factory, seeded) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE announcement_fts"))
    with session_factory() as fresh:
        result = search_announcements(
            fresh, AnnouncementFilters(q="انابيب"), per_page=48
        )
        assert not result.used_fts
        assert result.total >= 1
        assert any("أنابيب" in item.title_ar for item in result.items)


def test_hostile_query_is_harmless(seeded) -> None:
    for query in ['" OR *', "%_%", "NEAR(", "سياسة"]:
        result = search(seeded, q=query)
        assert result.total >= 0


def test_issuer_filter_with_unknown_slug_returns_empty(seeded) -> None:
    assert search(seeded, issuer_slug="does-not-exist").total == 0
