"""Pure mapping from SQLite ``tenders`` rows to the frontend Tender shape.

Only values supported by real stored data are derived:

* ``score`` is the stored ``relevance_score`` and ``priority`` reuses the
  thresholds already used by ``main._priority_badge`` (>=85 -> 1, >=70 -> 2,
  otherwise 3, the lowest tier the frontend can display).
* ``status`` is derived from the real ``deadline`` when it parses
  (past -> closed, within 7 days -> closing_soon, otherwise active) and
  falls back to the stored status text when it does not.
* ``publicationDate`` is the date part of ``first_seen`` (when this system
  first observed the tender); it is not an official publication date.
* ``products`` are recognized from the free-text ``product`` column written
  by the crawlers (e.g. ``"PVC Pipes"``, ``"PEHD Pipes"``,
  ``"Plastic Tanks"``, ``"أنابيب PVC/PEHD"``). Unknown text yields no
  products rather than a guessed category.
* Coordinates, estimated value, official reference and description are not
  stored in SQLite, so they are always ``None`` here.
"""

import re
from datetime import date

from api.models import ProductCode, TenderOut

_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

#: Text markers (matched case-insensitively) for each frontend product code.
#: The SQL filter fragments in ``api.repository`` are built from this table.
PRODUCT_MARKERS: dict[ProductCode, tuple[str, ...]] = {
    ProductCode.PVC_PIPES: ("PVC",),
    ProductCode.PEHD_PIPES: ("PEHD", "HDPE"),
    ProductCode.PE_TANKS: ("TANK", "خزان", "RESERVOIR", "RÉSERVOIR", "CITERNE"),
}

#: Frontend labels/colors, kept identical to ``src/data/mockTenders.ts``.
PRODUCT_LABELS: dict[ProductCode, str] = {
    ProductCode.PVC_PIPES: "أنابيب PVC",
    ProductCode.PEHD_PIPES: "أنابيب PEHD",
    ProductCode.PE_TANKS: "خزانات PE",
}
PRODUCT_COLORS: dict[ProductCode, str] = {
    ProductCode.PVC_PIPES: "#1a5490",
    ProductCode.PEHD_PIPES: "#2ca58d",
    ProductCode.PE_TANKS: "#f6a623",
}


def parse_stored_date(value: object) -> date | None:
    """Extract a ``YYYY-MM-DD`` date from a stored value, if present."""
    if value is None:
        return None
    match = _DATE_RE.search(str(value))
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def priority_for_score(score: int) -> int:
    """Map a relevance score to frontend priority 1/2/3 (project thresholds)."""
    if score >= 85:
        return 1
    if score >= 70:
        return 2
    return 3


def products_from_text(value: object) -> list[ProductCode]:
    """Recognize frontend product codes in crawler free-text product values."""
    if not value:
        return []
    text = str(value).upper()
    return [
        code
        for code, markers in PRODUCT_MARKERS.items()
        if any(marker.upper() in text for marker in markers)
    ]


def derive_status(raw_status: object, deadline: date | None, today: date) -> str:
    """Derive active/closing_soon/closed from the deadline or stored status."""
    if deadline is not None:
        if deadline < today:
            return "closed"
        if (deadline - today).days <= 7:
            return "closing_soon"
        return "active"
    text = str(raw_status or "").strip().lower()
    if "closed" in text or "مغلق" in text:
        return "closed"
    if "closing" in text or "قريب" in text:
        return "closing_soon"
    return "active"


def row_to_tender(row: dict, today: date) -> TenderOut:
    """Serialize one ``tenders`` row (as a dict) to ``TenderOut``."""
    title = str(row.get("title") or "")
    is_arabic = bool(_ARABIC_RE.search(title))
    deadline = parse_stored_date(row.get("deadline"))
    first_seen = parse_stored_date(row.get("first_seen"))
    try:
        score = int(row.get("relevance_score") or 0)
    except (TypeError, ValueError):
        score = 0
    link = str(row.get("link") or "").strip()
    organisation = str(row.get("organisation") or "")
    return TenderOut(
        id=str(row.get("id", "")),
        # The single stored title column has no language tag: Arabic text is
        # the Arabic title; Latin text is the French title and is mirrored
        # into titleAr so the dashboard heading is never blank.
        titleAr=title,
        titleFr="" if is_arabic else title,
        organisation=organisation,
        organisationShort=organisation,
        wilaya=str(row.get("wilaya") or ""),
        deadline=deadline.isoformat() if deadline else None,
        publicationDate=first_seen.isoformat() if first_seen else "",
        products=products_from_text(row.get("product")),
        score=max(0, score),
        priority=priority_for_score(max(0, score)),  # type: ignore[arg-type]
        status=derive_status(row.get("status"), deadline, today),  # type: ignore[arg-type]
        description=None,
        source=None,
        sourceUrl=link if link.startswith(("http://", "https://")) else None,
        latitude=None,
        longitude=None,
        reference=None,
        estimatedValue=None,
    )
