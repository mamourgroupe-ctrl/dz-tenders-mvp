"""Response models matching the React dashboard contract in ``src/types.ts``."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class ProductCode(StrEnum):
    """Product categories understood by the frontend."""

    PVC_PIPES = "PVC_PIPES"
    PEHD_PIPES = "PEHD_PIPES"
    PE_TANKS = "PE_TANKS"


class TenderOut(BaseModel):
    """One tender serialized from a SQLite ``tenders`` row.

    Fields the database does not store (``latitude``, ``longitude``,
    ``estimatedValue``, ``reference``, ``description``, ``source``) are
    explicitly nullable instead of being fabricated by the API.
    """

    id: str
    titleAr: str
    titleFr: str
    organisation: str
    organisationShort: str
    wilaya: str
    deadline: str | None
    publicationDate: str
    products: list[ProductCode]
    score: int
    priority: Literal[1, 2, 3]
    status: Literal["active", "closing_soon", "closed"]
    description: str | None
    source: str | None
    sourceUrl: str | None
    latitude: float | None
    longitude: float | None
    reference: str | None
    estimatedValue: str | None


class TenderPage(BaseModel):
    """Paginated tender envelope returned by ``GET /api/tenders``."""

    items: list[TenderOut]
    total: int
    page: int
    pageSize: int
    pages: int


class SummaryStats(BaseModel):
    """Aggregate counters returned by ``GET /api/stats/summary``."""

    total: int
    active: int
    priority1: int
    priority2: int
    priority3: int
    change: float


class WilayaPoint(BaseModel):
    """Tender count for one wilaya."""

    wilaya: str
    count: int
    percentage: int


class ProductPoint(BaseModel):
    """Tender count for one frontend product category."""

    product: ProductCode
    label: str
    count: int
    color: str


class TimelinePoint(BaseModel):
    """Tenders first seen on one calendar day."""

    date: str
    label: str
    tenders: int


class HealthResponse(BaseModel):
    """Service/database health returned by ``GET /health``."""

    status: Literal["ok", "degraded"]
    database: Literal["available", "unavailable"]
    tenders: int | None


class ErrorBody(BaseModel):
    """Consistent error envelope for every API failure."""

    code: str
    message: str
    details: list[dict[str, str]] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Top-level error wrapper: ``{"error": {...}}``."""

    error: ErrorBody
