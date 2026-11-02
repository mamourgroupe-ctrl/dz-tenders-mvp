"""FastAPI application factory for the Arabic-first public platform."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from webapp.config import Settings
from webapp.db import ensure_fts, make_engine, make_session_factory, schema_ready
from webapp.entitlements import ANONYMOUS
from webapp.security import CSRF_COOKIE, SESSION_COOKIE, new_token
from webapp.timeutils import today_algiers
from webapp.web.routes_auth import router as auth_router
from webapp.web.routes_public import router as public_router
from webapp.web.routes_seo import router as seo_router
from webapp.web.templating import SITE_NAME_AR, STATIC_DIR, build_templates

logger = logging.getLogger(__name__)

CSRF_MAX_AGE = 7 * 24 * 3600


def _security_headers(response: Response, settings: Settings) -> None:
    """Apply defensive headers to every response."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy", "geolocation=(), camera=(), microphone=(), payment=()"
    )
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; base-uri 'self'; object-src 'none'; "
        "frame-ancestors 'none'; form-action 'self'; "
        "img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "font-src 'self'; connect-src 'self'",
    )
    if settings.is_production:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )


def _error_response(
    request: Request,
    *,
    status_code: int,
    title: str,
    message: str,
) -> HTMLResponse:
    """Render a standalone Arabic error page without database access."""
    settings: Settings = request.app.state.settings
    token = getattr(request.state, "csrf_token", "") or ""
    context = {
        "request": request,
        "settings": settings,
        "user": None,
        "entitlements": ANONYMOUS,
        "csrf_token": token,
        "canonical_url": (
            f"{settings.public_base_url or str(request.base_url).rstrip('/')}"
            f"{request.url.path}"
        ),
        "current_path": request.url.path,
        "current_year": today_algiers().year,
        "page_url": lambda _request, page: request.url.path,
        "sort_url": lambda _request, sort: request.url.path,
        "status_code": status_code,
        "title": title,
        "message": message,
        "site_name": SITE_NAME_AR,
    }
    response = request.app.state.templates.TemplateResponse(
        request, "error.html", context, status_code=status_code
    )
    return response


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the public application.

    Args:
        settings: Explicit settings (tests); defaults to environment values.

    Returns:
        A FastAPI app with templates, static files, routers and security
        middleware. Database schema creation is **not** performed here —
        migrations and seeding are separate commands.
    """
    settings = settings or Settings.from_env()

    db_file = settings.database_path()
    if db_file is not None:
        db_file.parent.mkdir(parents=True, exist_ok=True)

    engine = make_engine(settings.database_url)
    sessionmaker = make_session_factory(engine)
    if settings.fts_enabled and schema_ready(engine):
        ensure_fts(engine)

    app = FastAPI(
        title="DZ Tenders — مناقصات الجزائر",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    app.state.templates = build_templates()

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        """Attach CSRF token, caching policy and security headers."""
        existing_csrf = request.cookies.get(CSRF_COOKIE)
        request.state.csrf_token = existing_csrf or new_token(24)
        response = await call_next(request)

        if not existing_csrf:
            response.set_cookie(
                CSRF_COOKIE,
                request.state.csrf_token,
                max_age=CSRF_MAX_AGE,
                httponly=True,
                secure=settings.secure_cookies,
                samesite="lax",
                path="/",
            )

        _security_headers(response, settings)

        path = request.url.path
        if path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "public, max-age=604800")
        elif request.cookies.get(SESSION_COOKIE):
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["Vary"] = "Cookie"
        elif request.method == "GET" and response.status_code == 200:
            response.headers.setdefault("Cache-Control", "public, max-age=60")
            response.headers["Vary"] = "Cookie"
        else:
            response.headers["Cache-Control"] = "no-store"

        if path in {"/connexion", "/deconnexion", "/health"} or path.startswith(
            "/admin"
        ):
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith(("/api", "/health")):
            return Response(
                content='{"error": {"code": "http_error", "message": "Request failed."}}',
                status_code=exc.status_code,
                media_type="application/json",
            )
        titles = {
            400: ("طلب غير صالح", "تحقق من الرابط أو البيانات المدخلة."),
            403: ("غير مسموح", "ليست لديك صلاحية الوصول إلى هذه الصفحة."),
            404: ("الصفحة غير موجودة", "قد يكون الرابط قديماً أو أن الإعلان حُذف."),
            405: ("طريقة غير مسموحة", "هذا العنوان لا يقبل طريقة الطلب المستعملة."),
            429: ("محاولات كثيرة", "الرجاء الانتظار قليلاً قبل إعادة المحاولة."),
        }
        title, message = titles.get(
            exc.status_code, ("حدث خطأ", "تعذر إتمام الطلب. حاول مرة أخرى.")
        )
        return _error_response(
            request, status_code=exc.status_code, title=title, message=message
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        logger.info("Invalid request on %s: %s", request.url.path, exc.errors()[:3])
        return _error_response(
            request,
            status_code=404,
            title="الصفحة غير موجودة",
            message="تحقق من الرابط؛ بعض المعرّفات غير صالحة.",
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s: %s", request.url.path, exc)
        return _error_response(
            request,
            status_code=500,
            title="خطأ داخلي",
            message="تعذر إتمام الطلب بسبب خطأ تقني. نعمل على معالجته.",
        )

    app.include_router(public_router)
    app.include_router(auth_router)
    app.include_router(seo_router)
    return app


__all__ = ["create_app"]


if __name__ == "__main__":  # pragma: no cover - manual convenience
    import uvicorn

    uvicorn.run(
        "webapp.web.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
