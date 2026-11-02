"""Account lifecycle: registration, phone OTP, email verification, reset.

Rules enforced here (not only in the HTML forms):

* one account per phone and per email, phone normalised to ``+213…``;
* passwords follow :func:`webapp.security.validate_password`;
* a new account stays inactive until the phone OTP is verified;
* OTPs are hashed, expire after ``APP_OTP_TTL_MINUTES`` and are invalidated
  after ``APP_OTP_MAX_ATTEMPTS`` wrong tries;
* email verification links are single-use and expire;
* password reset is phone + OTP, then every existing session is revoked.

Nothing here sends messages: callers pass the raw token/code to the configured
SMS or email provider so tests can inspect the console outbox.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from webapp.enums import AlertFrequency, TokenPurpose
from webapp.models import (
    Alert,
    OneTimeToken,
    Sector,
    User,
    UserSector,
    UserSession,
    Wilaya,
)
from webapp.security import (
    constant_time_equals,
    hash_password,
    new_token,
    normalize_phone,
    token_hash,
    validate_password,
)
from webapp.timeutils import utcnow

#: Digits in a phone OTP.
OTP_DIGITS = 6

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


class AccountError(Exception):
    """A user-facing validation error with an Arabic message."""

    def __init__(self, message: str, *, field: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.field = field


class TokenError(Exception):
    """An OTP or link failure; ``reason`` is a stable identifier."""

    MESSAGES = {
        "invalid": "الرمز غير صحيح. تحقق منه وحاول مجدداً.",
        "expired": "انتهت صلاحية الرمز. اطلب رمزاً جديداً.",
        "too_many": "تجاوزت عدد المحاولات المسموح. اطلب رمزاً جديداً.",
        "used": "استُعمل هذا الرابط من قبل.",
    }

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.message = self.MESSAGES.get(reason, self.MESSAGES["invalid"])


def normalize_email(value: str) -> str | None:
    """Return a lower-cased valid email address, or ``None``."""
    email = (value or "").strip().lower()
    if len(email) > 254 or not _EMAIL_RE.match(email):
        return None
    return email


def _generate_otp() -> str:
    """Uniform 6-digit code (``secrets`` avoids modulo bias pitfalls)."""
    return f"{secrets.randbelow(10**OTP_DIGITS):0{OTP_DIGITS}d}"


def latest_otp_age_seconds(
    db: Session, user: User, *, now: datetime | None = None
) -> int | None:
    """Seconds since the last OTP was issued, or ``None`` when never sent."""
    token = db.scalar(
        select(OneTimeToken)
        .where(
            OneTimeToken.user_id == user.id,
            OneTimeToken.purpose == TokenPurpose.PHONE_OTP,
        )
        .order_by(OneTimeToken.id.desc())
    )
    if token is None or token.sent_at is None:
        return None
    return int(((now or utcnow()) - token.sent_at).total_seconds())


def issue_otp(
    db: Session,
    user: User,
    *,
    ttl_minutes: int = 10,
    destination: str | None = None,
    now: datetime | None = None,
) -> str:
    """Invalidate previous OTPs, create a new one and return the raw code."""
    moment = now or utcnow()
    db.execute(
        delete(OneTimeToken).where(
            OneTimeToken.user_id == user.id,
            OneTimeToken.purpose == TokenPurpose.PHONE_OTP,
            OneTimeToken.used_at.is_(None),
        )
    )
    code = _generate_otp()
    db.add(
        OneTimeToken(
            user_id=user.id,
            token_hash=token_hash(code),
            purpose=TokenPurpose.PHONE_OTP,
            destination=destination or user.phone,
            expires_at=moment + timedelta(minutes=ttl_minutes),
            sent_at=moment,
            attempts=0,
        )
    )
    db.commit()
    return code


def _latest_otp(db: Session, user: User) -> OneTimeToken | None:
    return db.scalar(
        select(OneTimeToken)
        .where(
            OneTimeToken.user_id == user.id,
            OneTimeToken.purpose == TokenPurpose.PHONE_OTP,
            OneTimeToken.used_at.is_(None),
        )
        .order_by(OneTimeToken.id.desc())
    )


def verify_otp(
    db: Session,
    user: User,
    code: str,
    *,
    max_attempts: int = 5,
    now: datetime | None = None,
) -> None:
    """Validate a phone OTP, counting attempts and expiring after the limit.

    Raises:
        TokenError: ``invalid``, ``expired`` or ``too_many``.
    """
    moment = now or utcnow()
    token = _latest_otp(db, user)
    if token is None:
        raise TokenError("invalid")
    if token.expires_at <= moment:
        token.used_at = moment
        db.commit()
        raise TokenError("expired")

    token.attempts = int(token.attempts or 0) + 1
    if token.attempts > max_attempts:
        token.used_at = moment
        db.commit()
        raise TokenError("too_many")
    db.commit()

    if not constant_time_equals(token.token_hash, token_hash((code or "").strip())):
        raise TokenError("invalid")

    token.used_at = moment
    db.commit()


def activate_user(db: Session, user: User, *, now: datetime | None = None) -> None:
    """Mark the phone as verified and enable the account."""
    user.phone_verified_at = now or utcnow()
    user.is_active = True
    db.commit()


def issue_email_token(
    db: Session, user: User, *, ttl_hours: int = 48, now: datetime | None = None
) -> str:
    """Create a single-use email-verification token and return the raw value."""
    moment = now or utcnow()
    db.execute(
        delete(OneTimeToken).where(
            OneTimeToken.user_id == user.id,
            OneTimeToken.purpose == TokenPurpose.VERIFY_EMAIL,
            OneTimeToken.used_at.is_(None),
        )
    )
    raw = new_token(32)
    db.add(
        OneTimeToken(
            user_id=user.id,
            token_hash=token_hash(raw),
            purpose=TokenPurpose.VERIFY_EMAIL,
            destination=user.email,
            expires_at=moment + timedelta(hours=ttl_hours),
            sent_at=moment,
            attempts=0,
        )
    )
    db.commit()
    return raw


def verify_email_token(db: Session, raw: str, *, now: datetime | None = None) -> User:
    """Consume an email-verification token and mark the email verified."""
    moment = now or utcnow()
    token = db.scalar(
        select(OneTimeToken)
        .options(selectinload(OneTimeToken.user))
        .where(
            OneTimeToken.token_hash == token_hash((raw or "").strip()),
            OneTimeToken.purpose == TokenPurpose.VERIFY_EMAIL,
        )
    )
    if token is None:
        raise TokenError("invalid")
    if token.used_at is not None:
        raise TokenError("used")
    if token.expires_at <= moment:
        raise TokenError("expired")
    token.used_at = moment
    token.user.email_verified_at = moment
    db.commit()
    return token.user


def _sector_objects(db: Session, sector_ids: list[int]) -> list[Sector]:
    if not sector_ids:
        return []
    return list(
        db.scalars(
            select(Sector).where(Sector.id.in_(sector_ids), Sector.is_active.is_(True))
        ).all()
    )


def register_user(
    db: Session,
    *,
    company_name: str,
    phone: str,
    email: str,
    password: str,
    password_confirm: str,
    sector_ids: list[int],
) -> User:
    """Create an inactive account pending phone verification.

    Raises:
        AccountError: With a field name and an Arabic message.
    """
    company = (company_name or "").strip()
    if not 2 <= len(company) <= 200:
        raise AccountError(
            "اسم المؤسسة يجب أن يتراوح بين حرفين و200 حرف.", field="company"
        )

    normalized_phone = normalize_phone(phone)
    if normalized_phone is None:
        raise AccountError("رقم الهاتف غير صالح. مثال: 0555 12 34 56", field="phone")
    if db.scalar(select(User).where(User.phone == normalized_phone)) is not None:
        raise AccountError(
            "رقم الهاتف مستعمل بالفعل. سجّل الدخول أو استعمل رقماً آخر.", field="phone"
        )

    normalized_email = normalize_email(email)
    if normalized_email is None:
        raise AccountError("البريد الإلكتروني غير صالح.", field="email")
    if db.scalar(select(User).where(User.email == normalized_email)) is not None:
        raise AccountError("البريد الإلكتروني مستعمل بالفعل.", field="email")

    if password != password_confirm:
        raise AccountError("كلمتا المرور غير متطابقتين.", field="password")
    password_error = validate_password(password)
    if password_error:
        raise AccountError(password_error, field="password")

    sectors = _sector_objects(db, sector_ids)
    if not sectors:
        raise AccountError("اختر قطاعاً واحداً على الأقل.", field="sectors")

    user = User(
        phone=normalized_phone,
        email=normalized_email,
        company_name=company,
        password_hash=hash_password(password),
        is_active=False,
        locale="ar",
    )
    db.add(user)
    db.flush()
    db.add_all([UserSector(user_id=user.id, sector_id=sector.id) for sector in sectors])
    db.commit()
    db.refresh(user)
    return user


def request_password_reset(db: Session, phone: str) -> User | None:
    """Return the matching user, without revealing whether it exists."""
    normalized = normalize_phone(phone)
    if normalized is None:
        return None
    return db.scalar(
        select(User).where(User.phone == normalized, User.is_active.is_(True))
    )


def reset_password_with_otp(
    db: Session,
    user: User,
    code: str,
    new_password: str,
    *,
    max_attempts: int = 5,
    now: datetime | None = None,
) -> None:
    """Verify the OTP, replace the password and revoke every session."""
    error = validate_password(new_password)
    if error:
        raise AccountError(error, field="password")
    verify_otp(db, user, code, max_attempts=max_attempts, now=now)
    user.password_hash = hash_password(new_password)
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.commit()


def get_or_create_alert(db: Session, user: User) -> Alert:
    """Return the user's alert row, creating a daily default when missing."""
    alert = db.scalar(select(Alert).where(Alert.user_id == user.id).order_by(Alert.id))
    if alert is not None:
        return alert
    alert = Alert(
        user_id=user.id,
        name="تنبيهي اليومي",
        frequency=AlertFrequency.DAILY,
        is_active=True,
        unsubscribe_token=new_token(24),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def update_alert(
    db: Session,
    alert: Alert,
    *,
    frequency: AlertFrequency,
    sector_ids: list[int],
    wilaya_ids: list[int],
    is_active: bool,
) -> Alert:
    """Replace an alert's frequency and watched taxonomy."""
    alert.frequency = frequency
    alert.is_active = is_active
    alert.sectors = _sector_objects(db, sector_ids)
    alert.wilayas = (
        list(db.scalars(select(Wilaya).where(Wilaya.id.in_(wilaya_ids))).all())
        if wilaya_ids
        else []
    )
    db.commit()
    db.refresh(alert)
    return alert


def update_user_sectors(db: Session, user: User, sector_ids: list[int]) -> int:
    """Replace the interest sectors saved at registration."""
    sectors = _sector_objects(db, sector_ids)
    db.execute(delete(UserSector).where(UserSector.user_id == user.id))
    db.add_all([UserSector(user_id=user.id, sector_id=sector.id) for sector in sectors])
    db.commit()
    user.sectors = sectors
    return len(sectors)


__all__ = [
    "AccountError",
    "OTP_DIGITS",
    "TokenError",
    "activate_user",
    "get_or_create_alert",
    "issue_email_token",
    "issue_otp",
    "latest_otp_age_seconds",
    "normalize_email",
    "register_user",
    "request_password_reset",
    "reset_password_with_otp",
    "update_alert",
    "update_user_sectors",
    "verify_email_token",
    "verify_otp",
]
