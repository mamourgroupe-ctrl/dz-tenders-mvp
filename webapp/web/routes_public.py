"""Public Arabic pages: home, listings, detail, archive, offers, legal pages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from webapp import repositories as repo
from webapp.access import build_announcement_view, build_offer_view
from webapp.enums import AnnouncementType, BannerPlacement
from webapp.models import Announcement, ContactMessage
from webapp.search import (
    DEFAULT_PER_PAGE,
    MAX_PER_PAGE,
    SORT_OPTIONS,
    AnnouncementFilters,
    latest_announcements,
    published_announcement,
    search_announcements,
)
from webapp.security import RateLimiter, client_ip, hash_ip, normalize_phone
from webapp.text import truncate_words
from webapp.web.deps import PageContext, get_page_context, verify_csrf
from webapp.web.templating import SITE_NAME_AR, render

router = APIRouter()


@dataclass
class FilterState:
    """Raw filter values echoed back into the form."""

    q: str = ""
    type: str = ""
    wilaya: str = ""
    sector: str = ""
    issuer: str = ""
    date_from: str = ""
    date_to: str = ""
    sort: str = "relevance"
    per_page: int = DEFAULT_PER_PAGE
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, str]:
        """Template-friendly representation."""
        return {
            "q": self.q,
            "type": self.type,
            "wilaya": self.wilaya,
            "sector": self.sector,
            "issuer": self.issuer,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "sort": self.sort,
            "per_page": str(self.per_page),
        }

    @property
    def active_count(self) -> int:
        """Number of active filters (for the mobile filter badge)."""
        values = (
            self.type,
            self.wilaya,
            self.sector,
            self.issuer,
            self.date_from,
            self.date_to,
        )
        return sum(1 for value in values if value)


def _parse_date(raw: str, label: str, errors: list[str]) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        errors.append(f"صيغة التاريخ غير صحيحة في «{label}».")
        return None


def parse_filters(ctx: PageContext) -> tuple[AnnouncementFilters, FilterState]:
    """Validate query parameters against the taxonomy.

    Invalid values never raise: they are reported above the results and ignored
    so a shared/broken link still yields a usable page.
    """
    params = ctx.request.query_params
    db = ctx.db
    errors: list[str] = []
    state = FilterState(
        q=(params.get("q") or "").strip()[:200],
        type=(params.get("type") or "").strip(),
        wilaya=(params.get("wilaya") or "").strip(),
        sector=(params.get("sector") or "").strip(),
        issuer=(params.get("issuer") or "").strip(),
        date_from=(params.get("from") or "").strip(),
        date_to=(params.get("to") or "").strip(),
    )

    try:
        state.per_page = int(params.get("per_page") or DEFAULT_PER_PAGE)
    except ValueError:
        state.per_page = DEFAULT_PER_PAGE
    state.per_page = min(MAX_PER_PAGE, max(1, state.per_page))

    sort = (params.get("sort") or "").strip()
    state.sort = (
        sort if sort in SORT_OPTIONS else ("relevance" if state.q else "recent")
    )

    announcement_type: AnnouncementType | None = None
    if state.type:
        try:
            announcement_type = AnnouncementType(state.type)
        except ValueError:
            errors.append("نوع الإعلان المطلوب غير معروف.")
            state.type = ""

    wilaya_code = ""
    if state.wilaya:
        wilayas = repo.active_wilayas(db)
        matched = next(
            (
                w
                for w in wilayas
                if w.code == state.wilaya.zfill(2) or w.slug == state.wilaya
            ),
            None,
        )
        if matched is None:
            errors.append("الولاية المطلوبة غير معروفة.")
            state.wilaya = ""
        else:
            wilaya_code = matched.code
            state.wilaya = matched.code

    sector_slug = ""
    if state.sector:
        sectors = {sector.slug for sector in repo.active_sectors(db)}
        if state.sector not in sectors:
            errors.append("القطاع المطلوب غير معروف.")
            state.sector = ""
        else:
            sector_slug = state.sector

    issuer_slug = ""
    if state.issuer:
        issuers = {issuer.slug for issuer in repo.active_issuers(db)}
        if state.issuer not in issuers:
            errors.append("المؤسسة المطلوبة غير معروفة.")
            state.issuer = ""
        else:
            issuer_slug = state.issuer

    date_from = _parse_date(state.date_from, "من تاريخ", errors)
    date_to = _parse_date(state.date_to, "إلى تاريخ", errors)
    if date_from and date_to and date_from > date_to:
        errors.append("تاريخ البداية يجب أن يسبق تاريخ النهاية.")
        date_from = date_to = None

    state.errors = errors
    filters = AnnouncementFilters(
        q=state.q,
        type=announcement_type,
        wilaya_code=wilaya_code,
        sector_slug=sector_slug,
        issuer_slug=issuer_slug,
        date_from=date_from,
        date_to=date_to,
        sort=state.sort,
        page=max(1, _int(params.get("page"), 1)),
        per_page=state.per_page,
    )
    return filters, state


def _int(value: str | None, default: int) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _views(ctx: PageContext, announcements: list[Announcement]):
    return [
        build_announcement_view(ctx.entitlements, announcement)
        for announcement in announcements
    ]


def _filter_options(db: Session) -> dict:
    return {
        "wilayas": repo.active_wilayas(db),
        "sectors": repo.active_sectors(db),
        "issuers": repo.active_issuers(db),
    }


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------
@router.get("/", name="home")
def home(request: Request, ctx: Annotated[PageContext, Depends(get_page_context)]):
    """Home page: search, live counters, latest announcements and sectors."""
    db = ctx.db
    latest_rows = latest_announcements(db, limit=6)
    latest = _views(ctx, latest_rows)
    stats = repo.home_stats(db)
    types = repo.type_counts(db)
    wilayas = repo.top_wilayas(db, limit=10)
    sectors = repo.active_sectors(db)
    banners = repo.active_banners(db, BannerPlacement.HOME_TOP)
    return render(
        ctx,
        "home.html",
        latest=latest,
        stats=stats,
        types=types,
        top_wilayas=wilayas,
        sectors=sectors,
        options={"wilayas": repo.active_wilayas(db), "sectors": sectors},
        banners=banners,
        sample_count=sum(1 for item in latest if item.announcement.is_sample),
    )


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------
@router.get("/annonces", name="announcements")
def announcements_list(
    request: Request, ctx: Annotated[PageContext, Depends(get_page_context)]
):
    """Advanced search with filters, sorting and pagination."""
    filters, state = parse_filters(ctx)
    if filters.q and not _search_allowed(ctx):
        raise HTTPException(status_code=429, detail="search_rate_limited")
    result = search_announcements(ctx.db, filters, per_page=state.per_page)
    if filters.q:
        repo.record_search(ctx.db, filters.q, result.total)
    return render(
        ctx,
        "list.html",
        result=result,
        filters=filters,
        state=state,
        options=_filter_options(ctx.db),
        views=_views(ctx, result.items),
        heading="المناقصات والاستشارات",
        intro="ابحث في كل الإعلانات المنشورة، مع تصفية حسب الولاية والقطاع والمؤسسة والأجل.",
        show_archive_link=True,
    )


@router.get("/annonces/{announcement_id}", name="announcement_detail")
@router.get("/annonces/{announcement_id}/{slug}", name="announcement_detail_slug")
def announcement_detail(
    request: Request,
    ctx: Annotated[PageContext, Depends(get_page_context)],
    announcement_id: int,
    slug: str | None = None,
):
    """Announcement detail with plan-gated fields and canonical redirect."""
    announcement = published_announcement(ctx.db, announcement_id)
    if announcement is None:
        raise HTTPException(status_code=404, detail="announcement_not_found")

    if slug != announcement.slug:
        target = f"/annonces/{announcement.id}/{quote(announcement.slug, safe='')}"
        query = request.url.query
        return RedirectResponse(
            f"{target}?{query}" if query else target, status_code=301
        )

    view = build_announcement_view(ctx.entitlements, announcement)
    repo.increment_view_count(ctx.db, announcement.id)
    similar = [
        build_announcement_view(ctx.entitlements, item)
        for item in repo.similar_announcements(ctx.db, announcement)
    ]
    structured_data = _structured_data(announcement, ctx.canonical_url)
    return render(
        ctx,
        "detail.html",
        view=view,
        announcement=announcement,
        similar=similar,
        structured_data=structured_data,
        page_description=truncate_words(announcement.title_ar, 155),
    )


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------
@router.get("/archives", name="archive")
def archive_index(
    request: Request, ctx: Annotated[PageContext, Depends(get_page_context)]
):
    """Announcements grouped by publication year."""
    if not _archive_allowed(ctx):
        raise HTTPException(status_code=429, detail="search_rate_limited")
    years = repo.archive_years(ctx.db)
    return render(
        ctx,
        "archive.html",
        years=years,
        total=sum(count for _year, count in years),
    )


@router.get("/archives/{year}", name="archive_year")
def archive_year(
    request: Request,
    ctx: Annotated[PageContext, Depends(get_page_context)],
    year: int,
):
    """One archive year, reusing the listing layout."""
    if not _archive_allowed(ctx):
        raise HTTPException(status_code=429, detail="search_rate_limited")
    if year < 2000 or year > 2100:
        raise HTTPException(status_code=404, detail="archive_not_found")
    start, end = repo.date_bounds_for_year(year)
    count = repo.count_by_year(ctx.db, year)
    if count == 0:
        raise HTTPException(status_code=404, detail="archive_not_found")

    filters, state = parse_filters(ctx)
    filters = AnnouncementFilters(
        q=filters.q,
        type=filters.type,
        wilaya_code=filters.wilaya_code,
        sector_slug=filters.sector_slug,
        issuer_slug=filters.issuer_slug,
        date_from=start,
        date_to=end,
        sort=filters.sort if filters.sort != "relevance" else "recent",
        page=filters.page,
        per_page=filters.per_page,
    )
    result = search_announcements(ctx.db, filters, per_page=filters.per_page)
    return render(
        ctx,
        "list.html",
        result=result,
        filters=filters,
        state=state,
        options=_filter_options(ctx.db),
        views=_views(ctx, result.items),
        heading=f"أرشيف سنة {year}",
        intro=f"كل الإعلانات المنشورة خلال سنة {year} ({count} إعلاناً).",
        archive_year=year,
        show_archive_link=False,
    )


# ---------------------------------------------------------------------------
# Subcontracting
# ---------------------------------------------------------------------------
@router.get("/sous-traitance", name="subcontracting")
def subcontracting_list(
    request: Request, ctx: Annotated[PageContext, Depends(get_page_context)]
):
    """Published subcontracting offers with sector/wilaya filters."""
    params = request.query_params
    sector = (params.get("sector") or "").strip()
    if sector and sector not in {s.slug for s in repo.active_sectors(ctx.db)}:
        sector = ""
    wilaya = (params.get("wilaya") or "").strip()
    if wilaya:
        active = repo.active_wilayas(ctx.db)
        matched = next(
            (w for w in active if w.code == wilaya.zfill(2) or w.slug == wilaya), None
        )
        wilaya = matched.code if matched else ""

    page = max(1, _int(params.get("page"), 1))
    result = repo.list_offers(
        ctx.db,
        page=page,
        per_page=DEFAULT_PER_PAGE,
        sector_slug=sector,
        wilaya_code=wilaya,
    )
    offers = [build_offer_view(ctx.entitlements, offer) for offer in result.items]
    return render(
        ctx,
        "subcontracting.html",
        result=result,
        offers=offers,
        options=_filter_options(ctx.db),
        selected={"sector": sector, "wilaya": wilaya},
    )


@router.get("/sous-traitance/{offer_id}", name="subcontracting_detail")
@router.get("/sous-traitance/{offer_id}/{slug}", name="subcontracting_detail_slug")
def subcontracting_detail(
    request: Request,
    ctx: Annotated[PageContext, Depends(get_page_context)],
    offer_id: int,
    slug: str | None = None,
):
    """Subcontracting offer detail; contact details require a paid plan."""
    offer = repo.published_offer(ctx.db, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="offer_not_found")
    if slug != offer.slug:
        target = f"/sous-traitance/{offer.id}/{quote(offer.slug, safe='')}"
        return RedirectResponse(target, status_code=301)
    view = build_offer_view(ctx.entitlements, offer)
    return render(ctx, "subcontracting_detail.html", view=view, offer=offer)


# ---------------------------------------------------------------------------
# Pricing and static pages
# ---------------------------------------------------------------------------
@router.get("/tarifs", name="pricing")
def pricing(request: Request, ctx: Annotated[PageContext, Depends(get_page_context)]):
    """Display the plans; subscription purchase arrives in Phase 2."""
    plans = repo.active_plans(ctx.db)
    return render(ctx, "pricing.html", plans=plans)


PAGES: dict[str, dict] = {
    "contact": {
        "title": "اتصل بنا",
        "description": "طرق التواصل مع فريق منصة مناقصات الجزائر.",
        "intro": "نستقبل أسئلتكم حول الاشتراكات، جودة المعطيات، أو الإعلان على المنصة.",
        "sections": [
            {
                "heading": "البريد الإلكتروني",
                "paragraphs": [
                    "للاستفسارات العامة: {email}",
                    "للاشتراكات والفواتير: {email}",
                ],
            },
            {
                "heading": "الهاتف",
                "paragraphs": [
                    "الهاتف: {phone}",
                    "أوقات العمل: من الأحد إلى الخميس، 08:30 – 16:30 (توقيت الجزائر).",
                ],
            },
            {
                "heading": "العنوان",
                "paragraphs": [
                    "قسنطينة، الجزائر.",
                    "العنوان البريدي الكامل: يُضاف عند تأكيد المعلومات القانونية.",
                ],
            },
        ],
    },
    "conditions-utilisation": {
        "title": "شروط الاستخدام",
        "description": "شروط استعمال منصة مناقصات الجزائر.",
        "intro": "مسودة أولية للمراجعة القانونية — لا تُعد نصاً قانونياً نهائياً.",
        "sections": [
            {
                "heading": "طبيعة الخدمة",
                "paragraphs": [
                    "المنصة تجمع وتنشر إعلانات المناقصات والاستشارات العمومية لأغراض إعلامية.",
                    "المصدر الرسمي يبقى الجهة صاحبة الإعلان، ولا تُعد المنصة طرفاً في أي إجراء تعاقدي.",  # noqa: E501
                ],
            },
            {
                "heading": "الاشتراكات",
                "paragraphs": [
                    "يُمنح الاشتراك بعد التحقق من الدفع، ولمدة محددة حسب الصيغة المختارة.",
                    "لا يُسمح بمشاركة الحساب أو إعادة نشر المعطيات المدفوعة دون إذن كتابي.",
                ],
            },
            {
                "heading": "المسؤولية",
                "paragraphs": [
                    "تبذل المنصة جهداً معقولاً لضمان دقة المعطيات، دون ضمان خلوها من الأخطاء.",
                    "يجب على المستخدم التحقق من الإعلان الأصلي قبل أي مشاركة.",
                ],
            },
        ],
    },
    "confidentialite": {
        "title": "سياسة الخصوصية",
        "description": "كيف نعالج معطياتكم الشخصية.",
        "intro": "مسودة أولية للمراجعة القانونية وفق القانون 18-07 المتعلق بحماية الأشخاص الطبيعيين.",  # noqa: E501
        "sections": [
            {
                "heading": "المعطيات المجمعة",
                "paragraphs": [
                    "اسم المؤسسة، رقم الهاتف، البريد الإلكتروني، القطاعات المختارة، وسجل المدفوعات.",  # noqa: E501
                    "لا نجمع معطيات أكثر من اللازم لتقديم الخدمة.",
                ],
            },
            {
                "heading": "الاستخدام والمشاركة",
                "paragraphs": [
                    "تُستخدم المعطيات لإدارة الحساب والاشتراك وإرسال التنبيهات المطلوبة.",
                    "لا تُبيع المنصة المعطيات الشخصية لأطراف ثالثة.",
                ],
            },
            {
                "heading": "الحقوق",
                "paragraphs": [
                    "يمكنكم طلب الاطلاع أو التصحيح أو الحذف عبر قنوات الاتصال المعلنة.",
                    "تُحفظ سجلات الدفع للمدة التي يفرضها القانون.",
                ],
            },
        ],
    },
    "cookies": {
        "title": "ملفات تعريف الارتباط",
        "description": "ملفات تعريف الارتباط المستعملة على المنصة.",
        "intro": "نستعمل عدداً محدوداً من الملفات الضرورية لتشغيل الموقع.",
        "sections": [
            {
                "heading": "ملفات ضرورية",
                "paragraphs": [
                    "ملف الجلسة «dz_session» للحفاظ على تسجيل الدخول، وملف «dz_csrf» لحماية النماذج.",  # noqa: E501
                    "هذان الملفان ضروريان ولا يمكن تعطيلهما دون تعطيل الوظائف الأساسية.",
                ],
            },
            {
                "heading": "ملف المظهر",
                "paragraphs": [
                    "نحفظ اختيار المظهر (فاتح/داكن) محلياً في المتصفح عبر localStorage، ولا يُرسل إلى الخادم.",  # noqa: E501
                ],
            },
            {
                "heading": "ما لا نستعمله",
                "paragraphs": [
                    "لا نستعمل حالياً ملفات تتبع إعلانية أو أدوات تحليل طرف ثالث.",
                    "أي إضافة مستقبلية ستُعلن هنا قبل تفعيلها.",
                ],
            },
        ],
    },
}


def _archive_allowed(ctx: PageContext) -> bool:
    """Throttle archive browsing: every page is a full historical scan."""
    settings = ctx.settings
    ip = client_ip(ctx.request, trust_proxy=settings.trust_proxy) or "unknown"
    limiter = RateLimiter(ctx.db)
    return limiter.hit(
        "archive_ip",
        ip,
        limit=settings.search_rate_limit,
        window_minutes=settings.rate_limit_window_minutes,
    )


def _search_allowed(ctx: PageContext) -> bool:
    """Throttle keyword searches per client IP (empty queries are free)."""
    settings = ctx.settings
    ip = client_ip(ctx.request, trust_proxy=settings.trust_proxy) or "unknown"
    limiter = RateLimiter(ctx.db)
    return limiter.hit(
        "search_ip",
        ip,
        limit=settings.search_rate_limit,
        window_minutes=settings.rate_limit_window_minutes,
    )


def _contact_page(
    ctx: PageContext,
    *,
    values: dict[str, str] | None = None,
    error: str = "",
    success: bool = False,
    status_code: int = 200,
):
    """Render the contact page with the message form."""
    page = PAGES["contact"]
    response = render(
        ctx,
        "page.html",
        page=page,
        page_title=page["title"],
        page_description=page["description"],
        contact_email=ctx.settings.contact_email,
        contact_phone=ctx.settings.contact_phone or "يُضاف عند تأكيد الرقم",
        form_values=values or {},
        form_error=error,
        form_success=success,
    )
    response.status_code = status_code
    return response


@router.get("/contact", name="contact")
def contact(request: Request, ctx: Annotated[PageContext, Depends(get_page_context)]):
    """Contact page with a throttled, CSRF-protected message form."""
    return _contact_page(ctx)


@router.post("/contact", name="contact_submit")
async def contact_submit(
    request: Request, ctx: Annotated[PageContext, Depends(get_page_context)]
):
    """Validate and store a contact message (never sends email directly)."""
    form = await request.form()
    values = {
        "name": str(form.get("name") or "").strip(),
        "email": str(form.get("email") or "").strip(),
        "phone": str(form.get("phone") or "").strip(),
        "subject": str(form.get("subject") or "").strip(),
        "message": str(form.get("message") or "").strip(),
    }

    # Honeypot: bots fill hidden fields, humans never see them.
    if str(form.get("website") or "").strip():
        return _contact_page(ctx, success=True)

    if not verify_csrf(request, form):
        return _contact_page(
            ctx,
            values=values,
            error="انتهت صلاحية النموذج. أعد تحميل الصفحة وحاول مجدداً.",
            status_code=400,
        )

    settings = ctx.settings
    ip = client_ip(request, trust_proxy=settings.trust_proxy) or "unknown"
    limiter = RateLimiter(ctx.db)
    allowed = limiter.hit(
        "contact_ip",
        ip,
        limit=settings.contact_rate_limit,
        window_minutes=settings.contact_rate_window_minutes,
    )
    if not allowed:
        return _contact_page(
            ctx,
            values=values,
            error="تم بلوغ حدّ الرسائل المسموح. الرجاء المحاولة لاحقاً.",
            status_code=429,
        )

    error = _validate_contact(values)
    if error:
        return _contact_page(ctx, values=values, error=error, status_code=400)

    phone = normalize_phone(values["phone"]) if values["phone"] else ""
    ctx.db.add(
        ContactMessage(
            name=values["name"],
            email=values["email"],
            phone=phone or "",
            subject=values["subject"],
            message=values["message"],
            ip_hash=hash_ip(ip),
        )
    )
    ctx.db.commit()
    return _contact_page(ctx, success=True)


def _validate_contact(values: dict[str, str]) -> str:
    """Return an Arabic error message, or an empty string when valid."""
    if not 2 <= len(values["name"]) <= 120:
        return "الاسم يجب أن يتراوح بين حرفين و120 حرفاً."
    email = values["email"]
    if "@" not in email or "." not in email.split("@")[-1] or len(email) > 254:
        return "البريد الإلكتروني غير صالح."
    if values["phone"] and normalize_phone(values["phone"]) is None:
        return "رقم الهاتف غير صالح. مثال: 0555 12 34 56"
    if len(values["subject"]) > 160:
        return "الموضوع طويل جداً (160 حرفاً كحد أقصى)."
    if not 10 <= len(values["message"]) <= 4000:
        return "الرسالة يجب أن تتراوح بين 10 و4000 حرف."
    return ""


def _legal_page(slug: str):
    page = PAGES[slug]

    def handler(
        request: Request, ctx: Annotated[PageContext, Depends(get_page_context)]
    ):
        return render(
            ctx,
            "page.html",
            page=page,
            page_title=page["title"],
            page_description=page["description"],
            contact_email=ctx.settings.contact_email,
            contact_phone=ctx.settings.contact_phone or "—",
        )

    return handler


for _slug in ("conditions-utilisation", "confidentialite", "cookies"):
    router.add_api_route(f"/{_slug}", _legal_page(_slug), methods=["GET"], name=_slug)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _structured_data(announcement: Announcement, canonical_url: str) -> dict:
    """Schema.org WebPage + BreadcrumbList; never includes gated fields."""
    public_summary = truncate_words(announcement.title_ar, 150)
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "name": announcement.title_ar,
                "description": public_summary,
                "inLanguage": "ar",
                "url": canonical_url,
                "datePublished": announcement.publish_date.isoformat(),
                "isPartOf": {"@type": "WebSite", "name": SITE_NAME_AR},
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": "الرئيسية",
                        "item": "/",
                    },
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": "الإعلانات",
                        "item": "/annonces",
                    },
                    {
                        "@type": "ListItem",
                        "position": 3,
                        "name": announcement.title_ar,
                        "item": canonical_url,
                    },
                ],
            },
        ],
    }
