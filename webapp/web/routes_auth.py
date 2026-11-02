"""Login/logout (registration and OTP arrive in Phase 2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from webapp.models import User
from webapp.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    RateLimiter,
    client_ip,
    create_session,
    delete_session,
    new_token,
    normalize_phone,
    verify_password,
)
from webapp.timeutils import utcnow
from webapp.web.deps import (
    PageContext,
    get_db,
    get_page_context,
    safe_next_url,
    verify_csrf,
)
from webapp.web.templating import render

router = APIRouter()

GENERIC_LOGIN_ERROR = "رقم الهاتف أو كلمة المرور غير صحيحة."
RATE_LIMIT_ERROR = "محاولات كثيرة. الرجاء المحاولة بعد بضع دقائق."


def _set_session_cookie(
    response: Response, token: str, *, secure: bool, ttl_hours: int
) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=ttl_hours * 3600,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _login_page(
    ctx: PageContext,
    *,
    error: str = "",
    phone: str = "",
    next_url: str = "/",
    status_code: int = 200,
):
    """Render the login form with an optional error and HTTP status."""
    response = render(
        ctx,
        "login.html",
        error=error,
        phone=phone,
        next_url=next_url,
        page_title="تسجيل الدخول",
        page_description="الدخول إلى حساب المشترك للاطلاع على تفاصيل المناقصات.",
    )
    response.status_code = status_code
    return response


@router.get("/connexion", name="login")
def login_form(
    request: Request,
    ctx: Annotated[PageContext, Depends(get_page_context)],
    next: str = "",
):
    """Render the login form (already-authenticated users go home)."""
    target = safe_next_url(next)
    if ctx.user is not None:
        return RedirectResponse(target, status_code=303)
    return _login_page(ctx, next_url=target)


@router.post("/connexion", name="login_submit")
async def login_submit(
    request: Request,
    ctx: Annotated[PageContext, Depends(get_page_context)],
    db: Annotated[Session, Depends(get_db)],
):
    """Authenticate by phone + password with CSRF and rate limiting."""
    form = await request.form()
    next_url = safe_next_url(str(form.get("next") or "/"))
    phone_raw = str(form.get("phone") or "").strip()
    password = str(form.get("password") or "")

    if not verify_csrf(request, form):
        return _login_page(
            ctx,
            error="انتهت صلاحية النموذج. أعد تحميل الصفحة وحاول مجدداً.",
            phone=phone_raw,
            next_url=next_url,
            status_code=400,
        )

    phone = normalize_phone(phone_raw)
    if phone is None:
        return _login_page(
            ctx,
            error="رقم الهاتف غير صالح. مثال: 0555 12 34 56",
            phone=phone_raw,
            next_url=next_url,
        )

    settings = ctx.settings
    limiter = RateLimiter(db)
    ip = client_ip(request, trust_proxy=settings.trust_proxy) or "unknown"
    window = settings.rate_limit_window_minutes

    ip_allowed = limiter.hit(
        "login_ip", ip, limit=settings.ip_rate_limit, window_minutes=window
    )
    phone_allowed = limiter.hit(
        "login_phone",
        phone,
        limit=settings.login_rate_limit,
        window_minutes=window,
    )
    if not ip_allowed or not phone_allowed:
        return _login_page(
            ctx,
            error=RATE_LIMIT_ERROR,
            phone=phone_raw,
            next_url=next_url,
            status_code=429,
        )

    user = db.scalar(select(User).where(User.phone == phone))
    password_ok = verify_password(password, user.password_hash if user else None)
    if user is None or not password_ok:
        return _login_page(
            ctx,
            error=GENERIC_LOGIN_ERROR,
            phone=phone_raw,
            next_url=next_url,
        )
    if not user.is_active:
        # Correct password, but the phone was never verified: resume the OTP
        # flow instead of pretending the credentials are wrong.
        response = RedirectResponse("/inscription/verifier", status_code=303)
        response.set_cookie(
            "dz_pending_phone",
            user.phone,
            max_age=30 * 60,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
            path="/inscription",
        )
        return response

    limiter.clear("login_phone", phone)
    old_token = request.cookies.get(SESSION_COOKIE)
    if old_token:
        delete_session(db, old_token)

    token = create_session(
        db,
        user,
        ttl_hours=settings.session_ttl_hours,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    user.last_login_at = utcnow()
    db.commit()

    response = RedirectResponse(next_url, status_code=303)
    _set_session_cookie(
        response,
        token,
        secure=settings.secure_cookies,
        ttl_hours=settings.session_ttl_hours,
    )
    response.set_cookie(
        CSRF_COOKIE,
        new_token(24),
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/deconnexion", name="logout")
async def logout(
    request: Request,
    ctx: Annotated[PageContext, Depends(get_page_context)],
    db: Annotated[Session, Depends(get_db)],
):
    """Revoke the server-side session (POST + CSRF only)."""
    form = await request.form()
    if not verify_csrf(request, form):
        return Response(
            "طلب غير صالح.", status_code=400, media_type="text/plain; charset=utf-8"
        )
    delete_session(db, request.cookies.get(SESSION_COOKIE))
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return response


__all__ = ["router"]
