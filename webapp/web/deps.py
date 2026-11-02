"""Request dependencies: DB session, current user, entitlements, CSRF."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from webapp.config import Settings
from webapp.entitlements import Entitlements, resolve_entitlements
from webapp.models import User
from webapp.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    constant_time_equals,
    find_session,
    new_token,
    same_origin,
)


def get_db(request: Request) -> Iterator[Session]:
    """Yield a request-scoped session from the app's factory."""
    factory = request.app.state.sessionmaker
    session: Session = factory()
    try:
        yield session
    finally:
        session.close()


def get_settings(request: Request) -> Settings:
    """Return the settings attached to the app."""
    return request.app.state.settings


@dataclass
class PageContext:
    """Everything a template needs about the current visitor."""

    request: Request
    db: Session
    settings: Settings
    user: User | None
    entitlements: Entitlements
    csrf_token: str
    canonical_url: str


def resolve_locale(request: Request) -> str:
    """Arabic is the default; French is reserved for Phase 6."""
    return "ar"


def get_page_context(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PageContext:
    """Resolve session → user → entitlements once per request."""
    raw_token = request.cookies.get(SESSION_COOKIE)
    session_row = find_session(db, raw_token)
    user = db.get(User, session_row.user_id) if session_row else None
    if user is not None and not user.is_active:
        user = None

    entitlements = resolve_entitlements(db, user)
    csrf_token = getattr(request.state, "csrf_token", "") or new_token(24)
    canonical = settings.public_base_url or str(request.base_url).rstrip("/")
    canonical_url = f"{canonical}{request.url.path}"
    return PageContext(
        request=request,
        db=db,
        settings=settings,
        user=user,
        entitlements=entitlements,
        csrf_token=csrf_token,
        canonical_url=canonical_url,
    )


def verify_csrf(request: Request, form) -> bool:
    """Double-submit CSRF token plus Origin/Referer defence in depth."""
    cookie_token = request.cookies.get(CSRF_COOKIE) or getattr(
        request.state, "csrf_token", None
    )
    submitted = form.get("csrf_token")
    if not isinstance(submitted, str):
        return False
    return constant_time_equals(cookie_token, submitted) and same_origin(request)


def client_host(request: Request) -> str | None:
    """Client IP label used by the rate limiter (hashed before storage)."""
    return request.client.host if request.client else None


def safe_next_url(value: str | None) -> str:
    """Accept only local absolute paths as post-login redirects."""
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/"
    if "\\" in value or "\n" in value:
        return "/"
    return value


__all__ = [
    "PageContext",
    "client_host",
    "get_db",
    "get_page_context",
    "get_settings",
    "resolve_locale",
    "safe_next_url",
    "verify_csrf",
]
