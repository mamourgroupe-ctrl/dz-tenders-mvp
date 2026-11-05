"""Time helpers: naive UTC storage, Africa/Algiers display."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

ALGIERS = ZoneInfo("Africa/Algiers")

ARABIC_MONTHS = (
    "جانفي",
    "فيفري",
    "مارس",
    "أفريل",
    "ماي",
    "جوان",
    "جويلية",
    "أوت",
    "سبتمبر",
    "أكتوبر",
    "نوفمبر",
    "ديسمبر",
)

ARABIC_MONTHS_ALT = (
    "يناير",
    "فبراير",
    "مارس",
    "أبريل",
    "مايو",
    "يونيو",
    "يوليو",
    "أغسطس",
    "سبتمبر",
    "أكتوبر",
    "نوفمبر",
    "ديسمبر",
)


def utcnow() -> datetime:
    """Current UTC time as a naive datetime (the storage convention)."""
    return datetime.now(UTC).replace(tzinfo=None)


def as_utc(value: datetime) -> datetime:
    """Normalise an aware/naive datetime to naive UTC."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def to_algiers(value: datetime) -> datetime:
    """Convert a stored naive-UTC datetime to Algiers local time."""
    return value.replace(tzinfo=UTC).astimezone(ALGIERS)


def today_algiers() -> date:
    """Today's date in Algiers (the reference for deadlines)."""
    return datetime.now(ALGIERS).date()


def format_date_ar(value: date | datetime | None, *, with_time: bool = False) -> str:
    """Format a date in Arabic with Western digits, e.g. ``12 أكتوبر 2026``.

    Args:
        value: A date or a stored naive-UTC datetime.
        with_time: Append the Algiers local time.

    Returns:
        A human-readable Arabic string, or an em dash when the value is None.
    """
    if value is None:
        return "—"
    if isinstance(value, datetime):
        local = to_algiers(value)
        day, month, year = local.day, local.month, local.year
        base = f"{day} {ARABIC_MONTHS[month - 1]} {year}"
        return f"{base}، {local:%H:%M}" if with_time else base
    return f"{value.day} {ARABIC_MONTHS[value.month - 1]} {value.year}"


def days_until(deadline: datetime | None, *, now: datetime | None = None) -> int | None:
    """Whole calendar days between today and a deadline (negative when past)."""
    if deadline is None:
        return None
    reference = (now or utcnow()).date()
    return (deadline.date() - reference).days


def deadline_label(deadline: datetime | None, *, now: datetime | None = None) -> str:
    """Arabic relative label for a deadline, e.g. ``باقٍ 3 أيام``."""
    days = days_until(deadline, now=now)
    if days is None:
        return "أجل غير محدد"
    if days < 0:
        return "انتهى الأجل"
    if days == 0:
        return "ينتهي اليوم"
    if days == 1:
        return "باقٍ يوم واحد"
    if days == 2:
        return "باقٍ يومان"
    if days <= 10:
        return f"باقٍ {days} أيام"
    return f"باقٍ {days} يوماً"


def add_months(value: datetime, months: int) -> datetime:
    """Add calendar months without external dependencies."""
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    day = min(value.day, 28)
    return value.replace(year=year, month=month, day=day)


def subscription_end(start: datetime, *, annual: bool) -> datetime:
    """End timestamp for a monthly/annual period starting at ``start``."""
    return add_months(start, 12 if annual else 1)


def is_expiring_soon(
    ends_at: datetime | None, *, days: int = 7, now: datetime | None = None
) -> bool:
    """Whether a subscription ends within ``days`` (renewal reminders)."""
    if ends_at is None:
        return False
    reference = now or utcnow()
    return reference < ends_at <= reference + timedelta(days=days)


def format_datetime_ar(value: datetime | None) -> str:
    """Format a stored UTC datetime in Algiers local time with minutes."""
    return format_date_ar(value, with_time=True)
