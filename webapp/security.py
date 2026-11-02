"""Password, token, phone and rate-limit primitives.

Nothing here depends on FastAPI, which keeps it unit-testable and reusable by
CLI commands and the future worker.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from webapp.models import RateLimitEvent, User, UserSession
from webapp.timeutils import utcnow

#: OWASP-reasonable argon2id parameters (memory 64 MiB, 3 passes).
_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)

#: Dummy hash used to equalise timing for unknown accounts.
_DUMMY_HASH = _hasher.hash("not-a-real-password")

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

_ALGERIAN_MOBILE = re.compile(r"^(?:0)?([5-7]\d{8})$")
_ALGERIAN_LANDLINE = re.compile(r"^(?:0)?([2-4]\d{7})$")
_PHONE_CLEAN = re.compile(r"[\s\-().]")

SESSION_COOKIE = "dz_session"
CSRF_COOKIE = "dz_csrf"


def hash_password(password: str) -> str:
    """Hash a password with argon2id.

    Args:
        password: Raw password (already length-validated by the caller).

    Returns:
        An argon2id encoded hash.
    """
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-time password verification with a dummy hash fallback."""
    target = password_hash or _DUMMY_HASH
    try:
        return _hasher.verify(target, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Whether the stored hash uses outdated parameters."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def validate_password(password: str) -> str | None:
    """Return an Arabic error message when the password is unacceptable."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return "كلمة المرور يجب أن تحتوي على 8 أحرف على الأقل."
    if len(password) > PASSWORD_MAX_LENGTH:
        return "كلمة المرور طويلة جداً."
    if password.strip() != password:
        return "لا يمكن أن تبدأ كلمة المرور أو تنتهي بمسافة."
    return None


def normalize_phone(raw: str) -> str | None:
    """Normalise an Algerian phone number to ``+213XXXXXXXXX``.

    Accepts ``0555 12 34 56``, ``555123456``, ``+213555123456`` and
    ``00213555123456``. Returns ``None`` for anything that is not a plausible
    Algerian mobile/landline number.
    """
    if not raw:
        return None
    cleaned = _PHONE_CLEAN.sub("", str(raw).strip())
    if cleaned.startswith("+213"):
        cleaned = cleaned[4:]
    elif cleaned.startswith("00213"):
        cleaned = cleaned[5:]
    elif cleaned.startswith("213"):
        cleaned = cleaned[3:]
    cleaned = cleaned.lstrip("0") if cleaned.startswith("0") else cleaned

    if len(cleaned) == 9 and _ALGERIAN_MOBILE.match(cleaned):
        return f"+213{cleaned}"
    if len(cleaned) == 8 and _ALGERIAN_LANDLINE.match(f"0{cleaned}"):
        return f"+213{cleaned}"
    return None


def format_phone(phone: str | None) -> str:
    """Format ``+213XXXXXXXXX`` for display (``0X XX XX XX XX``)."""
    if not phone or not phone.startswith("+213"):
        return phone or ""
    national = phone[4:]
    if len(national) == 9:
        return f"0{national[0]} {national[1:3]} {national[3:5]} {national[5:7]} {national[7:9]}"
    return phone


def new_token(nbytes: int = 32) -> str:
    """Return a URL-safe random token."""
    return secrets.token_urlsafe(nbytes)


def token_hash(token: str) -> str:
    """SHA-256 of a token; only hashes are stored server-side."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_ip(ip: str | None) -> str | None:
    """Hash an IP address for privacy-preserving abuse logs."""
    if not ip:
        return None
    return hashlib.sha256(f"dz-tenders|{ip}".encode()).hexdigest()


def constant_time_equals(left: str | None, right: str | None) -> bool:
    """Compare two strings without leaking length/prefix timing."""
    if not left or not right:
        return False
    return hmac.compare_digest(left, right)


def create_session(
    db: Session,
    user: User,
    *,
    ttl_hours: int,
    ip: str | None = None,
    user_agent: str | None = None,
) -> str:
    """Persist a new browser session and return the raw cookie token."""
    raw = new_token(32)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=token_hash(raw),
            expires_at=utcnow() + timedelta(hours=ttl_hours),
            ip_hash=hash_ip(ip),
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    db.commit()
    return raw


def find_session(
    db: Session, raw_token: str | None, *, now: datetime | None = None
) -> UserSession | None:
    """Return a live session row for a raw token, deleting it when expired."""
    if not raw_token:
        return None
    row = db.scalar(
        select(UserSession).where(UserSession.token_hash == token_hash(raw_token))
    )
    if row is None:
        return None
    moment = now or utcnow()
    if row.expires_at <= moment:
        db.delete(row)
        db.commit()
        return None
    return row


def delete_session(db: Session, raw_token: str | None) -> None:
    """Revoke one session by raw token."""
    if not raw_token:
        return
    db.execute(
        delete(UserSession).where(UserSession.token_hash == token_hash(raw_token))
    )
    db.commit()


def delete_user_sessions(db: Session, user_id: int) -> None:
    """Revoke every session of a user (password change, account lock)."""
    db.execute(delete(UserSession).where(UserSession.user_id == user_id))
    db.commit()


class RateLimiter:
    """Database-backed fixed-window limiter shared by all workers."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _key(self, bucket: str, key: str) -> str:
        return hashlib.sha256(f"{bucket}|{key}".encode()).hexdigest()

    def hit(self, bucket: str, key: str, *, limit: int, window_minutes: int) -> bool:
        """Record an attempt and report whether it is allowed.

        Args:
            bucket: Logical action (``login_phone``, ``login_ip``, …).
            key: Identity (phone, IP) — hashed before storage.
            limit: Maximum attempts inside the window.
            window_minutes: Window length in minutes.

        Returns:
            ``True`` when the attempt is within the limit (and is recorded),
            ``False`` when the caller must be throttled.
        """
        now = utcnow()
        window_start = now - timedelta(minutes=window_minutes)
        key_hash = self._key(bucket, key)

        # Opportunistic cleanup keeps the table bounded without a cron job.
        self.db.execute(
            delete(RateLimitEvent).where(
                RateLimitEvent.created_at < now - timedelta(days=2)
            )
        )

        count = self.db.scalar(
            select(func.count(RateLimitEvent.id)).where(
                RateLimitEvent.bucket == bucket,
                RateLimitEvent.key_hash == key_hash,
                RateLimitEvent.created_at >= window_start,
            )
        )
        if (count or 0) >= limit:
            self.db.commit()
            return False

        self.db.add(RateLimitEvent(bucket=bucket, key_hash=key_hash, created_at=now))
        self.db.commit()
        return True

    def clear(self, bucket: str, key: str) -> None:
        """Forget attempts for a key (successful login)."""
        self.db.execute(
            delete(RateLimitEvent).where(
                RateLimitEvent.bucket == bucket,
                RateLimitEvent.key_hash == self._key(bucket, key),
            )
        )
        self.db.commit()


def same_origin(request) -> bool:
    """CSRF defence-in-depth: reject a mismatched Origin/Referer.

    Returns True when neither header is present (older clients); the CSRF token
    remains the primary control in that case.
    """
    host = request.headers.get("host", "")
    for header in ("origin", "referer"):
        value = request.headers.get(header)
        if not value:
            continue
        parsed = urlsplit(value)
        if parsed.netloc and parsed.netloc != host:
            return False
    return True


def client_ip(request, *, trust_proxy: bool = False) -> str | None:
    """Best-effort client IP, honouring ``X-Forwarded-For`` only when trusted."""
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


__all__ = [
    "CSRF_COOKIE",
    "PASSWORD_MIN_LENGTH",
    "RateLimiter",
    "SESSION_COOKIE",
    "client_ip",
    "constant_time_equals",
    "create_session",
    "delete_session",
    "delete_user_sessions",
    "find_session",
    "format_phone",
    "hash_ip",
    "hash_password",
    "needs_rehash",
    "new_token",
    "normalize_phone",
    "same_origin",
    "token_hash",
    "validate_password",
    "verify_password",
]
