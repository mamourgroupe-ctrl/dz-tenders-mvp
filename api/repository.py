"""Read-only SQLite access for the API.

Safety properties enforced here:

* Connections use the SQLite URI ``mode=ro`` plus ``PRAGMA query_only`` —
  API requests can never create, update, delete or migrate data, and a
  missing database file is an error, never silently created.
* Every value reaching SQL is a bound parameter; user search text is
  additionally escaped for ``LIKE`` wildcards.
* Pagination is bounded by the route layer and re-clamped here.
"""

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from api.mapping import PRODUCT_MARKERS, parse_stored_date, priority_for_score, products_from_text
from api.models import ProductCode

REQUIRED_COLUMNS = {
    "id",
    "title",
    "organisation",
    "wilaya",
    "product",
    "deadline",
    "status",
    "link",
    "relevance_score",
    "first_seen",
}

SELECT_COLUMNS = (
    "id, title, organisation, wilaya, product, deadline, status, link,"
    " relevance_score, matched_families, first_seen, last_seen"
)


class DatabaseUnavailableError(Exception):
    """The configured database is missing, unreadable or not initialized."""


@dataclass(frozen=True)
class TenderFilters:
    """Validated filters for ``GET /api/tenders``."""

    search: str | None = None
    wilaya: str | None = None
    product: ProductCode | None = None
    priority: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    page: int = 1
    page_size: int = 20


def _escape_like(term: str) -> str:
    """Escape LIKE wildcards so user input is matched literally."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ReadOnlyTenderRepository:
    """SELECT-only repository over the existing ``tenders`` table."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        path = Path(self.db_path)
        if not path.is_file():
            raise DatabaseUnavailableError("tender database is not available")
        try:
            conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            raise DatabaseUnavailableError("tender database is not readable") from exc
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(tenders)")}
        except sqlite3.Error as exc:
            conn.close()
            raise DatabaseUnavailableError("tender database is not readable") from exc
        if not REQUIRED_COLUMNS.issubset(columns):
            conn.close()
            raise DatabaseUnavailableError("tender database schema is not initialized")
        return conn

    def count_tenders(self) -> int:
        """Return the total number of stored tenders."""
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM tenders").fetchone()
        return int(row["n"])

    @staticmethod
    def _where(filters: TenderFilters) -> tuple[str, list[object]]:
        clauses: list[str] = []
        params: list[object] = []
        if filters.search:
            pattern = f"%{_escape_like(filters.search.strip())}%"
            clauses.append(
                "(title LIKE ? ESCAPE '\\' OR organisation LIKE ? ESCAPE '\\'"
                " OR wilaya LIKE ? ESCAPE '\\' OR link LIKE ? ESCAPE '\\')"
            )
            params.extend([pattern, pattern, pattern, pattern])
        if filters.wilaya:
            clauses.append("wilaya = ?")
            params.append(filters.wilaya)
        if filters.product is not None:
            markers = PRODUCT_MARKERS[filters.product]
            fragment = " OR ".join("UPPER(product) LIKE UPPER(?)" for _ in markers)
            clauses.append(f"({fragment})")
            params.extend(f"%{marker}%" for marker in markers)
        if filters.priority == 1:
            clauses.append("relevance_score >= 85")
        elif filters.priority == 2:
            clauses.append("relevance_score >= 70 AND relevance_score < 85")
        elif filters.priority == 3:
            clauses.append("relevance_score < 70")
        if filters.date_from is not None:
            clauses.append("substr(deadline, 1, 10) >= ?")
            params.append(filters.date_from.isoformat())
        if filters.date_to is not None:
            clauses.append("substr(deadline, 1, 10) <= ?")
            params.append(filters.date_to.isoformat())
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def list_tenders(self, filters: TenderFilters) -> tuple[list[dict], int]:
        """Return one bounded page of raw rows plus the full match count."""
        page = max(1, filters.page)
        page_size = min(100, max(1, filters.page_size))
        where, params = self._where(filters)
        with self._connect() as conn:
            total = int(
                conn.execute(f"SELECT COUNT(*) AS n FROM tenders{where}", params).fetchone()["n"]
            )
            rows = conn.execute(
                f"SELECT {SELECT_COLUMNS} FROM tenders{where}"
                " ORDER BY first_seen DESC, id DESC LIMIT ? OFFSET ?",
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()
        return [dict(row) for row in rows], total

    def get_tender(self, tender_id: int) -> dict | None:
        """Return one raw row by numeric id, or ``None`` when unknown."""
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {SELECT_COLUMNS} FROM tenders WHERE id = ?", (tender_id,)
            ).fetchone()
        return dict(row) if row else None

    def _all_rows(self, columns: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(f"SELECT {columns} FROM tenders").fetchall()
        return [dict(row) for row in rows]

    def summary(self, today: date) -> dict:
        """Compute summary counters from real rows (see mapping rules)."""
        rows = self._all_rows("relevance_score, deadline, status, first_seen")
        total = len(rows)
        active = 0
        priorities = {1: 0, 2: 0, 3: 0}
        recent = previous = 0
        recent_start = today - timedelta(days=29)
        previous_start = today - timedelta(days=59)
        for row in rows:
            deadline = parse_stored_date(row.get("deadline"))
            if deadline is None or deadline >= today:
                active += 1
            score = row.get("relevance_score") or 0
            priorities[priority_for_score(int(score))] += 1
            seen = parse_stored_date(row.get("first_seen"))
            if seen is not None:
                if seen >= recent_start:
                    recent += 1
                elif seen >= previous_start:
                    previous += 1
        change = round((recent - previous) / previous * 100, 1) if previous else 0.0
        return {
            "total": total,
            "active": active,
            "priority1": priorities[1],
            "priority2": priorities[2],
            "priority3": priorities[3],
            "change": change,
        }

    def by_wilaya(self) -> list[dict]:
        """Count tenders per non-empty wilaya with integer percentages."""
        with self._connect() as conn:
            total = int(conn.execute("SELECT COUNT(*) AS n FROM tenders").fetchone()["n"])
            rows = conn.execute(
                "SELECT wilaya, COUNT(*) AS n FROM tenders"
                " WHERE wilaya IS NOT NULL AND wilaya != ''"
                " GROUP BY wilaya ORDER BY n DESC, wilaya ASC"
            ).fetchall()
        return [
            {
                "wilaya": row["wilaya"],
                "count": int(row["n"]),
                "percentage": round(int(row["n"]) / total * 100) if total else 0,
            }
            for row in rows
        ]

    def by_product(self) -> dict[ProductCode, int]:
        """Count tenders per frontend product code via the text mapping."""
        counts: dict[ProductCode, int] = {code: 0 for code in ProductCode}
        for row in self._all_rows("product"):
            for code in products_from_text(row.get("product")):
                counts[code] += 1
        return counts

    def timeline(self, today: date, days: int = 30) -> list[dict]:
        """Daily first-seen counts for the last ``days`` days, zeros included."""
        start = today - timedelta(days=days - 1)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT substr(first_seen, 1, 10) AS day, COUNT(*) AS n FROM tenders"
                " WHERE substr(first_seen, 1, 10) >= ? GROUP BY day",
                (start.isoformat(),),
            ).fetchall()
        counts = {row["day"]: int(row["n"]) for row in rows}
        points = []
        for offset in range(days):
            day = start + timedelta(days=offset)
            points.append(
                {
                    "date": day.isoformat(),
                    "label": day.strftime("%d %b"),
                    "tenders": counts.get(day.isoformat(), 0),
                }
            )
        return points
