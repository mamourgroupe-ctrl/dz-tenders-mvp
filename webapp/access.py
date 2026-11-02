"""Field-level access rules for announcements and subcontracting offers.

Requirement (Phase 1): the free tier exposes only title, type, sector, wilaya
and publication date. Paid tiers unlock issuer, deadline, full description,
source link and attachments, limited to the sectors of the subscription.

Routes build a :class:`AnnouncementView` and pass it to templates; hidden
fields are never placed in the template context, so they cannot leak through a
forgotten ``{% if %}``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from webapp.entitlements import Entitlements
from webapp.enums import AnnouncementType
from webapp.models import Announcement, Attachment, SubcontractingOffer

#: Machine-readable reasons, rendered as Arabic explanations in the template.
REASON_ANONYMOUS = "anonymous"
REASON_FREE_PLAN = "free_plan"
REASON_UNCOVERED_SECTOR = "uncovered_sector"
REASON_AUCTIONS_ONLY = "auctions_only"
REASON_SUBSCRIBED = "subscribed"
REASON_STAFF = "staff"

REASON_MESSAGES_AR: dict[str, str] = {
    REASON_ANONYMOUS: "أنشئ حساباً واشترك للاطلاع على المؤسسة والأجل والوصف الكامل.",
    REASON_FREE_PLAN: "هذه المعلومات متاحة للمشتركين فقط. اطّلع على الصيغ المتاحة.",
    REASON_UNCOVERED_SECTOR: (
        "قطاع هذه المناقصة غير مشمول في اشتراكك. أضف القطاع إلى اشتراكك للاطلاع على التفاصيل."
    ),
    REASON_AUCTIONS_ONLY: "اشتراكك مخصص للمزادات فقط. هذه المناقصة غير مشمولة.",
    REASON_SUBSCRIBED: "",
    REASON_STAFF: "",
}


@dataclass(frozen=True)
class AnnouncementView:
    """An announcement plus the exact fields the current visitor may see."""

    announcement: Announcement
    unlocked: bool
    reason: str
    issuer_name: str | None
    deadline_at: datetime | None
    description_ar: str | None
    description_fr: str | None
    reference: str | None
    source_url: str | None
    source_name: str | None
    estimated_value_dzd: int | None
    attachments: tuple[Attachment, ...]

    @property
    def reason_message(self) -> str:
        """Arabic explanation of a locked view (empty when unlocked)."""
        return REASON_MESSAGES_AR.get(self.reason, "")

    @property
    def show_locked_notice(self) -> bool:
        """Whether the detail page should display the subscription callout."""
        return not self.unlocked


def _locked(announcement: Announcement, reason: str) -> AnnouncementView:
    return AnnouncementView(
        announcement=announcement,
        unlocked=False,
        reason=reason,
        issuer_name=None,
        deadline_at=None,
        description_ar=None,
        description_fr=None,
        reference=None,
        source_url=None,
        source_name=None,
        estimated_value_dzd=None,
        attachments=(),
    )


def build_announcement_view(
    entitlements: Entitlements, announcement: Announcement
) -> AnnouncementView:
    """Return the permitted projection of ``announcement``.

    Args:
        entitlements: Effective rights of the visitor.
        announcement: Published announcement to project.

    Returns:
        A view whose hidden fields are ``None``/empty, never real values.
    """
    if entitlements.is_staff:
        return _unlocked(announcement, REASON_STAFF)

    if not entitlements.is_paid:
        return _locked(
            announcement,
            REASON_ANONYMOUS if not entitlements.is_authenticated else REASON_FREE_PLAN,
        )

    if entitlements.auctions_only and announcement.type != AnnouncementType.AUCTION:
        return _locked(announcement, REASON_AUCTIONS_ONLY)

    sector_ids = [sector.id for sector in announcement.sectors]
    if not entitlements.covers_sector(sector_ids):
        return _locked(announcement, REASON_UNCOVERED_SECTOR)

    return _unlocked(announcement, REASON_SUBSCRIBED)


def _unlocked(announcement: Announcement, reason: str) -> AnnouncementView:
    return AnnouncementView(
        announcement=announcement,
        unlocked=True,
        reason=reason,
        issuer_name=announcement.issuer_name
        or (announcement.issuer.name_ar if announcement.issuer else None),
        deadline_at=announcement.deadline_at,
        description_ar=announcement.description_ar,
        description_fr=announcement.description_fr,
        reference=announcement.reference,
        source_url=announcement.source_url,
        source_name=announcement.source_name,
        estimated_value_dzd=announcement.estimated_value_dzd,
        attachments=tuple(a for a in announcement.attachments if a.is_public),
    )


@dataclass(frozen=True)
class OfferView:
    """A subcontracting offer with contact details gated to paid accounts."""

    offer: SubcontractingOffer
    show_contact: bool
    reason: str


def build_offer_view(
    entitlements: Entitlements, offer: SubcontractingOffer
) -> OfferView:
    """Gate contact details behind an authenticated, non-expired subscription."""
    if entitlements.is_staff or entitlements.is_paid:
        return OfferView(offer=offer, show_contact=True, reason=REASON_SUBSCRIBED)
    return OfferView(
        offer=offer,
        show_contact=False,
        reason=(
            REASON_ANONYMOUS if not entitlements.is_authenticated else REASON_FREE_PLAN
        ),
    )


__all__ = [
    "AnnouncementView",
    "OfferView",
    "REASON_ANONYMOUS",
    "REASON_AUCTIONS_ONLY",
    "REASON_FREE_PLAN",
    "REASON_MESSAGES_AR",
    "REASON_STAFF",
    "REASON_SUBSCRIBED",
    "REASON_UNCOVERED_SECTOR",
    "build_announcement_view",
    "build_offer_view",
]
