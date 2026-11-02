"""Product-domain enumerations shared by models, UI and tests.

Values are stable identifiers stored in the database; Arabic and French
labels are presentation data and may change without a migration.
"""

from enum import StrEnum


class AnnouncementType(StrEnum):
    """The eight announcement kinds the platform publishes."""

    TENDER = "tender"
    CONSULTATION = "consultation"
    PROVISIONAL_AWARD = "provisional_award"
    AUCTION = "auction"
    CANCELLATION = "cancellation"
    DEADLINE_EXTENSION = "deadline_extension"
    NOTICE_OF_DEFAULT = "notice_of_default"
    CONTRACT_TERMINATION = "contract_termination"


class AnnouncementStatus(StrEnum):
    """Editorial lifecycle of an announcement."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    REJECTED = "rejected"


class UserRole(StrEnum):
    """Roles honoured by the admin area (Phase 4)."""

    USER = "user"
    EDITOR = "editor"
    SUPPORT = "support"
    ADMIN = "admin"


class PlanKind(StrEnum):
    """Subscription plan or a one-off add-on."""

    SUBSCRIPTION = "subscription"
    ADDON = "addon"


class BillingPeriod(StrEnum):
    """Billing cadence used by plans and payments."""

    MONTHLY = "monthly"
    ANNUAL = "annual"


class SubscriptionStatus(StrEnum):
    """Lifecycle of a user subscription."""

    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class PaymentStatus(StrEnum):
    """Manual-payment verification state."""

    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class PaymentMethod(StrEnum):
    """Supported offline payment channels."""

    BANK_TRANSFER = "bank_transfer"
    POSTAL_ACCOUNT = "postal_account"
    CASH = "cash"


class SubcontractingStatus(StrEnum):
    """Moderation state of a subcontracting offer."""

    PENDING = "pending"
    PUBLISHED = "published"
    REJECTED = "rejected"
    CLOSED = "closed"


class BannerPlacement(StrEnum):
    """Where an advertising banner may appear."""

    HOME_TOP = "home_top"
    HOME_MIDDLE = "home_middle"
    LIST_SIDEBAR = "list_sidebar"


class TokenPurpose(StrEnum):
    """One-time token purposes."""

    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"


class AlertFrequency(StrEnum):
    """Digest cadence chosen by a subscriber."""

    DAILY = "daily"
    WEEKLY = "weekly"


#: Arabic/French labels for the eight announcement types.
TYPE_LABELS: dict[AnnouncementType, tuple[str, str]] = {
    AnnouncementType.TENDER: ("مناقصة", "Appel d'offres"),
    AnnouncementType.CONSULTATION: ("استشارة", "Avis de consultation"),
    AnnouncementType.PROVISIONAL_AWARD: ("إسناد مؤقت", "Attribution provisoire"),
    AnnouncementType.AUCTION: ("مزاد", "Enchère"),
    AnnouncementType.CANCELLATION: ("إلغاء", "Annulation"),
    AnnouncementType.DEADLINE_EXTENSION: ("تمديد الأجل", "Prorogation de délai"),
    AnnouncementType.NOTICE_OF_DEFAULT: ("إعذار", "Mise en demeure"),
    AnnouncementType.CONTRACT_TERMINATION: ("فسخ العقد", "Résiliation de contrat"),
}

STATUS_LABELS: dict[AnnouncementStatus, tuple[str, str]] = {
    AnnouncementStatus.DRAFT: ("مسودة", "Brouillon"),
    AnnouncementStatus.PENDING_REVIEW: ("بانتظار المراجعة", "En revue"),
    AnnouncementStatus.PUBLISHED: ("منشورة", "Publiée"),
    AnnouncementStatus.ARCHIVED: ("مؤرشفة", "Archivée"),
    AnnouncementStatus.REJECTED: ("مرفوضة", "Rejetée"),
}

PAYMENT_METHOD_LABELS: dict[PaymentMethod, tuple[str, str]] = {
    PaymentMethod.BANK_TRANSFER: ("تحويل بنكي", "Virement bancaire"),
    PaymentMethod.POSTAL_ACCOUNT: ("حساب بريدي (CCP)", "Compte postal (CCP)"),
    PaymentMethod.CASH: ("دفع نقدي", "Paiement en espèces"),
}

PAYMENT_STATUS_LABELS: dict[PaymentStatus, tuple[str, str]] = {
    PaymentStatus.PENDING: ("بانتظار التحقق", "En attente de vérification"),
    PaymentStatus.VERIFIED: ("مؤكد", "Vérifié"),
    PaymentStatus.REJECTED: ("مرفوض", "Rejeté"),
}

SUBSCRIPTION_STATUS_LABELS: dict[SubscriptionStatus, tuple[str, str]] = {
    SubscriptionStatus.PENDING: ("بانتظار التفعيل", "En attente d'activation"),
    SubscriptionStatus.ACTIVE: ("نشط", "Active"),
    SubscriptionStatus.EXPIRED: ("منتهي", "Expirée"),
    SubscriptionStatus.CANCELLED: ("ملغى", "Annulée"),
}

STYLE_BY_TYPE: dict[AnnouncementType, str] = {
    AnnouncementType.TENDER: "tender",
    AnnouncementType.CONSULTATION: "consultation",
    AnnouncementType.PROVISIONAL_AWARD: "award",
    AnnouncementType.AUCTION: "auction",
    AnnouncementType.CANCELLATION: "cancellation",
    AnnouncementType.DEADLINE_EXTENSION: "extension",
    AnnouncementType.NOTICE_OF_DEFAULT: "default",
    AnnouncementType.CONTRACT_TERMINATION: "termination",
}


def type_label(value: AnnouncementType | str, lang: str = "ar") -> str:
    """Return the Arabic (default) or French label of an announcement type."""
    try:
        key = AnnouncementType(value)
    except ValueError:
        return str(value)
    return TYPE_LABELS[key][1 if lang == "fr" else 0]
