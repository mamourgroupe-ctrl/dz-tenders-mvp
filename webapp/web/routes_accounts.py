"""Self-service accounts: registration, OTP, reset, dashboard and billing."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from webapp import accounts, billing
from webapp import repositories as repo
from webapp.enums import (
    AlertFrequency,
    BillingPeriod,
    PaymentMethod,
    PaymentStatus,
    SubscriptionStatus,
    UserRole,
)
from webapp.models import (
    Alert,
    Announcement,
    Payment,
    SavedAnnouncement,
    Sector,
    Subscription,
    User,
    Wilaya,
)
from webapp.notifications import verification_email
from webapp.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    RateLimiter,
    client_ip,
    create_session,
    delete_session,
    new_token,
)
from webapp.sms import SmsMessage, otp_message
from webapp.timeutils import utcnow
from webapp.uploads import UploadError, resolve_stored, store_upload
from webapp.web.deps import (
    PageContext,
    get_db,
    get_page_context,
    safe_next_url,
    verify_csrf,
)
from webapp.web.templating import render

router = APIRouter()

PENDING_PHONE_COOKIE = "dz_pending_phone"
PENDING_TTL_SECONDS = 30 * 60
GENERIC_RATE_ERROR = "محاولات كثيرة. الرجاء المحاولة بعد بضع دقائق."
STAFF_PAYMENT_ROLES = {UserRole.ADMIN, UserRole.SUPPORT}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _login_redirect(request: Request, *, message: str = "") -> RedirectResponse:
    """Send anonymous visitors to the login page, preserving the target."""
    target = quote(request.url.path, safe="")
    suffix = f"&reason={quote(message, safe='')}" if message else ""
    return RedirectResponse(f"/connexion?next={target}{suffix}", status_code=303)


def _set_pending_phone(response: Response, phone: str, *, secure: bool) -> None:
    """Remember the phone being verified for a short while (HttpOnly)."""
    response.set_cookie(
        PENDING_PHONE_COOKIE,
        phone,
        max_age=PENDING_TTL_SECONDS,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _clear_pending_phone(response: Response) -> None:
    """Drop the pending-phone cookie (must use the same path as the setter)."""
    response.delete_cookie(PENDING_PHONE_COOKIE, path="/")


def _pending_user(request: Request, db: Session) -> User | None:
    """Resolve the account currently being phone-verified."""
    phone = request.cookies.get(PENDING_PHONE_COOKIE)
    if not phone:
        return None
    return db.scalar(select(User).where(User.phone == phone))


def _client_ip(ctx: PageContext) -> str:
    return client_ip(ctx.request, trust_proxy=ctx.settings.trust_proxy) or "unknown"


def _limit(
    ctx: PageContext, db: Session, bucket: str, key: str, limit: int, window: int
) -> bool:
    return RateLimiter(db).hit(bucket, key, limit=limit, window_minutes=window)


def _send_otp(request: Request, ctx: PageContext, user: User) -> str:
    """Issue and deliver a phone OTP through the configured provider."""
    code = accounts.issue_otp(
        ctx.db,
        user,
        ttl_minutes=ctx.settings.otp_ttl_minutes,
        destination=user.phone,
    )
    request.app.state.sms_provider.send(
        SmsMessage(
            phone=user.phone,
            text=otp_message(code, ttl_minutes=ctx.settings.otp_ttl_minutes),
        )
    )
    return code


def _send_verification_email(request: Request, ctx: PageContext, user: User) -> str:
    token = accounts.issue_email_token(
        ctx.db, user, ttl_hours=ctx.settings.email_token_ttl_hours
    )
    if user.email:
        request.app.state.email_provider.send(
            verification_email(
                ctx.settings, to=user.email, token=token, company_name=user.company_name
            )
        )
    return token


def _login_session(request: Request, ctx: PageContext, user: User) -> RedirectResponse:
    """Create a session, rotate CSRF and redirect to the dashboard."""
    old_token = request.cookies.get(SESSION_COOKIE)
    if old_token:
        delete_session(ctx.db, old_token)
    token = create_session(
        ctx.db,
        user,
        ttl_hours=ctx.settings.session_ttl_hours,
        ip=_client_ip(ctx),
        user_agent=request.headers.get("user-agent"),
    )
    user.last_login_at = utcnow()
    ctx.db.commit()

    response = RedirectResponse("/tableau-de-bord", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=ctx.settings.session_ttl_hours * 3600,
        httponly=True,
        secure=ctx.settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        new_token(24),
        max_age=ctx.settings.session_ttl_hours * 3600,
        httponly=True,
        secure=ctx.settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    return response


def _sectors(db: Session) -> list[Sector]:
    return repo.active_sectors(db)


def _wilayas(db: Session) -> list[Wilaya]:
    return repo.active_wilayas(db)


def _subscription_for(db: Session, user: User) -> Subscription | None:
    return db.scalar(
        select(Subscription)
        .options(selectinload(Subscription.plan), selectinload(Subscription.sectors))
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.id.desc())
    )


def _payments_for(db: Session, user: User) -> list[Payment]:
    return list(
        db.scalars(
            select(Payment)
            .options(selectinload(Payment.plan))
            .where(Payment.user_id == user.id)
            .order_by(Payment.id.desc())
            .limit(20)
        ).all()
    )


def _saved_for(db: Session, user: User) -> list[Announcement]:
    return list(
        db.scalars(
            select(Announcement)
            .join(
                SavedAnnouncement, SavedAnnouncement.announcement_id == Announcement.id
            )
            .where(SavedAnnouncement.user_id == user.id)
            .order_by(SavedAnnouncement.created_at.desc())
            .limit(30)
        ).all()
    )


# ---------------------------------------------------------------------------
# Registration and phone verification
# ---------------------------------------------------------------------------
@router.get("/inscription", name="register")
def register_form(ctx: Annotated[PageContext, Depends(get_page_context)]):
    """Registration form (company, phone, email, password, sectors)."""
    if ctx.user is not None:
        return RedirectResponse("/tableau-de-bord", status_code=303)
    return render(
        ctx,
        "register.html",
        sectors=_sectors(ctx.db),
        values={},
        error="",
        page_title="إنشاء حساب",
        page_description="إنشاء حساب مشترك في منصة مناقصات الجزائر.",
    )


@router.post("/inscription", name="register_submit")
async def register_submit(
    request: Request,
    ctx: Annotated[PageContext, Depends(get_page_context)],
    db: Annotated[Session, Depends(get_db)],
):
    """Validate the form, create an inactive account and send the OTP."""
    form = await request.form()
    values = {
        "company": str(form.get("company") or "").strip(),
        "phone": str(form.get("phone") or "").strip(),
        "email": str(form.get("email") or "").strip(),
        "sectors": [str(value) for value in form.getlist("sectors")],
    }

    def failure(message: str, status: int = 400):
        return render(
            ctx,
            "register.html",
            sectors=_sectors(db),
            values=values,
            error=message,
            page_title="إنشاء حساب",
            page_description="إنشاء حساب مشترك في منصة مناقصات الجزائر.",
        )

    if not verify_csrf(request, form):
        response = failure("انتهت صلاحية النموذج. أعد تحميل الصفحة وحاول مجدداً.")
        response.status_code = 400
        return response

    if not _limit(ctx, db, "register_ip", _client_ip(ctx), 10, 60):
        response = failure(GENERIC_RATE_ERROR)
        response.status_code = 429
        return response

    if form.get("terms") != "on":
        response = failure("يجب الموافقة على شروط الاستخدام وسياسة الخصوصية.")
        response.status_code = 400
        return response

    sector_ids: list[int] = []
    for raw in values["sectors"]:
        try:
            sector_ids.append(int(raw))
        except ValueError:
            continue

    try:
        user = accounts.register_user(
            db,
            company_name=str(values["company"]),
            phone=str(values["phone"]),
            email=str(values["email"]),
            password=str(form.get("password") or ""),
            password_confirm=str(form.get("password_confirm") or ""),
            sector_ids=sector_ids,
        )
    except accounts.AccountError as exc:
        response = failure(exc.message)
        response.status_code = 400
        return response

    _send_otp(request, ctx, user)
    response = RedirectResponse("/inscription/verifier", status_code=303)
    _set_pending_phone(response, user.phone, secure=ctx.settings.secure_cookies)
    return response


@router.get("/inscription/verifier", name="verify_phone")
def verify_phone_form(
    request: Request, ctx: Annotated[PageContext, Depends(get_page_context)]
):
    """OTP entry page for the account created in this browser."""
    user = _pending_user(request, ctx.db)
    if user is None:
        return RedirectResponse("/inscription", status_code=303)
    if user.phone_verified_at is not None:
        return _login_session(request, ctx, user)
    return render(
        ctx,
        "verify_phone.html",
        phone=user.phone,
        error="",
        notice="",
        page_title="تأكيد رقم الهاتف",
        page_description="إدخال رمز التحقق المرسل إلى هاتفكم.",
    )


@router.post("/inscription/verifier", name="verify_phone_submit")
async def verify_phone_submit(
    request: Request,
    ctx: Annotated[PageContext, Depends(get_page_context)],
    db: Annotated[Session, Depends(get_db)],
):
    """Consume the OTP, activate the account and send the email link."""
    user = _pending_user(request, db)
    if user is None:
        return RedirectResponse("/inscription", status_code=303)

    form = await request.form()
    if not verify_csrf(request, form):
        response = render(
            ctx,
            "verify_phone.html",
            phone=user.phone,
            error="انتهت صلاحية النموذج. أعد تحميل الصفحة.",
            notice="",
            page_title="تأكيد رقم الهاتف",
            page_description="إدخال رمز التحقق المرسل إلى هاتفكم.",
        )
        response.status_code = 400
        return response

    code = str(form.get("code") or "").strip()
    try:
        accounts.verify_otp(
            db,
            user,
            code,
            max_attempts=ctx.settings.otp_max_attempts,
        )
    except accounts.TokenError as exc:
        response = render(
            ctx,
            "verify_phone.html",
            phone=user.phone,
            error=exc.message,
            notice="",
            page_title="تأكيد رقم الهاتف",
            page_description="إدخال رمز التحقق المرسل إلى هاتفكم.",
        )
        response.status_code = 400
        return response

    accounts.activate_user(db, user)
    _send_verification_email(request, ctx, user)
    response = _login_session(request, ctx, user)
    _clear_pending_phone(response)
    return response


@router.post("/inscription/renvoyer", name="resend_otp")
def resend_otp(
    request: Request, ctx: Annotated[PageContext, Depends(get_page_context)]
):
    """Re-send an OTP after the configured cooldown."""
    user = _pending_user(request, ctx.db)
    if user is None:
        return RedirectResponse("/inscription", status_code=303)

    age = accounts.latest_otp_age_seconds(ctx.db, user)
    if age is not None and age < ctx.settings.otp_resend_seconds:
        notice = (
            f"انتظر {ctx.settings.otp_resend_seconds - age} ثانية قبل طلب رمز جديد."
        )
    elif not _limit(
        ctx,
        ctx.db,
        "otp_resend",
        str(user.id),
        5,
        ctx.settings.contact_rate_window_minutes,
    ):
        notice = GENERIC_RATE_ERROR
    else:
        _send_otp(request, ctx, user)
        notice = "أُرسل رمز جديد. تحقق من هاتفك."

    return render(
        ctx,
        "verify_phone.html",
        phone=user.phone,
        error="",
        notice=notice,
        page_title="تأكيد رقم الهاتف",
        page_description="إدخال رمز التحقق المرسل إلى هاتفكم.",
    )


@router.get("/verifier-email", name="verify_email")
def verify_email(
    request: Request,
    ctx: Annotated[PageContext, Depends(get_page_context)],
    token: str = "",
):
    """Consume an email-verification link."""
    try:
        user = accounts.verify_email_token(ctx.db, token)
        message = (
            f"تم تأكيد البريد الإلكتروني لـ {user.email}. يمكنك الآن استقبال التنبيهات."
        )
        success = True
    except accounts.TokenError as exc:
        message = exc.message
        success = False
    return render(
        ctx,
        "message.html",
        heading="تأكيد البريد الإلكتروني",
        message=message,
        success=success,
        page_title="تأكيد البريد الإلكتروني",
        page_description="نتيجة تأكيد البريد الإلكتروني.",
    )


# ---------------------------------------------------------------------------
# Password reset (phone + OTP)
# ---------------------------------------------------------------------------
@router.get("/mot-de-passe-oublie", name="forgot_password")
def forgot_password_form(ctx: Annotated[PageContext, Depends(get_page_context)]):
    """Ask for the phone number registered on the account."""
    return render(
        ctx,
        "forgot_password.html",
        phone="",
        error="",
        notice="",
        page_title="استعادة كلمة المرور",
        page_description="إعادة تعيين كلمة المرور برمز يُرسل إلى هاتفكم.",
    )


@router.post("/mot-de-passe-oublie", name="forgot_password_submit")
async def forgot_password_submit(
    request: Request,
    ctx: Annotated[PageContext, Depends(get_page_context)],
    db: Annotated[Session, Depends(get_db)],
):
    """Send a reset OTP without revealing whether the number exists."""
    form = await request.form()
    phone = str(form.get("phone") or "").strip()
    notice = "إن كان الرقم مسجلاً، فسيصلكم رمز لإعادة التعيين خلال لحظات."

    if not verify_csrf(request, form):
        response = render(
            ctx,
            "forgot_password.html",
            phone=phone,
            error="انتهت صلاحية النموذج. أعد تحميل الصفحة.",
            notice="",
            page_title="استعادة كلمة المرور",
            page_description="إعادة تعيين كلمة المرور برمز يُرسل إلى هاتفكم.",
        )
        response.status_code = 400
        return response

    if not _limit(ctx, db, "forgot_ip", _client_ip(ctx), 5, 60):
        response = render(
            ctx,
            "forgot_password.html",
            phone=phone,
            error=GENERIC_RATE_ERROR,
            notice="",
            page_title="استعادة كلمة المرور",
            page_description="إعادة تعيين كلمة المرور برمز يُرسل إلى هاتفكم.",
        )
        response.status_code = 429
        return response

    user = accounts.request_password_reset(db, phone)
    if user is not None:
        _send_otp(request, ctx, user)
        response = RedirectResponse("/reinitialiser", status_code=303)
        _set_pending_phone(response, user.phone, secure=ctx.settings.secure_cookies)
        return response

    return render(
        ctx,
        "forgot_password.html",
        phone=phone,
        error="",
        notice=notice,
        page_title="استعادة كلمة المرور",
        page_description="إعادة تعيين كلمة المرور برمز يُرسل إلى هاتفكم.",
    )


@router.get("/reinitialiser", name="reset_password")
def reset_password_form(
    request: Request, ctx: Annotated[PageContext, Depends(get_page_context)]
):
    """New-password form for the phone being reset."""
    user = _pending_user(request, ctx.db)
    if user is None:
        return RedirectResponse("/mot-de-passe-oublie", status_code=303)
    return render(
        ctx,
        "reset_password.html",
        phone=user.phone,
        error="",
        page_title="كلمة مرور جديدة",
        page_description="تعيين كلمة مرور جديدة بعد التحقق من رقم الهاتف.",
    )


@router.post("/reinitialiser", name="reset_password_submit")
async def reset_password_submit(
    request: Request,
    ctx: Annotated[PageContext, Depends(get_page_context)],
    db: Annotated[Session, Depends(get_db)],
):
    """Verify the OTP, replace the password and revoke sessions."""
    user = _pending_user(request, db)
    if user is None:
        return RedirectResponse("/mot-de-passe-oublie", status_code=303)

    form = await request.form()

    def failure(message: str, status: int = 400):
        response = render(
            ctx,
            "reset_password.html",
            phone=user.phone,
            error=message,
            page_title="كلمة مرور جديدة",
            page_description="تعيين كلمة مرور جديدة بعد التحقق من رقم الهاتف.",
        )
        response.status_code = status
        return response

    if not verify_csrf(request, form):
        return failure("انتهت صلاحية النموذج. أعد تحميل الصفحة.")

    password = str(form.get("password") or "")
    if password != str(form.get("password_confirm") or ""):
        return failure("كلمتا المرور غير متطابقتين.")

    try:
        accounts.reset_password_with_otp(
            db,
            user,
            str(form.get("code") or ""),
            password,
            max_attempts=ctx.settings.otp_max_attempts,
        )
    except accounts.TokenError as exc:
        return failure(exc.message)
    except accounts.AccountError as exc:
        return failure(exc.message)

    response = RedirectResponse("/connexion?reset=1", status_code=303)
    _clear_pending_phone(response)
    return response


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@router.get("/tableau-de-bord", name="dashboard")
def dashboard(request: Request, ctx: Annotated[PageContext, Depends(get_page_context)]):
    """Subscriber dashboard: subscription, sectors, saves, alerts, payments."""
    user = ctx.user
    if user is None:
        return _login_redirect(request)

    subscription = _subscription_for(ctx.db, user)
    alert = accounts.get_or_create_alert(ctx.db, user)
    days_left = None
    if (
        subscription
        and subscription.status == SubscriptionStatus.ACTIVE
        and subscription.ends_at
    ):
        days_left = max(0, (subscription.ends_at - utcnow()).days)

    return render(
        ctx,
        "dashboard.html",
        subscription=subscription,
        days_left=days_left,
        payments=_payments_for(ctx.db, user),
        saved=_saved_for(ctx.db, user),
        alert=alert,
        interests=list(user.sectors),
        sectors=_sectors(ctx.db),
        wilayas=_wilayas(ctx.db),
        frequencies=list(AlertFrequency),
        notice=request.query_params.get("notice", ""),
        page_title="لوحة التحكم",
        page_description="إدارة الاشتراك والقطاعات والتنبيهات وسجل الدفع.",
    )


@router.post("/tableau-de-bord/alertes", name="update_alert")
async def update_alert(
    request: Request,
    ctx: Annotated[PageContext, Depends(get_page_context)],
    db: Annotated[Session, Depends(get_db)],
):
    """Save alert frequency and watched sectors/wilayas."""
    if ctx.user is None:
        return _login_redirect(request)
    form = await request.form()
    if not verify_csrf(request, form):
        raise HTTPException(status_code=400, detail="invalid_csrf")

    alert = db.scalar(select(Alert).where(Alert.user_id == ctx.user.id))
    if alert is None:
        alert = accounts.get_or_create_alert(db, ctx.user)

    frequency = (
        AlertFrequency.WEEKLY
        if str(form.get("frequency")) == AlertFrequency.WEEKLY.value
        else AlertFrequency.DAILY
    )
    sector_ids = _int_list(form.getlist("sectors"))
    wilaya_ids = _int_list(form.getlist("wilayas"))
    accounts.update_alert(
        db,
        alert,
        frequency=frequency,
        sector_ids=sector_ids,
        wilaya_ids=wilaya_ids,
        is_active=form.get("is_active") == "on",
    )
    return RedirectResponse("/tableau-de-bord?notice=alert", status_code=303)


@router.post("/tableau-de-bord/secteurs", name="update_interests")
async def update_interests(
    request: Request,
    ctx: Annotated[PageContext, Depends(get_page_context)],
    db: Annotated[Session, Depends(get_db)],
):
    """Replace the interest sectors saved at registration."""
    if ctx.user is None:
        return _login_redirect(request)
    form = await request.form()
    if not verify_csrf(request, form):
        raise HTTPException(status_code=400, detail="invalid_csrf")
    accounts.update_user_sectors(db, ctx.user, _int_list(form.getlist("sectors")))
    return RedirectResponse("/tableau-de-bord?notice=sectors", status_code=303)


@router.post("/tableau-de-bord/sauvegardes/{announcement_id}", name="toggle_saved")
def toggle_saved(
    request: Request,
    ctx: Annotated[PageContext, Depends(get_page_context)],
    db: Annotated[Session, Depends(get_db)],
    announcement_id: int,
):
    """Toggle a bookmark; login is required."""
    if ctx.user is None:
        return _login_redirect(request)
    repo.toggle_saved(db, ctx.user.id, announcement_id)
    target = safe_next_url(request.headers.get("referer") or "/tableau-de-bord")
    if target.startswith("http"):
        target = "/tableau-de-bord"
    return RedirectResponse(target, status_code=303)


def _int_list(values) -> list[int]:
    result: list[int] = []
    for value in values:
        try:
            result.append(int(value))
        except (TypeError, ValueError):
            continue
    return result


# ---------------------------------------------------------------------------
# Checkout and proof upload
# ---------------------------------------------------------------------------
@router.get("/abonnement", name="checkout")
def checkout(request: Request, ctx: Annotated[PageContext, Depends(get_page_context)]):
    """Plan/sector/method selection for a signed-in subscriber."""
    if ctx.user is None:
        return _login_redirect(request)
    plan_code = request.query_params.get("plan", "gold")
    plan = billing.get_plan(ctx.db, plan_code) or billing.get_plan(ctx.db, "gold")
    if plan is None:
        raise HTTPException(status_code=404, detail="plan_not_found")

    return render(
        ctx,
        "subscribe.html",
        plans=billing.active_plans(ctx.db),
        plan=plan,
        sectors=_sectors(ctx.db),
        interests=[sector.id for sector in ctx.user.sectors],
        methods=list(PaymentMethod),
        periods=list(BillingPeriod),
        addon_price=billing.addon_price(ctx.db),
        quote=lambda period, count: billing.quote(ctx.db, plan, period, count),
        error=request.query_params.get("error", ""),
        page_title="تفعيل الاشتراك",
        page_description="اختيار الصيغة والقطاعات وطريقة الدفع اليدوي.",
    )


@router.post("/abonnement", name="checkout_submit")
async def checkout_submit(
    request: Request,
    ctx: Annotated[PageContext, Depends(get_page_context)],
    db: Annotated[Session, Depends(get_db)],
):
    """Create a pending subscription and payment."""
    if ctx.user is None:
        return _login_redirect(request)
    form = await request.form()
    if not verify_csrf(request, form):
        raise HTTPException(status_code=400, detail="invalid_csrf")

    plan = billing.get_plan(db, str(form.get("plan") or ""))
    if plan is None:
        raise HTTPException(status_code=404, detail="plan_not_found")

    period = (
        BillingPeriod.ANNUAL
        if str(form.get("period")) == BillingPeriod.ANNUAL.value
        else BillingPeriod.MONTHLY
    )
    try:
        method = PaymentMethod(str(form.get("method") or ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_method") from None

    try:
        _subscription, payment = billing.create_subscription_request(
            db,
            ctx.user,
            plan=plan,
            period=period,
            sector_ids=_int_list(form.getlist("sectors")),
            method=method,
            reference=str(form.get("reference") or ""),
        )
    except billing.BillingError as exc:
        target = (
            f"/abonnement?plan={quote(plan.code)}&error={quote(exc.message, safe='')}"
        )
        return RedirectResponse(target, status_code=303)

    return RedirectResponse(f"/paiement/{payment.id}", status_code=303)


def _own_payment(db: Session, user: User, payment_id: int) -> Payment | None:
    return db.scalar(
        select(Payment)
        .options(
            selectinload(Payment.plan),
            selectinload(Payment.subscription).selectinload(Subscription.sectors),
        )
        .where(Payment.id == payment_id, Payment.user_id == user.id)
    )


@router.get("/paiement/{payment_id}", name="payment_detail")
def payment_detail(
    request: Request,
    ctx: Annotated[PageContext, Depends(get_page_context)],
    payment_id: int,
):
    """Payment instructions, upload form and status."""
    if ctx.user is None:
        return _login_redirect(request)
    payment = _own_payment(ctx.db, ctx.user, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="payment_not_found")
    return render(
        ctx,
        "payment.html",
        payment=payment,
        success=request.query_params.get("uploaded") == "1",
        error=request.query_params.get("error", ""),
        page_title=f"وصل الدفع #{payment.id}",
        page_description="تعليمات الدفع اليدوي ورفع وصل الدفع.",
    )


@router.post("/paiement/{payment_id}/preuve", name="payment_proof")
async def payment_proof(
    request: Request,
    ctx: Annotated[PageContext, Depends(get_page_context)],
    db: Annotated[Session, Depends(get_db)],
    payment_id: int,
):
    """Validate and store a proof of payment."""
    if ctx.user is None:
        return _login_redirect(request)
    payment = billing.pending_payment(db, ctx.user, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="payment_not_found")

    form = await request.form()
    if not verify_csrf(request, form):
        raise HTTPException(status_code=400, detail="invalid_csrf")
    if not _limit(ctx, db, "proof_upload", str(ctx.user.id), 10, 60):
        raise HTTPException(status_code=429, detail="upload_rate_limited")

    upload = form.get("proof")
    if upload is None or not hasattr(upload, "read"):
        return RedirectResponse(
            f"/paiement/{payment.id}?error=missing_file", status_code=303
        )

    data = await upload.read()
    try:
        stored = store_upload(
            data,
            original_name=getattr(upload, "filename", "proof") or "proof",
            declared_type=getattr(upload, "content_type", "") or "",
            settings=ctx.settings,
        )
    except UploadError as exc:
        target = f"/paiement/{payment.id}?error={quote(exc.message, safe='')}"
        return RedirectResponse(target, status_code=303)

    billing.attach_proof(db, payment, stored)
    return RedirectResponse(f"/paiement/{payment.id}?uploaded=1", status_code=303)


@router.get("/paiement/{payment_id}/preuve", name="payment_proof_file")
def payment_proof_file(
    request: Request,
    ctx: Annotated[PageContext, Depends(get_page_context)],
    payment_id: int,
):
    """Serve a proof only to its owner or to payment staff."""
    if ctx.user is None:
        return _login_redirect(request)
    payment = _own_payment(ctx.db, ctx.user, payment_id)
    if payment is None and ctx.user.role in STAFF_PAYMENT_ROLES:
        payment = ctx.db.get(Payment, payment_id)
    if payment is None or not payment.proof_filename:
        raise HTTPException(status_code=404, detail="proof_not_found")
    path = resolve_stored(ctx.settings, payment.proof_filename)
    if path is None:
        raise HTTPException(status_code=404, detail="proof_not_found")
    return FileResponse(
        path,
        media_type=payment.proof_content_type or "application/octet-stream",
        filename=payment.proof_original_name or "proof",
    )


# ---------------------------------------------------------------------------
# Staff: payment verification queue
# ---------------------------------------------------------------------------
@router.get("/admin/paiements", name="admin_payments")
def admin_payments(
    request: Request, ctx: Annotated[PageContext, Depends(get_page_context)]
):
    """Pending manual payments awaiting verification."""
    if ctx.user is None:
        return _login_redirect(request)
    if ctx.user.role not in STAFF_PAYMENT_ROLES:
        raise HTTPException(status_code=403, detail="forbidden")

    pending = list(
        ctx.db.scalars(
            select(Payment)
            .options(
                selectinload(Payment.plan),
                selectinload(Payment.user),
                selectinload(Payment.subscription),
            )
            .where(Payment.status == PaymentStatus.PENDING)
            .order_by(Payment.submitted_at)
        ).all()
    )
    recent = list(
        ctx.db.scalars(
            select(Payment)
            .options(selectinload(Payment.plan), selectinload(Payment.user))
            .where(Payment.status != PaymentStatus.PENDING)
            .order_by(Payment.verified_at.desc())
            .limit(20)
        ).all()
    )
    return render(
        ctx,
        "admin_payments.html",
        pending=pending,
        recent=recent,
        notice=request.query_params.get("notice", ""),
        error=request.query_params.get("error", ""),
        page_title="مراجعة المدفوعات",
        page_description="طابور التحقق من وصولات الدفع اليدوي.",
    )


@router.post("/admin/paiements/{payment_id}/verifier", name="admin_verify_payment")
async def admin_verify_payment(
    request: Request,
    ctx: Annotated[PageContext, Depends(get_page_context)],
    db: Annotated[Session, Depends(get_db)],
    payment_id: int,
):
    """Approve or reject a pending payment (admin/support only)."""
    if ctx.user is None:
        return _login_redirect(request)
    if ctx.user.role not in STAFF_PAYMENT_ROLES:
        raise HTTPException(status_code=403, detail="forbidden")

    form = await request.form()
    if not verify_csrf(request, form):
        raise HTTPException(status_code=400, detail="invalid_csrf")

    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="payment_not_found")

    approve = str(form.get("decision")) == "approve"
    try:
        billing.verify_payment(
            db,
            payment,
            admin=ctx.user,
            approve=approve,
            notes=str(form.get("notes") or ""),
        )
    except billing.BillingError as exc:
        target = f"/admin/paiements?error={quote(exc.message, safe='')}"
        return RedirectResponse(target, status_code=303)
    return RedirectResponse("/admin/paiements?notice=done", status_code=303)


@router.get("/desabonnement", name="unsubscribe")
def unsubscribe(
    request: Request, ctx: Annotated[PageContext, Depends(get_page_context)]
):
    """Deactivate an alert from its unsubscribe link (no login required)."""
    token = request.query_params.get("token", "")
    alert = ctx.db.scalar(select(Alert).where(Alert.unsubscribe_token == token))
    success = alert is not None
    if alert is not None:
        alert.is_active = False
        ctx.db.commit()
    return render(
        ctx,
        "message.html",
        heading="إلغاء التنبيهات",
        message=(
            "أُلغي تنبيهك اليومي. يمكنك إعادة تفعيله من لوحة التحكم."
            if success
            else "رابط غير صالح أو منتهٍ."
        ),
        success=success,
        page_title="إلغاء التنبيهات",
        page_description="إلغاء اشتراك التنبيهات البريدية.",
    )


__all__ = ["PENDING_PHONE_COOKIE", "router"]
