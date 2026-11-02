"""Jinja environment: Arabic filters, URL helpers and design tokens."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi.templating import Jinja2Templates

from webapp.enums import STYLE_BY_TYPE, TYPE_LABELS, AnnouncementType
from webapp.search import SORT_OPTIONS
from webapp.text import format_dzd, truncate_words
from webapp.timeutils import deadline_label, format_date_ar, format_datetime_ar

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

SITE_NAME_AR = "مناقصات الجزائر"
SITE_NAME_FR = "DZ Tenders"
SITE_TAGLINE = "منصة المناقصات والاستشارات العمومية الجزائرية"


def _announcement_path(announcement) -> str:
    """Canonical path of an announcement, slug percent-encoded."""
    return f"/annonces/{announcement.id}/{quote(announcement.slug, safe='')}"


def _offer_path(offer) -> str:
    """Canonical path of a subcontracting offer."""
    return f"/sous-traitance/{offer.id}/{quote(offer.slug, safe='')}"


def announcement_path(announcement) -> str:
    """Public URL path for an announcement."""
    return _announcement_path(announcement)


def offer_path(offer) -> str:
    """Public URL path for a subcontracting offer."""
    return _offer_path(offer)


def build_templates() -> Jinja2Templates:
    """Create the Jinja2 templates object with shared filters/globals."""
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    env = templates.env

    env.filters["date_ar"] = format_date_ar
    env.filters["datetime_ar"] = format_datetime_ar
    env.filters["deadline_label"] = deadline_label
    env.filters["dzd"] = format_dzd
    env.filters["truncate_words"] = truncate_words
    env.filters["type_label"] = lambda value: TYPE_LABELS.get(
        AnnouncementType(value), (str(value), str(value))
    )[0]
    env.filters["type_label_fr"] = lambda value: TYPE_LABELS.get(
        AnnouncementType(value), (str(value), str(value))
    )[1]
    env.filters["percent"] = lambda value, total: (
        round((value / total) * 100) if total else 0
    )
    env.filters["type_class"] = lambda value: STYLE_BY_TYPE.get(
        AnnouncementType(value), "tender"
    )

    env.globals.update(
        site_name=SITE_NAME_AR,
        site_name_fr=SITE_NAME_FR,
        site_tagline=SITE_TAGLINE,
        announcement_types=list(AnnouncementType),
        type_labels=TYPE_LABELS,
        sort_options=SORT_OPTIONS,
        ann_url=_announcement_path,
        offer_url=_offer_path,
    )
    return templates


def page_url(request, page: int) -> str:
    """Current URL with ``page`` replaced, preserving every other filter."""
    params: dict[str, str] = {}
    for key, value in request.query_params.items():
        if key != "page" and value:
            params[key] = value
    if page > 1:
        params["page"] = str(page)
    query = urlencode(params, doseq=True)
    return f"{request.url.path}?{query}" if query else request.url.path


def sort_url(request, sort: str) -> str:
    """Current URL with the ``sort`` parameter replaced."""
    params = {
        key: value for key, value in request.query_params.items() if key != "sort"
    }
    if sort and sort != "relevance":
        params["sort"] = sort
    query = urlencode(params, doseq=True)
    return f"{request.url.path}?{query}" if query else request.url.path


__all__ = [
    "SITE_NAME_AR",
    "SITE_NAME_FR",
    "SITE_TAGLINE",
    "STATIC_DIR",
    "TEMPLATES_DIR",
    "announcement_path",
    "build_templates",
    "offer_path",
    "page_url",
    "sort_url",
]


def render(ctx, template_name: str, **extra):
    """Render a template with the shared page context.

    Args:
        ctx: :class:`webapp.web.deps.PageContext`.
        template_name: Template path under ``webapp/templates``.
        **extra: Page-specific context values.

    Returns:
        A Starlette ``TemplateResponse``.
    """
    from webapp.timeutils import today_algiers

    context = {
        "request": ctx.request,
        "settings": ctx.settings,
        "user": ctx.user,
        "entitlements": ctx.entitlements,
        "csrf_token": ctx.csrf_token,
        "canonical_url": ctx.canonical_url,
        "current_path": ctx.request.url.path,
        "current_year": today_algiers().year,
        "page_url": page_url,
        "sort_url": sort_url,
    }
    context.update(extra)
    return ctx.request.app.state.templates.TemplateResponse(
        ctx.request, template_name, context
    )
