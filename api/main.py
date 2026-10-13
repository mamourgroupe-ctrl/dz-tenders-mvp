"""FastAPI application factory for the read-only DZ Tenders API.

Route layout (matching ``src/lib/api.ts``):

* ``GET /health`` (and ``/api/health``) — service + database health.
* ``GET /api/tenders`` / ``GET /api/tenders/{id}``
* ``GET /api/stats/summary|by-wilaya|by-product|timeline``

The service is intentionally public-read and unauthenticated: it exposes
only tender listings already collected for publication. It never writes
to the database (see ``api.repository``) and returns a consistent
``{"error": {"code", "message"}}`` envelope without stack traces, SQL or
filesystem paths.
"""

import logging
import os
from collections.abc import Callable
from datetime import date

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.mapping import PRODUCT_COLORS, PRODUCT_LABELS, row_to_tender
from api.models import (
    HealthResponse,
    ProductCode,
    ProductPoint,
    SummaryStats,
    TenderOut,
    TenderPage,
    TimelinePoint,
    WilayaPoint,
)
from api.repository import DatabaseUnavailableError, ReadOnlyTenderRepository, TenderFilters
from storage.paths import resolve_db_path

logger = logging.getLogger(__name__)

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


class ApiError(Exception):
    """An error that maps directly onto the consistent error envelope."""

    def __init__(
        self, status_code: int, code: str, message: str, details: list | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []


def _error_response(status_code: int, code: str, message: str, details=None) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "details": details or []}}
    return JSONResponse(status_code=status_code, content=body)


def _parse_cors_origins(raw: str | None) -> list[str]:
    origins = [origin.strip() for origin in (raw or "").split(",") if origin.strip()]
    return origins or [origin.strip() for origin in DEFAULT_CORS_ORIGINS.split(",")]


def create_app(
    db_path: str | None = None,
    cors_origins: list[str] | None = None,
    today_provider: Callable[[], date] = date.today,
) -> FastAPI:
    """Build the FastAPI app.

    Args:
        db_path: SQLite path; defaults to ``DB_PATH`` resolved against the
            repository root (the API never creates this file).
        cors_origins: Allowed origins; defaults to ``CORS_ORIGINS`` env or
            the local Vite dev origins. Credentials are never enabled, so a
            wildcard origin cannot be combined with credentialed requests.
        today_provider: Clock injection for deterministic tests.
    """
    repository = ReadOnlyTenderRepository(resolve_db_path(db_path))
    origins = (
        cors_origins if cors_origins is not None else _parse_cors_origins(os.getenv("CORS_ORIGINS"))
    )

    app = FastAPI(title="DZ Tenders API", version="1.0.0", docs_url="/api/docs")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Accept", "Content-Type"],
    )

    @app.exception_handler(ApiError)
    async def _api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message, details=exc.details)

    @app.exception_handler(DatabaseUnavailableError)
    async def _db_error_handler(_request: Request, _exc: DatabaseUnavailableError) -> JSONResponse:
        return _error_response(
            503, "database_unavailable", "Tender data is temporarily unavailable."
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(part) for part in err["loc"]), "issue": err["msg"]}
            for err in exc.errors()
        ]
        return _error_response(
            422, "validation_error", "Invalid request parameters.", details=details
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        message = (
            "The requested resource was not found." if exc.status_code == 404 else "Request failed."
        )
        return _error_response(exc.status_code, code, message)

    @app.exception_handler(Exception)
    async def _unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error: %s", exc)
        return _error_response(500, "internal_error", "An internal error occurred.")

    def _health() -> JSONResponse:
        try:
            count = repository.count_tenders()
        except DatabaseUnavailableError:
            body = HealthResponse(status="degraded", database="unavailable", tenders=None)
            return JSONResponse(status_code=503, content=body.model_dump())
        body = HealthResponse(status="ok", database="available", tenders=count)
        return JSONResponse(status_code=200, content=body.model_dump())

    app.add_api_route("/health", _health, methods=["GET"], response_model=HealthResponse)
    app.add_api_route("/api/health", _health, methods=["GET"], response_model=HealthResponse)

    router = APIRouter(prefix="/api")

    @router.get("/tenders", response_model=TenderPage)
    async def list_tenders(
        search: str | None = Query(default=None, max_length=200),
        wilaya: str | None = Query(default=None, max_length=100),
        product: ProductCode | None = None,
        priority: int | None = Query(default=None, ge=1, le=3),
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
    ) -> TenderPage:
        """List tenders with validated filters and bounded pagination."""
        if date_from and date_to and date_from > date_to:
            raise ApiError(
                422,
                "validation_error",
                "date_from must be on or before date_to.",
                details=[{"field": "date_from", "issue": "must be on or before date_to"}],
            )
        filters = TenderFilters(
            search=search,
            wilaya=wilaya,
            product=product,
            priority=priority,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
        rows, total = repository.list_tenders(filters)
        today = today_provider()
        return TenderPage(
            items=[row_to_tender(row, today) for row in rows],
            total=total,
            page=page,
            pageSize=page_size,
            pages=max(1, -(-total // page_size)),
        )

    @router.get("/tenders/{tender_id}", response_model=TenderOut)
    async def get_tender(tender_id: str) -> TenderOut:
        """Return one tender, or a consistent 404 for unknown/invalid ids."""
        if not tender_id.isdecimal():
            raise ApiError(404, "not_found", "Tender not found.")
        row = repository.get_tender(int(tender_id))
        if row is None:
            raise ApiError(404, "not_found", "Tender not found.")
        return row_to_tender(row, today_provider())

    @router.get("/stats/summary", response_model=SummaryStats)
    async def stats_summary() -> SummaryStats:
        """Return aggregate counters computed from stored rows."""
        return SummaryStats(**repository.summary(today_provider()))

    @router.get("/stats/by-wilaya", response_model=list[WilayaPoint])
    async def stats_by_wilaya() -> list[WilayaPoint]:
        """Return tender counts grouped by wilaya."""
        return [WilayaPoint(**point) for point in repository.by_wilaya()]

    @router.get("/stats/by-product", response_model=list[ProductPoint])
    async def stats_by_product() -> list[ProductPoint]:
        """Return tender counts for each frontend product category."""
        counts = repository.by_product()
        return [
            ProductPoint(
                product=code,
                label=PRODUCT_LABELS[code],
                count=counts[code],
                color=PRODUCT_COLORS[code],
            )
            for code in ProductCode
        ]

    @router.get("/stats/timeline", response_model=list[TimelinePoint])
    async def stats_timeline() -> list[TimelinePoint]:
        """Return daily first-seen counts for the last 30 days."""
        return [TimelinePoint(**point) for point in repository.timeline(today_provider())]

    app.include_router(router)
    return app


app = create_app()
