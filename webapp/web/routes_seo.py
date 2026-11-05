"""SEO surface: robots.txt, sitemap.xml and the public health probe."""

from __future__ import annotations

from typing import Annotated
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from webapp import repositories as repo
from webapp.config import Settings
from webapp.enums import AnnouncementStatus, SubcontractingStatus
from webapp.models import Announcement, SubcontractingOffer
from webapp.search import PUBLIC_STATUSES
from webapp.web.deps import get_db, get_settings
from webapp.web.templating import announcement_path, offer_path

router = APIRouter()

#: Upper bound per sitemap file; a sitemap index is a Phase 6 item.
SITEMAP_LIMIT = 5000

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def _base_url(request: Request, settings: Settings) -> str:
    return settings.public_base_url or str(request.base_url).rstrip("/")


@router.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
def robots(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> PlainTextResponse:
    """Disallow account/admin areas and advertise the sitemap."""
    base = _base_url(request, settings)
    body = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /connexion",
            "Disallow: /deconnexion",
            "Disallow: /compte",
            "Disallow: /admin",
            "Disallow: /health",
            "",
            f"Sitemap: {base}/sitemap.xml",
            "",
        ]
    )
    return PlainTextResponse(body)


@router.get("/sitemap.xml", include_in_schema=False)
def sitemap(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """XML sitemap of public pages, announcements, archives and offers."""
    base = _base_url(request, settings)
    urls: list[tuple[str, str | None, str]] = [
        (f"{base}/", None, "daily"),
        (f"{base}/annonces", None, "daily"),
        (f"{base}/archives", None, "weekly"),
        (f"{base}/sous-traitance", None, "daily"),
        (f"{base}/tarifs", None, "monthly"),
        (f"{base}/contact", None, "yearly"),
        (f"{base}/conditions-utilisation", None, "yearly"),
        (f"{base}/confidentialite", None, "yearly"),
        (f"{base}/cookies", None, "yearly"),
    ]

    for year, _count in repo.archive_years(db):
        urls.append((f"{base}/archives/{year}", None, "monthly"))

    announcements = db.scalars(
        select(Announcement)
        .where(Announcement.status.in_(PUBLIC_STATUSES))
        .order_by(Announcement.publish_date.desc(), Announcement.id.desc())
        .limit(SITEMAP_LIMIT)
    ).all()
    for announcement in announcements:
        urls.append(
            (
                f"{base}{announcement_path(announcement)}",
                announcement.publish_date.isoformat(),
                (
                    "weekly"
                    if announcement.status == AnnouncementStatus.PUBLISHED
                    else "yearly"
                ),
            )
        )

    offers = db.scalars(
        select(SubcontractingOffer)
        .where(SubcontractingOffer.status == SubcontractingStatus.PUBLISHED)
        .order_by(SubcontractingOffer.id.desc())
        .limit(SITEMAP_LIMIT)
    ).all()
    for offer in offers:
        published = (
            offer.published_at.date().isoformat() if offer.published_at else None
        )
        urls.append((f"{base}{offer_path(offer)}", published, "weekly"))

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<urlset xmlns="{SITEMAP_NS}">',
    ]
    for loc, lastmod, changefreq in urls:
        lines.append("<url>")
        lines.append(f"<loc>{escape(loc)}</loc>")
        if lastmod:
            lines.append(f"<lastmod>{lastmod}</lastmod>")
        lines.append(f"<changefreq>{changefreq}</changefreq>")
        lines.append("</url>")
    lines.append("</urlset>")
    return Response("\n".join(lines), media_type="application/xml")


@router.get("/health", include_in_schema=False)
def health(db: Annotated[Session, Depends(get_db)]) -> JSONResponse:
    """Database-backed health probe without sensitive details."""
    try:
        count = int(db.scalar(select(func.count(Announcement.id))) or 0)
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "unavailable"},
        )
    return JSONResponse(
        status_code=200,
        content={"status": "ok", "database": "available", "announcements": count},
    )


__all__ = ["router"]
