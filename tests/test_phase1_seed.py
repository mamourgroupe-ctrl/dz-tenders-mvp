"""Reference data, demo content and idempotency of the seeder."""

from __future__ import annotations

import json

from sqlalchemy import func, select, text

from webapp.db import make_engine, make_session_factory, session_scope
from webapp.enums import AnnouncementType, PlanKind, SubcontractingStatus
from webapp.models import (
    Announcement,
    Issuer,
    Plan,
    Sector,
    SubcontractingOffer,
    Wilaya,
)
from webapp.seed import load_wilayas_override, seed_all, seed_wilayas
from webapp.seed_data import WILAYAS


def test_reference_counts(seeded) -> None:
    db = seeded
    assert db.scalar(select(func.count(Wilaya.id))) == 69
    assert db.scalar(select(func.count(Sector.id))) == 16
    assert db.scalar(select(func.count(Issuer.id))) == 20
    assert db.scalar(select(func.count(Plan.id))) == 8
    assert db.scalar(select(func.count(Announcement.id))) == 24
    assert db.scalar(select(func.count(SubcontractingOffer.id))) == 5


def test_wilaya_codes_are_official_and_unique(seeded) -> None:
    codes = [row for row in seeded.scalars(select(Wilaya.code).order_by(Wilaya.code))]
    assert codes == [code for code, _slug, _ar, _fr in sorted(WILAYAS)]
    assert len(set(codes)) == 69
    assert codes[0] == "01" and codes[-1] == "69"


def test_eight_announcement_types_are_present(seeded) -> None:
    types = set(seeded.scalars(select(Announcement.type)).all())
    assert types == set(AnnouncementType)
    for kind in AnnouncementType:
        assert (
            seeded.scalar(
                select(func.count(Announcement.id)).where(Announcement.type == kind)
            )
            >= 1
        )


def test_sample_content_is_flagged_and_attributed(seeded) -> None:
    announcements = seeded.scalars(select(Announcement)).all()
    assert all(item.is_sample for item in announcements)
    assert all(
        item.source_url and item.source_url.startswith("https://example.dz")
        for item in announcements
    )
    assert all(item.source_name == "بيانات تجريبية" for item in announcements)
    assert all(item.search_text for item in announcements)


def test_public_offers_exclude_pending(seeded) -> None:
    published = seeded.scalars(
        select(SubcontractingOffer).where(
            SubcontractingOffer.status == SubcontractingStatus.PUBLISHED
        )
    ).all()
    pending = seeded.scalars(
        select(SubcontractingOffer).where(
            SubcontractingOffer.status == SubcontractingStatus.PENDING
        )
    ).all()
    assert len(published) == 4
    assert len(pending) == 1


def test_plans_cover_required_tiers(seeded) -> None:
    plans = {plan.code: plan for plan in seeded.scalars(select(Plan)).all()}
    assert {"free", "bronze", "silver", "gold", "premium", "platinum"} <= set(plans)
    assert "auctions_only" in plans and plans["auctions_only"].auctions_only
    assert plans["extra_sector"].kind == PlanKind.ADDON
    assert plans["bronze"].sector_limit == 1
    assert plans["silver"].sector_limit == 4
    assert plans["gold"].sector_limit == 6
    assert plans["premium"].sector_limit == 10
    assert plans["platinum"].sector_limit is None
    assert plans["gold"].annual_discount_percent > 0
    assert plans["gold"].is_price_placeholder is True


def test_seed_is_idempotent(seeded) -> None:
    second = seed_all(seeded, with_demo=True)
    assert second.announcements == 0
    assert second.offers == 0
    assert seeded.scalar(select(func.count(Announcement.id))) == 24
    assert seeded.scalar(select(func.count(Wilaya.id))) == 69


def test_fts_index_has_one_row_per_announcement(seeded) -> None:
    count = seeded.execute(text("SELECT COUNT(*) FROM announcement_fts")).scalar()
    assert count == 24


def test_wilaya_override_file_is_supported(tmp_path) -> None:
    payload = [
        {"code": "01", "name_ar": "أدرار", "name_fr": "Adrar", "slug": "adrar"},
        {"code": "69", "name_ar": "ولاية إضافية", "name_fr": "Wilaya additionnelle"},
    ]
    path = tmp_path / "wilayas.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    rows = load_wilayas_override(str(path))
    assert [row[0] for row in rows] == ["01", "69"]
    assert rows[1][1] == "wilaya-additionnelle"

    engine = make_engine(f"sqlite+pysqlite:///{tmp_path / 'override.db'}")
    from webapp.db import Base

    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with session_scope(factory) as db:
        assert seed_wilayas(db, rows) == 2
        codes = list(db.scalars(select(Wilaya.code).order_by(Wilaya.code)))
        assert codes == ["01", "69"]
    engine.dispose()


def test_wilaya_override_rejects_duplicates(tmp_path) -> None:
    payload = [
        {"code": "01", "name_ar": "أدرار", "name_fr": "Adrar"},
        {"code": "01", "name_ar": "مكرر", "name_fr": "Doublon"},
    ]
    path = tmp_path / "wilayas.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    import pytest

    with pytest.raises(ValueError):
        load_wilayas_override(str(path))
